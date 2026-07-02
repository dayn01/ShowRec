import { useState, useEffect } from "react";
import { api, getProfileId, setProfileId, Profile } from "../api";

const EMOJIS = ["🍿", "🎬", "📺", "🦸", "👽", "🧙", "🐱", "🌟", "🎮", "👤", "👩", "👨", "🧒"];

async function switchTo(id: number) {
  setProfileId(id);
  // Clear per-device watch caches so the new profile re-seeds cleanly
  ["wc_shows", "wc_episodes", "wc_progress", "wc_dismissed", "wc_watchlist"].forEach(k => localStorage.removeItem(k));
  // Auto-refresh this profile if its data is stale (throttled — skips if fresh).
  // Await the quick "started/fresh" response so the request isn't cancelled by reload.
  try { await api.refreshProfile(id, false); } catch {}
  window.location.reload();
}

const KEEP = "__keep__";  // sentinel: leave the existing Plex link unchanged

export default function ProfileSwitcher() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [jellyfinUsers, setJellyfinUsers] = useState<{ id: string; name: string }[]>([]);
  const [plexUsers, setPlexUsers] = useState<{ id: string; title: string; owner: boolean }[]>([]);

  // shared add/edit form
  const [name, setName] = useState("");
  const [emoji, setEmoji] = useState("🍿");
  const [jfUser, setJfUser] = useState<string>("");
  const [plexUser, setPlexUser] = useState<string>("");

  const activeId = getProfileId();
  const active = profiles.find(p => p.id === activeId) ?? profiles[0];
  const formOpen = adding || editingId !== null;

  useEffect(() => {
    api.getProfiles().then(d => setProfiles(d.profiles)).catch(() => {});
  }, []);

  function loadUserLists() {
    fetch("/api/upcoming/jellyfin-users")
      .then(r => r.ok ? r.json() : null)
      .then(d => setJellyfinUsers(d?.users ?? []))
      .catch(() => {});
    api.getPlexUsers().then(d => setPlexUsers(d.users)).catch(() => {});
  }

  function openAdd() {
    setEditingId(null);
    setName(""); setEmoji("🍿"); setJfUser(""); setPlexUser("");
    setAdding(true);
    loadUserLists();
  }

  function openEdit(p: Profile) {
    setAdding(false);
    setEditingId(p.id);
    setName(p.name); setEmoji(p.emoji || "👤");
    setJfUser(p.jellyfin_user_id || "");
    setPlexUser(p.plex_linked ? KEEP : "");  // can't know which Plex user from token alone
    loadUserLists();
  }

  function closeForm() {
    setAdding(false); setEditingId(null);
  }

  async function save() {
    if (!name.trim()) return;
    if (editingId !== null) {
      const body: any = { name: name.trim(), emoji, jellyfin_user_id: jfUser || "" };
      if (plexUser !== KEEP) body.plex_user = plexUser || "";  // only change Plex if touched
      const updated = await api.updateProfile(editingId, body);
      setProfiles(prev => prev.map(p => p.id === updated.id ? updated : p));
      closeForm();
    } else {
      const p = await api.createProfile({
        name: name.trim(), emoji,
        jellyfin_user_id: jfUser || null,
        plex_user: plexUser || null,
      });
      closeForm();
      switchTo(p.id);  // jump straight into the new profile
    }
  }

  async function remove(id: number) {
    if (!confirm("Delete this profile and all its data?")) return;
    try {
      await api.deleteProfile(id);
      setProfiles(prev => prev.filter(p => p.id !== id));
      if (id === activeId && profiles.length) switchTo(profiles.find(p => p.id !== id)!.id);
    } catch {}
  }

  const [refreshing, setRefreshing] = useState<number | null>(null);
  async function refresh(id: number) {
    setRefreshing(id);
    try { await api.refreshProfile(id); } catch {}
    // Give the background sync a moment, then clear the indicator
    setTimeout(() => setRefreshing(r => (r === id ? null : r)), 4000);
  }

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(o => !o)}
        title="Switch profile"
        style={{
          display: "flex", alignItems: "center", gap: 8,
          background: "var(--surface2)", border: "1px solid var(--border)",
          borderRadius: 20, padding: "5px 12px 5px 8px", cursor: "pointer", color: "var(--text)",
        }}
      >
        <span style={{ fontSize: 18 }}>{active?.emoji ?? "👤"}</span>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{active?.name ?? "Profile"}</span>
        <span style={{ color: "var(--muted)", fontSize: 11 }}>▼</span>
      </button>

      {open && (
        <>
          <div onClick={() => { setOpen(false); closeForm(); }} style={{ position: "fixed", inset: 0, zIndex: 90 }} />
          <div style={{
            position: "absolute", top: "calc(100% + 8px)", right: 0, zIndex: 100,
            background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12,
            width: 280, boxShadow: "0 8px 32px rgba(0,0,0,0.5)", overflow: "hidden",
          }}>
            <div style={{ padding: "10px 14px", fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 600 }}>
              Profiles
            </div>

            {profiles.map(p => (
              <div key={p.id} style={{
                display: "flex", alignItems: "center", gap: 10, padding: "8px 14px",
                background: p.id === activeId ? "rgba(124,106,247,0.12)" : "transparent",
                cursor: "pointer",
              }}
                onClick={() => p.id !== activeId && switchTo(p.id)}
              >
                <span style={{ fontSize: 20 }}>{p.emoji}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{p.name}</div>
                  <div style={{ fontSize: 11, color: "var(--muted)" }}>
                    {[p.jellyfin_user_id && "Jellyfin", p.plex_linked && "Plex"].filter(Boolean).join(" + ") || "Standalone"}
                  </div>
                </div>
                {p.id === activeId && <span style={{ color: "var(--accent2)", fontSize: 13 }}>✓</span>}
                <button onClick={e => { e.stopPropagation(); refresh(p.id); }} title="Re-sync this profile's account"
                  style={{ background: "none", border: "none", color: refreshing === p.id ? "var(--accent2)" : "var(--muted)", cursor: "pointer", fontSize: 13 }}>
                  {refreshing === p.id ? "⏳" : "↻"}
                </button>
                <button onClick={e => { e.stopPropagation(); openEdit(p); }} title="Edit"
                  style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 13 }}>✎</button>
                {profiles.length > 1 && (
                  <button onClick={e => { e.stopPropagation(); remove(p.id); }} title="Delete"
                    style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 14 }}>🗑</button>
                )}
              </div>
            ))}

            {/* Add / edit profile */}
            <div style={{ borderTop: "1px solid var(--border)", padding: 10 }}>
              {!formOpen ? (
                <button onClick={openAdd} style={{
                  width: "100%", padding: "9px", borderRadius: 8, border: "1px dashed var(--border)",
                  background: "transparent", color: "var(--accent2)", cursor: "pointer", fontSize: 13, fontWeight: 600,
                }}>+ Add profile</button>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {EMOJIS.map(e => (
                      <button key={e} onClick={() => setEmoji(e)} style={{
                        fontSize: 18, width: 30, height: 30, borderRadius: 8, cursor: "pointer",
                        border: emoji === e ? "2px solid var(--accent)" : "1px solid var(--border)",
                        background: "var(--surface2)",
                      }}>{e}</button>
                    ))}
                  </div>
                  <input
                    value={name} onChange={e => setName(e.target.value)} placeholder="Profile name"
                    autoFocus
                    style={{ padding: "9px 12px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface2)", color: "var(--text)", fontSize: 14, outline: "none" }}
                  />
                  {jellyfinUsers.length > 0 && (
                    <select
                      value={jfUser} onChange={e => setJfUser(e.target.value)}
                      style={{ padding: "9px 12px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface2)", color: "var(--text)", fontSize: 13 }}
                    >
                      <option value="">No Jellyfin user</option>
                      {jellyfinUsers.map(u => (
                        <option key={u.id} value={u.id}>Jellyfin: {u.name}</option>
                      ))}
                    </select>
                  )}
                  {plexUsers.length > 0 && (
                    <select
                      value={plexUser} onChange={e => setPlexUser(e.target.value)}
                      style={{ padding: "9px 12px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface2)", color: "var(--text)", fontSize: 13 }}
                    >
                      {editingId !== null && <option value={KEEP}>Keep current Plex link</option>}
                      <option value="">No Plex user</option>
                      {plexUsers.map(u => (
                        <option key={u.id} value={u.id}>Plex: {u.title}{u.owner ? " (owner)" : ""}</option>
                      ))}
                    </select>
                  )}
                  {jellyfinUsers.length === 0 && plexUsers.length === 0 && (
                    <div style={{ fontSize: 12, color: "var(--muted)", padding: "2px 2px" }}>
                      Standalone profile (no linked accounts)
                    </div>
                  )}
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={save} disabled={!name.trim()} style={{
                      flex: 1, padding: "9px", borderRadius: 8, border: "none",
                      background: "var(--accent)", color: "#fff", fontWeight: 600, cursor: "pointer", fontSize: 13,
                      opacity: name.trim() ? 1 : 0.5,
                    }}>{editingId !== null ? "Save" : "Create"}</button>
                    <button onClick={closeForm} style={{
                      padding: "9px 14px", borderRadius: 8, border: "1px solid var(--border)",
                      background: "transparent", color: "var(--muted)", cursor: "pointer", fontSize: 13,
                    }}>Cancel</button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
