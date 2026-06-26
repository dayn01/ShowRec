import { useState } from "react";
import { Routes, Route, NavLink, useLocation } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Upcoming from "./pages/Upcoming";
import Watching from "./pages/Watching";
import Watched from "./pages/Watched";
import Watchlist from "./pages/Watchlist";
import Stats from "./pages/Stats";
import Search from "./pages/Search";
import StatusBar from "./components/StatusBar";
import HiddenTitles from "./components/HiddenTitles";
import ProfileSwitcher from "./components/ProfileSwitcher";
import { useIsMobile } from "./useIsMobile";

const NAV = [
  { to: "/", label: "Recommendations", end: true },
  { to: "/watching", label: "Watching" },
  { to: "/watched", label: "Watched" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/upcoming", label: "Upcoming" },
  { to: "/stats", label: "Stats" },
  { to: "/search", label: "🔍 Search" },
];

const navStyle = ({ isActive }: { isActive: boolean }): React.CSSProperties => ({
  padding: "8px 18px",
  borderRadius: 8,
  fontWeight: isActive ? 600 : 400,
  color: isActive ? "var(--text)" : "var(--muted)",
  background: isActive ? "var(--surface2)" : "transparent",
  fontSize: 14,
  transition: "all 0.15s",
});

function MobileNav({ onOpenHidden }: { onOpenHidden: () => void }) {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const current = NAV.find(n => (n.end ? loc.pathname === n.to : loc.pathname.startsWith(n.to))) ?? NAV[0];

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", gap: 8,
          background: "var(--surface2)", border: "1px solid var(--border)",
          borderRadius: 8, padding: "7px 12px", cursor: "pointer", color: "var(--text)",
          fontSize: 14, fontWeight: 600,
        }}
      >
        <span style={{ fontSize: 16 }}>☰</span>
        <span style={{ whiteSpace: "nowrap" }}>{current.label}</span>
      </button>

      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 90 }} />
          <div style={{
            position: "absolute", top: "calc(100% + 8px)", left: 0, zIndex: 100,
            background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12,
            minWidth: 200, boxShadow: "0 8px 32px rgba(0,0,0,0.5)", overflow: "hidden", padding: 6,
          }}>
            {NAV.map(n => (
              <NavLink key={n.to} to={n.to} end={n.end} onClick={() => setOpen(false)}
                style={({ isActive }) => ({
                  display: "block", padding: "11px 14px", borderRadius: 8, fontSize: 15,
                  color: isActive ? "var(--accent2)" : "var(--text)",
                  background: isActive ? "rgba(124,106,247,0.12)" : "transparent",
                  fontWeight: isActive ? 600 : 400,
                })}
              >{n.label}</NavLink>
            ))}
            <div style={{ borderTop: "1px solid var(--border)", marginTop: 4, paddingTop: 4 }}>
              <button onClick={() => { setOpen(false); onOpenHidden(); }}
                style={{
                  display: "block", width: "100%", textAlign: "left", padding: "11px 14px",
                  borderRadius: 8, border: "none", background: "transparent",
                  color: "var(--muted)", cursor: "pointer", fontSize: 15,
                }}
              >🙈 Hidden titles</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function App() {
  const [showHidden, setShowHidden] = useState(false);
  const isMobile = useIsMobile();

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <header className="app-header" style={{
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        // Pad past the notch/status bar (iOS safe area); grows the header to suit.
        padding: "env(safe-area-inset-top, 0px) 24px 0",
        display: "flex",
        alignItems: "center",
        gap: isMobile ? 12 : 32,
        height: "calc(60px + env(safe-area-inset-top, 0px))",
        position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20 }}>📺</span>
          {!isMobile && <span style={{ fontWeight: 700, fontSize: 16, color: "var(--text)" }}>ShowRec</span>}
        </div>

        {isMobile ? (
          <MobileNav onOpenHidden={() => setShowHidden(true)} />
        ) : (
          <nav className="app-nav" style={{ display: "flex", gap: 4 }}>
            {NAV.map(n => (
              <NavLink key={n.to} to={n.to} end={n.end} style={navStyle}>{n.label}</NavLink>
            ))}
          </nav>
        )}

        <div className="app-header-right" style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          {!isMobile && <span className="app-statusbar"><StatusBar /></span>}
          <ProfileSwitcher />
          {!isMobile && (
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
          )}
        </div>
      </header>

      {showHidden && <HiddenTitles onClose={() => setShowHidden(false)} />}

      {/* Main */}
      <main className="main-content" style={{ flex: 1, padding: "28px 24px", maxWidth: 1400, width: "100%", margin: "0 auto" }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/watching" element={<Watching />} />
          <Route path="/watched" element={<Watched />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/upcoming" element={<Upcoming />} />
          <Route path="/stats" element={<Stats />} />
          <Route path="/search" element={<Search />} />
        </Routes>
      </main>
    </div>
  );
}
