import { useState, useEffect, useRef } from "react";
import { api, getProfileId } from "../api";
import MediaCard from "../components/MediaCard";
import CustomSearch from "../components/CustomSearch";
import DetailModal from "../components/DetailModal";
import RecSettingsModal, { FeedStats } from "../components/RecSettingsModal";
import { GenreFilter, genreName, applyGenreFilter } from "../components/GenreFilter";
import { useWatched } from "../WatchedContext";

type Tab = "for-you" | "trending-shows" | "trending-movies" | "custom";

const tabs: { id: Tab; label: string }[] = [
  { id: "for-you", label: "For You" },
  { id: "trending-shows", label: "Trending Shows" },
  { id: "trending-movies", label: "Trending Films" },
  { id: "custom", label: "✨ Custom Search" },
];

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
  const { isWatched, showProgress, isDismissed, isWatchlisted } = useWatched();
  const [tab, setTab] = useState<Tab>("for-you");
  const [selected, setSelected] = useState<{ id: number; mediaType: string } | null>(null);
  const [genreFilter, setGenreFilter] = useState<string[]>([]);
  const [forYouType, setForYouType] = useState<"all" | "tv" | "movie">("all");
  const [forYouVisible, setForYouVisible] = useState(24);  // client-side Load More
  const [forYouMeta, setForYouMeta] = useState<{ top_genres?: string[]; based_on?: number; trakt_blended?: boolean; tastedive_blended?: boolean; ai_blended?: boolean } | null>(null);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [tuning, setTuning] = useState(false);
  // After "Mark Seen" or "+ Watchlist", keep the card briefly (showing its new
  // state) then fade it out before it's filtered from the grid.
  const [lingering, setLingering] = useState<Set<number>>(new Set());
  const [fadingOut, setFadingOut] = useState<Set<number>>(new Set());

  function lingerAndFade(id: number) {
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
    !isDismissed(i.id) && !isWatchlisted(i.id) &&
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
                onMarkedSeen={() => lingerAndFade(item.id)}
                onWatchlisted={() => lingerAndFade(item.id)}
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
