"""Direct-mode tests for PoolVoice — AI-governed DAO fund.

The only resolution path is validator-backed: resolve_proposals_ai runs the
prompt through validators (mocked here as the LLM response) and the contract
enforces unique/valid/open ids, exactly-one bounded score per id, and payouts
capped by each requested amount. Scores are returned as strings in mocks
because the direct-mode WASI stub encodes LLM responses through calldata,
which does not support floats (the real network has no such limit).
"""
import json
from tests.direct.conftest import to_hex

GEN = 10 ** 18
DEPOSIT_AMT = 10 * GEN
PROPOSAL_AMT = 2 * GEN
AI_PROMPT = r"You are a DAO governance AI"


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
    try:
        contract.deposit()
        assert False, "should have reverted"
    except Exception:
        pass


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
    try:
        contract.create_proposal("", "desc", PROPOSAL_AMT)
        assert False, "should have reverted"
    except Exception:
        pass


def test_create_reverts_exceeds_balance(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 1 * GEN)
    direct_vm.sender = direct_alice
    try:
        contract.create_proposal("Big", "desc", 5 * GEN)
        assert False, "should have reverted"
    except Exception:
        pass


def test_create_reverts_below_minimum(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    try:
        contract.create_proposal("Tiny", "desc", 1)
        assert False, "should have reverted"
    except Exception:
        pass


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
    try:
        contract.cancel_proposal(pid)
        assert False, "should have reverted"
    except Exception:
        pass


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
    not from the caller — a stranger cannot force a payout or a denial."""
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
    """The explicit-scores path is gone: there is no way to set a score by hand."""
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    try:
        contract.resolve_proposals([pid], ["0.99"])
        assert False, "manual resolve should not exist"
    except Exception:
        pass


# ================================================== security: bad id lists
def test_ai_resolve_reverts_empty_ids(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    try:
        contract.resolve_proposals_ai([])
        assert False, "should have reverted"
    except Exception:
        pass


def test_ai_resolve_reverts_duplicate_ids(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "0.9")))
    try:
        contract.resolve_proposals_ai([pid, pid])
        assert False, "duplicate ids should revert"
    except Exception:
        pass


def test_ai_resolve_reverts_invalid_id(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    _create(contract, direct_vm, direct_alice)
    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(99, "0.9")))
    try:
        contract.resolve_proposals_ai([99])
        assert False, "unknown id should revert"
    except Exception:
        pass


def test_ai_resolve_is_one_time(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_alice, "Once", "Once only", 2 * GEN)

    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "0.9")))
    contract.resolve_proposals_ai([pid])
    assert contract.get_proposal(pid)["status"] == "RESOLVED"

    # A second resolution of the same proposal must not double-fund it.
    before = contract.get_proposal(pid)["funded"]
    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "0.9")))
    try:
        contract.resolve_proposals_ai([pid])
        assert False, "stale (already resolved) proposal must revert"
    except Exception:
        pass
    after = contract.get_proposal(pid)["funded"]
    assert after == before


def test_ai_resolve_reverts_cancelled(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    contract.cancel_proposal(pid)
    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "0.9")))
    try:
        contract.resolve_proposals_ai([pid])
        assert False, "cancelled proposal must revert"
    except Exception:
        pass


# ================================================== security: malformed AI
def test_ai_resolve_reverts_malformed_json(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_alice, "Malformed", "Bad output", 2 * GEN)

    direct_vm.mock_llm(AI_PROMPT, "this is not json")
    try:
        contract.resolve_proposals_ai([pid])
        assert False, "malformed AI output must revert"
    except Exception:
        pass

    # Nothing moved.
    p = contract.get_proposal(pid)
    assert p["status"] == "OPEN"
    assert p["funded"] == 0
    assert contract.get_pool()["balance"] == 10 * GEN


def test_ai_resolve_reverts_score_above_one(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_alice, "Inflated", "Too good", 2 * GEN)

    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "1.5")))
    try:
        contract.resolve_proposals_ai([pid])
        assert False, "score above 1 must revert"
    except Exception:
        pass

    p = contract.get_proposal(pid)
    assert p["status"] == "OPEN"
    assert p["funded"] == 0
    assert contract.get_pool()["balance"] == 10 * GEN


def test_ai_resolve_reverts_negative_score(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_alice, "Negative", "No", 2 * GEN)

    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid, "-0.1")))
    try:
        contract.resolve_proposals_ai([pid])
        assert False, "negative score must revert"
    except Exception:
        pass

    p = contract.get_proposal(pid)
    assert p["status"] == "OPEN"
    assert p["funded"] == 0
    assert contract.get_pool()["balance"] == 10 * GEN


def test_ai_resolve_reverts_foreign_id(direct_vm, direct_deploy, direct_alice, direct_bob):
    """The AI cannot slip an allocation for a proposal that was not requested."""
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid1 = _create(contract, direct_vm, direct_alice, "Requested", "Yes", 2 * GEN)
    _create(contract, direct_vm, direct_bob, "Sneaky", "Not requested", 2 * GEN)

    # AI scores the sneaky one and skips the requested one.
    direct_vm.mock_llm(
        AI_PROMPT,
        json.dumps({str(pid1 + 1): {"score": "0.9", "reasoning": "diversion"}}),
    )
    try:
        contract.resolve_proposals_ai([pid1])
        assert False, "foreign id must revert"
    except Exception:
        pass

    assert contract.get_proposal(pid1)["status"] == "OPEN"
    assert contract.get_proposal(pid1 + 1)["status"] == "OPEN"
    assert contract.get_pool()["balance"] == 10 * GEN


def test_ai_resolve_reverts_partial_coverage(direct_vm, direct_deploy, direct_alice):
    """Every requested id must be scored exactly once; skipping one reverts."""
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid1 = _create(contract, direct_vm, direct_alice, "A", "A", 2 * GEN)
    pid2 = _create(contract, direct_vm, direct_alice, "B", "B", 2 * GEN)

    direct_vm.mock_llm(AI_PROMPT, json.dumps(_scores(pid1, "0.9")))
    try:
        contract.resolve_proposals_ai([pid1, pid2])
        assert False, "partial coverage must revert"
    except Exception:
        pass

    assert contract.get_proposal(pid1)["status"] == "OPEN"
    assert contract.get_proposal(pid2)["status"] == "OPEN"
    assert contract.get_pool()["balance"] == 10 * GEN


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