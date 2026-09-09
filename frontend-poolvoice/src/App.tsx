import { Link, NavLink, Route, Routes } from "react-router-dom";
import { PoolVoiceProvider } from "./context/PoolVoiceContext";
import { WalletButton } from "./components/WalletButton";
import { Home } from "./pages/Home";
import { Proposals } from "./pages/Proposals";
import { Submit } from "./pages/Submit";
import { CONTRACT_ADDRESS, EXPLORER_ADDR, shortAddr } from "./config";

function Header() {
  return (
    <header className="site-head">
      <Link to="/" className="brand">
        <span className="brand-mark" aria-hidden="true">
          ◉
        </span>
        PoolVoice
      </Link>
      <nav className="site-nav" aria-label="Main">
        <NavLink to="/" end className={({ isActive }) => (isActive ? "on" : "")}>
          Home
        </NavLink>
        <NavLink to="/proposals" className={({ isActive }) => (isActive ? "on" : "")}>
          Proposals
        </NavLink>
        <NavLink to="/submit" className={({ isActive }) => (isActive ? "on" : "")}>
          Submit
        </NavLink>
      </nav>
      <WalletButton />
    </header>
  );
}

function Footer() {
  return (
    <footer className="site-foot">
      <div className="foot-inner">
        <p>
          PoolVoice is an AI-governed community fund on GenLayer. Contract{" "}
          <a href={EXPLORER_ADDR(CONTRACT_ADDRESS)} target="_blank" rel="noreferrer">
            {shortAddr(CONTRACT_ADDRESS)}
          </a>{" "}
          on StudioNet.
        </p>
        <p className="foot-fine">
          Demo network. GEN here has no value. The mechanics are the point.
        </p>
      </div>
    </footer>
  );
}

function NotFound() {
  return (
    <main className="page page-narrow">
      <div className="empty">
        <p className="empty-title">Page not found.</p>
        <p>
          <Link to="/">Back to the pool</Link>
        </p>
      </div>
    </main>
  );
}

export default function App() {
  return (
    <PoolVoiceProvider>
      <div className="shell">
        <Header />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/proposals" element={<Proposals />} />
          <Route path="/submit" element={<Submit />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
        <Footer />
      </div>
    </PoolVoiceProvider>
  );
}
