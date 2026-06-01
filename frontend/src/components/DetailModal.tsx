import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, DetailedMedia, Recommendation } from "../api";
import SeasonRow from "./SeasonRow";
import { useWatched } from "../WatchedContext";

const PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='300'%3E%3Crect width='200' height='300' fill='%231a1a24'/%3E%3C/svg%3E";

function fmt(minutes?: number) {
  if (!minutes) return null;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function fmtMoney(n?: number) {
  if (!n) return null;
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

function fmtDate(iso?: string) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

interface Props {
  tmdbId: number;
  mediaType: string;
  onClose: () => void;
}

export default function DetailModal({ tmdbId, mediaType, onClose }: Props) {
  // Track the currently-shown title so "More Like This" can navigate within the modal.
  const [current, setCurrent] = useState({ tmdbId, mediaType });
  useEffect(() => { setCurrent({ tmdbId, mediaType }); }, [tmdbId, mediaType]);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["details", current.mediaType, current.tmdbId],
    queryFn: () => api.getDetails(current.mediaType, current.tmdbId),
    staleTime: 1000 * 60 * 60 * 6, // trust cache for 6h
  });

  const { data: similar } = useQuery({
    queryKey: ["similar", current.mediaType, current.tmdbId],
    queryFn: () => api.getSimilar(current.mediaType, current.tmdbId),
    staleTime: 1000 * 60 * 60 * 6,
    enabled: !!data,
  });
  const similarItems = similar?.results ?? [];

  // Auto-expand the current/latest season and trigger background season prefetch
  const [autoExpandSeason, setAutoExpandSeason] = useState<number | null>(null);
  useEffect(() => {
    if (!data || current.mediaType !== "tv" || !data.seasons?.length) return;
    // Seed TMDB episode counts into context so watched logic is accurate
    initSeasonTotals(data.id, data.seasons);
    // Auto-expand the last aired season
    const today = new Date().toISOString().slice(0, 10);
    const airedSeasons = data.seasons.filter((s: any) => !s.air_date || s.air_date <= today);
    const target = airedSeasons[airedSeasons.length - 1] ?? data.seasons[0];
    if (target) setAutoExpandSeason(target.season_number);
    // Trigger background prefetch of all seasons into SQLite
    fetch(`/api/details/tv/${current.tmdbId}/prefetch-seasons`, { method: "POST" }).catch(() => {});
  }, [data?.id]);

  // Navigate the modal to a similar title (scroll back to top).
  const scrollRef = useRef<HTMLDivElement | null>(null);
  function openSimilar(item: Recommendation) {
    setAutoExpandSeason(null);
    setCurrent({ tmdbId: item.id, mediaType: item.media_type });
    scrollRef.current?.scrollTo({ top: 0 });
  }

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Prevent body scroll
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  const { isWatched, markWatched, markUnwatched, markShowComplete, initSeasonTotals,
          isWatchlisted, toggleWatchlist, dismiss } = useWatched();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const onWatchlist = data ? isWatchlisted(data.id) : false;

  function watchlistToggle() {
    if (!data) return;
    toggleWatchlist({
      id: data.id, media_type: data.media_type,
      title: data.title, poster_url: data.poster_url,
      vote_average: data.vote_average, overview: data.overview,
      release_date: data.release_date, first_air_date: data.first_air_date,
    });
  }

  function notInterested() {
    if (!data) return;
    dismiss(data.id, data.media_type, data.title);
    onClose();  // hide it and close the modal
  }

  const score = data ? Math.round(data.vote_average * 10) : 0;
  const scoreColor = score >= 75 ? "var(--green)" : score >= 55 ? "var(--yellow)" : "var(--red)";
  const runtime = data?.runtime ?? data?.episode_run_time?.[0];

  async function toggleWatched() {
    if (!data || loading) return;
    setLoading(true);
    const year = parseInt((data.release_date || data.first_air_date || "").slice(0, 4)) || undefined;
    const watched = isWatched(data.id);
    try {
      if (watched) {
        await api.markUnwatched(data.id, data.media_type, data.title);
        markUnwatched(data.id);
      } else {
        const res: any = await api.markWatched(data.id, data.media_type, data.title, year);
        if (data.media_type === "tv" && res?.seasons) markShowComplete(data.id, res.seasons);
        else markWatched(data.id);
      }
    } catch {
      setError(true);
      setTimeout(() => setError(false), 3000);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      onClick={onClose}
      className="modal-backdrop"
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)",
        zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center",
        padding: 24, backdropFilter: "blur(4px)",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="modal-panel"
        style={{
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 16, width: "100%", maxWidth: 860,
          maxHeight: "90vh", overflow: "hidden", display: "flex", flexDirection: "column",
          position: "relative",
        }}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          style={{
            position: "absolute", top: 14, right: 14, zIndex: 10,
            background: "rgba(0,0,0,0.6)", border: "none", color: "#fff",
            width: 32, height: 32, borderRadius: "50%", cursor: "pointer",
            fontSize: 18, lineHeight: "32px", textAlign: "center",
          }}
        >×</button>

        {isLoading && (
          <div style={{ padding: 60, textAlign: "center", color: "var(--muted)" }}>Loading…</div>
        )}

        {isError && (
          <div style={{ padding: 60, textAlign: "center", color: "var(--red)" }}>Failed to load details.</div>
        )}

        {data && (
          <div ref={scrollRef} style={{ overflowY: "auto" }}>
            {/* Backdrop */}
            {data.backdrop_url && (
              <div style={{ position: "relative", height: 220, overflow: "hidden" }}>
                <img src={data.backdrop_url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                <div style={{ position: "absolute", inset: 0, background: "linear-gradient(to bottom, transparent 40%, var(--surface))" }} />
              </div>
            )}

            {/* Main content */}
            <div style={{ display: "flex", gap: 24, padding: "0 24px 24px", marginTop: data.backdrop_url ? -80 : 24 }}>
              {/* Poster */}
              <img
                src={data.poster_url || PLACEHOLDER}
                alt={data.title}
                style={{ width: 140, height: 210, objectFit: "cover", borderRadius: 10, flexShrink: 0, border: "2px solid var(--border)", position: "relative" }}
                onError={e => { (e.target as HTMLImageElement).src = PLACEHOLDER; }}
              />

              {/* Info */}
              <div style={{ flex: 1, paddingTop: data.backdrop_url ? 80 : 0 }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                  <h2 style={{ fontSize: 22, fontWeight: 700, flex: 1 }}>{data.title}</h2>
                  <span style={{ fontWeight: 700, fontSize: 18, color: scoreColor }}>{score > 0 ? `${score}%` : "N/A"}</span>
                </div>

                <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                  <button
                    onClick={toggleWatched}
                    disabled={loading}
                    style={{
                      padding: "8px 18px", borderRadius: 20, border: "none",
                      cursor: loading ? "wait" : "pointer", fontWeight: 600, fontSize: 13,
                      background: error ? "var(--red)" : data && isWatched(data.id) ? "var(--green)" : "var(--accent)",
                      color: data && isWatched(data.id) ? "#000" : "#fff",
                      transition: "background 0.2s",
                    }}
                  >
                    {loading ? "Saving…"
                      : error ? "Error — try again"
                      : data && isWatched(data.id) ? "✓ Seen (undo)"
                      : "Mark as Seen"}
                  </button>

                  <button
                    onClick={watchlistToggle}
                    style={{
                      padding: "8px 16px", borderRadius: 20,
                      border: "1px solid var(--border)", cursor: "pointer", fontWeight: 600, fontSize: 13,
                      background: onWatchlist ? "var(--accent)" : "var(--surface2)",
                      color: onWatchlist ? "#fff" : "var(--text)",
                      transition: "background 0.2s",
                    }}
                  >
                    {onWatchlist ? "✓ On Watchlist" : "+ Watchlist"}
                  </button>

                  <button
                    onClick={notInterested}
                    title="Not interested — hide this"
                    style={{
                      padding: "8px 16px", borderRadius: 20,
                      border: "1px solid var(--border)", cursor: "pointer", fontWeight: 600, fontSize: 13,
                      background: "var(--surface2)", color: "var(--muted)",
                    }}
                  >
                    ✕ Not Interested
                  </button>
                </div>

                {data.tagline && (
                  <div style={{ color: "var(--muted)", fontStyle: "italic", fontSize: 13, marginTop: 4 }}>{data.tagline}</div>
                )}

                {/* Meta row */}
                <div style={{ display: "flex", gap: 16, marginTop: 10, flexWrap: "wrap" }}>
                  {(data.release_date || data.first_air_date) && (
                    <span style={{ fontSize: 13, color: "var(--muted)" }}>
                      📅 {fmtDate(data.release_date || data.first_air_date)}
                    </span>
                  )}
                  {runtime && (
                    <span style={{ fontSize: 13, color: "var(--muted)" }}>⏱ {fmt(runtime)}</span>
                  )}
                  {data.number_of_seasons && (
                    <span style={{ fontSize: 13, color: "var(--muted)" }}>
                      📺 {data.number_of_seasons} season{data.number_of_seasons !== 1 ? "s" : ""} · {data.number_of_episodes} episodes
                    </span>
                  )}
                  {data.networks && data.networks.length > 0 && (
                    <span style={{ fontSize: 13, color: "var(--muted)" }}>🔗 {data.networks.join(", ")}</span>
                  )}
                  {data.status && (
                    <span style={{ fontSize: 13, color: "var(--muted)" }}>● {data.status}</span>
                  )}
                </div>

                {/* Genres */}
                {data.genres.length > 0 && (
                  <div style={{ display: "flex", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
                    {data.genres.map(g => (
                      <span key={g} style={{
                        background: "var(--surface2)", border: "1px solid var(--border)",
                        borderRadius: 20, padding: "2px 10px", fontSize: 12, color: "var(--muted)",
                      }}>{g}</span>
                    ))}
                  </div>
                )}

                {/* Overview */}
                {data.overview && (
                  <p style={{ fontSize: 14, lineHeight: 1.6, color: "var(--text)", marginTop: 14 }}>{data.overview}</p>
                )}

                {/* Movie extras */}
                {data.media_type === "movie" && (data.budget || data.revenue) && (
                  <div style={{ display: "flex", gap: 24, marginTop: 12 }}>
                    {data.budget ? <span style={{ fontSize: 13, color: "var(--muted)" }}>Budget: {fmtMoney(data.budget)}</span> : null}
                    {data.revenue ? <span style={{ fontSize: 13, color: "var(--muted)" }}>Revenue: {fmtMoney(data.revenue)}</span> : null}
                  </div>
                )}
              </div>
            </div>

            {/* Seasons */}
            {data.seasons && data.seasons.length > 0 && (
              <div style={{ padding: "0 24px 24px" }}>
                <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 12, color: "var(--accent2)" }}>
                  Seasons & Episodes
                </h3>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {data.seasons.map(s => {
                    const next = data.next_episode_to_air;
                    const upcoming = next && next.season_number === s.season_number
                      ? { episode_number: next.episode_number, name: next.name, air_date: next.air_date }
                      : null;
                    return (
                      <SeasonRow
                        key={s.season_number}
                        season={s}
                        tmdbId={data.id}
                        showTitle={data.title}
                        autoExpand={autoExpandSeason === s.season_number}
                        upcomingEpisode={upcoming}
                      />
                    );
                  })}
                </div>
              </div>
            )}

            {/* Cast */}
            {data.cast && data.cast.length > 0 && (
              <div style={{ padding: "0 24px 24px" }}>
                <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 12, color: "var(--accent2)" }}>Cast</h3>
                <div style={{ display: "flex", gap: 12, overflowX: "auto", paddingBottom: 8 }}>
                  {data.cast.map((c, i) => (
                    <div key={i} style={{ flexShrink: 0, width: 80, textAlign: "center" }}>
                      <img
                        src={c.profile_url || PLACEHOLDER}
                        alt={c.name}
                        style={{ width: 64, height: 64, objectFit: "cover", borderRadius: "50%", border: "2px solid var(--border)" }}
                        onError={e => { (e.target as HTMLImageElement).src = PLACEHOLDER; }}
                      />
                      <div style={{ fontSize: 11, fontWeight: 600, marginTop: 4, lineHeight: 1.2 }}>{c.name}</div>
                      <div style={{ fontSize: 10, color: "var(--muted)", lineHeight: 1.2 }}>{c.character}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* More Like This — TasteDive similar titles (only when an API key is set) */}
            {similarItems.length > 0 && (
              <div style={{ padding: "0 24px 24px" }}>
                <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 12, color: "var(--accent2)" }}>
                  More Like This
                </h3>
                <div style={{ display: "flex", gap: 12, overflowX: "auto", paddingBottom: 8 }}>
                  {similarItems.map(item => {
                    const simScore = Math.round((item.vote_average || 0) * 10);
                    return (
                      <div
                        key={`${item.media_type}-${item.id}`}
                        onClick={() => openSimilar(item)}
                        title={item.title || item.name}
                        style={{ flexShrink: 0, width: 110, cursor: "pointer" }}
                      >
                        <div style={{ position: "relative" }}>
                          <img
                            src={item.poster_url || PLACEHOLDER}
                            alt={item.title || item.name}
                            style={{ width: 110, height: 165, objectFit: "cover", borderRadius: 8, border: "1px solid var(--border)" }}
                            onError={e => { (e.target as HTMLImageElement).src = PLACEHOLDER; }}
                          />
                          {simScore > 0 && (
                            <div style={{
                              position: "absolute", top: 6, right: 6,
                              background: "rgba(0,0,0,0.75)", borderRadius: 12,
                              padding: "1px 6px", fontSize: 11, fontWeight: 700,
                              color: simScore >= 75 ? "var(--green)" : simScore >= 55 ? "var(--yellow)" : "var(--red)",
                            }}>{simScore}%</div>
                          )}
                        </div>
                        <div style={{ fontSize: 12, fontWeight: 600, marginTop: 4, lineHeight: 1.3 }}>
                          {item.title || item.name}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
