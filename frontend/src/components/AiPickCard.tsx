import { useState } from "react";
import { Recommendation, api } from "../api";
import { useWatched } from "../WatchedContext";

const PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='300'%3E%3Crect width='200' height='300' fill='%231a1a24'/%3E%3C/svg%3E";

interface Props {
  item: Recommendation & { reason: string; reddit_buzz: string | null };
  onClick: () => void;
}

export default function AiPickCard({ item, onClick }: Props) {
  const title = item.title || item.name || "Unknown";
  const year = (item.release_date || item.first_air_date || "").slice(0, 4);
  const score = Math.round(item.vote_average * 10);
  const scoreColor = score >= 75 ? "var(--green)" : score >= 55 ? "var(--yellow)" : "var(--red)";

  const { isWatched, markWatched, markUnwatched } = useWatched();
  const watched = isWatched(item.id);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  async function toggleSeen(e: React.MouseEvent) {
    e.stopPropagation();
    if (loading) return;
    setLoading(true);
    try {
      if (watched) {
        await api.markUnwatched(item.id, item.media_type, title);
        markUnwatched(item.id);
      } else {
        await api.markWatched(item.id, item.media_type, title, parseInt(year) || undefined);
        markWatched(item.id);
      }
    } catch {
      setError(true);
      setTimeout(() => setError(false), 2500);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      onClick={onClick}
      style={{
        background: "var(--surface)",
        border: watched ? "1px solid var(--green)" : "1px solid var(--border)",
        borderRadius: 14,
        overflow: "hidden",
        display: "flex",
        gap: 0,
        cursor: "pointer",
        transition: "transform 0.15s, box-shadow 0.15s",
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLElement).style.transform = "translateY(-3px)";
        (e.currentTarget as HTMLElement).style.boxShadow = "0 8px 32px rgba(124,106,247,0.25)";
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLElement).style.transform = "";
        (e.currentTarget as HTMLElement).style.boxShadow = "";
      }}
    >
      {/* Poster */}
      <div style={{ position: "relative", width: 90, flexShrink: 0 }}>
        <img
          src={item.poster_url || PLACEHOLDER}
          alt={title}
          style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          onError={e => { (e.target as HTMLImageElement).src = PLACEHOLDER; }}
        />
        <div style={{
          position: "absolute", top: 6, left: 6,
          background: "var(--accent)", borderRadius: 20,
          padding: "1px 7px", fontSize: 10, fontWeight: 700, color: "#fff",
          textTransform: "uppercase",
        }}>
          {item.media_type === "tv" ? "TV" : "Film"}
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 15, lineHeight: 1.2 }}>{title}</div>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>
              {year}{score > 0 ? ` · ` : ""}{score > 0 && <span style={{ color: scoreColor }}>{score}%</span>}
            </div>
          </div>
          <button
            onClick={toggleSeen}
            disabled={loading}
            style={{
              padding: "4px 12px", borderRadius: 20,
              border: "1px solid var(--border)",
              fontSize: 11, fontWeight: 600, cursor: "pointer", flexShrink: 0,
              background: error ? "var(--red)" : watched ? "var(--green)" : "var(--surface2)",
              color: watched ? "#000" : "var(--text)",
            }}
          >
            {loading ? "…" : error ? "Error" : watched ? "✓ Seen" : "Mark Seen"}
          </button>
        </div>

        {/* AI reason */}
        <div style={{
          fontSize: 13, color: "var(--text)", lineHeight: 1.4,
          borderLeft: "2px solid var(--accent)", paddingLeft: 10,
        }}>
          {item.reason}
        </div>

        {/* Reddit buzz */}
        {item.reddit_buzz && (
          <div style={{
            fontSize: 12, color: "var(--muted)", lineHeight: 1.4,
            background: "var(--surface2)", borderRadius: 8,
            padding: "6px 10px", display: "flex", gap: 6, alignItems: "flex-start",
          }}>
            <span style={{ flexShrink: 0 }}>🔥</span>
            <span>{item.reddit_buzz}</span>
          </div>
        )}
      </div>
    </div>
  );
}
