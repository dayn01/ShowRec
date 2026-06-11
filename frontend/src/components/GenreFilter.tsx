import { useState } from "react";
import { useIsMobile } from "../useIsMobile";

// TMDB genre id → name (single source of truth for the frontend genre filters).
export const GENRE_MAP: Record<number, string> = {
  28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
  99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
  27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance",
  878: "Sci-Fi", 10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western",
  // TV genres
  10759: "Action & Adventure", 10762: "Kids", 10763: "News", 10764: "Reality",
  10765: "Sci-Fi & Fantasy", 10766: "Soap", 10767: "Talk", 10768: "War & Politics",
};

export function genreName(id: number) { return GENRE_MAP[id] ?? null; }

export function applyGenreFilter(items: any[], selected: string[]): any[] {
  if (selected.length === 0) return items;
  return items.filter(item =>
    (item.genre_ids ?? []).some((gid: number) => selected.includes(genreName(gid) ?? ""))
  );
}

// ── Genre filter bar (desktop chips / mobile dropdown) ────────────────────────
export function GenreFilter({ items, selected, onChange }: {
  items: any[]; selected: string[]; onChange: (g: string[]) => void;
}) {
  const counts: Record<string, number> = {};
  for (const item of items) {
    for (const gid of item.genre_ids ?? []) {
      const name = genreName(gid);
      if (name) counts[name] = (counts[name] ?? 0) + 1;
    }
  }
  const genres = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([name]) => name);

  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);

  if (genres.length === 0) return null;

  function toggle(g: string) {
    onChange(selected.includes(g) ? selected.filter(x => x !== g) : [...selected, g]);
  }

  // ── Mobile: collapsible dropdown ──
  if (isMobile) {
    const label = selected.length === 0
      ? "All genres"
      : selected.length === 1 ? selected[0] : `${selected.length} genres`;
    return (
      <div style={{ position: "relative", marginBottom: 16 }}>
        <button
          onClick={() => setOpen(o => !o)}
          style={{
            width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 14px", borderRadius: 10, fontSize: 14, cursor: "pointer",
            border: selected.length ? "1px solid var(--accent)" : "1px solid var(--border)",
            background: "var(--surface2)",
            color: selected.length ? "var(--accent2)" : "var(--text)", fontWeight: 600,
          }}
        >
          <span>🎭 {label}</span>
          <span style={{ color: "var(--muted)" }}>{open ? "▲" : "▼"}</span>
        </button>

        {open && (
          <>
            {/* tap-away backdrop */}
            <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
            <div style={{
              position: "absolute", top: "calc(100% + 6px)", left: 0, right: 0, zIndex: 50,
              background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12,
              maxHeight: 320, overflowY: "auto", padding: 6,
              boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
            }}>
              {selected.length > 0 && (
                <button onClick={() => onChange([])} style={{
                  width: "100%", textAlign: "left", padding: "10px 12px", borderRadius: 8,
                  border: "none", background: "transparent", color: "var(--muted)",
                  cursor: "pointer", fontSize: 13,
                }}>✕ Clear all</button>
              )}
              {genres.map(g => {
                const on = selected.includes(g);
                return (
                  <button key={g} onClick={() => toggle(g)} style={{
                    width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "10px 12px", borderRadius: 8, border: "none", cursor: "pointer",
                    background: on ? "rgba(124,106,247,0.15)" : "transparent",
                    color: on ? "var(--accent2)" : "var(--text)", fontSize: 14,
                    fontWeight: on ? 600 : 400,
                  }}>
                    <span>{g}</span>
                    {on && <span>✓</span>}
                  </button>
                );
              })}
            </div>
          </>
        )}
      </div>
    );
  }

  // ── Desktop: inline chips ──
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
      {genres.map(g => (
        <button key={g} onClick={() => toggle(g)} style={{
          padding: "4px 12px", borderRadius: 20, fontSize: 12, cursor: "pointer",
          border: selected.includes(g) ? "1px solid var(--accent)" : "1px solid var(--border)",
          background: selected.includes(g) ? "rgba(124,106,247,0.15)" : "var(--surface2)",
          color: selected.includes(g) ? "var(--accent2)" : "var(--muted)",
          fontWeight: selected.includes(g) ? 600 : 400,
          transition: "all 0.15s",
        }}>{g}</button>
      ))}
      {selected.length > 0 && (
        <button onClick={() => onChange([])} style={{
          padding: "4px 10px", borderRadius: 20, fontSize: 12, cursor: "pointer",
          border: "1px solid var(--border)", background: "transparent", color: "var(--muted)",
        }}>✕ Clear</button>
      )}
    </div>
  );
}
