"""Direct-mode tests for PoolVoice, an AI-governed DAO fund.

The only resolution path is validator-backed: resolve_proposals_ai runs the
prompt through validators (mocked here as the LLM response) and the contract
enforces unique/valid/open ids, exactly-one bounded score per id, and payouts
capped by each requested amount. Scores are returned as strings in mocks
because the direct-mode WASI stub encodes LLM responses through calldata,
which does not support floats (the real network has no such limit).
"""
import ast
import json
from pathlib import Path

from tests.direct.conftest import to_hex

GEN = 10 ** 18
DEPOSIT_AMT = 10 * GEN
PROPOSAL_AMT = 2 * GEN
AI_PROMPT = r"You are a DAO governance AI"
CONTRACT_SRC = Path(__file__).resolve().parents[2] / "contracts" / "pool_voice.py"


def _deposit(contract, vm, sender, amount=DEPOSIT_AMT):
    vm.sender = sender
    vm.value = amount
    contract.deposit()
    vm.value = 0


def _create(contract, vm, sender, title="Test Proposal", desc="A test", amount=PROPOSAL_AMT):
    vm.sender = sender
    pid = int(contract.create_proposal(title, desc, amount))
    return pid


def _scores(pid, score, reasoning="ai says"):
    """AI response object; score as string (calldata-safe in direct mode)."""
    return {str(pid): {"score": score, "reasoning": reasoning}}


REVERT_TYPE = "genlayer.gl.vm.UserError"


def _error_kind(err):
    """Dotted class name of an exception, e.g. ``genlayer.gl.vm.UserError``.

    ``genlayer`` only exists inside the WASI runner, so the revert type cannot
    be imported here; it is identified by name instead.
    """
    cls = type(err)
    return f"{cls.__module__}.{cls.__name__}"


def _expect_revert(call, *args, **kwargs):
    """Run a call that must be rejected, and fail loudly when it is not.

    The earlier version of these tests wrote::

        try:
            contract.forbidden()
            assert False, "should have reverted"
        except Exception:
            pass

    which caught its own failure assertion: ``AssertionError`` is an
    ``Exception``, so a call that quietly succeeded still produced a green
    test, and so did a call that failed for an unrelated reason. Here the
    exception must be the contract's own revert type, and a call that returns
    is reported as a failure.
    """
    try:
        returned = call(*args, **kwargs)
    except Exception as err:
        if _error_kind(err) != REVERT_TYPE:
            raise AssertionError(
                f"expected a revert from {getattr(call, '__name__', call)!r}, "
                f"got {_error_kind(err)}: {err}"
            ) from err
        return err
    raise AssertionError(
        f"{getattr(call, '__name__', call)!r} was not rejected; it returned {returned!r}"
    )


def _ledger(contract):
    """Pool balance, funded total, and proposal count. No rejection may move these."""
    pool = contract.get_pool()
    return (
        int(pool["balance"]),
        int(pool["total_funded"]),
        int(pool["total_proposals"]),
    )


def _proposal_state(contract, pid):
    """Everything a rejected call could have changed on one proposal."""
    p = contract.get_proposal(pid)
    return (
        p["status"],
        int(p["funded"]),
        str(p["score"]),
        int(p["resolved_at"]),
    )


def _rejected_without_moving(contract, call, *args, pids=()):
    """Assert a call reverts and that no pool money and no proposal changed."""
    before_ledger = _ledger(contract)
    before_proposals = {pid: _proposal_state(contract, pid) for pid in pids}
    err = _expect_revert(call, *args)
    assert _ledger(contract) == before_ledger, "pool balance or funded total moved"
    for pid, expected in before_proposals.items():
        now = _proposal_state(contract, pid)
        assert now == expected, f"proposal {pid} changed: {expected} -> {now}"
    return err


# ================================================================== deposit
def test_deposit_sets_sponsor(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pool = contract.get_pool()
    assert pool["balance"] == DEPOSIT_AMT
    assert pool["sponsor"].lower() == to_hex(direct_alice).lower()


def test_deposit_reverts_on_zero(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    direct_vm.sender = direct_alice
    direct_vm.value = 0
    err = _rejected_without_moving(contract, contract.deposit)
    direct_vm.value = 0
    assert "must send GEN" in str(err)
    assert _ledger(contract) == (0, 0, 0)


def test_multiple_deposits(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 5 * GEN)
    _deposit(contract, direct_vm, direct_bob, 3 * GEN)
    pool = contract.get_pool()
    assert pool["balance"] == 8 * GEN


# ============================================================ create proposal
def test_create_proposal(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    assert pid == 1
    p = contract.get_proposal(pid)
    assert p["status"] == "OPEN"
    assert p["amount"] == PROPOSAL_AMT


def test_create_reverts_empty_title(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    _rejected_without_moving(contract, contract.create_proposal, "", "desc", PROPOSAL_AMT)
    assert _ledger(contract) == (DEPOSIT_AMT, 0, 0)
    assert contract.list_proposals(0, 10) == []


def test_create_reverts_exceeds_balance(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 1 * GEN)
    direct_vm.sender = direct_alice
    _rejected_without_moving(contract, contract.create_proposal, "Big", "desc", 5 * GEN)
    assert _ledger(contract) == (1 * GEN, 0, 0)
    assert contract.list_proposals(0, 10) == []


def test_create_reverts_below_minimum(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    _rejected_without_moving(contract, contract.create_proposal, "Tiny", "desc", 1)
    assert _ledger(contract) == (DEPOSIT_AMT, 0, 0)
    assert contract.list_proposals(0, 10) == []


# ================================================================ cancel
def test_cancel_by_proposer(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    contract.cancel_proposal(pid)
    assert contract.get_proposal(pid)["status"] == "CANCELLED"


def test_cancel_reverts_not_proposer(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    direct_vm.sender = direct_bob
    _rejected_without_moving(contract, contract.cancel_proposal, pid, pids=[pid])
    assert contract.get_proposal(pid)["status"] == "OPEN"


# ============================================================== AI resolve
def test_ai_resolve_funds_high_score(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_bob, "High Value", "Great project", 3 * GEN)

    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "0.85")))
    contract.resolve_proposals_ai([pid])

    p = contract.get_proposal(pid)
    assert p["status"] == "RESOLVED"
    assert float(p["score"]) == 0.85
    assert p["funded"] > 0
    assert p["funded"] <= 3 * GEN


def test_ai_resolve_low_score_not_funded(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_bob, "Low Value", "Weak project", 3 * GEN)

    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "0.2")))
    contract.resolve_proposals_ai([pid])

    p = contract.get_proposal(pid)
    assert p["status"] == "RESOLVED"
    assert float(p["score"]) == 0.2
    assert p["funded"] == 0


def test_ai_resolve_proportional(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid1 = _create(contract, direct_vm, direct_bob, "Proposal A", "Desc A", 3 * GEN)
    pid2 = _create(contract, direct_vm, direct_charlie, "Proposal B", "Desc B", 3 * GEN)

    direct_vm.mock_llm(
        AI_PROMPT,
        json.dumps({**{str(pid1): {"score": "0.8", "reasoning": "a"}},
                    **{str(pid2): {"score": "0.4", "reasoning": "b"}}}),
    )
    contract.resolve_proposals_ai([pid1, pid2])

    p1 = contract.get_proposal(pid1)
    p2 = contract.get_proposal(pid2)
    assert p1["status"] == "RESOLVED"
    assert p2["status"] == "RESOLVED"
    assert p1["funded"] > 0
    assert p2["funded"] == 0


def test_ai_resolve_by_stranger_uses_validator_score(
    direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie
):
    """Anyone may trigger resolution, but the score comes from the validators,
    not from the caller. A stranger cannot force a payout or a denial."""
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_bob, "Neutral", "Whatever", 3 * GEN)

    direct_vm.sender = direct_charlie
    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "0.6")))
    contract.resolve_proposals_ai([pid])

    p = contract.get_proposal(pid)
    assert p["status"] == "RESOLVED"
    assert float(p["score"]) == 0.6
    assert p["funded"] > 0


# ================================================== security: no manual path
def test_manual_resolve_path_removed(direct_vm, direct_deploy, direct_alice):
    """The explicit-scores path is gone: there is no way to set a score by hand.

    A missing method raises ``AttributeError``, which is a different failure
    from a revert, so it is caught on its own rather than through
    ``Exception``. The contract then has to survive a call whose whole point
    is to hand it a score, with nothing moving.
    """
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)

    assert not hasattr(contract, "resolve_proposals"), "manual scoring method exists"
    before_ledger = _ledger(contract)
    before_state = _proposal_state(contract, pid)
    try:
        contract.resolve_proposals([pid], ["0.99"])
    except AttributeError:
        pass
    else:
        raise AssertionError("resolve_proposals(ids, scores) was callable")
    assert _ledger(contract) == before_ledger
    assert _proposal_state(contract, pid) == before_state
    assert contract.get_proposal(pid)["status"] == "OPEN"
    assert contract.get_proposal(pid)["funded"] == 0


# ================================================== security: bad id lists
def test_ai_resolve_reverts_empty_ids(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    _rejected_without_moving(contract, contract.resolve_proposals_ai, [], pids=[pid])


def test_ai_resolve_reverts_duplicate_ids(direct_vm, direct_deploy, direct_alice):
    """Repeating an id must not resolve it twice or pay it twice."""
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "0.9")))

    err = _rejected_without_moving(
        contract, contract.resolve_proposals_ai, [pid, pid], pids=[pid]
    )
    assert "duplicate" in str(err)
    assert contract.get_proposal(pid)["status"] == "OPEN"
    assert contract.get_proposal(pid)["funded"] == 0


def test_ai_resolve_reverts_invalid_id(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(99, "0.9")))
    err = _rejected_without_moving(contract, contract.resolve_proposals_ai, [99], pids=[pid])
    assert "not found" in str(err)


def test_ai_resolve_reverts_zero_id(direct_vm, direct_deploy, direct_alice):
    """Ids are 1-based; 0 must not alias anything."""
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(0, "0.9")))
    _rejected_without_moving(contract, contract.resolve_proposals_ai, [0], pids=[pid])


def test_ai_resolve_is_one_time(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_alice, "Once", "Once only", 2 * GEN)

    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "0.9")))
    contract.resolve_proposals_ai([pid])
    assert contract.get_proposal(pid)["status"] == "RESOLVED"

    # A second resolution of the same proposal must not double-fund it.
    before_ledger = _ledger(contract)
    before_state = _proposal_state(contract, pid)
    funded_once = before_state[1]
    assert funded_once > 0

    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "0.9")))
    err = _rejected_without_moving(
        contract, contract.resolve_proposals_ai, [pid], pids=[pid]
    )
    assert "not open" in str(err)
    assert _ledger(contract) == before_ledger
    assert _proposal_state(contract, pid) == before_state
    assert contract.get_proposal(pid)["funded"] == funded_once


def test_ai_resolve_reverts_cancelled(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    contract.cancel_proposal(pid)
    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "0.9")))
    _rejected_without_moving(contract, contract.resolve_proposals_ai, [pid], pids=[pid])
    assert contract.get_proposal(pid)["status"] == "CANCELLED"
    assert contract.get_proposal(pid)["funded"] == 0


# ================================================== security: malformed AI
def test_ai_resolve_reverts_malformed_json(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_alice, "Malformed", "Bad output", 2 * GEN)

    direct_vm.mock_llm(AI_PROMPT, "this is not json")
    _rejected_without_moving(contract, contract.resolve_proposals_ai, [pid], pids=[pid])

    # Nothing moved.
    p = contract.get_proposal(pid)
    assert p["status"] == "OPEN"
    assert p["funded"] == 0
    assert _ledger(contract) == (10 * GEN, 0, 1)


def test_ai_resolve_reverts_score_above_one(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_alice, "Inflated", "Too good", 2 * GEN)

    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "1.5")))
    err = _rejected_without_moving(
        contract, contract.resolve_proposals_ai, [pid], pids=[pid]
    )
    assert "out of range" in str(err)

    p = contract.get_proposal(pid)
    assert p["status"] == "OPEN"
    assert p["funded"] == 0
    assert _ledger(contract) == (10 * GEN, 0, 1)


def test_ai_resolve_reverts_negative_score(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_alice, "Negative", "No", 2 * GEN)

    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "-0.1")))
    _rejected_without_moving(contract, contract.resolve_proposals_ai, [pid], pids=[pid])

    p = contract.get_proposal(pid)
    assert p["status"] == "OPEN"
    assert p["funded"] == 0
    assert _ledger(contract) == (10 * GEN, 0, 1)


def test_ai_resolve_reverts_foreign_id(direct_vm, direct_deploy, direct_alice, direct_bob):
    """The AI cannot slip an allocation for a proposal that was not requested."""
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid1 = _create(contract, direct_vm, direct_alice, "Requested", "Yes", 2 * GEN)
    pid2 = _create(contract, direct_vm, direct_bob, "Sneaky", "Not requested", 2 * GEN)

    # AI scores the sneaky one and skips the requested one.
    direct_vm.mock_llm(
        AI_PROMPT,
        json.dumps({str(pid2): {"score": "0.9", "reasoning": "diversion"}}),
    )
    _rejected_without_moving(
        contract, contract.resolve_proposals_ai, [pid1], pids=[pid1, pid2]
    )

    assert contract.get_proposal(pid1)["status"] == "OPEN"
    assert contract.get_proposal(pid2)["status"] == "OPEN"
    assert contract.get_proposal(pid1)["funded"] == 0
    assert contract.get_proposal(pid2)["funded"] == 0
    assert _ledger(contract) == (10 * GEN, 0, 2)


def test_ai_resolve_reverts_partial_coverage(direct_vm, direct_deploy, direct_alice):
    """Every requested id must be scored exactly once; skipping one reverts."""
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid1 = _create(contract, direct_vm, direct_alice, "A", "A", 2 * GEN)
    pid2 = _create(contract, direct_vm, direct_alice, "B", "B", 2 * GEN)

    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid1, "0.9")))
    _rejected_without_moving(
        contract, contract.resolve_proposals_ai, [pid1, pid2], pids=[pid1, pid2]
    )

    assert contract.get_proposal(pid1)["status"] == "OPEN"
    assert contract.get_proposal(pid2)["status"] == "OPEN"
    assert contract.get_proposal(pid1)["funded"] == 0
    assert contract.get_proposal(pid2)["funded"] == 0
    assert _ledger(contract) == (10 * GEN, 0, 2)


# ================================================== security: over-limit caps
def test_ai_resolve_payout_capped_by_requested_amount(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    """A perfect score can never pay out more than the proposal asked for."""
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_bob, "Small ask", "Little money", 2 * GEN)

    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "1.0")))
    contract.resolve_proposals_ai([pid])

    p = contract.get_proposal(pid)
    assert p["funded"] == 2 * GEN
    pool = contract.get_pool()
    assert pool["balance"] == 10 * GEN - 2 * GEN
    assert pool["total_funded"] == 2 * GEN


def test_ai_resolve_total_never_exceeds_pool(
    direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie
):
    """Sum of payouts stays within the pool no matter how good the scores are."""
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 5 * GEN)
    pid1 = _create(contract, direct_vm, direct_bob, "A", "A", 4 * GEN)
    pid2 = _create(contract, direct_vm, direct_charlie, "B", "B", 4 * GEN)

    direct_vm.mock_llm(
        AI_PROMPT,
        json.dumps({**{str(pid1): {"score": "1.0", "reasoning": "a"}},
                    **{str(pid2): {"score": "1.0", "reasoning": "b"}}}),
    )
    contract.resolve_proposals_ai([pid1, pid2])

    p1 = contract.get_proposal(pid1)
    p2 = contract.get_proposal(pid2)
    assert p1["funded"] + p2["funded"] <= 5 * GEN
    assert p1["funded"] <= 4 * GEN
    assert p2["funded"] <= 4 * GEN
    assert contract.get_pool()["balance"] >= 0


# ================================================================ views
def test_list_proposals(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 20 * GEN)
    _create(contract, direct_vm, direct_alice, "P1", "D1", 1 * GEN)
    _create(contract, direct_vm, direct_bob, "P2", "D2", 2 * GEN)

    listed = contract.list_proposals(0, 10)
    assert len(listed) == 2
    assert listed[0]["title"] == "P1"
    assert listed[1]["title"] == "P2"


def test_list_filter_status(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 20 * GEN)
    pid1 = _create(contract, direct_vm, direct_alice, "P1", "D1", 1 * GEN)
    _create(contract, direct_vm, direct_alice, "P2", "D2", 1 * GEN)

    direct_vm.sender = direct_alice
    contract.cancel_proposal(pid1)

    open_only = contract.list_proposals(0, 10, "OPEN")
    assert len(open_only) == 1
    assert open_only[0]["title"] == "P2"


# =============================================== source-level fund guards
def _decorator_path(node):
    """``gl.public.write.payable`` -> "gl.public.write.payable"."""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def _attribute_path(node, prefix=()):
    """``self.pool.balance`` -> ("self", "pool", "balance")."""
    if isinstance(node, ast.Attribute):
        return _attribute_path(node.value, prefix) + (node.attr,)
    if isinstance(node, ast.Name):
        return prefix + (node.id,)
    return ()


def _assign_paths(node):
    """Attribute paths of every assignment target under ``node``."""
    paths = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assign):
            targets = sub.targets
        elif isinstance(sub, (ast.AugAssign, ast.AnnAssign)):
            targets = [sub.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Subscript):
                target = target.value
            path = _attribute_path(target)
            if path:
                paths.append(path)
    return paths


def _contract_tree():
    return ast.parse(CONTRACT_SRC.read_text())


def test_write_surface_is_exactly_four_methods():
    """Nothing outside this set can be called to write state or move funds."""
    writes = set()
    for node in ast.walk(_contract_tree()):
        if not isinstance(node, ast.FunctionDef):
            continue
        if any(_decorator_path(d).startswith("gl.public.write") for d in node.decorator_list):
            writes.add(node.name)
    assert writes == {
        "deposit",
        "create_proposal",
        "cancel_proposal",
        "resolve_proposals_ai",
    }


def test_allocator_is_only_reachable_from_the_validator_path():
    """``_allocate`` is what funds proposals, and only one method calls it."""
    callers = {}
    for node in ast.walk(_contract_tree()):
        if not isinstance(node, ast.FunctionDef):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and _attribute_path(sub.func) == (
                "self",
                "_allocate",
            ):
                callers[node.name] = callers.get(node.name, 0) + 1
    assert callers == {"resolve_proposals_ai": 1}


def test_only_allocate_writes_a_score_or_moves_pool_money():
    """A score, a funded total, or a balance change is written in one place.

    This is what makes the negative tests above hold for the whole contract
    surface rather than for the handful of paths they happen to exercise: any
    new write entry that scores or pays would break this test even before
    someone proves it with a call.
    """
    payout_writers = {}
    balance_writers = set()
    for node in ast.walk(_contract_tree()):
        if not isinstance(node, ast.FunctionDef):
            continue
        for path in _assign_paths(node):
            joined = ".".join(path)
            if joined in ("p.score", "p.funded", "self.pool.total_funded"):
                payout_writers.setdefault(joined, set()).add(node.name)
            if joined == "self.pool.balance":
                balance_writers.add(node.name)

    assert payout_writers == {
        "p.score": {"_allocate"},
        "p.funded": {"_allocate"},
        "self.pool.total_funded": {"__init__", "_allocate"},
    }
    # deposit only ever adds gl.message.value; nothing else may touch the balance.
    assert balance_writers == {"deposit", "_allocate"}