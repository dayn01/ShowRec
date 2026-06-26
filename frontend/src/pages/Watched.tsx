import { useState, useEffect } from "react";
import { api, Recommendation } from "../api";
import { useWatched } from "../WatchedContext";
import MediaCard from "../components/MediaCard";
import DetailModal from "../components/DetailModal";
import { SortControl, sortRecommendations } from "../components/SortControl";

type SubTab = "tv" | "movie" | "stopped";

const SORTS = [
  { id: "recent", label: "Recently watched" },
  { id: "title", label: "Title A–Z" },
  { id: "rating", label: "Rating" },
  { id: "release", label: "Release year" },
];

export default function Watched() {
  const { isWatched, showProgress, isStopped } = useWatched();
  const [items, setItems] = useState<Recommendation[]>([]);
  const [stoppedItems, setStoppedItems] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<SubTab>("tv");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");
  const [selected, setSelected] = useState<{ id: number; mediaType: string } | null>(null);
  const [visibleCount, setVisibleCount] = useState(40);

  useEffect(() => {
    api.getWatchedLibrary()
      .then(d => setItems(d.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
    api.getStoppedList().then(d => setStoppedItems(d.items)).catch(() => {});
  }, []);

  // Reset the visible window when the tab, search or sort changes
  useEffect(() => { setVisibleCount(40); }, [tab, query, sort]);

  // Reactively drop items that get unmarked while viewing
  const stillWatched = (i: Recommendation) =>
    i.media_type === "tv" ? showProgress(i.id) === "full" : isWatched(i.id);

  const q = query.trim().toLowerCase();
  // Filter the fetched stopped list by live state so a resume drops it instantly.
  const liveStopped = stoppedItems.filter(i => isStopped(i.id));
  const base = tab === "stopped"
    ? liveStopped
    : items.filter(i => i.media_type === tab && !isStopped(i.id) && stillWatched(i));
  const filtered = base.filter(i => !q || (i.title || i.name || "").toLowerCase().includes(q));
  const visible = sortRecommendations(filtered, sort);
  const shown = visible.slice(0, visibleCount);

  const tvCount = items.filter(i => i.media_type === "tv" && !isStopped(i.id) && stillWatched(i)).length;
  const movieCount = items.filter(i => i.media_type === "movie" && !isStopped(i.id) && stillWatched(i)).length;
  const stoppedCount = liveStopped.length;

  return (
    <div>
      {/* Sub-tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {([
          ["tv", `TV Shows${tvCount ? ` (${tvCount})` : ""}`],
          ["movie", `Films${movieCount ? ` (${movieCount})` : ""}`],
          ...(stoppedCount ? [["stopped", `⏹ Stopped (${stoppedCount})`]] : []),
        ] as [SubTab, string][]).map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{
            padding: "7px 18px", borderRadius: 20, fontSize: 13,
            border: tab === id ? "1px solid var(--accent)" : "1px solid var(--border)",
            background: tab === id ? "var(--accent)" : "var(--surface)",
            color: tab === id ? "#fff" : "var(--muted)",
            fontWeight: tab === id ? 600 : 400, cursor: "pointer", transition: "all 0.15s",
          }}>{label}</button>
        ))}
      </div>

      {/* Search + sort */}
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 20 }}>
        <div style={{ position: "relative", flex: 1, minWidth: 220, maxWidth: 420 }}>
        <span style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "var(--muted)", fontSize: 14 }}>🔍</span>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder={`Search ${tab === "stopped" ? "stopped shows" : tab === "tv" ? "watched shows" : "watched films"}…`}
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
        <SortControl options={SORTS} value={sort} onChange={setSort} />
      </div>

      {loading && (
        <div style={{ color: "var(--muted)", textAlign: "center", padding: 60, fontSize: 14 }}>Loading…</div>
      )}

      {!loading && visible.length === 0 && (
        <div style={{ color: "var(--muted)", textAlign: "center", padding: 60, fontSize: 14 }}>
          {q
            ? `No ${tab === "stopped" ? "stopped shows" : tab === "tv" ? "watched shows" : "watched films"} match "${query}".`
            : tab === "stopped"
            ? <>
                <div style={{ fontSize: 36, marginBottom: 12 }}>⏹</div>
                Shows you stop watching will appear here. Open a show and choose “Stop watching”.
              </>
            : <>
                <div style={{ fontSize: 36, marginBottom: 12 }}>✓</div>
                No watched {tab === "tv" ? "TV shows" : "films"} yet. Mark something as Seen and it'll appear here.
              </>}
        </div>
      )}

      <div className="media-grid">
        {shown.map(item => (
          <MediaCard key={`${item.media_type}-${item.id}`} item={item}
            onClick={() => setSelected({ id: item.id, mediaType: item.media_type })} />
        ))}
      </div>

      {visible.length > shown.length && (
        <div style={{ display: "flex", justifyContent: "center", marginTop: 28 }}>
          <button onClick={() => setVisibleCount(c => c + 40)} style={{
            padding: "10px 32px", borderRadius: 20, border: "1px solid var(--border)",
            background: "var(--surface2)", color: "var(--text)", fontWeight: 600,
            fontSize: 14, cursor: "pointer",
          }}>
            Load more ({visible.length - shown.length} more)
          </button>
        </div>
      )}

      {selected && (
        <DetailModal tmdbId={selected.id} mediaType={selected.mediaType} onClose={() => {
          setSelected(null);
          // Pick up any show just stopped/resumed from the modal.
          api.getStoppedList().then(d => setStoppedItems(d.items)).catch(() => {});
        }} />
      )}
    </div>
  );
}
