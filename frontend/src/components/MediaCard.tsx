import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Recommendation, api, thumb } from "../api";
import { useWatched } from "../WatchedContext";
import { useIsMobile } from "../useIsMobile";

// Jellyseerr/Overseerr availability → badge appearance. Absent status = no badge.
const REQUEST_BADGES: Record<string, { label: string; bg: string; color: string }> = {
  available:  { label: "✓ In Library", bg: "var(--green)",  color: "#000" },
  partial:    { label: "◐ Partial",    bg: "var(--yellow)", color: "#000" },
  processing: { label: "⬇ Downloading", bg: "var(--accent)", color: "#fff" },
  pending:    { label: "⏳ Requested",  bg: "var(--accent)", color: "#fff" },
};

const PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='300' viewBox='0 0 200 300'%3E%3Crect width='200' height='300' fill='%231a1a24'/%3E%3Ctext x='100' y='155' text-anchor='middle' fill='%234444aa' font-size='14' font-family='sans-serif'%3ENo Image%3C/text%3E%3C/svg%3E";

export default function MediaCard({ item, onClick, onMarkedSeen, fading, onSimilar, onWatchlisted }: {
  item: Recommendation; onClick: () => void; onMarkedSeen?: () => void; fading?: boolean;
  onSimilar?: () => void; onWatchlisted?: () => void;
}) {
  const title = item.title || item.name || "Unknown";
  const year = (item.release_date || item.first_air_date || "").slice(0, 4);
  const score = Math.round(item.vote_average * 10);
  const scoreColor = score >= 75 ? "var(--green)" : score >= 55 ? "var(--yellow)" : "var(--red)";

  const { isWatched, markWatched, markUnwatched, markShowComplete, showProgress, dismiss, undismiss,
          isLiked, like, unlike, isWatchlisted, toggleWatchlist } = useWatched();
  const watched = isWatched(item.id);
  const onWatchlist = isWatchlisted(item.id);
  const liked = isLiked(item.id);

  function thumbDown(e: React.MouseEvent) {
    e.stopPropagation();
    dismiss(item.id, item.media_type, title);   // 👎 = not interested (hidden from recs)
  }

  function thumbUp(e: React.MouseEvent) {
    e.stopPropagation();
    if (liked) unlike(item.id, item.media_type);
    else like(item.id, item.media_type, title);
  }

  function watchlistClick(e: React.MouseEvent) {
    e.stopPropagation();
    const adding = !onWatchlist;
    toggleWatchlist(item);
    if (adding) onWatchlisted?.();   // let the parent linger + fade before removing it
  }
  const progress = item.media_type === "tv" ? showProgress(item.id) : (watched ? "full" : "none");
  const borderColor = progress === "full" ? "var(--green)" : progress === "partial" ? "var(--yellow)" : "var(--border)";

  // Bulk Jellyseerr/Overseerr status map (one shared fetch across all cards).
  const { data: reqStatuses } = useQuery({
    queryKey: ["request-statuses"],
    queryFn: api.getRequestStatuses,
    staleTime: 1000 * 60 * 2,
  });
  const reqBadge = reqStatuses?.enabled
    ? REQUEST_BADGES[reqStatuses.statuses[item.id]]
    : undefined;
  // On mobile the poster corner is crowded → show the badge in the content area
  // (where the description blurb is hidden) instead.
  const isMobile = useIsMobile();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  // Drive hover-only buttons from JS state, not CSS :hover. CSS :hover sticks to
  // whatever sits under a stationary cursor after a card is dismissed and the grid
  // reflows — which made the next tile show a (red) dismiss X without being moused
  // onto. mouseenter only fires on real pointer movement, so this avoids that.
  const [hovered, setHovered] = useState(false);

  async function toggleSeen(e: React.MouseEvent) {
    e.stopPropagation();
    if (loading) return;
    setLoading(true);
    try {
      if (watched) {
        await api.markUnwatched(item.id, item.media_type, title);
        markUnwatched(item.id);
      } else {
        const res: any = await api.markWatched(item.id, item.media_type, title, parseInt(year) || undefined);
        if (item.media_type === "tv" && res?.seasons) markShowComplete(item.id, res.seasons);
        else markWatched(item.id);
        onMarkedSeen?.();   // let the parent linger + fade the card before removing it
      }
    } catch {
      setError(true);
      setTimeout(() => setError(false), 2500);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div onClick={onClick} style={{
      background: "var(--surface)",
      border: `1px solid ${borderColor}`,
      borderRadius: 12,
      overflow: "hidden",
      display: "flex",
      flexDirection: "column",
      transition: "transform 0.15s, box-shadow 0.15s, opacity 0.45s",
      opacity: fading ? 0 : 1,
      pointerEvents: fading ? "none" : undefined,
      cursor: "pointer",
    }}
      onMouseEnter={e => {
        setHovered(true);
        (e.currentTarget as HTMLElement).style.transform = "translateY(-4px)";
        (e.currentTarget as HTMLElement).style.boxShadow = "0 8px 32px rgba(124,106,247,0.2)";
      }}
      onMouseLeave={e => {
        setHovered(false);
        (e.currentTarget as HTMLElement).style.transform = "";
        (e.currentTarget as HTMLElement).style.boxShadow = "";
      }}
    >
      <div style={{ position: "relative", aspectRatio: "2/3", overflow: "hidden" }}>
        <img
          src={thumb(item.poster_url, "w342") || PLACEHOLDER}
          alt={title}
          loading="lazy"
          decoding="async"
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
          onError={e => { (e.target as HTMLImageElement).src = PLACEHOLDER; }}
        />
        <div style={{
          position: "absolute", top: 8, right: 8,
          background: "rgba(0,0,0,0.75)", borderRadius: 20,
          padding: "2px 8px", fontSize: 12, fontWeight: 700, color: scoreColor,
        }}>
          {score > 0 ? `${score}%` : "N/A"}
        </div>
        {/* Thumbs — under the score badge, appear on hover (👍 stays lit when liked) */}
        <div className="dismiss-btn" style={{
          position: "absolute", top: 38, right: 8, display: "flex", flexDirection: "column", gap: 6,
          opacity: hovered || liked ? 1 : 0, transition: "opacity 0.15s",
        }}>
          <button
            onClick={thumbUp}
            title={liked ? "Liked — click to undo" : "I like this (more like it)"}
            style={{
              background: liked ? "var(--accent)" : "rgba(0,0,0,0.75)", border: "none", borderRadius: "50%",
              width: 24, height: 24, cursor: "pointer", color: "#fff",
              fontSize: 12, lineHeight: "24px", textAlign: "center", padding: 0,
            }}
          >👍</button>
          <button
            onClick={thumbDown}
            title="Not interested — hide this"
            style={{
              background: "rgba(0,0,0,0.75)", border: "none", borderRadius: "50%",
              width: 24, height: 24, cursor: "pointer", color: "#fff",
              fontSize: 12, lineHeight: "24px", textAlign: "center", padding: 0,
            }}
          >👎</button>
        </div>
        <div style={{
          position: "absolute", top: 8, left: 8,
          background: "var(--accent)", borderRadius: 20,
          padding: "2px 8px", fontSize: 11, fontWeight: 600, color: "#fff",
          textTransform: "uppercase", letterSpacing: 0.5,
        }}>
          {item.media_type === "tv" ? "TV" : "Film"}
        </div>
        {item.ai_endorsed && (
          <div style={{
            position: "absolute", top: 34, left: 8,
            background: "rgba(124,106,247,0.9)", borderRadius: 20,
            padding: "2px 8px", fontSize: 10, fontWeight: 700, color: "#fff",
          }}>✨ AI Pick</div>
        )}
        {item.new_season && (
          <div style={{
            position: "absolute", bottom: 8, left: 8, right: 8,
            background: "rgba(224,184,108,0.95)", borderRadius: 8,
            padding: "3px 8px", fontSize: 10, fontWeight: 700, color: "#000",
            textAlign: "center", lineHeight: 1.3,
          }}>🆕 {item.reason || "New season"}</div>
        )}
        {/* Jellyseerr/Overseerr status: requested/downloading → flips to ✓ when in library.
            Desktop: poster corner. Mobile: moved to the content area below (less crowded). */}
        {!isMobile && reqBadge && (
          <div style={{
            position: "absolute", top: item.ai_endorsed ? 60 : 34, left: 8,
            background: reqBadge.bg, borderRadius: 20,
            padding: "2px 8px", fontSize: 10, fontWeight: 700, color: reqBadge.color,
          }}>{reqBadge.label}</div>
        )}

        <div style={{
          position: "absolute", bottom: 0, left: 0, right: 0,
          background: "linear-gradient(transparent, rgba(0,0,0,0.85))",
          padding: "24px 8px 8px",
          display: "flex", flexDirection: "column", alignItems: "center", gap: 5,
          opacity: (watched || onWatchlist || hovered) ? 1 : 0,
        }}
          className="seen-overlay"
        >
          <button
            onClick={toggleSeen}
            disabled={loading}
            style={{
              padding: "5px 14px", borderRadius: 20, border: "none",
              fontSize: 12, fontWeight: 600, cursor: "pointer",
              background: error ? "var(--red)" : watched ? "var(--green)" : progress === "partial" ? "var(--yellow)" : "rgba(255,255,255,0.2)",
              color: (watched || progress === "partial") ? "#000" : "#fff",
              backdropFilter: "blur(4px)",
              transition: "background 0.2s",
            }}
          >
            {loading ? "…" : error ? "Error" : watched ? "✓ Seen" : progress === "partial" ? "▶ Watching" : "Mark Seen"}
          </button>
          <button
            onClick={watchlistClick}
            title={onWatchlist ? "Remove from watchlist" : "Add to watchlist"}
            style={{
              padding: "5px 14px", borderRadius: 20, border: "none",
              fontSize: 12, fontWeight: 600, cursor: "pointer",
              background: onWatchlist ? "var(--accent)" : "rgba(255,255,255,0.2)",
              color: "#fff", backdropFilter: "blur(4px)", transition: "background 0.2s",
            }}
          >
            {onWatchlist ? "✓ Watchlist" : "+ Watchlist"}
          </button>
          {onSimilar && (
            <button
              onClick={e => { e.stopPropagation(); onSimilar(); }}
              title="Find similar titles"
              style={{
                padding: "5px 14px", borderRadius: 20, border: "none",
                fontSize: 12, fontWeight: 600, cursor: "pointer",
                background: "rgba(255,255,255,0.2)", color: "#fff",
                backdropFilter: "blur(4px)", transition: "background 0.2s",
              }}
            >
              ≈ Similar
            </button>
          )}
        </div>
      </div>

      <div style={{ padding: "12px 14px", flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ fontWeight: 600, fontSize: 14, lineHeight: 1.3 }}>{title}</div>
        {year && <div style={{ fontSize: 12, color: "var(--muted)" }}>{year}</div>}
        {item.reason ? (
          <div className="card-blurb" style={{
            fontSize: 12, color: "var(--text)", marginTop: 4, lineHeight: 1.4,
            borderLeft: "2px solid var(--accent)", paddingLeft: 8,
            display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden",
          }}>
            <span style={{ color: "var(--accent2)" }}>✨ </span>{item.reason}
          </div>
        ) : (
          <div className="card-blurb" style={{
            fontSize: 12, color: "var(--muted)", marginTop: 4,
            display: "-webkit-box", WebkitLineClamp: 3,
            WebkitBoxOrient: "vertical", overflow: "hidden",
          }}>
            {item.overview || "No description available."}
          </div>
        )}
        {/* Mobile: availability badge sits where the (hidden) blurb was, bottom-centered. */}
        {isMobile && reqBadge && (
          <div style={{
            marginTop: "auto", alignSelf: "center",
            background: reqBadge.bg, borderRadius: 20,
            padding: "3px 12px", fontSize: 11, fontWeight: 700, color: reqBadge.color,
          }}>{reqBadge.label}</div>
        )}
      </div>
    </div>
  );
}
