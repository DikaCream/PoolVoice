import { useState } from "react";
import { Link } from "react-router-dom";
import { usePoolVoice } from "../context/PoolVoiceContext";
import { describeError } from "../lib/errors";
import { EXPLORER_TX, GEN } from "../config";

const MIN_AMOUNT = 0.01;

export function Submit() {
  const { contract, wallet } = usePoolVoice();

  // proposal form
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("0.5");
  // sponsor form
  const [depositAmount, setDepositAmount] = useState("1");

  const [busy, setBusy] = useState<"" | "propose" | "deposit">("");
  const [feedback, setFeedback] = useState<{ kind: "ok" | "err"; text: string; tx?: string } | null>(
    null,
  );

  const connected = !!wallet.address;

  function validate(): string | null {
    if (title.trim().length < 1 || title.trim().length > 200)
      return "Give the proposal a title — 1 to 200 characters.";
    if (description.trim().length < 1 || description.trim().length > 2000)
      return "Describe the work — 1 to 2000 characters.";
    const n = Number(amount);
    if (!Number.isFinite(n) || n <= 0) return "Enter a valid GEN amount.";
    if (n < MIN_AMOUNT) return "The minimum ask is 0.01 GEN.";
    return null;
  }

  async function submitProposal(e: React.FormEvent) {
    e.preventDefault();
    const v = validate();
    if (v) {
      setFeedback({ kind: "err", text: v });
      return;
    }
    setBusy("propose");
    setFeedback(null);
    try {
      const wei = BigInt(Math.round(Number(amount) * 1e6)) * (GEN / 1000000n);
      const hash = await contract.createProposal(title.trim(), description.trim(), wei);
      setFeedback({
        kind: "ok",
        text: "Proposal submitted. Waiting for the network to confirm it…",
        tx: hash,
      });
      await contract.waitForReceipt(hash);
      setFeedback({
        kind: "ok",
        text: "Confirmed. Your proposal is on the board — validators score open proposals in batches.",
        tx: hash,
      });
      setTitle("");
      setDescription("");
    } catch (err) {
      setFeedback({ kind: "err", text: describeError(err) });
    } finally {
      setBusy("");
    }
  }

  async function deposit(e: React.FormEvent) {
    e.preventDefault();
    const n = Number(depositAmount);
    if (!Number.isFinite(n) || n <= 0) {
      setFeedback({ kind: "err", text: "Enter a valid GEN amount to deposit." });
      return;
    }
    setBusy("deposit");
    setFeedback(null);
    try {
      const wei = BigInt(Math.round(n * 1e6)) * (GEN / 1000000n);
      const hash = await contract.deposit(wei);
      setFeedback({
        kind: "ok",
        text: "Deposit sent. Waiting for confirmation…",
        tx: hash,
      });
      await contract.waitForReceipt(hash);
      setFeedback({
        kind: "ok",
        text: `Confirmed. ${n} GEN added to the pool.`,
        tx: hash,
      });
    } catch (err) {
      setFeedback({ kind: "err", text: describeError(err) });
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="page page-narrow">
      <header className="page-head">
        <div>
          <h1 className="page-title">Make your ask</h1>
          <p className="page-sub">
            Two fields, one number, one transaction. Validators do the rest.
          </p>
        </div>
      </header>

      {!connected && (
        <div className="notice notice-info">
          Connect a wallet to submit a proposal or fund the pool.
          <button className="notice-retry" onClick={wallet.connect} disabled={wallet.busy}>
            {wallet.busy ? "Connecting…" : "Connect"}
          </button>
        </div>
      )}

      {feedback && (
        <div className={`notice ${feedback.kind === "ok" ? "notice-ok" : "notice-err"}`} role="status">
          <span>{feedback.text}</span>
          {feedback.tx && (
            <a className="notice-tx" href={EXPLORER_TX(feedback.tx)} target="_blank" rel="noreferrer">
              view transaction ↗
            </a>
          )}
        </div>
      )}

      <section className="panel">
        <h2 className="panel-title">Fund the pool</h2>
        <p className="panel-sub">
          Sponsors grow the pot. Every GEN deposited is GEN a builder can ask
          for. The first deposit names you the pool's sponsor.
        </p>
        <form className="form" onSubmit={deposit}>
          <label className="form-field">
            <span className="form-label">Deposit (GEN)</span>
            <input
              className="form-input"
              type="number"
              min="0.001"
              step="any"
              value={depositAmount}
              onChange={(e) => setDepositAmount(e.target.value)}
              disabled={!connected || busy !== ""}
            />
          </label>
          <button className="btn btn-solid" type="submit" disabled={!connected || busy !== ""}>
            {busy === "deposit" ? "Sending…" : "Deposit into pool"}
          </button>
        </form>
      </section>

      <section className="panel">
        <h2 className="panel-title">Submit a proposal</h2>
        <p className="panel-sub">
          Say what gets built, who benefits, and how much GEN you need. The
          minimum ask is 0.01 GEN; the amount is reserved against the pool
          while your proposal is open.
        </p>
        <form className="form" onSubmit={submitProposal}>
          <label className="form-field">
            <span className="form-label">Title</span>
            <input
              className="form-input"
              type="text"
              maxLength={200}
              placeholder="One line: what gets built"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={!connected || busy !== ""}
            />
          </label>
          <label className="form-field">
            <span className="form-label">Description</span>
            <textarea
              className="form-input form-textarea"
              maxLength={2000}
              rows={6}
              placeholder="What you'll deliver, who benefits, and how the community can check the result."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={!connected || busy !== ""}
            />
          </label>
          <label className="form-field">
            <span className="form-label">Requested amount (GEN)</span>
            <input
              className="form-input"
              type="number"
              min={MIN_AMOUNT}
              step="any"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              disabled={!connected || busy !== ""}
            />
          </label>
          <button className="btn btn-solid" type="submit" disabled={!connected || busy !== ""}>
            {busy === "propose" ? "Submitting…" : "Submit proposal"}
          </button>
        </form>
      </section>

      <p className="fineprint">
        Scoring happens when anyone triggers a resolve on a batch of open
        proposals — the AI scores every proposal in the batch on community
        benefit, feasibility, and alignment, and funded proposals are paid
        proportionally. Read the current board on the{" "}
        <Link to="/proposals">proposals page</Link>.
      </p>
    </main>
  );
}
