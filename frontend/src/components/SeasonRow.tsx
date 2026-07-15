import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useWatched } from "../WatchedContext";
import { useIsMobile } from "../useIsMobile";

type WatchState = "idle" | "loading" | "error";

// Per-season Overseerr state → button look. "none" = requestable.
const SEASON_BTN: Record<string, { bg: string; color: string; label: string; mobile: string }> = {
  none:       { bg: "var(--surface2)", color: "var(--text)", label: "⬇ Request",     mobile: "⬇" },
  pending:    { bg: "var(--accent)",   color: "#fff",        label: "⏳ Downloading", mobile: "⏳" },
  processing: { bg: "var(--accent)",   color: "#fff",        label: "⏳ Downloading", mobile: "⏳" },
  partial:    { bg: "var(--yellow)",   color: "#000",        label: "◐ Partial",      mobile: "◐" },
  available:  { bg: "var(--green)",    color: "#000",        label: "✓ Available",    mobile: "✓" },
};

function SeenBtn({ watched, partial, state, onMark, onUnmark, small, mobile }: {
  watched: boolean; partial?: boolean; state: WatchState;
  onMark: () => void; onUnmark: () => void; small?: boolean; mobile?: boolean;
}) {
  const bg = state === "error" ? "var(--red)"
    : watched ? "var(--green)"
    : partial ? "var(--yellow)"
    : "var(--surface2)";
  const color = (watched || partial) ? "#000" : "var(--text)";
  // Compact to an icon on phones so the row's buttons don't overflow the card
  // (the partial "▶ Watching" was the widest and got clipped).
  const label = state === "loading" ? "…"
    : state === "error" ? (mobile ? "✕" : "Error")
    : watched ? (mobile ? "✓" : "✓ Seen")
    : partial ? (mobile ? "▶" : "▶ Watching")
    : (mobile ? "Seen" : "Mark Seen");

  return (
    <button
      onClick={e => { e.stopPropagation(); watched ? onUnmark() : onMark(); }}
      disabled={state === "loading"}
      title={watched ? "Seen — tap to undo" : partial ? "Watching — tap to mark the season seen" : "Mark the season seen"}
      style={{
        padding: mobile ? "5px 9px" : small ? "3px 10px" : "5px 14px",
        borderRadius: 20, border: "1px solid var(--border)",
        cursor: state === "loading" ? "wait" : "pointer",
        fontWeight: 600, fontSize: small ? 11 : 12, whiteSpace: "nowrap", flexShrink: 0,
        background: bg, color,
        transition: "background 0.2s",
      }}
    >
      {label}
    </button>
  );
}

function EpisodeRow({ ep, tmdbId, showTitle, seasonNumber, totalEpisodes }: {
  ep: any; tmdbId: number; showTitle: string; seasonNumber: number; totalEpisodes: number;
}) {
  const { isEpisodeWatched, markEpisodeWatched, markEpisodeUnwatched } = useWatched();
  const watched = isEpisodeWatched(tmdbId, seasonNumber, ep.episode_number);
  const [state, setState] = useState<WatchState>("idle");

  async function mark() {
    setState("loading");
    try {
      await api.markEpisodeWatched(tmdbId, showTitle, seasonNumber, ep.episode_number);
      markEpisodeWatched(tmdbId, seasonNumber, ep.episode_number, totalEpisodes);
      setState("idle");
    } catch { setState("error"); setTimeout(() => setState("idle"), 2500); }
  }

  async function unmark() {
    setState("loading");
    try {
      await api.markEpisodeUnwatched(tmdbId, showTitle, seasonNumber, ep.episode_number);
      markEpisodeUnwatched(tmdbId, seasonNumber, ep.episode_number);
      setState("idle");
    } catch { setState("error"); setTimeout(() => setState("idle"), 2500); }
  }

  const score = ep.vote_average ? Math.round(ep.vote_average * 10) : null;
  const scoreColor = score && score >= 75 ? "var(--green)" : score && score >= 55 ? "var(--yellow)" : "var(--red)";

  // Unaired = has an air_date that is still in the future
  const today = new Date().toISOString().slice(0, 10);
  const isUpcoming = !!ep.air_date && ep.air_date > today;

  return (
    <div style={{
      display: "flex", gap: 12, alignItems: "flex-start",
      padding: "10px 12px", borderRadius: 8,
      background: watched ? "rgba(74,222,128,0.06)" : isUpcoming ? "rgba(124,106,247,0.06)" : "var(--bg)",
      borderLeft: watched ? "3px solid var(--green)" : isUpcoming ? "3px solid var(--accent)" : "3px solid transparent",
      opacity: isUpcoming ? 0.85 : 1,
      transition: "all 0.2s",
    }}>
      {ep.still_url && (
        <img src={ep.still_url} alt={ep.name}
          style={{ width: 80, height: 45, objectFit: "cover", borderRadius: 6, flexShrink: 0 }}
          onError={e => { (e.target as HTMLImageElement).style.display = "none"; }} />
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, color: "var(--muted)", flexShrink: 0 }}>E{String(ep.episode_number).padStart(2, "0")}</span>
          <span style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ep.name}</span>
          {isUpcoming && (
            <span style={{
              background: "var(--accent)", color: "#fff", borderRadius: 10,
              padding: "1px 7px", fontSize: 10, fontWeight: 700, flexShrink: 0,
            }}>📅 {fmtUpcoming(ep.air_date)}</span>
          )}
          {!isUpcoming && score && <span style={{ fontSize: 11, color: scoreColor, flexShrink: 0 }}>{score}%</span>}
          {ep.runtime && <span style={{ fontSize: 11, color: "var(--muted)", flexShrink: 0 }}>{ep.runtime}m</span>}
          {ep.air_date && !isUpcoming && <span style={{ fontSize: 11, color: "var(--muted)", flexShrink: 0 }}>{ep.air_date}</span>}
          {ep.available && (
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--green)", flexShrink: 0 }}
              title="Available in your library">● On server</span>
          )}
          {ep.available && ep.play_url && (
            <a href={ep.play_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
              title="Play in Jellyfin"
              style={{
                fontSize: 10, fontWeight: 700, color: "#000", background: "var(--green)",
                borderRadius: 10, padding: "1px 8px", flexShrink: 0, textDecoration: "none",
              }}>▶ Play</a>
          )}
        </div>
        {ep.overview && (
          <div style={{
            fontSize: 12, color: "var(--muted)", marginTop: 3,
            display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
          }}>{ep.overview}</div>
        )}
      </div>
      {isUpcoming ? (
        <span style={{
          fontSize: 11, color: "var(--accent2)", fontWeight: 600,
          whiteSpace: "nowrap", flexShrink: 0, padding: "5px 10px",
        }}>Not aired</span>
      ) : (
        <SeenBtn watched={watched} state={state} onMark={mark} onUnmark={unmark} small />
      )}
    </div>
  );
}

function fmtUpcoming(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((d.getTime() - today.getTime()) / 86400000);
  if (diff === 0) return "today";
  if (diff === 1) return "tomorrow";
  if (diff > 1 && diff <= 14) return `in ${diff}d`;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

interface Props {
  season: {
    season_number: number; name: string; episode_count: number;
    air_date?: string; poster_url: string | null; overview?: string;
  };
  tmdbId: number;
  showTitle: string;
  autoExpand?: boolean;
  upcomingEpisode?: {        // Next unaired episode in this season
    episode_number: number;
    name: string;
    air_date: string;
  } | null;
}

export default function SeasonRow({ season, tmdbId, showTitle, autoExpand = false, upcomingEpisode = null }: Props) {
  const [expanded, setExpanded] = useState(autoExpand);
  const [state, setState] = useState<WatchState>("idle");

  const { isSeasonWatched, seasonProgress, markSeasonWatched, markSeasonUnwatched, updateSeasonTotal } = useWatched();
  const watched = isSeasonWatched(tmdbId, season.season_number);
  const progress = seasonProgress(tmdbId, season.season_number);

  // Per-season request (Overseerr/Jellyseerr). Shares the cached enabled flag.
  const { data: reqStatuses } = useQuery({
    queryKey: ["request-statuses"],
    queryFn: api.getRequestStatuses,
    staleTime: 1000 * 60 * 2,
  });
  const requestEnabled = !!reqStatuses?.enabled;
  // Per-show status (incl. per-season) — shares DetailModal's cache.
  const { data: showReq } = useQuery({
    queryKey: ["request-status", "tv", tmdbId],
    queryFn: () => api.getRequestStatus("tv", tmdbId),
    staleTime: 1000 * 60 * 5,
    enabled: requestEnabled,
  });
  const seasonStatus = showReq?.seasons?.[String(season.season_number)];
  const [reqState, setReqState] = useState<"idle" | "sending" | "done" | "error">("idle");
  // Effective season state for the button: an in-flight/just-sent click reads as
  // "processing"; otherwise the Overseerr per-season status (none = requestable).
  const effStatus = reqState === "done" ? "processing"
    : (seasonStatus && seasonStatus !== "unknown" ? seasonStatus : "none");
  const seasonRequested = effStatus !== "none";   // anything but "none" disables re-request
  // A still-downloading request can be cancelled; "available"/"partial" are on disk.
  const cancelable = effStatus === "pending" || effStatus === "processing";
  const [cancelState, setCancelState] = useState<"idle" | "canceling">("idle");
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();

  async function requestSeason(e: React.MouseEvent) {
    e.stopPropagation();
    if (reqState === "sending" || reqState === "done") return;
    setReqState("sending");
    try {
      await api.requestMedia(tmdbId, "tv", [season.season_number]);
      setReqState("done");
      // Optimistically flip the cached statuses so this season (and the card badge)
      // read "Downloading" instantly — surviving a remount — before Jellyseerr
      // propagates, then invalidate to reconcile. Mirrors cancelSeason(); without
      // it the season snaps back to "Request" on reopen and you re-request.
      const sk = String(season.season_number);
      queryClient.setQueryData(["request-status", "tv", tmdbId], (old: any) =>
        old ? { ...old, seasons: { ...(old.seasons || {}), [sk]: "processing" } } : old);
      queryClient.setQueryData(["request-statuses"], (old: any) =>
        old?.statuses ? { ...old, statuses: { ...old.statuses, [String(tmdbId)]: "processing" } } : old);
      queryClient.invalidateQueries({ queryKey: ["request-status", "tv", tmdbId] });
      queryClient.invalidateQueries({ queryKey: ["request-statuses"] });
    } catch {
      setReqState("error");
      setTimeout(() => setReqState("idle"), 2500);
    }
  }

  async function cancelSeason(e: React.MouseEvent) {
    e.stopPropagation();
    if (cancelState === "canceling") return;
    setCancelState("canceling");
    try {
      await api.cancelRequest(tmdbId, "tv", [season.season_number]);
      setReqState("idle");
      // Refetch the per-show status so this (and any seasons cancelled alongside it)
      // flip back to requestable; refresh the bulk map too so card badges update.
      queryClient.invalidateQueries({ queryKey: ["request-status", "tv", tmdbId] });
      queryClient.invalidateQueries({ queryKey: ["request-statuses"] });
    } catch {
      // leave the request button as-is; user can retry
    } finally {
      setCancelState("idle");
    }
  }

  const { data: episodeData, isLoading } = useQuery({
    queryKey: ["season", tmdbId, season.season_number],
    queryFn: () => api.getSeasonEpisodes(tmdbId, season.season_number),
    enabled: expanded,
  });

  // Correct the total whenever TMDB episode list loads
  useEffect(() => {
    if (episodeData?.episodes?.length) {
      updateSeasonTotal(tmdbId, season.season_number, episodeData.episodes.length);
    }
  }, [episodeData]);

  async function markSeason() {
    setState("loading");
    try {
      // Get the episode list — from already-loaded data, or fetch it now if the
      // season was never expanded.
      let episodes = episodeData?.episodes;
      if (!episodes?.length) {
        try {
          const data = await api.getSeasonEpisodes(tmdbId, season.season_number);
          episodes = data.episodes;
        } catch { /* fall back to count-only */ }
      }

      // Only mark episodes that have actually aired — applied to whichever list we
      // obtained (previously the aired filter was skipped on the fetch-now path,
      // so marking a collapsed season also marked unaired episodes).
      const today = new Date().toISOString().slice(0, 10);
      const epNumbers = episodes?.length
        ? episodes
            .filter(ep => !ep.air_date || ep.air_date <= today)
            .map(ep => ep.episode_number)
        : undefined;

      await api.markSeasonWatched(tmdbId, showTitle, season.season_number, epNumbers);
      markSeasonWatched(tmdbId, season.season_number, season.episode_count, epNumbers);
      setState("idle");
    } catch { setState("error"); setTimeout(() => setState("idle"), 2500); }
  }

  async function unmarkSeason() {
    setState("loading");
    try {
      await api.markSeasonUnwatched(tmdbId, showTitle, season.season_number);
      markSeasonUnwatched(tmdbId, season.season_number);
      setState("idle");
    } catch { setState("error"); setTimeout(() => setState("idle"), 2500); }
  }

  const isFullyWatched = watched; // isSeasonWatched: watched >= total && total > 0
  const isPartial = !isFullyWatched && progress && progress.watched > 0;
  const hasUpcoming = !!upcomingEpisode;
  const borderColor = isFullyWatched ? "var(--green)"
    : isPartial ? "var(--yellow)"
    : hasUpcoming ? "var(--accent)"
    : "transparent";
  const displayTotal = progress?.total > 0 ? progress.total : season.episode_count;

  function fmtAirDate(iso: string): string {
    const d = new Date(iso + "T00:00:00");
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const diff = Math.round((d.getTime() - today.getTime()) / 86400000);
    if (diff === 0) return "today";
    if (diff === 1) return "tomorrow";
    if (diff > 1 && diff <= 14) return `in ${diff} days`;
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  }

  return (
    <div style={{
      background: "var(--surface2)", border: "1px solid var(--border)",
      borderRadius: 10, overflow: "hidden",
      borderLeft: `3px solid ${borderColor}`,
      transition: "border-color 0.2s",
    }}>
      {/* Season header */}
      <div
        onClick={() => setExpanded(v => !v)}
        style={{ padding: "12px 16px", display: "flex", gap: 14, alignItems: "center", cursor: "pointer" }}
      >
        {season.poster_url && (
          <img src={season.poster_url} alt={season.name}
            style={{ width: 44, height: 66, objectFit: "cover", borderRadius: 6, flexShrink: 0 }}
            onError={e => { (e.target as HTMLImageElement).style.display = "none"; }} />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{season.name}</div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <span>{season.episode_count} episodes{season.air_date ? ` · ${season.air_date.slice(0, 4)}` : ""}</span>
            {progress && progress.watched > 0 && (
              <span style={{
                background: isFullyWatched ? "var(--green)" : "var(--yellow)",
                color: "#000", borderRadius: 10, padding: "1px 7px", fontSize: 10, fontWeight: 700,
              }}>
                {progress.watched}/{displayTotal} watched
              </span>
            )}
            {hasUpcoming && (
              <span style={{
                background: "var(--accent)", color: "#fff", borderRadius: 10,
                padding: "1px 8px", fontSize: 10, fontWeight: 700,
              }}>
                📅 E{upcomingEpisode!.episode_number} {fmtAirDate(upcomingEpisode!.air_date)}
              </span>
            )}
          </div>
          {season.overview && !expanded && (
            <div style={{
              fontSize: 12, color: "var(--muted)", marginTop: 4,
              display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
            }}>{season.overview}</div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {requestEnabled && (() => {
            const cfg = SEASON_BTN[effStatus] ?? SEASON_BTN.none;
            const sending = reqState === "sending";
            const error = reqState === "error";
            const title = effStatus === "available" ? "This season is on your server"
              : effStatus === "partial" ? "Some episodes are available"
              : effStatus !== "none" ? "Waiting on download"
              : "Request this season via Overseerr/Jellyseerr";
            const canceling = cancelState === "canceling";
            return (
              <>
                <button
                  onClick={requestSeason}
                  disabled={sending || seasonRequested}
                  title={title}
                  style={{
                    padding: isMobile ? "5px 9px" : "5px 12px",
                    borderRadius: 20, border: "1px solid var(--border)",
                    cursor: sending ? "wait" : seasonRequested ? "default" : "pointer",
                    fontWeight: 600, fontSize: 12, whiteSpace: "nowrap", flexShrink: 0,
                    background: error ? "var(--red)" : cfg.bg,
                    color: error ? "#fff" : cfg.color,
                    transition: "background 0.2s",
                  }}
                >
                  {isMobile
                    ? (sending ? "…" : error ? "✕" : cfg.mobile)
                    : (sending ? "Requesting…" : error ? "Error" : cfg.label)}
                </button>
                {cancelable && (
                  <button
                    onClick={cancelSeason}
                    disabled={canceling}
                    title="Cancel this season's request"
                    style={{
                      padding: isMobile ? "5px 9px" : "5px 12px",
                      borderRadius: 20, border: "1px solid var(--border)",
                      cursor: canceling ? "wait" : "pointer",
                      fontWeight: 600, fontSize: 12, whiteSpace: "nowrap", flexShrink: 0,
                      background: "var(--surface2)", color: "var(--muted)",
                      transition: "background 0.2s",
                    }}
                  >
                    {canceling ? "…" : (isMobile ? "✕" : "✕ Cancel")}
                  </button>
                )}
              </>
            );
          })()}
          <SeenBtn watched={isFullyWatched} partial={!!isPartial} state={state} onMark={markSeason} onUnmark={unmarkSeason} mobile={isMobile} />
          <span style={{ color: "var(--muted)", fontSize: 14, userSelect: "none" }}>
            {expanded ? "▲" : "▼"}
          </span>
        </div>
      </div>

      {/* Episodes */}
      {expanded && (
        <div style={{ borderTop: "1px solid var(--border)", padding: "8px 12px", display: "flex", flexDirection: "column", gap: 4 }}>
          {isLoading && (
            <div style={{ color: "var(--muted)", fontSize: 13, padding: 12, textAlign: "center" }}>Loading episodes…</div>
          )}
          {episodeData?.episodes.map(ep => (
            <EpisodeRow
              key={ep.episode_number}
              ep={ep}
              tmdbId={tmdbId}
              showTitle={showTitle}
              seasonNumber={season.season_number}
              totalEpisodes={episodeData.episodes.length}
            />
          ))}
        </div>
      )}
    </div>
  );
}
