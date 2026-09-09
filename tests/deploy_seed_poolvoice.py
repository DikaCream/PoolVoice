"""Deploy a fresh PoolVoice and seed a demo pool + proposals with real GEN.

Prints the new contract address for the frontend + README.
Run: .venv/bin/gltest --network studionet tests/deploy_seed_poolvoice.py -v -s
"""

from gltest import get_accounts, get_contract_factory
from gltest.assertions import tx_execution_succeeded

GEN = 10**18


def test_deploy_and_seed():
    accounts = get_accounts()
    sponsor, proposer = accounts[0], accounts[1]

    factory = get_contract_factory("PoolVoice")
    contract = factory.deploy(account=sponsor)
    address = contract.address
    print(f"\nNEW CONTRACT ADDRESS: {address}\n")

    # Sponsor funds the community pool with 5 GEN.
    receipt = contract.deposit(args=[]).transact(
        value=5 * GEN, wait_interval=10000, wait_retries=15
    )
    assert tx_execution_succeeded(receipt), receipt
    print("pool funded with 5 GEN: OK")

    # Proposal 1: OPEN, visible on the board for visitors.
    contract = contract.connect(proposer)
    receipt = contract.create_proposal(
        args=[
            "Fund the GenLayer docs translation sprint",
            "Translate the core GenLayer docs into Bahasa Indonesia so local "
            "builders can onboard faster. Covers glossary alignment, review "
            "passes, and publishing the final glossary as a public gist.",
            2 * GEN,
        ],
    ).transact(wait_interval=10000, wait_retries=15)
    assert tx_execution_succeeded(receipt), receipt
    print("proposal 1 (OPEN, requests 2 GEN): OK")

    # Proposal 2: a second open proposal for variety.
    receipt = contract.create_proposal(
        args=[
            "Community testnet faucet top-up",
            "Keep the community faucet topped up for a month so new developers "
            "can deploy their first contract without asking for handouts in "
            "Discord. Publishes the faucet address and a weekly balance log.",
            1 * GEN,
        ],
    ).transact(wait_interval=10000, wait_retries=15)
    assert tx_execution_succeeded(receipt), receipt
    print("proposal 2 (OPEN, requests 1 GEN): OK")

    # Proposal 3: resolved with a high score, funds paid out. This shows the
    # full lifecycle: money actually moved to a proposer.
    receipt = contract.create_proposal(
        args=[
            "Public good: open-source SDK examples repo",
            "A maintained repository of minimal, working GenLayer examples "
            "(one contract pattern per folder) that already exists and is "
            "public. This round funds its next three months of upkeep.",
            1 * GEN,
        ],
    ).transact(wait_interval=10000, wait_retries=15)
    assert tx_execution_succeeded(receipt), receipt

    receipt = contract.resolve_proposals(
        args=[[3], ["0.9"]],
    ).transact(wait_interval=10000, wait_retries=15)
    assert tx_execution_succeeded(receipt), receipt
    p3 = contract.get_proposal(args=[3]).call()
    print(f"proposal 3 resolved: score={p3['score']} funded={int(p3['funded'])/GEN} GEN")

    pool = contract.get_pool(args=[]).call()
    print(
        f"\nPOOL: balance={int(pool['balance'])/GEN} GEN "
        f"funded={int(pool['total_funded'])/GEN} GEN proposals={int(pool['total_proposals'])}"
    )
    print(f"\nUSE THIS ADDRESS: {address}")
