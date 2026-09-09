import { createContext, useContext, useMemo, type ReactNode } from "react";
import { createPoolVoiceClient } from "../lib/client";
import { PoolVoice } from "../lib/contract";
import { useWallet } from "../hooks/useWallet";

interface PoolVoiceContextValue {
  wallet: ReturnType<typeof useWallet>;
  contract: PoolVoice;
}

const PoolVoiceContext = createContext<PoolVoiceContextValue | null>(null);

export function PoolVoiceProvider({ children }: { children: ReactNode }) {
  const wallet = useWallet();
  const contract = useMemo(() => {
    const client = createPoolVoiceClient(wallet.address);
    return new PoolVoice(client);
  }, [wallet.address]);

  return (
    <PoolVoiceContext.Provider value={{ wallet, contract }}>
      {children}
    </PoolVoiceContext.Provider>
  );
}

export function usePoolVoice(): PoolVoiceContextValue {
  const ctx = useContext(PoolVoiceContext);
  if (!ctx) {
    throw new Error("usePoolVoice must be used within a PoolVoiceProvider");
  }
  return ctx;
}
