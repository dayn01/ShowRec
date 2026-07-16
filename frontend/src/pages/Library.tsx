import { useState, useEffect } from "react";
import { api, Recommendation } from "../api";
import MediaCard from "../components/MediaCard";
import DetailModal from "../components/DetailModal";
import { GenreFilter, applyGenreFilter } from "../components/GenreFilter";
import { SortControl, sortRecommendations } from "../components/SortControl";

const SORTS = [
  { id: "added", label: "Recently added" },
  { id: "title", label: "Title A–Z" },
  { id: "rating", label: "Rating" },
  { id: "release", label: "Release year" },
];

export default function Library() {
  const [items, setItems] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<{ id: number; mediaType: string } | null>(null);
  const [genreFilter, setGenreFilter] = useState<string[]>([]);
  const [typeFilter, setTypeFilter] = useState<"all" | "tv" | "movie">("all");
  const [sort, setSort] = useState("added");

  useEffect(() => {
    api.getAllLibrary()
      .then(d => setItems(d.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const hasTv = items.some(i => i.media_type === "tv");
  const hasMovie = items.some(i => i.media_type === "movie");
  // Narrow to the chosen media type before genre/sort so counts and genre chips
  // reflect only what's on screen.
  const typed = typeFilter === "all" ? items : items.filter(i => i.media_type === typeFilter);
  // "added" (newest on the server first) is Library-specific; the rest are the
  // shared generic sorts. Items with no known added-date sink to the bottom.
  const ordered = sort === "added"
    ? [...typed].sort((a, b) => (b.added ?? 0) - (a.added ?? 0))
    : sortRecommendations(typed, sort);
  const visible = applyGenreFilter(ordered, genreFilter);

  if (loading) {
    return <div style={{ color: "var(--muted)", textAlign: "center", padding: 60 }}>Loading your library…</div>;
  }

  if (items.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 80, color: "var(--muted)" }}>
        <div style={{ fontSize: 40, marginBottom: 16 }}>🎞️</div>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Your library is empty</div>
        <div style={{ fontSize: 14 }}>
          Connect Jellyfin or Plex in Setup — everything on your server shows up here.
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 16 }}>
        <p style={{ color: "var(--muted)", fontSize: 13, margin: 0 }}>
          {genreFilter.length > 0 || typeFilter !== "all"
            ? `${visible.length} of ${items.length} titles`
            : `${items.length} title${items.length !== 1 ? "s" : ""} on your server`}
        </p>
        {hasTv && hasMovie && (
          <div style={{ display: "flex", gap: 6 }}>
            {([["all", "All"], ["tv", "TV Shows"], ["movie", "Movies"]] as const).map(([id, label]) => (
              <button key={id} onClick={() => setTypeFilter(id)} style={{
                padding: "4px 12px", borderRadius: 20, fontSize: 12, cursor: "pointer",
                border: typeFilter === id ? "1px solid var(--accent)" : "1px solid var(--border)",
                background: typeFilter === id ? "rgba(124,106,247,0.15)" : "var(--surface2)",
                color: typeFilter === id ? "var(--accent2)" : "var(--muted)",
                fontWeight: typeFilter === id ? 600 : 400, transition: "all 0.15s",
              }}>{label}</button>
            ))}
          </div>
        )}
        <span style={{ marginLeft: "auto" }}>
          <SortControl options={SORTS} value={sort} onChange={setSort} />
        </span>
      </div>

      <GenreFilter items={typed} selected={genreFilter} onChange={setGenreFilter} />

      {visible.length === 0 ? (
        <div style={{ color: "var(--muted)", textAlign: "center", padding: 40, fontSize: 14 }}>
          No library titles match the current filters.
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
