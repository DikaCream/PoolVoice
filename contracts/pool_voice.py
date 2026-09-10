# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""PoolVoice: AI-governed community fund.

A community pool accepts GEN deposits. Anyone submits a funding proposal
with a title, description, and requested amount. Validators run the same
prompt over every open proposal and score each one on community benefit,
feasibility, and alignment (0-1), reach consensus on the scores through the
comparative equivalence principle, then funds are allocated proportionally,
capped by each proposal's requested amount. All AI reasoning is stored
on-chain for full transparency.
"""
from genlayer import *
from dataclasses import dataclass
import datetime
import json

# ---------------------------------------------------------------- statuses
OPEN = "OPEN"
RESOLVED = "RESOLVED"
CANCELLED = "CANCELLED"

GEN_ONE = 10 ** 18
MIN_PROPOSAL_GEN = GEN_ONE // 100  # 0.01 GEN
FUNDING_THRESHOLD = 0.5            # score must be above this to receive funds
MAX_REASON_CHARS = 500

# ------------------------------------------------------------- data models
@allow_storage
@dataclass
class Pool:
    sponsor: Address
    has_sponsor: bool
    balance: u256
    total_funded: u256
    total_proposals: u256

@allow_storage
@dataclass
class Proposal:
    id: u256
    title: str
    description: str
    amount: u256
    proposer: Address
    status: str
    score: str
    reasoning: str
    funded: u256
    created_at: u256
    resolved_at: u256

# -------------------------------------------------------------- events
class Deposited(gl.Event):
    def __init__(self, sender: Address, amount: u256, /, **blob): ...

class ProposalCreated(gl.Event):
    def __init__(self, proposal_id: u256, proposer: Address, amount: u256, /, **blob): ...

class ProposalResolved(gl.Event):
    def __init__(self, proposal_id: u256, /, **blob): ...

class ProposalCancelled(gl.Event):
    def __init__(self, proposal_id: u256, /, **blob): ...

# ---------------------------------------------------------------- payouts
@gl.evm.contract_interface
class _NativeRecipient:
    class View:
        pass
    class Write:
        pass

# ==============================================================
class PoolVoice(gl.Contract):
    pool: Pool
    proposals: TreeMap[u256, Proposal]
    next_proposal_id: u256

    def __init__(self):
        self.pool.total_funded = u256(0)
        self.pool.total_proposals = u256(0)
        self.next_proposal_id = u256(1)

    def _now(self) -> int:
        raw = gl.message_raw.get("datetime")
        if raw is None:
            return 0
        try:
            return int(
                datetime.datetime.fromisoformat(
                    raw.replace("Z", "+00:00")
                ).timestamp()
            )
        except Exception:
            return 0

    # -------------------------------------------------- deposit
    @gl.public.write.payable
    def deposit(self) -> None:
        if gl.message.value == 0:
            raise gl.vm.UserError("must send GEN")
        if not self.pool.has_sponsor:
            self.pool.sponsor = gl.message.sender_address
            self.pool.has_sponsor = True
        self.pool.balance = u256(int(self.pool.balance) + gl.message.value)
        Deposited(gl.message.sender_address, gl.message.value).emit()

    # -------------------------------------------------- create proposal
    @gl.public.write
    def create_proposal(self, title: str, description: str, amount: u256) -> u256:
        if len(title) == 0 or len(title) > 200:
            raise gl.vm.UserError("title: 1-200 chars")
        if len(description) == 0 or len(description) > 2000:
            raise gl.vm.UserError("description: 1-2000 chars")
        if int(amount) < MIN_PROPOSAL_GEN:
            raise gl.vm.UserError("amount must be >= 0.01 GEN")
        if int(amount) > int(self.pool.balance):
            raise gl.vm.UserError("amount exceeds pool balance")

        pid = u256(int(self.pool.total_proposals) + 1)
        self.pool.total_proposals = pid
        self.proposals[pid] = Proposal(
            id=pid,
            title=title,
            description=description,
            amount=amount,
            proposer=gl.message.sender_address,
            status=OPEN,
            score="0.0",
            reasoning="",
            funded=u256(0),
            created_at=u256(self._now()),
            resolved_at=u256(0),
        )
        ProposalCreated(pid, gl.message.sender_address, amount).emit()
        return pid

    # -------------------------------------------------- cancel
    @gl.public.write
    def cancel_proposal(self, proposal_id: u256) -> None:
        p = self._get(proposal_id)
        if p.status != OPEN:
            raise gl.vm.UserError("not open")
        if gl.message.sender_address != p.proposer:
            raise gl.vm.UserError("only proposer")
        p.status = CANCELLED
        ProposalCancelled(proposal_id).emit()

    # -------------------------------------------------- resolve with AI
    @gl.public.write
    def resolve_proposals_ai(self, ids: list[u256]) -> None:
        """Resolve proposals using validator-backed AI scoring.

        Any caller may trigger this; the scores come from the validators
        running the same prompt and reaching consensus, never from the
        caller. Every id must be unique, exist, and still be open. The AI
        must return exactly one bounded score (0-1) per requested id, and
        each payout is capped by the proposal's requested amount.
        """
        if len(ids) == 0:
            raise gl.vm.UserError("no proposals to resolve")
        budget = int(self.pool.balance)
        if budget == 0:
            raise gl.vm.UserError("pool is empty")

        # Validate ids up front: unique, in range, all still open.
        wanted: set[int] = set()
        targets: dict[int, Proposal] = {}
        for pid in ids:
            key = int(pid)
            if key in wanted:
                raise gl.vm.UserError("duplicate proposal id")
            wanted.add(key)
            if key < 1 or key > int(self.pool.total_proposals):
                raise gl.vm.UserError("proposal not found")
            p = self.proposals[u256(key)]
            if p.status != OPEN:
                raise gl.vm.UserError("proposal not open")
            targets[key] = p

        context_parts = []
        for key in wanted:
            p = targets[key]
            context_parts.append(
                f"#{key} | {p.title}\n{p.description}\nRequested: {int(p.amount) / GEN_ONE} GEN"
            )
        context = "\n---\n".join(context_parts)

        prompt = (
            "You are a DAO governance AI. Score each proposal 0-1 on community benefit, "
            "feasibility, and alignment with the open-source AI ecosystem. "
            "Return STRICT JSON only, no prose, no markdown fences: an object mapping "
            "every proposal id to its score, of the form "
            '{"<id>": {"score": <float 0-1>, "reasoning": "<str>"}}. '
            "One entry per proposal, every id exactly once. Be strict. "
            "Proposals:\n" + context
        )

        def do_evaluate() -> str:
            # Text format on purpose: the raw LLM text crosses the WASM boundary
            # as a string (calldata-safe). JSON scores parsed here stay inside
            # the VM and are re-serialized into the canonical string below.
            try:
                raw = gl.nondet.exec_prompt(prompt)
            except Exception:
                raw = None
            if isinstance(raw, str):
                start = raw.find("{")
                end = raw.rfind("}")
                if start >= 0 and end > start:
                    raw = raw[start : end + 1]
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {"error": "unparseable"}
            elif raw is None:
                data = {"error": "unparseable"}
            else:
                data = raw
            return json.dumps(data, sort_keys=True)

        principle = (
            "Both answers are AI funding scores for the same set of proposals. "
            "They are equivalent if and only if, for every proposal id, both answers "
            "agree on whether the score is above 0.5 (funded) or at or below 0.5 "
            "(not funded), both answers cover exactly the same set of proposal ids, "
            "and neither answer gives a score outside 0-1. Exact score values and the "
            "reasoning text may differ slightly. If either answer is an error object, "
            "they are equivalent only if both are."
        )

        result = gl.eq_principle.prompt_comparative(do_evaluate, principle)
        try:
            evaluations = json.loads(str(result))
        except Exception:
            raise gl.vm.UserError("AI returned invalid result")

        self._allocate(ids, evaluations, budget, targets)

    # -------------------------------------------------- internal allocate
    def _allocate(
        self,
        ids: list[u256],
        evaluations: dict,
        budget: int,
        targets: dict[int, Proposal],
    ) -> None:
        if not isinstance(evaluations, dict) or len(evaluations) == 0:
            raise gl.vm.UserError("AI returned invalid result")
        if len(evaluations) != len(ids):
            raise gl.vm.UserError("AI must score every proposal exactly once")

        by_id: dict[int, tuple[float, str]] = {}
        for key_raw, ev in evaluations.items():
            try:
                pid = int(key_raw)
            except Exception:
                raise gl.vm.UserError("AI returned invalid result")
            if pid in by_id or pid not in targets:
                raise gl.vm.UserError("AI returned invalid result")
            if not isinstance(ev, dict):
                raise gl.vm.UserError("AI returned invalid result")
            try:
                score = float(ev.get("score"))
            except Exception:
                raise gl.vm.UserError("AI returned invalid result")
            if score != score or score > 1.0 or score < 0.0:
                raise gl.vm.UserError("AI score out of range")
            reasoning = str(ev.get("reasoning", ""))[:MAX_REASON_CHARS]
            by_id[pid] = (score, reasoning)

        total_score = 0.0
        for key in targets:
            score, _ = by_id[key]
            if score > FUNDING_THRESHOLD:
                total_score += score

        for key in targets:
            p = targets[key]
            score, reasoning = by_id[key]
            p.score = str(score)
            p.reasoning = reasoning
            share = 0
            if total_score > 0 and score > FUNDING_THRESHOLD:
                share = int(budget * score / total_score)
                share = min(share, int(p.amount))            # cap by requested amount
                share = min(share, int(self.pool.balance))   # cap by remaining pool
            if share > 0:
                p.funded = u256(share)
                self.pool.balance = u256(int(self.pool.balance) - share)
                self.pool.total_funded = u256(int(self.pool.total_funded) + share)
                _NativeRecipient(p.proposer).emit_transfer(value=u256(share))
            p.status = RESOLVED
            p.resolved_at = u256(self._now())
            ProposalResolved(
                u256(key),
                score=p.score,
                funded=int(p.funded),
                reasoning=reasoning,
            ).emit()

    # -------------------------------------------------- views
    @gl.public.view
    def get_pool(self) -> dict:
        return {
            "balance": int(self.pool.balance),
            "total_funded": int(self.pool.total_funded),
            "total_proposals": int(self.pool.total_proposals),
            "sponsor": self.pool.sponsor.as_hex,
        }

    @gl.public.view
    def get_proposal(self, proposal_id: u256) -> dict:
        p = self._get(proposal_id)
        return {
            "id": int(p.id), "title": p.title, "description": p.description,
            "amount": int(p.amount), "proposer": p.proposer.as_hex,
            "status": p.status, "score": p.score,
            "reasoning": p.reasoning, "funded": int(p.funded),
            "created_at": int(p.created_at), "resolved_at": int(p.resolved_at),
        }

    @gl.public.view
    def list_proposals(self, offset: u256, limit: u256, status_filter: str = "") -> list[dict]:
        result = []
        total = int(self.pool.total_proposals)
        start = max(int(offset), 1)
        end = min(start + int(limit), total + 1)
        for i in range(start, end):
            p = self._get(u256(i))
            if status_filter and p.status != status_filter:
                continue
            result.append({
                "id": int(p.id), "title": p.title, "amount": int(p.amount),
                "proposer": p.proposer.as_hex, "status": p.status,
                "score": p.score, "funded": int(p.funded),
                "created_at": int(p.created_at),
            })
        return result

    # -------------------------------------------------- internal
    def _get(self, pid: u256) -> Proposal:
        if int(pid) < 1 or int(pid) > int(self.pool.total_proposals):
            raise gl.vm.UserError("proposal not found")
        return self.proposals[pid]