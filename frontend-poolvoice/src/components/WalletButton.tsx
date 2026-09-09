import { useState } from "react";
import { usePoolVoice } from "../context/PoolVoiceContext";
import { formatGen, shortAddr } from "../config";

export function WalletButton() {
  const { wallet } = usePoolVoice();
  const [menuOpen, setMenuOpen] = useState(false);

  if (!wallet.hasProvider) {
    return (
      <a
        className="btn btn-solid"
        href="https://metamask.io/download/"
        target="_blank"
        rel="noreferrer"
      >
        Install a wallet
      </a>
    );
  }

  if (!wallet.address) {
    return (
      <button className="btn btn-solid" onClick={wallet.connect} disabled={wallet.busy}>
        {wallet.busy ? "Connecting…" : "Connect wallet"}
      </button>
    );
  }

  return (
    <div className="wallet-chip-wrap">
      <button
        className="wallet-chip"
        onClick={() => setMenuOpen((v) => !v)}
        aria-expanded={menuOpen}
      >
        <span className="dot dot-ok" aria-hidden="true" />
        {shortAddr(wallet.address)}
        <span className="wallet-balance">{formatGen(wallet.balance, 2)} GEN</span>
      </button>
      {menuOpen && (
        <div className="wallet-menu" role="menu">
          {wallet.error && <p className="wallet-menu-err">{wallet.error}</p>}
          <button
            className="wallet-menu-item"
            onClick={() => {
              setMenuOpen(false);
              wallet.disconnect();
            }}
          >
            Disconnect
          </button>
        </div>
      )}
    </div>
  );
}
