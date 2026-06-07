import { useEffect, useState } from "react";
import { api, thumb } from "../api";
import { useWatched } from "../WatchedContext";

const PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='60' height='90'%3E%3Crect width='60' height='90' fill='%231a1a24'/%3E%3C/svg%3E";

interface Item {
  tmdb_id: number;
  media_type: string;
  title: string;
  poster_url: string | null;
}

export default function HiddenTitles({ onClose }: { onClose: () => void }) {
  const { undismiss } = useWatched();
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.getDismissedList()
      .then(d => setItems(d.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", h); document.body.style.overflow = ""; };
  }, [onClose]);

  function restore(item: Item) {
    undismiss(item.tmdb_id, item.media_type);
    setItems(prev => prev.filter(i => i.tmdb_id !== item.tmdb_id));
  }

  const q = query.trim().toLowerCase();
  const filtered = q ? items.filter(i => i.title.toLowerCase().includes(q)) : items;

  return (
    <div
      onClick={onClose}
      className="modal-backdrop"
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)", zIndex: 1000,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 24, backdropFilter: "blur(4px)",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="modal-panel"
        style={{
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 16, width: "100%", maxWidth: 560, maxHeight: "85vh",
          display: "flex", flexDirection: "column", overflow: "hidden",
        }}
      >
        {/* Header */}
        <div style={{
          padding: "18px 22px", borderBottom: "1px solid var(--border)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>Hidden Titles</div>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>
              {q ? `${filtered.length} of ${items.length}` : items.length} title{items.length !== 1 ? "s" : ""} marked "not interested"
            </div>
          </div>
          <button onClick={onClose} style={{
            background: "var(--surface2)", border: "1px solid var(--border)",
            color: "#fff", width: 30, height: 30, borderRadius: "50%",
            cursor: "pointer", fontSize: 16, lineHeight: "28px",
          }}>×</button>
        </div>

        {/* Search */}
        {!loading && items.length > 0 && (
          <div style={{ padding: "12px 16px 4px" }}>
            <div style={{ position: "relative" }}>
              <span style={{
                position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)",
                color: "var(--muted)", fontSize: 13, pointerEvents: "none",
              }}>🔍</span>
              <input
                autoFocus
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Search hidden titles…"
                style={{
                  width: "100%", padding: "9px 32px 9px 34px",
                  background: "var(--surface2)", border: "1px solid var(--border)",
                  borderRadius: 10, color: "var(--text)", fontSize: 14, outline: "none",
                }}
                onFocus={e => { e.target.style.borderColor = "var(--accent)"; }}
                onBlur={e => { e.target.style.borderColor = "var(--border)"; }}
              />
              {query && (
                <button
                  onClick={() => setQuery("")}
                  style={{
                    position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)",
                    background: "none", border: "none", color: "var(--muted)",
                    cursor: "pointer", fontSize: 14,
                  }}
                >✕</button>
              )}
            </div>
          </div>
        )}

        {/* Body */}
        <div style={{ overflowY: "auto", padding: "8px 12px" }}>
          {loading && (
            <div style={{ color: "var(--muted)", textAlign: "center", padding: 40, fontSize: 14 }}>Loading…</div>
          )}
          {!loading && items.length === 0 && (
            <div style={{ color: "var(--muted)", textAlign: "center", padding: 50, fontSize: 14 }}>
              <div style={{ fontSize: 32, marginBottom: 10 }}>🙈</div>
              No hidden titles. Click the ✕ on any card to hide it.
            </div>
          )}
          {!loading && items.length > 0 && filtered.length === 0 && (
            <div style={{ color: "var(--muted)", textAlign: "center", padding: 40, fontSize: 14 }}>
              No hidden titles match "{query}".
            </div>
          )}
          {filtered.map(item => (
            <div key={item.tmdb_id} style={{
              display: "flex", gap: 12, alignItems: "center",
              padding: "8px 10px", borderRadius: 10,
            }}>
              <img
                src={thumb(item.poster_url, "w92") || PLACEHOLDER}
                alt={item.title}
                loading="lazy"
                decoding="async"
                style={{ width: 40, height: 60, objectFit: "cover", borderRadius: 6, flexShrink: 0 }}
                onError={e => { (e.target as HTMLImageElement).src = PLACEHOLDER; }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {item.title}
                </div>
                <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase" }}>
                  {item.media_type === "tv" ? "TV" : "Film"}
                </div>
              </div>
              <button
                onClick={() => restore(item)}
                style={{
                  padding: "6px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600,
                  border: "1px solid var(--border)", background: "var(--surface2)",
                  color: "var(--text)", cursor: "pointer", flexShrink: 0,
                }}
              >↩ Restore</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
