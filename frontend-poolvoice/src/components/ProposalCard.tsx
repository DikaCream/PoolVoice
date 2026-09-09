import { EXPLORER_ADDR, formatGen, shortAddr } from "../config";
import type { Proposal } from "../lib/types";

function StatusTag({ status }: { status: Proposal["status"] }) {
  return <span className={`tag tag-${status.toLowerCase()}`}>{status}</span>;
}

function ScoreMeter({ score }: { score: string }) {
  const n = Math.max(0, Math.min(1, parseFloat(score) || 0));
  const pct = Math.round(n * 100);
  return (
    <div className="score-meter" role="img" aria-label={`AI score ${pct} out of 100`}>
      <div className="score-meter-head">
        <span className="score-label">AI score</span>
        <span className="score-value">{pct}/100</span>
      </div>
      <div className="score-track">
        <div className="score-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function ProposalCard({ p }: { p: Proposal }) {
  const requested = formatGen(p.amount, 2);
  const funded = p.funded > 0n ? formatGen(p.funded, 2) : null;

  return (
    <article className={`pcard pcard-${p.status.toLowerCase()}`}>
      <header className="pcard-top">
        <span className="pcard-num">#{p.id}</span>
        <StatusTag status={p.status} />
        {funded && <span className="funded-chip">{funded} GEN funded</span>}
      </header>

      <h3 className="pcard-title">{p.title}</h3>
      <p className="pcard-desc">{p.description}</p>

      {p.reasoning && (
        <blockquote className="pcard-reason">
          <span className="pcard-reason-label">Why the AI funded it</span>
          {p.reasoning}
        </blockquote>
      )}

      <footer className="pcard-foot">
        <div className="pcard-amount">
          <span className="pcard-amount-label">{p.status === "RESOLVED" ? "Funded" : "Requested"}</span>
          <span className="pcard-amount-value">
            {p.status === "RESOLVED" ? (funded ?? "0 GEN") : `${requested} GEN`}
          </span>
        </div>
        <a
          className="pcard-proposer"
          href={EXPLORER_ADDR(p.proposer)}
          target="_blank"
          rel="noreferrer"
        >
          by {shortAddr(p.proposer)}
        </a>
      </footer>

      {p.status === "RESOLVED" && <ScoreMeter score={p.score} />}
    </article>
  );
}
