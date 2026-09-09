# PoolVoice: the fund that reads the room

An AI-governed community fund on GenLayer. Sponsors fill a shared pool with
GEN, builders submit funding proposals, and AI validators score every proposal
on community benefit, feasibility, and alignment. Funded proposals are paid
proportionally to their scores, and every score plus the reasoning behind it
lands on-chain.

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
3. **AI scores the batch.** When a resolve runs, validators execute the same
   scoring prompt over the selected proposals and must agree on the result
   before anything moves. Scores run 0 to 1.
4. **The pool splits by the scores.** Proposals scoring above 0.5 are funded
   proportionally (`budget × score / total_score`), capped at the pool
   balance. Everything else resolves at 0. The reasoning for every decision is
   emitted as an on-chain event and stored on the proposal.

A proposer can cancel their own open proposal. The contract also accepts
explicit scores (`resolve_proposals` with `ids` + `scores`), which is how the
deterministic allocation path is regression-tested without an LLM; the
validator-scored path (`resolve_proposals_ai`) uses the same allocation code.

## On-chain

| | |
|---|---|
| Network | GenLayer StudioNet |
| Contract | [`0xF7351672C3502ba922954eedB932Aeee099E4607`](https://explorer-studio.genlayer.com/address/0xF7351672C3502ba922954eedB932Aeee099E4607) |
| Contract source | [`contracts/pool_voice.py`](contracts/pool_voice.py) |
| Pool state | 5 GEN in pool · 5 GEN paid out · 3 proposals (2 open, 1 resolved at 0.9) |

The resolved demo proposal shows the full lifecycle: submitted, scored, and
paid 5 GEN with its reasoning stored on-chain.

## Running locally

The frontend is a Vite + React app that talks to StudioNet through
[genlayer-js](https://www.npmjs.com/package/genlayer-js) and any injected
wallet.

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
  local VM and covers deposits, proposal guards, cancellation, proportional
  allocation, and pagination. 17 tests.
- **Integration** (`tests/integration/test_pool_voice.py`) deploys to StudioNet
  and exercises the real consensus path: sponsor deposit, proposal from a
  second wallet, resolve with payout, and cancellation.

```bash
# direct (fast, no network)
python -m pytest tests/direct/test_pool_voice.py -v

# on-chain (StudioNet must be reachable)
gltest --network studionet tests/integration/test_pool_voice.py -v -s
```

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
