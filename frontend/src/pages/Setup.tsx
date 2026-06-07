import { useState } from "react";
import { api } from "../api";

/**
 * First-run setup wizard.
 *
 * Flow: a checklist of which integrations to configure → one page per ticked
 * integration → a finish page. On save the backend writes .env, locks itself,
 * and starts the first sync. After that the .env can only be changed over SSH.
 */

type Vals = Record<string, string>;

interface Integration {
  key: string;
  label: string;
  desc: string;
  required?: boolean;
}

const INTEGRATIONS: Integration[] = [
  { key: "tmdb", label: "TMDB", desc: "Show & movie data (required)", required: true },
  { key: "jellyfin", label: "Jellyfin", desc: "Sync your watch history" },
  { key: "anthropic", label: "AI picks (Claude)", desc: "AI-personalised recommendations" },
  { key: "trakt", label: "Trakt", desc: "Watch history & watchlist" },
  { key: "plex", label: "Plex", desc: "Sync your watch history" },
  { key: "overseerr", label: "Overseerr / Jellyseerr", desc: "Request button + availability" },
  { key: "ha", label: "Home Assistant", desc: "New-episode notifications" },
  { key: "tastedive", label: "TasteDive", desc: "“More like this” similar titles" },
];

// Plain field lists for the simple integrations. TMDB and Jellyfin have custom
// pages (test button / account picker) handled separately.
const FIELDS: Record<string, { env: string; label: string; placeholder?: string }[]> = {
  anthropic: [{ env: "ANTHROPIC_API_KEY", label: "Anthropic API key", placeholder: "sk-ant-…" }],
  trakt: [
    { env: "TRAKT_CLIENT_ID", label: "Trakt Client ID" },
    { env: "TRAKT_CLIENT_SECRET", label: "Trakt Client Secret" },
    { env: "TRAKT_ACCESS_TOKEN", label: "Trakt Access Token" },
  ],
  plex: [
    { env: "PLEX_URL", label: "Plex URL", placeholder: "http://192.168.1.x:32400" },
    { env: "PLEX_TOKEN", label: "Plex Token" },
  ],
  overseerr: [
    { env: "OVERSEERR_URL", label: "Overseerr / Jellyseerr URL", placeholder: "http://192.168.1.x:5055" },
    { env: "OVERSEERR_API_KEY", label: "API Key" },
  ],
  ha: [
    { env: "HA_URL", label: "Home Assistant URL", placeholder: "http://192.168.1.x:8123" },
    { env: "HA_TOKEN", label: "Long-Lived Access Token" },
    { env: "HA_NOTIFICATION_SERVICE", label: "Notification service", placeholder: "notify.notify" },
  ],
  tastedive: [{ env: "TASTEDIVE_API_KEY", label: "TasteDive API key" }],
};

const JELLYFIN_ENV = ["JELLYFIN_URL", "JELLYFIN_API_KEY", "JELLYFIN_USER_ID"];

const EMOJIS = ["🍿", "🎬", "📺", "🦸", "👽", "🧙", "🐱", "🌟", "🎮", "👤", "👩", "👨", "🧒"];

const card: React.CSSProperties = {
  background: "var(--surface)", border: "1px solid var(--border)",
  borderRadius: 14, padding: 28, width: "100%", maxWidth: 560,
  boxShadow: "0 8px 40px rgba(0,0,0,0.4)",
};
const inputStyle: React.CSSProperties = {
  width: "100%", padding: "10px 12px", borderRadius: 8,
  border: "1px solid var(--border)", background: "var(--surface2)",
  color: "var(--text)", fontSize: 14, outline: "none", boxSizing: "border-box",
};
const labelStyle: React.CSSProperties = {
  fontSize: 12, color: "var(--muted)", fontWeight: 600,
  display: "block", marginBottom: 5, marginTop: 14,
};
const primaryBtn: React.CSSProperties = {
  padding: "10px 18px", borderRadius: 8, border: "none",
  background: "var(--accent)", color: "#fff", fontWeight: 600,
  cursor: "pointer", fontSize: 14,
};
const ghostBtn: React.CSSProperties = {
  padding: "10px 16px", borderRadius: 8, border: "1px solid var(--border)",
  background: "transparent", color: "var(--muted)", cursor: "pointer", fontSize: 14,
};

function Field({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <input style={inputStyle} value={value} placeholder={placeholder}
        onChange={e => onChange(e.target.value)} />
    </div>
  );
}

export default function Setup({ onDone }: { onDone: () => void }) {
  const [selected, setSelected] = useState<Record<string, boolean>>({ tmdb: true });
  const [step, setStep] = useState(0);
  const [vals, setVals] = useState<Vals>({});
  const set = (k: string, v: string) => setVals(p => ({ ...p, [k]: v }));

  const [profileName, setProfileName] = useState("Me");
  const [profileEmoji, setProfileEmoji] = useState("🍿");

  const [tmdbState, setTmdbState] = useState<"idle" | "testing" | "ok" | "fail">("idle");
  const [jfState, setJfState] = useState<"idle" | "testing" | "ok" | "fail">("idle");
  const [jfUsers, setJfUsers] = useState<{ id: string; name: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pages = checklist, then one per ticked integration, then profile, then finish.
  const pages: string[] = [
    "select",
    ...INTEGRATIONS.filter(i => selected[i.key]).map(i => i.key),
    "profile",
    "finish",
  ];
  const page = pages[Math.min(step, pages.length - 1)];

  function toggle(key: string) {
    if (key === "tmdb") return; // required
    setSelected(p => ({ ...p, [key]: !p[key] }));
  }

  async function testTmdb() {
    setTmdbState("testing");
    try {
      const r = await api.testTmdb(vals.TMDB_API_KEY || "");
      setTmdbState(r.ok ? "ok" : "fail");
    } catch { setTmdbState("fail"); }
  }

  async function testJellyfin() {
    setJfState("testing"); setJfUsers([]);
    try {
      const r = await api.testJellyfin(vals.JELLYFIN_URL || "", vals.JELLYFIN_API_KEY || "");
      if (r.ok) { setJfState("ok"); setJfUsers(r.users); } else setJfState("fail");
    } catch { setJfState("fail"); }
  }

  function buildPayload(): Vals {
    const keys = new Set<string>(["TMDB_API_KEY"]);
    for (const integ of INTEGRATIONS) {
      if (integ.key === "tmdb" || !selected[integ.key]) continue;
      if (integ.key === "jellyfin") JELLYFIN_ENV.forEach(k => keys.add(k));
      else (FIELDS[integ.key] || []).forEach(f => keys.add(f.env));
    }
    const payload: Vals = {};
    for (const k of keys) if (vals[k] && vals[k].trim()) payload[k] = vals[k].trim();
    return payload;
  }

  async function finish() {
    setSaving(true); setError(null);
    try {
      await api.saveSetup(buildPayload(), { name: profileName.trim() || "Me", emoji: profileEmoji });
      onDone();
    } catch (e: any) {
      setError(e?.message || "Save failed");
      setSaving(false);
    }
  }

  // Next is blocked only on the TMDB page until a key is entered.
  const canNext = page !== "tmdb" || !!(vals.TMDB_API_KEY && vals.TMDB_API_KEY.trim());

  return (
    <div style={{
      minHeight: "100vh", display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", padding: 20, gap: 18,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 26 }}>📺</span>
        <span style={{ fontWeight: 700, fontSize: 20, color: "var(--text)" }}>ShowRec setup</span>
      </div>
      <div style={{ color: "var(--muted)", fontSize: 12 }}>
        Step {step + 1} of {pages.length}
      </div>

      <div style={card}>
        {/* ── Checklist ── */}
        {page === "select" && (
          <>
            <h2 style={{ margin: "0 0 6px", color: "var(--text)", fontSize: 18 }}>What do you want to set up?</h2>
            <p style={{ color: "var(--muted)", fontSize: 13, margin: "0 0 12px" }}>
              Tick the integrations you use. You'll only be asked to fill in the ones you pick.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {INTEGRATIONS.map(i => (
                <label key={i.key} style={{
                  display: "flex", alignItems: "center", gap: 12, padding: "10px 12px",
                  borderRadius: 8, border: "1px solid var(--border)",
                  background: selected[i.key] ? "rgba(124,106,247,0.12)" : "var(--surface2)",
                  cursor: i.required ? "default" : "pointer", opacity: i.required ? 0.9 : 1,
                }}>
                  <input type="checkbox" checked={!!selected[i.key]} disabled={i.required}
                    onChange={() => toggle(i.key)} style={{ width: 16, height: 16 }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ color: "var(--text)", fontSize: 14, fontWeight: 600 }}>{i.label}</div>
                    <div style={{ color: "var(--muted)", fontSize: 12 }}>{i.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </>
        )}

        {/* ── TMDB ── */}
        {page === "tmdb" && (
          <>
            <h2 style={{ margin: "0 0 6px", color: "var(--text)", fontSize: 18 }}>TMDB API key (required)</h2>
            <p style={{ color: "var(--muted)", fontSize: 13, margin: 0 }}>
              Free v3 key from themoviedb.org → Settings → API.
            </p>
            <Field label="TMDB_API_KEY" value={vals.TMDB_API_KEY || ""}
              onChange={v => { set("TMDB_API_KEY", v); setTmdbState("idle"); }}
              placeholder="32-character key" />
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
              <button style={ghostBtn} onClick={testTmdb} disabled={!vals.TMDB_API_KEY || tmdbState === "testing"}>
                {tmdbState === "testing" ? "Testing…" : "Test key"}
              </button>
              {tmdbState === "ok" && <span style={{ color: "var(--accent2)", fontSize: 13 }}>✓ Valid</span>}
              {tmdbState === "fail" && <span style={{ color: "#e06c6c", fontSize: 13 }}>✗ Rejected</span>}
            </div>
          </>
        )}

        {/* ── Jellyfin ── */}
        {page === "jellyfin" && (
          <>
            <h2 style={{ margin: "0 0 6px", color: "var(--text)", fontSize: 18 }}>Jellyfin</h2>
            <p style={{ color: "var(--muted)", fontSize: 13, margin: 0 }}>
              Use the server's LAN IP or public URL. Get an API key from Dashboard → API Keys.
            </p>
            <Field label="JELLYFIN_URL" value={vals.JELLYFIN_URL || ""}
              onChange={v => { set("JELLYFIN_URL", v); setJfState("idle"); }}
              placeholder="https://jellyfin.example.com" />
            <Field label="JELLYFIN_API_KEY" value={vals.JELLYFIN_API_KEY || ""}
              onChange={v => { set("JELLYFIN_API_KEY", v); setJfState("idle"); }} />
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
              <button style={ghostBtn} onClick={testJellyfin}
                disabled={!vals.JELLYFIN_URL || !vals.JELLYFIN_API_KEY || jfState === "testing"}>
                {jfState === "testing" ? "Connecting…" : "Connect & list accounts"}
              </button>
              {jfState === "fail" && <span style={{ color: "#e06c6c", fontSize: 13 }}>✗ Couldn't connect</span>}
            </div>
            {jfState === "ok" && (
              <>
                <label style={labelStyle}>Which account is yours?</label>
                <select style={inputStyle} value={vals.JELLYFIN_USER_ID || ""}
                  onChange={e => set("JELLYFIN_USER_ID", e.target.value)}>
                  <option value="">Select account…</option>
                  {jfUsers.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
                </select>
              </>
            )}
          </>
        )}

        {/* ── Generic integration pages ── */}
        {FIELDS[page] && (
          <>
            <h2 style={{ margin: "0 0 6px", color: "var(--text)", fontSize: 18 }}>
              {INTEGRATIONS.find(i => i.key === page)?.label}
            </h2>
            <p style={{ color: "var(--muted)", fontSize: 13, margin: 0 }}>
              {INTEGRATIONS.find(i => i.key === page)?.desc}
            </p>
            {FIELDS[page].map(f => (
              <Field key={f.env} label={f.label} value={vals[f.env] || ""}
                onChange={v => set(f.env, v)} placeholder={f.placeholder} />
            ))}
          </>
        )}

        {/* ── Profile ── */}
        {page === "profile" && (
          <>
            <h2 style={{ margin: "0 0 6px", color: "var(--text)", fontSize: 18 }}>Create your profile</h2>
            <p style={{ color: "var(--muted)", fontSize: 13, margin: 0 }}>
              This is your personal profile — it holds your watch history,
              watchlist, and recommendations.
              {selected.jellyfin && vals.JELLYFIN_USER_ID
                ? " It'll be linked to the Jellyfin account you picked."
                : ""}
            </p>
            <label style={labelStyle}>Profile name</label>
            <input style={inputStyle} value={profileName} placeholder="Me" autoFocus
              onChange={e => setProfileName(e.target.value)} />
            <label style={labelStyle}>Pick an emoji</label>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {EMOJIS.map(e => (
                <button key={e} onClick={() => setProfileEmoji(e)} style={{
                  fontSize: 18, width: 34, height: 34, borderRadius: 8, cursor: "pointer",
                  border: profileEmoji === e ? "2px solid var(--accent)" : "1px solid var(--border)",
                  background: "var(--surface2)",
                }}>{e}</button>
              ))}
            </div>
            {selected.jellyfin && !vals.JELLYFIN_USER_ID && (
              <p style={{ color: "#e0b86c", fontSize: 12, marginTop: 12 }}>
                ⚠ You enabled Jellyfin but didn't pick an account on the Jellyfin
                step — go Back if you want this profile linked, or continue for a
                standalone profile.
              </p>
            )}
          </>
        )}

        {/* ── Finish ── */}
        {page === "finish" && (
          <>
            <h2 style={{ margin: "0 0 6px", color: "var(--text)", fontSize: 18 }}>Ready to finish</h2>
            <p style={{ color: "var(--muted)", fontSize: 13 }}>
              These keys will be written to <code>.env</code> and the first sync will start.
            </p>
            <div style={{
              background: "var(--surface2)", border: "1px solid var(--border)",
              borderRadius: 8, padding: "12px 14px", margin: "10px 0",
            }}>
              <div style={{ color: "var(--text)", fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                ⚠ One-time setup
              </div>
              <div style={{ color: "var(--muted)", fontSize: 13, lineHeight: 1.5 }}>
                After you finish, this wizard locks itself. <b>Going forward, the
                <code> .env</code> can only be changed over SSH.</b> To re-run setup later,
                SSH into the Pi, clear <code>~/show-rec/.env</code> (e.g.
                <code> mv .env .env.old</code>), and restart the service.
              </div>
            </div>
            <ul style={{ color: "var(--text)", fontSize: 13, lineHeight: 1.8, marginTop: 4 }}>
              <li>Profile: {profileEmoji} {profileName.trim() || "Me"}
                {selected.jellyfin && vals.JELLYFIN_USER_ID ? " (Jellyfin-linked)" : ""}</li>
              {INTEGRATIONS.filter(i => selected[i.key]).map(i => {
                const ok = i.key === "tmdb" ? !!vals.TMDB_API_KEY
                  : i.key === "jellyfin" ? !!vals.JELLYFIN_USER_ID
                  : (FIELDS[i.key] || []).some(f => vals[f.env]);
                return <li key={i.key}>{i.label}: {ok ? "✓ configured" : "— left blank"}</li>;
              })}
            </ul>
            {error && <p style={{ color: "#e06c6c", fontSize: 13 }}>{error}</p>}
          </>
        )}

        {/* ── Nav ── */}
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 22 }}>
          <button style={ghostBtn} onClick={() => setStep(s => Math.max(0, s - 1))}
            disabled={step === 0 || saving}>Back</button>
          {page !== "finish" ? (
            <button style={primaryBtn} onClick={() => setStep(s => s + 1)} disabled={!canNext}>
              {page === "tmdb" && !canNext ? "Enter a key to continue" : "Next"}
            </button>
          ) : (
            <button style={primaryBtn} onClick={finish} disabled={saving || !vals.TMDB_API_KEY}>
              {saving ? "Saving…" : "Finish & start"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
