import { useState } from "react";
import { Routes, Route, NavLink } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Upcoming from "./pages/Upcoming";
import Watching from "./pages/Watching";
import Watchlist from "./pages/Watchlist";
import Search from "./pages/Search";
import StatusBar from "./components/StatusBar";
import HiddenTitles from "./components/HiddenTitles";
import ProfileSwitcher from "./components/ProfileSwitcher";

const navStyle = ({ isActive }: { isActive: boolean }): React.CSSProperties => ({
  padding: "8px 18px",
  borderRadius: 8,
  fontWeight: isActive ? 600 : 400,
  color: isActive ? "var(--text)" : "var(--muted)",
  background: isActive ? "var(--surface2)" : "transparent",
  fontSize: 14,
  transition: "all 0.15s",
});

export default function App() {
  const [showHidden, setShowHidden] = useState(false);
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <header className="app-header" style={{
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        padding: "0 24px",
        display: "flex",
        alignItems: "center",
        gap: 32,
        height: 60,
        position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20 }}>📺</span>
          <span style={{ fontWeight: 700, fontSize: 16, color: "var(--text)" }}>ShowRec</span>
        </div>

        <nav className="app-nav" style={{ display: "flex", gap: 4 }}>
          <NavLink to="/" end style={navStyle}>Recommendations</NavLink>
          <NavLink to="/watching" style={navStyle}>Watching</NavLink>
          <NavLink to="/watchlist" style={navStyle}>Watchlist</NavLink>
          <NavLink to="/upcoming" style={navStyle}>Upcoming</NavLink>
          <NavLink to="/search" style={navStyle}>🔍 Search</NavLink>
        </nav>

        <div className="app-header-right" style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          <span className="app-statusbar"><StatusBar /></span>
          <ProfileSwitcher />
          <button
            onClick={() => setShowHidden(true)}
            title="Hidden titles"
            style={{
              background: "var(--surface2)", border: "1px solid var(--border)",
              color: "var(--muted)", borderRadius: 8, padding: "6px 12px",
              cursor: "pointer", fontSize: 13, display: "flex", alignItems: "center", gap: 6,
              whiteSpace: "nowrap",
            }}
          >🙈 Hidden</button>
        </div>
      </header>

      {showHidden && <HiddenTitles onClose={() => setShowHidden(false)} />}

      {/* Main */}
      <main className="main-content" style={{ flex: 1, padding: "28px 24px", maxWidth: 1400, width: "100%", margin: "0 auto" }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/watching" element={<Watching />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/upcoming" element={<Upcoming />} />
          <Route path="/search" element={<Search />} />
        </Routes>
      </main>
    </div>
  );
}
