import { useState, useEffect } from "react";
import { api, Recommendation } from "../api";
import { useWatched } from "../WatchedContext";
import MediaCard from "../components/MediaCard";
import DetailModal from "../components/DetailModal";
import { GenreFilter, applyGenreFilter } from "../components/GenreFilter";
import { SortControl, sortRecommendations } from "../components/SortControl";

const SORTS = [
  { id: "smart", label: "Smart (availability)" },
  { id: "added", label: "Recently added" },
  { id: "title", label: "Title A–Z" },
  { id: "rating", label: "Rating" },
  { id: "release", label: "Release year" },
];

export default function Watchlist() {
  const { isWatchlisted, isDismissed, isOwned, isEpisodeWatched } = useWatched();
  const [items, setItems] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<{ id: number; mediaType: string } | null>(null);
  const [genreFilter, setGenreFilter] = useState<string[]>([]);
  const [sort, setSort] = useState("smart");
  const [availMap, setAvailMap] = useState<Record<string, [number, number]>>({});

  useEffect(() => {
    api.getWatchlist()
      .then(d => setItems(d.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
    api.getAvailableEpisodes().then(d => setAvailMap(d.items || {})).catch(() => {});
  }, []);

  // A TV show with a newer downloaded episode you haven't watched.
  const hasEpisodeAvailable = (id: number) => {
    const a = availMap[String(id)];
    return a ? !isEpisodeWatched(id, a[0], a[1]) : false;
  };

  // Reactively drop items removed from the watchlist or marked "not interested".
  // Order by weight: on Jellyfin/Plex → newer episode of a show you're watching →
  // a season released recently (TMDB) → most recently added (backend: newest first).
  const onList = items.filter(i => isWatchlisted(i.id) && !isDismissed(i.id));
  const weight = (item: Recommendation, idx: number) =>
    (isOwned(item.id) ? 1_000_000 : 0) +
    (hasEpisodeAvailable(item.id) ? 100_000 : 0) +
    (item.new_season ? 10_000 : 0) +     // a season just dropped on TMDB
    (onList.length - idx);               // recency (earlier index = newer)
  const ranked = onList
    .map((item, idx) => ({ item, idx }))
    .sort((a, b) => weight(b.item, b.idx) - weight(a.item, a.idx))
    .map(x => x.item);
  // "smart" = the weighted availability order; "added" keeps the backend's
  // newest-first order; the rest are generic sorts.
  const ordered = sort === "smart" ? ranked
    : sort === "added" ? onList
    : sortRecommendations(onList, sort);
  const visible = applyGenreFilter(ordered, genreFilter);

  if (loading) {
    return <div style={{ color: "var(--muted)", textAlign: "center", padding: 60 }}>Loading…</div>;
  }

  if (onList.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 80, color: "var(--muted)" }}>
        <div style={{ fontSize: 40, marginBottom: 16 }}>🔖</div>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Your watchlist is empty</div>
        <div style={{ fontSize: 14 }}>Tap the + on any title to save it here for later.</div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 16 }}>
        <p style={{ color: "var(--muted)", fontSize: 13, margin: 0 }}>
          {genreFilter.length > 0
            ? `${visible.length} of ${onList.length} titles`
            : `${onList.length} title${onList.length !== 1 ? "s" : ""} saved to watch`}
        </p>
        <span style={{ marginLeft: "auto" }}>
          <SortControl options={SORTS} value={sort} onChange={setSort} />
        </span>
      </div>

      <GenreFilter items={onList} selected={genreFilter} onChange={setGenreFilter} />

      {visible.length === 0 ? (
        <div style={{ color: "var(--muted)", textAlign: "center", padding: 40, fontSize: 14 }}>
          No watchlist titles match the selected genres.
        </div>
      ) : (
        <div className="media-grid">
          {visible.map(item => (
            <MediaCard key={`${item.media_type}-${item.id}`} item={item}
              onClick={() => setSelected({ id: item.id, mediaType: item.media_type })} />
          ))}
        </div>
      )}

      {selected && (
        <DetailModal tmdbId={selected.id} mediaType={selected.mediaType} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
