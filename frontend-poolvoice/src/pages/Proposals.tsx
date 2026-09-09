import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { usePoolVoice } from "../context/PoolVoiceContext";
import { ProposalCard } from "../components/ProposalCard";
import { describeError } from "../lib/errors";
import { formatGen } from "../config";
import type { Pool, Proposal } from "../lib/types";

type Filter = "ALL" | "OPEN" | "RESOLVED" | "CANCELLED";

const FILTERS: Filter[] = ["ALL", "OPEN", "RESOLVED", "CANCELLED"];

export function Proposals() {
  const { contract, wallet } = usePoolVoice();
  const [proposals, setProposals] = useState<Proposal[] | null>(null);
  const [pool, setPool] = useState<Pool | null>(null);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [error, setError] = useState<string | null>(null);
  const [cancelBusy, setCancelBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [list, p] = await Promise.all([
        contract.listProposals(0, 50),
        contract.getPool(),
      ]);
      setProposals(list);
      setPool(p);
    } catch (e) {
      setError(describeError(e));
    }
  }, [contract]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCancel(id: number) {
    setCancelBusy(id);
    setError(null);
    try {
      const hash = await contract.cancelProposal(id);
      await contract.waitForReceipt(hash);
      await load();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setCancelBusy(null);
    }
  }

  const shown = proposals?.filter((p) => filter === "ALL" || p.status === filter) ?? [];

  return (
    <main className="page">
      <header className="page-head">
        <div>
          <h1 className="page-title">Proposals</h1>
          <p className="page-sub">
            {pool
              ? `${formatGen(pool.balance, 2)} GEN in the pool · ${formatGen(pool.total_funded, 2)} GEN paid out · ${pool.total_proposals} total`
              : "Loading the pool…"}
          </p>
        </div>
        <Link className="btn btn-solid" to="/submit">
          Submit a proposal
        </Link>
      </header>

      <nav className="filter-row" aria-label="Filter proposals">
        {FILTERS.map((f) => (
          <button
            key={f}
            className={`filter-chip ${filter === f ? "filter-chip-on" : ""}`}
            onClick={() => setFilter(f)}
          >
            {f.toLowerCase()}
          </button>
        ))}
      </nav>

      {error && (
        <div className="notice notice-err" role="alert">
          {error}
          <button className="notice-retry" onClick={load}>
            Retry
          </button>
        </div>
      )}

      {proposals === null && !error && <p className="muted">Loading proposals…</p>}

      {proposals !== null && shown.length === 0 && (
        <div className="empty">
          <p className="empty-title">Nothing here yet.</p>
          <p>
            The pool is waiting for its first ask.{" "}
            <Link to="/submit">Submit a proposal</Link> — it takes two fields and
            a transaction.
          </p>
        </div>
      )}

      <div className="pgrid">
        {shown.map((p) => (
          <div key={p.id} className="pgrid-cell">
            {wallet.address &&
              p.status === "OPEN" &&
              p.proposer.toLowerCase() === wallet.address.toLowerCase() && (
                <button
                  className="cancel-btn"
                  disabled={cancelBusy === p.id}
                  onClick={() => handleCancel(p.id)}
                >
                  {cancelBusy === p.id ? "Cancelling…" : "Cancel mine"}
                </button>
              )}
            <ProposalCard p={p} />
          </div>
        ))}
      </div>
    </main>
  );
}
