# PoolVoice: the fund that reads the room

An AI-governed community fund on GenLayer. Sponsors fill a shared pool with
GEN, builders submit funding proposals, and AI validators score every proposal
on community benefit, feasibility, and alignment. Funded proposals are paid
proportionally to their scores, capped at each requested amount, and every
score plus the reasoning behind it lands on-chain.

Live app: https://poolvoice.vercel.app

## Why it exists

Small grant programs usually die in a reviewer's inbox. PoolVoice replaces the
committee with a public prompt and consensus math: the same scoring rules apply
to every proposal in a batch, the model's reasoning is stored next to each
score, and the pool splits by the numbers. No backroom, no vote-buying, no
hidden formula.

## How it works

1. **Sponsor funds the pool.** Anyone can `deposit` GEN. The pool balance is a
   public number, and proposal amounts are reserved against it while they are
   open.
2. **Builders make the ask.** `create_proposal` takes a title, a description
   (what gets delivered and who benefits), and a GEN amount. Minimum 0.01.
3. **AI scores the batch.** `resolve_proposals_ai` runs the scoring prompt
   through the validators and reaches consensus via the comparative
   equivalence principle. The caller never supplies a score: validators
   produce it, validators agree on it, then anything moves.
4. **The pool splits by the scores.** Proposals scoring above 0.5 are funded
   proportionally (`budget × score / total_score`), then capped by the
   proposal's own requested amount and the remaining pool balance. Everything
   else resolves at 0. The reasoning for every decision is emitted as an
   on-chain event and stored on the proposal.

### Resolution rules (enforced in the contract)

- Every requested id must be unique, must exist, and must still be open.
- The AI must return exactly one bounded score (0 to 1) per requested id, no
  foreign ids, no gaps.
- A proposal resolves exactly once; a stale or cancelled proposal cannot be
  resolved.
- No payout can exceed the requested amount or the remaining pool balance.

A proposer can cancel their own open proposal. There is no manual scoring
entry point: the only way money moves is through the validator-backed AI path.

## On-chain

| | |
|---|---|
| Network | GenLayer StudioNet |
| Contract | [`0xff32C5E21295CdEa8C982E0aC9e358eF1FC526a8`](https://explorer-studio.genlayer.com/address/0xff32C5E21295CdEa8C982E0aC9e358eF1FC526a8) |
| Contract source | [`contracts/pool_voice.py`](contracts/pool_voice.py) |
| Pool state | 5 GEN in pool · 1 GEN paid out · 3 proposals (2 open, 1 AI-resolved at 0.91) |

The resolved demo proposal shows the full lifecycle: submitted, scored by the
validators, and paid 1 GEN with its reasoning stored on-chain.

## Running locally

The frontend is a Vite + React app that talks to StudioNet through
[genlayer-js](https://www.npmjs.com/package/genlayer-js) and any injected
wallet. The Proposals page includes a "Score with AI" action that calls
`resolve_proposals_ai` for the open proposals.

```bash
cd frontend-poolvoice
npm install
npm run dev
```

Set `VITE_CONTRACT_ADDRESS` to point the app at a different PoolVoice
deployment; the default is the address above.

### Tests

The contract has two test layers:

- **Direct mode** (`tests/direct/test_pool_voice.py`) runs the contract in a
  local VM and covers deposits, proposal guards, cancellation, the AI
  resolution workflow (validators mocked), and rejection proofs: the manual
  path is gone, duplicate or stale ids revert, malformed or out-of-bounds AI
  output reverts with nothing moved, foreign or partial coverage reverts, and
  payouts stay capped by the requested amount and the pool balance. 32 tests.
- **Integration** (`tests/integration/test_pool_voice.py`) deploys to StudioNet
  and exercises the real consensus path: sponsor deposit, proposal from a
  second wallet, validator-backed AI resolve with payout, and cancellation.

```bash
# direct (fast, no network)
python -m pytest tests/direct/test_pool_voice.py -v

# on-chain (StudioNet must be reachable)
gltest --network studionet tests/integration/test_pool_voice.py -v -s

# fresh deploy + demo data
gltest --network studionet tests/deploy_seed_poolvoice.py -v -s
```

Rejection proofs go through one helper, `_expect_revert`, which passes only if
the call raised the contract's own revert type. A call that quietly returns
fails the test with the value it returned. Each rejection proof then compares
the pool ledger (balance, funded total, proposal count) and the touched
proposals against a snapshot taken before the call, so a forbidden call that
transferred anything is caught even if it also reverted later.

Three more tests read the contract source and fail if that property stops
holding: the public write surface must be exactly the four known methods, the
funding routine must be called from one place, and no function other than it
may write a proposal score, a funded total, or the pool balance.

## Project layout

```
contracts/pool_voice.py        the PoolVoice contract
tests/direct/                  local VM test suite
tests/integration/             StudioNet integration tests
tests/deploy_seed_poolvoice.py fresh deploy + demo data seeder
frontend-poolvoice/            Vite + React app (the live site)
```

## Notes

- StudioNet GEN is valueless; the mechanics are the point.
- Scores are stored as strings (for example `"0.85"`) because calldata floats
  are not a thing here. The allocation math converts and clamps them.
- Deposits are payable; every other write reverts if you attach value.