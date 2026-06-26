import { useState, useEffect } from "react";
import { api, ViewingStats } from "../api";
import { thumb } from "../api";

const PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='300'%3E%3Crect width='200' height='300' fill='%231a1a24'/%3E%3C/svg%3E";

// Friendly source labels for the breakdown.
const SOURCE_LABEL: Record<string, string> = {
  jellyfin: "Jellyfin", plex: "Plex", trakt: "Trakt",
  netflix: "Netflix", user: "Marked by hand", unknown: "Other",
};

function fmtHours(minutes: number): { big: string; sub: string } {
  const hours = minutes / 60;
  if (hours >= 48) return { big: `${Math.round(hours / 24)}`, sub: "days watched" };
  return { big: `${Math.round(hours)}`, sub: "hours watched" };
}

function StatCard({ value, label, accent }: { value: string | number; label: string; accent?: string }) {
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14,
      padding: "18px 20px", flex: 1, minWidth: 130,
    }}>
      <div style={{ fontSize: 28, fontWeight: 800, color: accent || "var(--text)" }}>{value}</div>
      <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>{label}</div>
    </div>
  );
}

export default function Stats() {
  const [stats, setStats] = useState<ViewingStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getStats()
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div style={{ color: "var(--muted)", textAlign: "center", padding: 60 }}>Loading…</div>;
  }

  if (!stats || (stats.movies_watched === 0 && stats.episodes_watched === 0)) {
    return (
      <div style={{ textAlign: "center", padding: 80, color: "var(--muted)" }}>
        <div style={{ fontSize: 40, marginBottom: 16 }}>📊</div>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>No viewing stats yet</div>
        <div style={{ fontSize: 14 }}>Watch or mark some titles and your stats will appear here.</div>
      </div>
    );
  }

  const hrs = fmtHours(stats.total_minutes);
  const maxGenre = stats.top_genres[0]?.count || 1;
  const sources = Object.entries(stats.sources).sort((a, b) => b[1] - a[1]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      {/* Headline numbers */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <StatCard value={hrs.big} label={hrs.sub} accent="var(--accent2)" />
        <StatCard value={stats.episodes_watched} label="episodes" />
        <StatCard value={stats.shows_watched} label="TV shows" />
        <StatCard value={stats.movies_watched} label="films" />
      </div>

      {/* Top genres */}
      {stats.top_genres.length > 0 && (
        <section>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Top genres</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {stats.top_genres.map(g => (
              <div key={g.name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 13, width: 120, flexShrink: 0, color: "var(--text)" }}>{g.name}</span>
                <div style={{ flex: 1, height: 10, background: "var(--surface2)", borderRadius: 5, overflow: "hidden" }}>
                  <div style={{ width: `${(g.count / maxGenre) * 100}%`, height: "100%", background: "var(--accent)", borderRadius: 5 }} />
                </div>
                <span style={{ fontSize: 12, color: "var(--muted)", width: 36, textAlign: "right", flexShrink: 0 }}>{g.count}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Most-watched shows */}
      {stats.top_shows.length > 0 && (
        <section>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Most-watched shows</h2>
          <div style={{ display: "flex", gap: 14, overflowX: "auto", paddingBottom: 6 }}>
            {stats.top_shows.map(s => (
              <div key={s.id} style={{ width: 110, flexShrink: 0 }}>
                <img
                  src={thumb(s.poster_url, "w185") || PLACEHOLDER}
                  alt={s.title}
                  loading="lazy"
                  style={{ width: 110, height: 165, objectFit: "cover", borderRadius: 10, display: "block", border: "1px solid var(--border)" }}
                  onError={e => { (e.target as HTMLImageElement).src = PLACEHOLDER; }}
                />
                <div style={{ fontSize: 12, fontWeight: 600, marginTop: 6, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.title}</div>
                <div style={{ fontSize: 11, color: "var(--muted)" }}>{s.episodes} episode{s.episodes !== 1 ? "s" : ""}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Where it came from */}
      {sources.length > 0 && (
        <section>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Tracked from</h2>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {sources.map(([src, count]) => (
              <div key={src} style={{
                background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 20,
                padding: "6px 14px", fontSize: 13, color: "var(--text)",
              }}>
                {SOURCE_LABEL[src] || src} <span style={{ color: "var(--muted)" }}>· {count}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
