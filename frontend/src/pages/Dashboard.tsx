import { useState, useEffect, useRef } from "react";
import { api, getProfileId } from "../api";
import MediaCard from "../components/MediaCard";
import CustomSearch from "../components/CustomSearch";
import DetailModal from "../components/DetailModal";
import RecSettingsModal, { FeedStats } from "../components/RecSettingsModal";
import { useWatched } from "../WatchedContext";
import { useIsMobile } from "../useIsMobile";

type Tab = "for-you" | "trending-shows" | "trending-movies" | "custom";

const tabs: { id: Tab; label: string }[] = [
  { id: "for-you", label: "For You" },
  { id: "trending-shows", label: "Trending Shows" },
  { id: "trending-movies", label: "Trending Films" },
  { id: "custom", label: "✨ Custom Search" },
];

// TMDB genre id → name
const GENRE_MAP: Record<number, string> = {
  28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
  99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
  27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance",
  878: "Sci-Fi", 10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western",
  // TV genres
  10759: "Action & Adventure", 10762: "Kids", 10763: "News", 10764: "Reality",
  10765: "Sci-Fi & Fantasy", 10766: "Soap", 10767: "Talk", 10768: "War & Politics",
};

function genreName(id: number) { return GENRE_MAP[id] ?? null; }

// ── Paginated data hook ──────────────────────────────────────────────────────
function usePaged<T>(fetcher: (page: number) => Promise<T[]>, enabled: boolean) {
  const [items, setItems] = useState<T[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (!enabled || fetchedRef.current) return;
    fetchedRef.current = true;
    setLoading(true);
    setError(false);
    fetcher(1)
      .then(data => { setItems(data); setHasMore(data.length >= 20); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [enabled]);

  async function loadMore() {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const next = page + 1;
      const data = await fetcher(next);
      setItems(prev => {
        const ids = new Set(prev.map((i: any) => i.id));
        const fresh = data.filter((i: any) => !ids.has(i.id));
        return [...prev, ...fresh];
      });
      setPage(next);
      setHasMore(data.length >= 20);
    } finally {
      setLoadingMore(false);
    }
  }

  // Force a fresh fetch from page 1 (e.g. after the user retunes their feed).
  function reload() {
    setLoading(true);
    setError(false);
    setPage(1);
    fetcher(1)
      .then(data => { setItems(data); setHasMore(data.length >= 20); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }

  return { items, loading, loadingMore, error, hasMore, loadMore, reload };
}

// ── Genre filter bar ─────────────────────────────────────────────────────────
function GenreFilter({ items, selected, onChange }: {
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

function buildFeedStats(items: any[], meta: any): FeedStats {
  const counts: Record<string, number> = {};
  let tv = 0, movie = 0;
  for (const it of items) {
    if (it.media_type === "tv") tv++;
    else if (it.media_type === "movie") movie++;
    for (const gid of it.genre_ids ?? []) {
      const name = genreName(gid);
      if (name) counts[name] = (counts[name] ?? 0) + 1;
    }
  }
  const genreCounts = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({ name, count }));
  return {
    total: items.length, tv, movie,
    basedOn: meta?.based_on,
    traktBlended: meta?.trakt_blended,
    tastediveBlended: meta?.tastedive_blended,
    aiBlended: meta?.ai_blended,
    genreCounts,
  };
}

function applyGenreFilter(items: any[], selected: string[]): any[] {
  if (selected.length === 0) return items;
  return items.filter(item =>
    (item.genre_ids ?? []).some((gid: number) => selected.includes(genreName(gid) ?? ""))
  );
}

function LoadMoreBtn({ onClick, loading, hasMore }: { onClick: () => void; loading: boolean; hasMore: boolean }) {
  if (!hasMore) return (
    <div style={{ textAlign: "center", marginTop: 32, color: "var(--muted)", fontSize: 13 }}>
      No more results
    </div>
  );
  return (
    <div style={{ display: "flex", justifyContent: "center", marginTop: 32 }}>
      <button onClick={onClick} disabled={loading} style={{
        padding: "10px 32px", borderRadius: 20, border: "1px solid var(--border)",
        background: "var(--surface2)", color: "var(--text)", fontWeight: 600,
        fontSize: 14, cursor: loading ? "wait" : "pointer",
        opacity: loading ? 0.6 : 1, transition: "all 0.15s",
      }}>
        {loading ? "Loading…" : "Load More"}
      </button>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const { isWatched, showProgress, isDismissed } = useWatched();
  const [tab, setTab] = useState<Tab>("for-you");
  const [selected, setSelected] = useState<{ id: number; mediaType: string } | null>(null);
  const [genreFilter, setGenreFilter] = useState<string[]>([]);
  const [forYouType, setForYouType] = useState<"all" | "tv" | "movie">("all");
  const [forYouVisible, setForYouVisible] = useState(24);  // client-side Load More
  const [forYouMeta, setForYouMeta] = useState<{ top_genres?: string[]; based_on?: number; trakt_blended?: boolean; tastedive_blended?: boolean; ai_blended?: boolean } | null>(null);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [tuning, setTuning] = useState(false);
  // After "Mark Seen", keep the card around briefly (showing ✓ Seen) then fade it out.
  const [lingering, setLingering] = useState<Set<number>>(new Set());
  const [fadingOut, setFadingOut] = useState<Set<number>>(new Set());

  function handleMarkedSeen(id: number) {
    setLingering(prev => new Set(prev).add(id));
    window.setTimeout(() => setFadingOut(prev => new Set(prev).add(id)), 1400);
    window.setTimeout(() => {
      setLingering(prev => { const n = new Set(prev); n.delete(id); return n; });
      setFadingOut(prev => { const n = new Set(prev); n.delete(id); return n; });
    }, 1850);
  }

  useEffect(() => {
    api.getStatus().then(s => setAiEnabled(!!s.ai_enabled)).catch(() => {});
  }, []);

  // Hide the Custom Search (AI) tab when no Anthropic key is configured
  const visibleTabs = aiEnabled ? tabs : tabs.filter(t => t.id !== "custom");

  // If AI gets disabled while on the custom tab, bounce to For You
  useEffect(() => {
    if (!aiEnabled && tab === "custom") setTab("for-you");
  }, [aiEnabled, tab]);

  const forYou = usePaged(async (page) => {
    // Recommendations are a small ranked pool (~80) — load all at once so the
    // TV/Movies and genre filters have the full set to work with.
    if (page > 1) return [];
    const data = await api.getRecommendations(200);
    setForYouMeta(data as any);
    return data.recommendations;
  }, tab === "for-you");

  const trendingShows = usePaged(async (page) => {
    const data = await api.getTrending("shows", page);
    return data.trending;
  }, tab === "trending-shows");

  const trendingMovies = usePaged(async (page) => {
    const data = await api.getTrending("movies", page);
    return data.trending;
  }, tab === "trending-movies");

  const active =
    tab === "for-you" ? forYou :
    tab === "trending-shows" ? trendingShows : trendingMovies;

  // Hide anything already marked as seen (movies watched, shows fully complete).
  // Reactive — updates the grid the moment you click "Mark Seen".
  // Exception: a show flagged new_season is resurfaced (it has a new season),
  // so it shows even when watched — but "not interested" still hides it.
  const notWatched = (i: any) =>
    !isDismissed(i.id) &&
    (i.new_season ||
      (i.media_type === "tv" ? showProgress(i.id) !== "full" : !isWatched(i.id)));

  const shouldShow = (i: any) => notWatched(i) || lingering.has(i.id);
  let baseItems = active.items.filter(shouldShow);
  // For You media-type sub-filter
  if (tab === "for-you" && forYouType !== "all") {
    baseItems = baseItems.filter((i: any) => i.media_type === forYouType);
  }
  const filteredItems = applyGenreFilter(baseItems, genreFilter);

  // For You paginates client-side (its whole pool is loaded at once)
  const displayItems = tab === "for-you" ? filteredItems.slice(0, forYouVisible) : filteredItems;
  const forYouHasMore = tab === "for-you" && filteredItems.length > forYouVisible;

  // Reset the visible count when the For You filters change
  useEffect(() => { setForYouVisible(24); }, [forYouType, genreFilter, tab]);

  return (
    <div>
      {/* Main tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 24, flexWrap: "wrap" }}>
        {visibleTabs.map(t => (
          <button key={t.id} onClick={() => { setTab(t.id); setGenreFilter([]); }} style={{
            padding: "7px 18px", borderRadius: 20, border: "1px solid var(--border)",
            background: tab === t.id ? "var(--accent)" : "var(--surface)",
            color: tab === t.id ? "#fff" : "var(--muted)",
            fontWeight: tab === t.id ? 600 : 400, cursor: "pointer", fontSize: 13, transition: "all 0.15s",
          }}>{t.label}</button>
        ))}
      </div>

      {/* Custom AI search */}
      {tab === "custom" && <CustomSearch />}

      {/* Grid tabs */}
      {tab !== "custom" && (
        <div>
          {tab === "for-you" && active.items.length > 0 && (
            <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 12 }}>
              Based on {forYouMeta?.based_on ?? "your"} watched titles
              {forYouMeta?.top_genres?.length ? (
                <> · you tend to like <span style={{ color: "var(--accent2)" }}>{forYouMeta.top_genres.slice(0, 3).join(", ")}</span></>
              ) : null}
              {aiEnabled && (forYouMeta?.trakt_blended ? " · ✨ AI + Trakt blended" : " · ✨ AI blended")}
            </p>
          )}

          {/* For You TV/Movies sub-tabs */}
          {tab === "for-you" && active.items.length > 0 && (
            <div style={{ display: "flex", gap: 6, marginBottom: 14, alignItems: "center" }}>
              {([["all", "All"], ["tv", "TV Shows"], ["movie", "Films"]] as const).map(([id, label]) => (
                <button key={id} onClick={() => setForYouType(id)} style={{
                  padding: "5px 14px", borderRadius: 20, fontSize: 12,
                  border: forYouType === id ? "1px solid var(--accent)" : "1px solid var(--border)",
                  background: forYouType === id ? "rgba(124,106,247,0.15)" : "var(--surface2)",
                  color: forYouType === id ? "var(--accent2)" : "var(--muted)",
                  fontWeight: forYouType === id ? 600 : 400, cursor: "pointer", transition: "all 0.15s",
                }}>{label}</button>
              ))}
              <button onClick={() => setTuning(true)} title="Tune your recommendations" style={{
                marginLeft: "auto", padding: "5px 14px", borderRadius: 20, fontSize: 12,
                border: "1px solid var(--border)", background: "var(--surface2)",
                color: "var(--muted)", fontWeight: 600, cursor: "pointer", transition: "all 0.15s",
              }}>⚙ Tune</button>
            </div>
          )}

          {/* Genre filter */}
          {baseItems.length > 0 && (
            <GenreFilter items={baseItems} selected={genreFilter} onChange={setGenreFilter} />
          )}

          {active.loading && (
            <div style={{ color: "var(--muted)", textAlign: "center", padding: 60, fontSize: 14 }}>Loading…</div>
          )}
          {active.error && <ErrorBox />}

          {!active.loading && !active.error && filteredItems.length === 0 && active.items.length > 0 && (
            <div style={{ color: "var(--muted)", textAlign: "center", padding: 40, fontSize: 14 }}>
              {genreFilter.length > 0
                ? "No results for selected genres in what's loaded — try Load More."
                : tab === "for-you" && forYouType !== "all"
                ? `No ${forYouType === "tv" ? "TV shows" : "films"} in what's loaded yet — try Load More.`
                : "No results."}
            </div>
          )}

          <div className="media-grid">
            {displayItems.map((item: any) => (
              <MediaCard key={item.id} item={item}
                fading={fadingOut.has(item.id)}
                onMarkedSeen={() => handleMarkedSeen(item.id)}
                onClick={() => setSelected({ id: item.id, mediaType: item.media_type })} />
            ))}
          </div>

          {/* Load More — trending paginates from the server; For You reveals more locally */}
          {!active.loading && active.items.length > 0 && tab !== "for-you" && (
            <LoadMoreBtn loading={active.loadingMore} hasMore={active.hasMore} onClick={active.loadMore} />
          )}
          {tab === "for-you" && forYouHasMore && (
            <LoadMoreBtn loading={false} hasMore={true} onClick={() => setForYouVisible(v => v + 24)} />
          )}
        </div>
      )}

      {selected && (
        <DetailModal tmdbId={selected.id} mediaType={selected.mediaType}
          onClose={() => setSelected(null)} />
      )}

      {tuning && (
        <RecSettingsModal
          profileId={getProfileId()}
          topGenres={forYouMeta?.top_genres}
          stats={buildFeedStats(forYou.items, forYouMeta)}
          onClose={() => setTuning(false)}
          onSaved={() => forYou.reload()}
        />
      )}
    </div>
  );
}

function ErrorBox() {
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 12, padding: 24, color: "var(--muted)", fontSize: 14,
    }}>
      <strong style={{ color: "var(--red)" }}>Could not load data.</strong>
      <p style={{ marginTop: 8 }}>Make sure the backend is running and your API keys are set in <code>.env</code>.</p>
    </div>
  );
}
