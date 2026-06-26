import { useState, useEffect } from "react";
import { useWatched } from "../WatchedContext";
import { api } from "../api";
import DetailModal from "../components/DetailModal";

const PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='300'%3E%3Crect width='200' height='300' fill='%231a1a24'/%3E%3C/svg%3E";

interface ShowDetail {
  id: number;
  title: string;
  poster_url: string | null;
  number_of_seasons: number;
  number_of_episodes: number;
  status: string;
  networks: string[];
  overview: string;
  vote_average: number;
  seasons?: {
    season_number: number;
    name: string;
    episode_count: number;
    air_date?: string;
    poster_url: string | null;
    overview?: string;
  }[];
}

export default function Watching() {
  const { partiallyWatchedIds, seasonProgress, isSeasonWatched, initSeasonTotals, showProgress, isDismissed, lastWatchedAt, isEpisodeWatched } = useWatched();
  const [shows, setShows] = useState<ShowDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(40);
  // Latest library-available episode per show (Jellyfin) → {id: [season, ep]}.
  const [availMap, setAvailMap] = useState<Record<string, [number, number]>>({});

  useEffect(() => {
    api.getAvailableEpisodes().then(d => setAvailMap(d.items || {})).catch(() => {});
  }, []);

  // "Ready to continue" = the newest downloaded episode hasn't been watched yet.
  const readyToContinue = (id: number) => {
    const a = availMap[String(id)];
    return a ? !isEpisodeWatched(id, a[0], a[1]) : false;
  };

  useEffect(() => {
    if (partiallyWatchedIds.length === 0) { setShows([]); return; }
    setLoading(true);
    // One batched request instead of one per show — far faster with a long list.
    api.getDetailsBatch(partiallyWatchedIds)
      .then(({ shows: valid }) => {
        setShows(valid as ShowDetail[]);
        // Seed TMDB episode counts into context so progress bars are accurate
        valid.forEach((show: any) => {
          if (show.seasons?.length) {
            initSeasonTotals(show.id, show.seasons);
          }
        });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [partiallyWatchedIds.join(",")]);

  // Reset the visible window when the search changes
  useEffect(() => { setVisibleCount(40); }, [query]);

  // Only show shows that still have unwatched episodes (progress = "partial").
  // Sort: a new episode ready on the server first, then most recently watched.
  const allInProgress = shows
    .filter(show => showProgress(show.id) === "partial" && !isDismissed(show.id))
    .sort((a, b) => {
      const ra = readyToContinue(a.id) ? 1 : 0;
      const rb = readyToContinue(b.id) ? 1 : 0;
      if (ra !== rb) return rb - ra;                 // ready-to-continue on top
      return lastWatchedAt(b.id) - lastWatchedAt(a.id);  // then by recency
    });
  const q = query.trim().toLowerCase();
  const inProgressShows = q
    ? allInProgress.filter(s => (s.title || "").toLowerCase().includes(q))
    : allInProgress;
  const shownShows = inProgressShows.slice(0, visibleCount);

  if (!loading && partiallyWatchedIds.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 80, color: "var(--muted)" }}>
        <div style={{ fontSize: 40, marginBottom: 16 }}>📺</div>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Nothing in progress</div>
        <div style={{ fontSize: 14 }}>Mark individual episodes as seen to track your progress here.</div>
      </div>
    );
  }

  return (
    <div>
      <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 12 }}>
        {loading
          ? "Loading…"
          : q
          ? `${inProgressShows.length} of ${allInProgress.length} shows`
          : `${allInProgress.length} show${allInProgress.length !== 1 ? "s" : ""} in progress`}
      </p>

      {/* Search */}
      {allInProgress.length > 0 && (
        <div style={{ position: "relative", marginBottom: 20, maxWidth: 420 }}>
          <span style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "var(--muted)", fontSize: 14 }}>🔍</span>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search what you're watching…"
            style={{
              width: "100%", padding: "10px 14px 10px 38px",
              background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 10, color: "var(--text)", fontSize: 14, outline: "none",
            }}
            onFocus={e => { e.target.style.borderColor = "var(--accent)"; }}
            onBlur={e => { e.target.style.borderColor = "var(--border)"; }}
          />
          {query && (
            <button onClick={() => setQuery("")} style={{
              position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
              background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 14,
            }}>✕</button>
          )}
        </div>
      )}

      {loading && (
        <div style={{ color: "var(--muted)", textAlign: "center", padding: 60 }}>Loading…</div>
      )}

      {!loading && q && inProgressShows.length === 0 && (
        <div style={{ color: "var(--muted)", textAlign: "center", padding: 40, fontSize: 14 }}>
          No shows match "{query}".
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {shownShows.map(show => {
          const score = Math.round((show.vote_average ?? 0) * 10);
          const scoreColor = score >= 75 ? "var(--green)" : score >= 55 ? "var(--yellow)" : "var(--red)";

          // Count watched vs total seasons
          const seasons = Array.from({ length: show.number_of_seasons ?? 0 }, (_, i) => i + 1);
          const watchedSeasons = seasons.filter(s => isSeasonWatched(show.id, s)).length;

          // Find latest in-progress season
          const inProgressSeason = seasons.find(s => {
            const p = seasonProgress(show.id, s);
            return p && p.watched > 0 && p.watched < p.total;
          });
          const inProgressData = inProgressSeason ? seasonProgress(show.id, inProgressSeason) : null;

          return (
            <div
              key={show.id}
              onClick={() => setSelected(show.id)}
              style={{
                background: "var(--surface)", border: "1px solid var(--yellow)",
                borderRadius: 14, overflow: "hidden", display: "flex",
                cursor: "pointer", transition: "transform 0.15s, box-shadow 0.15s",
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)";
                (e.currentTarget as HTMLElement).style.boxShadow = "0 6px 24px rgba(250,204,21,0.15)";
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLElement).style.transform = "";
                (e.currentTarget as HTMLElement).style.boxShadow = "";
              }}
            >
              {/* Poster */}
              <div style={{ width: 80, flexShrink: 0 }}>
                <img
                  src={show.poster_url || PLACEHOLDER}
                  alt={show.title}
                  loading="lazy"
                  decoding="async"
                  style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                  onError={e => { (e.target as HTMLImageElement).src = PLACEHOLDER; }}
                />
              </div>

              {/* Info */}
              <div style={{ flex: 1, padding: "14px 18px", display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span style={{ fontWeight: 700, fontSize: 15 }}>{show.title}</span>
                      {readyToContinue(show.id) && (
                        <span style={{
                          background: "var(--green)", color: "#000", borderRadius: 10,
                          padding: "1px 8px", fontSize: 10, fontWeight: 700,
                        }}>▶ New episode</span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>
                      {show.networks?.join(", ")}
                      {show.status ? ` · ${show.status}` : ""}
                      {score > 0 && <span style={{ color: scoreColor }}> · {score}%</span>}
                    </div>
                  </div>
                </div>

                {/* Season progress bars — only seasons with episodes still to watch */}
                <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 4 }}>
                  {seasons.map(s => {
                    const p = seasonProgress(show.id, s);
                    const full = isSeasonWatched(show.id, s);
                    // Only show partially-watched seasons (started but not finished)
                    if (full || !p || p.watched === 0 || p.watched >= p.total) return null;
                    const pct = Math.round((p.watched / Math.max(p.total, 1)) * 100);
                    return (
                      <div key={s} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 11, color: "var(--muted)", width: 28, flexShrink: 0 }}>S{String(s).padStart(2, "0")}</span>
                        <div style={{ flex: 1, height: 6, background: "var(--surface2)", borderRadius: 3, overflow: "hidden" }}>
                          <div style={{ width: `${pct}%`, height: "100%", background: "var(--yellow)", borderRadius: 3, transition: "width 0.3s" }} />
                        </div>
                        <span style={{ fontSize: 11, color: "var(--muted)", width: 40, textAlign: "right", flexShrink: 0 }}>
                          {p.watched}/{p.total}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* Current progress label */}
                {inProgressData && (
                  <div style={{ fontSize: 12, color: "var(--yellow)", marginTop: 2 }}>
                    ▶ Season {inProgressSeason} — {inProgressData.watched} of {inProgressData.total} episodes watched
                  </div>
                )}
                {!inProgressData && watchedSeasons > 0 && (
                  <div style={{ fontSize: 12, color: "var(--green)" }}>
                    ✓ {watchedSeasons} of {show.number_of_seasons} season{show.number_of_seasons !== 1 ? "s" : ""} complete
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {inProgressShows.length > shownShows.length && (
        <div style={{ display: "flex", justifyContent: "center", marginTop: 24 }}>
          <button onClick={() => setVisibleCount(c => c + 40)} style={{
            padding: "10px 32px", borderRadius: 20, border: "1px solid var(--border)",
            background: "var(--surface2)", color: "var(--text)", fontWeight: 600,
            fontSize: 14, cursor: "pointer",
          }}>
            Load more ({inProgressShows.length - shownShows.length} more)
          </button>
        </div>
      )}

      {selected && (
        <DetailModal
          tmdbId={selected}
          mediaType="tv"
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
