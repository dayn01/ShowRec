import { useEffect, useState } from "react";
import { api, RecSettings } from "../api";

// Genres a user is likely to want to tune. Names must match the backend's
// GENRE_MAP values so the per-genre multipliers line up.
const GENRES = [
  "Action", "Action & Adventure", "Adventure", "Animation", "Comedy", "Crime",
  "Documentary", "Drama", "Family", "Fantasy", "History", "Horror", "Kids",
  "Music", "Mystery", "Reality", "Romance", "Sci-Fi", "Sci-Fi & Fantasy",
  "Thriller", "War", "Western",
];

export interface FeedStats {
  total: number;
  tv: number;
  movie: number;
  basedOn?: number;
  traktBlended?: boolean;
  tastediveBlended?: boolean;
  aiBlended?: boolean;
  genreCounts: { name: string; count: number }[];   // sorted, most common first
}

interface Props {
  profileId: number;
  topGenres?: string[];
  stats?: FeedStats;
  onClose: () => void;
  onSaved: () => void;
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span style={{
      background: "rgba(124,106,247,0.15)", border: "1px solid var(--accent)",
      color: "var(--accent2)", borderRadius: 20, padding: "2px 10px", fontSize: 11, fontWeight: 600,
    }}>{children}</span>
  );
}

function weightLabel(v: number) {
  if (v <= 0) return "Hidden";
  if (v < 0.75) return "Much less";
  if (v < 0.95) return "Less";
  if (v <= 1.05) return "Normal";
  if (v <= 1.5) return "More";
  return "Much more";
}

export default function RecSettingsModal({ profileId, topGenres, stats, onClose, onSaved }: Props) {
  const [genreWeight, setGenreWeight] = useState(1);
  const [multipliers, setMultipliers] = useState<Record<string, number>>({});
  const [advanced, setAdvanced] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getRecSettings(profileId)
      .then(s => {
        setGenreWeight(s.genre_weight ?? 1);
        setMultipliers(s.genre_multipliers ?? {});
        // Open the advanced section if any per-genre tweak is already set
        if (Object.keys(s.genre_multipliers ?? {}).length > 0) setAdvanced(true);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [profileId]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const mult = (g: string) => multipliers[g] ?? 1;
  function setMult(g: string, v: number) {
    setMultipliers(prev => ({ ...prev, [g]: v }));
  }

  function reset() {
    setGenreWeight(1);
    setMultipliers({});
  }

  async function save() {
    setSaving(true);
    try {
      const body: RecSettings = { genre_weight: genreWeight, genre_multipliers: multipliers };
      await api.saveRecSettings(profileId, body);
      onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  }

  // Show top genres first in the advanced list, then the rest alphabetically.
  const ordered = [
    ...GENRES.filter(g => topGenres?.includes(g)),
    ...GENRES.filter(g => !topGenres?.includes(g)),
  ];

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)", zIndex: 1100,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 24, backdropFilter: "blur(4px)",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 16,
          width: "100%", maxWidth: 520, maxHeight: "88vh", overflow: "hidden",
          display: "flex", flexDirection: "column", position: "relative",
        }}
      >
        <button
          onClick={onClose}
          style={{
            position: "absolute", top: 14, right: 14, zIndex: 10,
            background: "rgba(0,0,0,0.4)", border: "none", color: "#fff",
            width: 30, height: 30, borderRadius: "50%", cursor: "pointer",
            fontSize: 17, lineHeight: "30px", textAlign: "center",
          }}
        >×</button>

        <div style={{ padding: "22px 24px 12px" }}>
          <h2 style={{ fontSize: 19, fontWeight: 700 }}>Tune your recommendations</h2>
          <p style={{ fontSize: 13, color: "var(--muted)", marginTop: 4 }}>
            Adjust how much genres shape your <strong>For You</strong> feed. Changes apply instantly.
          </p>
        </div>

        {loading ? (
          <div style={{ padding: 50, textAlign: "center", color: "var(--muted)" }}>Loading…</div>
        ) : (
          <div style={{ overflowY: "auto", padding: "0 24px 8px" }}>
            {/* Feed stats */}
            {stats && stats.total > 0 && (
              <div style={{
                background: "var(--surface2)", border: "1px solid var(--border)",
                borderRadius: 12, padding: "14px 16px", marginBottom: 8,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 6 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Your For You feed</span>
                  {stats.basedOn != null && (
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>from {stats.basedOn} watched titles</span>
                  )}
                </div>

                <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
                  {stats.total} titles · {stats.tv} shows · {stats.movie} films
                </div>

                {/* Blend sources */}
                {(stats.aiBlended || stats.traktBlended || stats.tastediveBlended) && (
                  <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                    {stats.aiBlended && <Badge>✨ AI</Badge>}
                    {stats.traktBlended && <Badge>Trakt</Badge>}
                    {stats.tastediveBlended && <Badge>TasteDive</Badge>}
                  </div>
                )}

                {/* Genre breakdown */}
                {stats.genreCounts.length > 0 && (
                  <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                    <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>
                      Genre mix
                    </div>
                    {stats.genreCounts.slice(0, 8).map(({ name, count }) => {
                      const max = stats.genreCounts[0].count || 1;
                      const pct = Math.round((count / max) * 100);
                      return (
                        <div key={name} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ fontSize: 12, width: 130, flexShrink: 0, color: "var(--text)",
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
                          <div style={{ flex: 1, height: 7, background: "var(--surface)", borderRadius: 4, overflow: "hidden" }}>
                            <div style={{ width: `${pct}%`, height: "100%", background: "var(--accent)", borderRadius: 4 }} />
                          </div>
                          <span style={{ fontSize: 11, color: "var(--muted)", width: 26, textAlign: "right", flexShrink: 0 }}>{count}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* General genre affinity */}
            <div style={{ marginTop: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <label style={{ fontSize: 14, fontWeight: 600 }}>Genre affinity</label>
                <span style={{ fontSize: 12, color: "var(--accent2)" }}>{weightLabel(genreWeight)}</span>
              </div>
              <p style={{ fontSize: 12, color: "var(--muted)", margin: "4px 0 8px" }}>
                How strongly the genres you watch most pull the feed toward similar genres.
              </p>
              <input
                type="range" min={0} max={2} step={0.05} value={genreWeight}
                onChange={e => setGenreWeight(parseFloat(e.target.value))}
                style={{ width: "100%", accentColor: "var(--accent)" }}
              />
            </div>

            {/* Advanced: per-genre */}
            <button
              onClick={() => setAdvanced(a => !a)}
              style={{
                marginTop: 18, marginBottom: 4, background: "none", border: "none",
                color: "var(--accent2)", cursor: "pointer", fontSize: 13, fontWeight: 600,
                padding: 0, display: "flex", alignItems: "center", gap: 6,
              }}
            >
              {advanced ? "▾" : "▸"} Advanced — adjust individual genres
            </button>

            {advanced && (
              <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 14 }}>
                <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>
                  Drag a genre down to see less of it, or all the way to <strong>Hidden</strong> to
                  remove it. (e.g. lower <em>Animation</em>, <em>Family</em> and <em>Kids</em> for fewer
                  family cartoons.)
                </p>
                {ordered.map(g => {
                  const v = mult(g);
                  const hidden = v <= 0;
                  return (
                    <div key={g}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                        <span style={{ fontSize: 13, fontWeight: v !== 1 ? 600 : 400,
                          color: v !== 1 ? "var(--text)" : "var(--muted)" }}>{g}</span>
                        <span style={{ fontSize: 11, color: hidden ? "var(--red)" : "var(--muted)" }}>
                          {weightLabel(v)}
                        </span>
                      </div>
                      <input
                        type="range" min={0} max={2} step={0.05} value={v}
                        onChange={e => setMult(g, parseFloat(e.target.value))}
                        style={{ width: "100%", accentColor: hidden ? "var(--red)" : "var(--accent)" }}
                      />
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div style={{
          display: "flex", justifyContent: "space-between", gap: 10,
          padding: "14px 24px", borderTop: "1px solid var(--border)",
        }}>
          <button
            onClick={reset}
            style={{
              padding: "9px 16px", borderRadius: 20, border: "1px solid var(--border)",
              background: "var(--surface2)", color: "var(--muted)", cursor: "pointer",
              fontSize: 13, fontWeight: 600,
            }}
          >Reset to defaults</button>
          <button
            onClick={save}
            disabled={saving || loading}
            style={{
              padding: "9px 22px", borderRadius: 20, border: "none",
              background: "var(--accent)", color: "#fff", cursor: saving ? "wait" : "pointer",
              fontSize: 13, fontWeight: 600,
            }}
          >{saving ? "Saving…" : "Save"}</button>
        </div>
      </div>
    </div>
  );
}
