import { useState, useEffect } from "react";
import { api, Recommendation } from "../api";
import { useWatched } from "../WatchedContext";
import MediaCard from "../components/MediaCard";
import DetailModal from "../components/DetailModal";

export default function Watchlist() {
  const { isWatchlisted, isDismissed } = useWatched();
  const [items, setItems] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<{ id: number; mediaType: string } | null>(null);

  useEffect(() => {
    api.getWatchlist()
      .then(d => setItems(d.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  // Reactively drop items removed from the watchlist or marked "not interested"
  const visible = items.filter(i => isWatchlisted(i.id) && !isDismissed(i.id));

  if (loading) {
    return <div style={{ color: "var(--muted)", textAlign: "center", padding: 60 }}>Loading…</div>;
  }

  if (visible.length === 0) {
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
      <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 16 }}>
        {visible.length} title{visible.length !== 1 ? "s" : ""} saved to watch
      </p>
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
