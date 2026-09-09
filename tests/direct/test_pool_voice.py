"""Direct-mode tests for PoolVoice, the AI-governed DAO fund."""
import json
from tests.direct.conftest import to_hex

GEN = 10 ** 18
DEPOSIT_AMT = 10 * GEN
PROPOSAL_AMT = 2 * GEN


def _deposit(contract, vm, sender, amount=DEPOSIT_AMT):
    vm.sender = sender
    vm.value = amount
    contract.deposit()
    vm.value = 0


def _create(contract, vm, sender, title="Test Proposal", desc="A test", amount=PROPOSAL_AMT):
    vm.sender = sender
    pid = int(contract.create_proposal(title, desc, amount))
    return pid


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


# ============================================================== resolve
def test_resolve_high_score_gets_funded(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_bob, "High Value", "Great project", 3 * GEN)

    contract.resolve_proposals([pid], ["0.85"])
    p = contract.get_proposal(pid)
    assert p["status"] == "RESOLVED"
    assert float(p["score"]) == 0.85
    assert p["funded"] > 0


def test_resolve_low_score_not_funded(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid = _create(contract, direct_vm, direct_bob, "Low Value", "Weak project", 3 * GEN)

    contract.resolve_proposals([pid], ["0.2"])
    p = contract.get_proposal(pid)
    assert p["status"] == "RESOLVED"
    assert float(p["score"]) == 0.2
    assert p["funded"] == 0


def test_resolve_proportional(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice, 10 * GEN)
    pid1 = _create(contract, direct_vm, direct_bob, "Proposal A", "Desc A", 3 * GEN)
    pid2 = _create(contract, direct_vm, direct_charlie, "Proposal B", "Desc B", 3 * GEN)

    contract.resolve_proposals([pid1, pid2], ["0.8", "0.4"])

    p1 = contract.get_proposal(pid1)
    p2 = contract.get_proposal(pid2)
    assert p1["status"] == "RESOLVED"
    assert p2["status"] == "RESOLVED"
    assert p1["funded"] > 0
    assert p2["funded"] == 0


def test_resolve_reverts_empty_ids(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    try:
        contract.resolve_proposals([], [])
        assert False, "should have reverted"
    except Exception:
        pass


def test_resolve_reverts_non_open(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    contract.cancel_proposal(pid)
    try:
        contract.resolve_proposals([pid], ["0.9"])
        assert False, "should have reverted"
    except Exception:
        pass


def test_resolve_reverts_length_mismatch(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/pool_voice.py")
    _deposit(contract, direct_vm, direct_alice)
    pid = _create(contract, direct_vm, direct_alice)
    try:
        contract.resolve_proposals([pid], ["0.9", "0.5"])
        assert False, "should have reverted"
    except Exception:
        pass


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
