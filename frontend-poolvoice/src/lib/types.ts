export type ProposalStatus = "OPEN" | "RESOLVED" | "CANCELLED";

export interface Pool {
  balance: bigint;
  total_funded: bigint;
  total_proposals: number;
  sponsor: string;
}

export interface Proposal {
  id: number;
  title: string;
  description: string;
  amount: bigint;
  proposer: string;
  status: ProposalStatus;
  score: string;
  reasoning: string;
  funded: bigint;
  created_at: number;
  resolved_at: number;
}

export function toBigInt(v: unknown): bigint {
  if (typeof v === "bigint") return v;
  if (typeof v === "number") return BigInt(Math.trunc(v));
  if (typeof v === "string") {
    try {
      return BigInt(v);
    } catch {
      return 0n;
    }
  }
  return 0n;
}

export function toInt(v: unknown): number {
  const n = Number(toBigInt(v));
  return Number.isFinite(n) ? n : 0;
}

export function fromMapLike(v: any): Record<string, any> {
  if (v instanceof Map) {
    const out: Record<string, any> = {};
    v.forEach((val: any, key: any) => {
      out[String(key)] = val;
    });
    return out;
  }
  return (v ?? {}) as Record<string, any>;
}

export function toPool(v: any): Pool {
  const o = fromMapLike(v);
  return {
    balance: toBigInt(o.balance),
    total_funded: toBigInt(o.total_funded),
    total_proposals: toInt(o.total_proposals),
    sponsor: String(o.sponsor ?? ""),
  };
}

export function toProposal(v: any): Proposal {
  const o = fromMapLike(v);
  const status = String(o.status ?? "OPEN");
  return {
    id: toInt(o.id),
    title: String(o.title ?? ""),
    description: String(o.description ?? ""),
    amount: toBigInt(o.amount),
    proposer: String(o.proposer ?? ""),
    status: (["OPEN", "RESOLVED", "CANCELLED"].includes(status)
      ? status
      : "OPEN") as ProposalStatus,
    score: String(o.score ?? "0.0"),
    reasoning: String(o.reasoning ?? ""),
    funded: toBigInt(o.funded),
    created_at: toInt(o.created_at),
    resolved_at: toInt(o.resolved_at),
  };
}
