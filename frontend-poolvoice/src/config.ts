export const NETWORK: "localnet" | "studionet" =
  (import.meta.env.VITE_NETWORK as "localnet" | "studionet") || "studionet";

export const RPC_URL = (import.meta.env.VITE_RPC_URL as string) || "";

/** Deployed PoolVoice contract on GenLayer StudioNet. */
export const CONTRACT_ADDRESS =
  (import.meta.env.VITE_CONTRACT_ADDRESS as string) ||
  "0xff32C5E21295CdEa8C982E0aC9e358eF1FC526a8";

export const STUDIONET_CHAIN_ID = 777;
export const STUDIONET_CHAIN_ID_HEX = "0x309";

export const EXPLORER_TX = (hash: string) =>
  `https://explorer-studio.genlayer.com/tx/${hash}`;
export const EXPLORER_ADDR = (address: string) =>
  `https://explorer-studio.genlayer.com/address/${address}`;

export const GEN = 10n ** 18n;

export function formatGen(wei: bigint, maxDecimals = 2): string {
  const whole = wei / GEN;
  const frac = (wei % GEN) / (GEN / 10n ** BigInt(maxDecimals));
  if (frac === 0n) return whole.toString();
  const fracStr = frac.toString().padStart(maxDecimals, "0").replace(/0+$/, "");
  return `${whole}.${fracStr}`;
}

export function shortAddr(a: string): string {
  if (!a || a.length < 12) return a;
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}
