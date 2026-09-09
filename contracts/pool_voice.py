# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""PoolVoice: AI-governed community fund.

A community pool accepts GEN deposits. Anyone submits a funding proposal
with a title, description, and requested amount. An AI agent scores every
active proposal on community benefit, feasibility, and alignment (0-1),
then funds are allocated proportionally. All AI reasoning is stored on-chain
for full transparency.
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
        """Resolve proposals using AI sentiment scoring."""
        if len(ids) == 0:
            raise gl.vm.UserError("no proposals to resolve")
        budget = int(self.pool.balance)
        if budget == 0:
            raise gl.vm.UserError("pool is empty")

        context_parts = []
        for pid in ids:
            p = self._get(pid)
            if p.status != OPEN:
                raise gl.vm.UserError(f"proposal #{pid} not open")
            context_parts.append(
                f"#{pid} | {p.title}\n{p.description}\nRequested: {int(p.amount) / GEN_ONE} GEN"
            )
        context = "\n---\n".join(context_parts)

        prompt = (
            "You are a DAO governance AI. Score each proposal 0-1 on community benefit, "
            "feasibility, and alignment with the open-source AI ecosystem. "
            "Return JSON array: [{\"id\": <int>, \"score\": <float 0-1>, \"reasoning\": \"<str>\"}]. "
            "Be strict.\n\nProposals:\n" + context
        )

        def do_evaluate() -> str:
            return gl.nondet.exec_prompt(prompt)

        llm_result = gl.eq_principle.strict_eq(do_evaluate)
        if isinstance(llm_result, str):
            evaluations = json.loads(llm_result)
        elif isinstance(llm_result, list):
            evaluations = llm_result
        elif isinstance(llm_result, dict):
            evaluations = [llm_result]
        else:
            raise gl.vm.UserError("AI returned invalid result")
        if not isinstance(evaluations, list) or len(evaluations) == 0:
            raise gl.vm.UserError("AI returned invalid result")

        self._allocate(ids, evaluations, budget)

    # -------------------------------------------------- resolve manually
    @gl.public.write
    def resolve_proposals(self, ids: list[u256], scores: list[str], reasoning: str = "") -> None:
        """Resolve proposals with explicit scores (for direct testing / manual override)."""
        if len(ids) == 0:
            raise gl.vm.UserError("no proposals to resolve")
        if len(ids) != len(scores):
            raise gl.vm.UserError("ids and scores length mismatch")
        budget = int(self.pool.balance)
        if budget == 0:
            raise gl.vm.UserError("pool is empty")

        evaluations = []
        for i, pid in enumerate(ids):
            evaluations.append({
                "id": int(pid),
                "score": float(scores[i]),
                "reasoning": reasoning,
            })

        self._allocate(ids, evaluations, budget)

    # -------------------------------------------------- internal allocate
    def _allocate(self, ids: list[u256], evaluations: list, budget: int) -> None:
        scored: list[tuple[int, float, str]] = []
        total_score = 0.0
        for ev in evaluations:
            pid = ev["id"]
            score = float(ev["score"])
            reasoning = str(ev.get("reasoning", ""))
            p = self._get(pid)
            p.score = str(score)
            p.reasoning = reasoning
            if score > 0.5:
                scored.append((pid, score, reasoning))
                total_score += score

        for pid, score, reasoning in scored:
            p = self._get(pid)
            share = int(budget * score / total_score) if total_score > 0 else 0
            if share > int(self.pool.balance):
                share = int(self.pool.balance)
            if share > 0:
                p.funded = u256(share)
                self.pool.balance = u256(int(self.pool.balance) - share)
                self.pool.total_funded = u256(int(self.pool.total_funded) + share)
                _NativeRecipient(p.proposer).emit_transfer(value=u256(share))
            p.status = RESOLVED
            p.resolved_at = u256(self._now())
            ProposalResolved(
                u256(int(pid)),
                score=str(p.score),
                funded=int(p.funded),
                reasoning=reasoning,
            ).emit()

        for ev in evaluations:
            pid = ev["id"]
            p = self._get(pid)
            if p.status != RESOLVED:
                p.status = RESOLVED
                p.resolved_at = u256(self._now())
                ProposalResolved(
                    u256(int(pid)),
                    score=str(p.score),
                    funded=0,
                    reasoning=str(p.reasoning),
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
