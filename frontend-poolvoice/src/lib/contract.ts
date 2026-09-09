import { CONTRACT_ADDRESS } from "../config";
import { Pool, Proposal, toBigInt, toInt, toPool, toProposal, fromMapLike } from "./types";

export class PoolVoice {
  constructor(private client: any, private address: string = CONTRACT_ADDRESS) {}

  private async read(functionName: string, args: unknown[] = []): Promise<any> {
    return this.client.readContract({
      address: this.address as `0x${string}`,
      functionName,
      args,
    });
  }

  private async write(
    functionName: string,
    args: unknown[],
    value: bigint = 0n,
  ): Promise<string> {
    const txHash = await this.client.writeContract({
      address: this.address as `0x${string}`,
      functionName,
      args,
      value,
    });
    return txHash as string;
  }

  async waitForReceipt(txHash: string, retries = 50, interval = 3000): Promise<any> {
    return this.client.waitForTransactionReceipt({
      hash: txHash,
      status: "ACCEPTED" as any,
      retries,
      interval,
    });
  }

  // ---- reads ----------------------------------------------------------
  async getPool(): Promise<Pool> {
    return toPool(await this.read("get_pool"));
  }

  async getProposal(id: number): Promise<Proposal | null> {
    const v = await this.read("get_proposal", [id]);
    if (v == null) return null;
    return toProposal(v);
  }

  async listProposals(offset = 0, limit = 50, statusFilter = ""): Promise<Proposal[]> {
    const v = await this.read("list_proposals", [offset, limit, statusFilter]);
    return Array.isArray(v) ? v.map(toProposal) : [];
  }

  // ---- writes ---------------------------------------------------------
  /** Sponsor funds the pool (amount sent as tx value). */
  async deposit(wei: bigint): Promise<string> {
    return this.write("deposit", [], wei);
  }

  /** Submit a funding proposal against the pool. */
  async createProposal(title: string, description: string, amountWei: bigint): Promise<string> {
    return this.write("create_proposal", [title, description, amountWei]);
  }

  /** Proposer cancels their own open proposal. */
  async cancelProposal(id: number): Promise<string> {
    return this.write("cancel_proposal", [id]);
  }

  /** Resolve a batch of proposals from explicit 0-1 scores (string decimals). */
  async resolveProposals(ids: number[], scores: string[], reasoning = ""): Promise<string> {
    return this.write("resolve_proposals", [ids, scores, reasoning]);
  }
}

export { toBigInt, toInt, fromMapLike };
