import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { usePoolVoice } from "../context/PoolVoiceContext";
import { formatGen } from "../config";
import type { Pool } from "../lib/types";

function usePool(): { pool: Pool | null; error: string | null } {
  const { contract } = usePoolVoice();
  const [pool, setPool] = useState<Pool | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    contract
      .getPool()
      .then((p) => alive && setPool(p))
      .catch((e) => alive && setError(String(e?.message ?? e)));
    return () => {
      alive = false;
    };
  }, [contract]);

  return { pool, error };
}

export function Home() {
  const { pool, error } = usePool();

  return (
    <main className="home">
      <section className="hero">
        <p className="hero-kicker">An AI-governed community fund</p>
        <h1 className="hero-title">
          The fund that
          <br />
          <em>reads the room.</em>
        </h1>
        <p className="hero-sub">
          Sponsors fill a shared pool. Builders submit funding proposals. AI
          validators score every proposal on community benefit and feasibility,
          and the money splits by the scores. No committee, no backroom, no
          vote-buying. Every score and every line of reasoning lands on-chain.
        </p>
        <div className="hero-cta">
          <Link className="btn btn-solid btn-lg" to="/proposals">
            Read the proposals
          </Link>
          <Link className="btn btn-ghost btn-lg" to="/submit">
            Submit yours
          </Link>
        </div>
      </section>

      <section className="poolbar" aria-label="Pool status">
        {error && <p className="poolbar-err">Pool data unavailable: {error}</p>}
        {pool && (
          <>
            <div className="poolbar-cell">
              <span className="poolbar-num">{formatGen(pool.balance, 2)}</span>
              <span className="poolbar-label">GEN in the pool</span>
            </div>
            <div className="poolbar-cell">
              <span className="poolbar-num">{formatGen(pool.total_funded, 2)}</span>
              <span className="poolbar-label">GEN paid out so far</span>
            </div>
            <div className="poolbar-cell">
              <span className="poolbar-num">{pool.total_proposals}</span>
              <span className="poolbar-label">proposals submitted</span>
            </div>
          </>
        )}
      </section>

      <section className="how">
        <h2 className="section-title">How a proposal becomes a payout</h2>
        <ol className="steps">
          <li className="step">
            <span className="step-num">1</span>
            <h3>A sponsor fills the pool</h3>
            <p>
              Anyone can deposit GEN. The first depositor is recorded as the
              pool's sponsor; everyone after just grows the pot. The pool is a
              public number. You can watch it move.
            </p>
          </li>
          <li className="step">
            <span className="step-num">2</span>
            <h3>Builders make the ask</h3>
            <p>
              A proposal states what will be built, why the community benefits,
              and exactly how much GEN it needs. The amount is reserved against
              the pool the moment it's submitted.
            </p>
          </li>
          <li className="step">
            <span className="step-num">3</span>
            <h3>AI scores the work, not the hype</h3>
            <p>
              Validators run the same prompt over every proposal and score it
              zero to one on community benefit, feasibility, and alignment.
              Consensus on the score is reached before anything is paid.
            </p>
          </li>
          <li className="step">
            <span className="step-num">4</span>
            <h3>The pool splits by the scores</h3>
            <p>
              Funded proposals are paid proportionally to their score. A 0.9
              takes home twice a 0.45's share. Everything below the bar gets
              nothing, and the reasoning for every decision stays on-chain.
            </p>
          </li>
        </ol>
      </section>

      <section className="ethos">
        <h2 className="section-title">Why this is different</h2>
        <div className="ethos-grid">
          <div className="ethos-item">
            <h3>Grants without the politics</h3>
            <p>
              Most small grant programs die in a reviewer's inbox. Here the
              criteria are written into a prompt, the prompt is public, and the
              same rules apply to every proposal in the batch.
            </p>
          </div>
          <div className="ethos-item">
            <h3>Reasoning you can audit</h3>
            <p>
              A score with no explanation is a coin flip. Every resolved
              proposal carries the model's reasoning on-chain, next to the
              number it produced.
            </p>
          </div>
          <div className="ethos-item">
            <h3>Small money, real speed</h3>
            <p>
              The pool is built for many modest payouts, not one giant prize.
              Submit on Tuesday, get scored the same week, for the cost of a
              transaction.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
