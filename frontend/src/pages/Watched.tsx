import { useState, useEffect } from "react";
import { api, Recommendation } from "../api";
import { useWatched } from "../WatchedContext";
import MediaCard from "../components/MediaCard";
import DetailModal from "../components/DetailModal";

type SubTab = "tv" | "movie";

export default function Watched() {
  const { isWatched, showProgress } = useWatched();
  const [items, setItems] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<SubTab>("tv");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<{ id: number; mediaType: string } | null>(null);

  useEffect(() => {
    api.getWatchedLibrary()
      .then(d => setItems(d.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  // Reactively drop items that get unmarked while viewing
  const stillWatched = (i: Recommendation) =>
    i.media_type === "tv" ? showProgress(i.id) === "full" : isWatched(i.id);

  const q = query.trim().toLowerCase();
  const visible = items
    .filter(i => i.media_type === tab)
    .filter(stillWatched)
    .filter(i => !q || (i.title || i.name || "").toLowerCase().includes(q));

  const tvCount = items.filter(i => i.media_type === "tv" && stillWatched(i)).length;
  const movieCount = items.filter(i => i.media_type === "movie" && stillWatched(i)).length;

  return (
    <div>
      {/* Sub-tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {([["tv", `TV Shows${tvCount ? ` (${tvCount})` : ""}`], ["movie", `Films${movieCount ? ` (${movieCount})` : ""}`]] as const).map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{
            padding: "7px 18px", borderRadius: 20, fontSize: 13,
            border: tab === id ? "1px solid var(--accent)" : "1px solid var(--border)",
            background: tab === id ? "var(--accent)" : "var(--surface)",
            color: tab === id ? "#fff" : "var(--muted)",
            fontWeight: tab === id ? 600 : 400, cursor: "pointer", transition: "all 0.15s",
          }}>{label}</button>
        ))}
      </div>

      {/* Search */}
      <div style={{ position: "relative", marginBottom: 20, maxWidth: 420 }}>
        <span style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "var(--muted)", fontSize: 14 }}>🔍</span>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder={`Search watched ${tab === "tv" ? "shows" : "films"}…`}
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

      {loading && (
        <div style={{ color: "var(--muted)", textAlign: "center", padding: 60, fontSize: 14 }}>Loading…</div>
      )}

      {!loading && visible.length === 0 && (
        <div style={{ color: "var(--muted)", textAlign: "center", padding: 60, fontSize: 14 }}>
          {q
            ? `No watched ${tab === "tv" ? "shows" : "films"} match "${query}".`
            : <>
                <div style={{ fontSize: 36, marginBottom: 12 }}>✓</div>
                No watched {tab === "tv" ? "TV shows" : "films"} yet. Mark something as Seen and it'll appear here.
              </>}
        </div>
      )}

      <div className="media-grid">
        {visible.map(item => (
          <MediaCard key={`${item.media_type}-${item.id}`} item={item}
            onClick={() => setSelected({ id: item.id, mediaType: item.media_type })} />
        ))}
      </div>

      {selected && (
        <DetailModal tmdbId={selected.id} mediaType={selected.mediaType} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
