"""Integration tests for PoolVoice on StudioNet.

Run: gltest --network studionet tests/integration/test_pool_voice.py -v -s

These exercise the real consensus pipeline: a sponsor funds the community
pool, a second wallet submits a funding proposal, and the contract resolves
it from an explicit score (the AI path itself is exercised by validators via
nondeterministic exec_prompt; the deterministic allocation math is covered by
the fast direct-mode tests).
"""

import pytest
from gltest import get_accounts, get_contract_factory
from gltest.assertions import tx_execution_succeeded

GEN = 10**18
DEPOSIT = 2 * GEN
PROPOSAL_AMT = GEN // 2


def _deploy(account):
    factory = get_contract_factory("PoolVoice")
    contract = factory.deploy(account=account)

    pool = contract.get_pool(args=[]).call()
    assert int(pool["total_proposals"]) == 0
    assert int(pool["balance"]) == 0
    return contract


@pytest.mark.integration
def test_deposit_create_resolve_lifecycle():
    accounts = get_accounts()
    sponsor, proposer = accounts[0], accounts[1]
    contract = _deploy(account=sponsor)

    # Sponsor funds the pool.
    receipt = contract.deposit(args=[]).transact(
        value=DEPOSIT, wait_interval=10000, wait_retries=15
    )
    assert tx_execution_succeeded(receipt)

    pool = contract.get_pool(args=[]).call()
    assert int(pool["balance"]) == DEPOSIT
    assert pool["sponsor"].lower() == sponsor.address.lower()

    # A second wallet submits a proposal.
    contract = contract.connect(proposer)
    receipt = contract.create_proposal(
        args=["Fund public goods", "Integration test proposal", PROPOSAL_AMT],
    ).transact(wait_interval=10000, wait_retries=15)
    assert tx_execution_succeeded(receipt)

    listed = contract.list_proposals(args=[0, 10]).call()
    assert len(listed) == 1
    assert listed[0]["title"] == "Fund public goods"
    assert listed[0]["status"] == "OPEN"
    pid = int(listed[0]["id"])

    # Resolve from an explicit score. Money moves proportionally.
    contract = contract.connect(sponsor)
    receipt = contract.resolve_proposals(
        args=[[pid], ["0.85"]],
    ).transact(wait_interval=10000, wait_retries=15)
    assert tx_execution_succeeded(receipt)

    p = contract.get_proposal(args=[pid]).call()
    assert p["status"] == "RESOLVED"
    assert float(p["score"]) == 0.85
    assert int(p["funded"]) > 0

    pool = contract.get_pool(args=[]).call()
    assert int(pool["balance"]) == DEPOSIT - int(p["funded"])
    assert int(pool["total_funded"]) == int(p["funded"])


@pytest.mark.integration
def test_cancel_proposal():
    accounts = get_accounts()
    sponsor, proposer = accounts[0], accounts[1]
    contract = _deploy(account=sponsor)

    receipt = contract.deposit(args=[]).transact(
        value=DEPOSIT, wait_interval=10000, wait_retries=15
    )
    assert tx_execution_succeeded(receipt)

    contract = contract.connect(proposer)
    receipt = contract.create_proposal(
        args=["Cancel me", "Will be cancelled", PROPOSAL_AMT],
    ).transact(wait_interval=10000, wait_retries=15)
    assert tx_execution_succeeded(receipt)

    receipt = contract.cancel_proposal(args=[1]).transact(
        wait_interval=10000, wait_retries=15
    )
    assert tx_execution_succeeded(receipt)

    p = contract.get_proposal(args=[1]).call()
    assert p["status"] == "CANCELLED"

    # The reserved amount is back in the pool.
    pool = contract.get_pool(args=[]).call()
    assert int(pool["balance"]) == DEPOSIT
