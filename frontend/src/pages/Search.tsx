import { useState, useEffect, useRef } from "react";
import { api, Recommendation } from "../api";
import MediaCard from "../components/MediaCard";
import DetailModal from "../components/DetailModal";

type FilterType = "multi" | "tv" | "movie";

export default function Search() {
  const [query, setQuery] = useState("");
  const [type, setType] = useState<FilterType>("multi");
  const [results, setResults] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [selected, setSelected] = useState<{ id: number; mediaType: string } | null>(null);
  const debounce = useRef<number | undefined>(undefined);

  // "Similar to" discovery (TasteDive). Works without the AI Custom Search.
  const [tasteDive, setTasteDive] = useState(false);
  const [similarFor, setSimilarFor] = useState<Recommendation | null>(null);
  const [similarItems, setSimilarItems] = useState<Recommendation[]>([]);
  const [similarLoading, setSimilarLoading] = useState(false);

  useEffect(() => {
    api.getStatus().then(s => setTasteDive(!!s.tastedive)).catch(() => {});
  }, []);

  async function showSimilar(item: Recommendation) {
    setSimilarFor(item);
    setSimilarItems([]);
    setSimilarLoading(true);
    try {
      const data = await api.getSimilar(item.media_type, item.id);
      setSimilarItems(data.results);
    } catch {
      setSimilarItems([]);
    } finally {
      setSimilarLoading(false);
    }
  }

  // Debounced live search
  useEffect(() => {
    if (debounce.current) window.clearTimeout(debounce.current);
    setSimilarFor(null);   // a new query exits the "similar to" view
    if (query.trim().length < 2) {
      setResults([]); setSearched(false); return;
    }
    debounce.current = window.setTimeout(async () => {
      setLoading(true);
      try {
        const data = await api.searchTitles(query.trim(), type);
        setResults(data.results);
        setSearched(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 350);
    return () => { if (debounce.current) window.clearTimeout(debounce.current); };
  }, [query, type]);

  const similarTitle = similarFor?.title || similarFor?.name || "";

  return (
    <div>
      {/* Search bar */}
      <div style={{ position: "relative", marginBottom: 16 }}>
        <span style={{ position: "absolute", left: 16, top: "50%", transform: "translateY(-50%)", fontSize: 16, color: "var(--muted)" }}>🔍</span>
        <input
          autoFocus
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search for any TV show or film…"
          style={{
            width: "100%", padding: "14px 16px 14px 44px",
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 12, color: "var(--text)", fontSize: 16, outline: "none",
          }}
          onFocus={e => { e.target.style.borderColor = "var(--accent)"; }}
          onBlur={e => { e.target.style.borderColor = "var(--border)"; }}
        />
      </div>

      {/* Type filter */}
      <div style={{ display: "flex", gap: 6, marginBottom: 24 }}>
        {([["multi", "All"], ["tv", "TV Shows"], ["movie", "Films"]] as const).map(([id, label]) => (
          <button key={id} onClick={() => setType(id)} style={{
            padding: "5px 14px", borderRadius: 20, fontSize: 12,
            border: type === id ? "1px solid var(--accent)" : "1px solid var(--border)",
            background: type === id ? "rgba(124,106,247,0.15)" : "var(--surface2)",
            color: type === id ? "var(--accent2)" : "var(--muted)",
            fontWeight: type === id ? 600 : 400, cursor: "pointer", transition: "all 0.15s",
          }}>{label}</button>
        ))}
      </div>

      {/* ── Similar-to view ── */}
      {similarFor ? (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 16, fontWeight: 700 }}>
              Similar to <span style={{ color: "var(--accent2)" }}>{similarTitle}</span>
            </h2>
            <button onClick={() => setSimilarFor(null)} style={{
              padding: "4px 12px", borderRadius: 20, fontSize: 12, cursor: "pointer",
              border: "1px solid var(--border)", background: "var(--surface2)", color: "var(--muted)",
            }}>← Back to results</button>
          </div>

          {similarLoading && (
            <div style={{ color: "var(--muted)", textAlign: "center", padding: 40, fontSize: 14 }}>Finding similar titles…</div>
          )}
          {!similarLoading && similarItems.length === 0 && (
            <div style={{ color: "var(--muted)", textAlign: "center", padding: 40, fontSize: 14 }}>
              No similar titles found for "{similarTitle}".
            </div>
          )}

          <div className="media-grid">
            {similarItems.map(item => (
              <MediaCard key={`${item.media_type}-${item.id}`} item={item}
                onClick={() => setSelected({ id: item.id, mediaType: item.media_type })}
                onSimilar={tasteDive ? () => showSimilar(item) : undefined} />
            ))}
          </div>
        </div>
      ) : (
        /* ── Normal search results ── */
        <>
          {query.trim().length < 2 && (
            <div style={{ color: "var(--muted)", textAlign: "center", padding: 60, fontSize: 14 }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>🔍</div>
              Type at least 2 characters to search the TMDB catalogue.
            </div>
          )}

          {loading && (
            <div style={{ color: "var(--muted)", textAlign: "center", padding: 40, fontSize: 14 }}>Searching…</div>
          )}

          {searched && !loading && results.length === 0 && (
            <div style={{ color: "var(--muted)", textAlign: "center", padding: 40, fontSize: 14 }}>
              No results for "{query}".
            </div>
          )}

          <div className="media-grid">
            {results.map(item => (
              <MediaCard key={`${item.media_type}-${item.id}`} item={item}
                onClick={() => setSelected({ id: item.id, mediaType: item.media_type })}
                onSimilar={tasteDive ? () => showSimilar(item) : undefined} />
            ))}
          </div>
        </>
      )}

      {selected && (
        <DetailModal tmdbId={selected.id} mediaType={selected.mediaType} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
