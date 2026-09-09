/** Turn any wallet / RPC / contract error into a sentence a human can act on. */
export function describeError(e: unknown): string {
  if (e == null) return "Something went wrong.";
  const anyE = e as any;

  const raw =
    anyE?.shortMessage ??
    anyE?.message ??
    (typeof e === "string" ? e : undefined) ??
    String(e);

  const lower = String(raw).toLowerCase();

  if (lower.includes("user rejected") || lower.includes("user denied"))
    return "You rejected the request in your wallet.";
  if (lower.includes("chain") && lower.includes("add"))
    return "Your wallet needs the GenLayer StudioNet network added.";
  if (lower.includes("unrecognized chain") || lower.includes("4902"))
    return "Add the GenLayer StudioNet network to your wallet, then try again.";
  if (lower.includes("insufficient funds") || lower.includes("exceeds") || lower.includes("balance"))
    return "Not enough GEN in the connected wallet for this action.";
  if (lower.includes("failed to fetch") || lower.includes("network") || lower.includes("connection"))
    return "Could not reach GenLayer StudioNet. The network may be busy, try again in a moment.";
  if (lower.includes("timeout") || lower.includes("timed out"))
    return "The transaction took too long to confirm. Check the explorer before retrying.";
  if (lower.includes("title")) return "Check the title: 1-200 characters.";
  if (lower.includes("description")) return "Check the description: 1-2000 characters.";
  if (lower.includes("amount must be")) return "The requested amount must be at least 0.01 GEN.";
  if (lower.includes("amount exceeds pool")) return "The request is larger than the pool balance.";
  if (lower.includes("pool is empty")) return "The pool is empty. A sponsor needs to fund it first.";
  if (lower.includes("not open")) return "That proposal is no longer open.";
  if (lower.includes("only proposer")) return "Only the proposer can cancel this proposal.";
  if (lower.includes("length mismatch")) return "Proposal IDs and scores must line up one-to-one.";
  if (lower.includes("must send gen")) return "Attach a GEN amount to the deposit.";

  return raw.length > 220 ? `${raw.slice(0, 220)}…` : raw;
}
