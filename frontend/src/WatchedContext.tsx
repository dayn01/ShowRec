import { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from "react";
import { getProfileId } from "./api";

const pidHeaders = () => ({ "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) });

const epKey = (tmdbId: number, season: number, episode: number) => `${tmdbId}_${season}_${episode}`;
const sKey = (tmdbId: number, season: number) => `${tmdbId}_${season}`;

export interface SeasonProgress {
  watched: number;  // episodes watched (from Trakt/user actions)
  total: number;    // TMDB episode count (source of truth — 0 = not yet known)
}

interface WatchedContextType {
  isWatched: (tmdbId: number) => boolean;
  markWatched: (tmdbId: number) => void;
  markUnwatched: (tmdbId: number) => void;
  markShowComplete: (tmdbId: number, seasons: { season_number: number; total: number; watched: number[] }[]) => void;
  showProgress: (tmdbId: number) => "none" | "partial" | "full";
  partiallyWatchedIds: number[];

  // Called when show detail opens — seeds TMDB totals for all seasons at once
  initSeasonTotals: (tmdbId: number, seasons: { season_number: number; episode_count: number }[]) => void;
  updateSeasonTotal: (tmdbId: number, season: number, total: number) => void;

  isSeasonWatched: (tmdbId: number, season: number) => boolean;
  seasonProgress: (tmdbId: number, season: number) => SeasonProgress | null;
  markSeasonWatched: (tmdbId: number, season: number, total: number, episodeNumbers?: number[]) => void;
  markSeasonUnwatched: (tmdbId: number, season: number) => void;

  isEpisodeWatched: (tmdbId: number, season: number, episode: number) => boolean;
  markEpisodeWatched: (tmdbId: number, season: number, episode: number, totalEpisodes?: number) => void;
  markEpisodeUnwatched: (tmdbId: number, season: number, episode: number) => void;

  // Thumbs: 👎 = "not interested" (dismiss), 👍 = liked (positive taste signal)
  isDismissed: (tmdbId: number) => boolean;
  dismiss: (tmdbId: number, mediaType: string, title: string) => void;
  undismiss: (tmdbId: number, mediaType: string) => void;
  isLiked: (tmdbId: number) => boolean;
  like: (tmdbId: number, mediaType: string, title: string) => void;
  unlike: (tmdbId: number, mediaType: string) => void;

  // Watchlist
  isWatchlisted: (tmdbId: number) => boolean;
  toggleWatchlist: (item: any) => void;

  // In the connected Jellyfin/Plex library
  isOwned: (tmdbId: number) => boolean;
  ownedLink: (tmdbId: number) => { source: string; url: string | null } | null;
}

const WatchedContext = createContext<WatchedContextType>({
  isWatched: () => false, markWatched: () => {}, markUnwatched: () => {}, markShowComplete: () => {},
  showProgress: () => "none", partiallyWatchedIds: [],
  initSeasonTotals: () => {}, updateSeasonTotal: () => {},
  isSeasonWatched: () => false, seasonProgress: () => null,
  markSeasonWatched: () => {}, markSeasonUnwatched: () => {},
  isEpisodeWatched: () => false, markEpisodeWatched: () => {}, markEpisodeUnwatched: () => {},
  isDismissed: () => false, dismiss: () => {}, undismiss: () => {},
  isLiked: () => false, like: () => {}, unlike: () => {},
  isWatchlisted: () => false, toggleWatchlist: () => {},
  isOwned: () => false, ownedLink: () => null,
});

function loadSet(key: string): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(key) || "[]")); } catch { return new Set(); }
}
function saveSet(key: string, s: Set<string>) {
  localStorage.setItem(key, JSON.stringify([...s]));
}
function loadMap(key: string): Map<string, SeasonProgress> {
  try { return new Map(JSON.parse(localStorage.getItem(key) || "[]")); } catch { return new Map(); }
}
function saveMap(key: string, m: Map<string, SeasonProgress>) {
  localStorage.setItem(key, JSON.stringify([...m]));
}

export function WatchedProvider({ children }: { children: ReactNode }) {
  // One-time reset of stale watch-state caches. Bump WC_VERSION whenever the
  // backend watch-state shape changes so old (wrong) localStorage is discarded.
  // The DB is the source of truth and re-seeds on load, so this is safe.
  const WC_VERSION = "4";
  if (typeof window !== "undefined" && localStorage.getItem("wc_version") !== WC_VERSION) {
    ["wc_shows", "wc_episodes", "wc_progress", "wc_seasons", "wc_season_progress"]
      .forEach(k => localStorage.removeItem(k));
    localStorage.setItem("wc_version", WC_VERSION);
  }

  const [watchedShows, setWatchedShows] = useState<Set<string>>(() => loadSet("wc_shows"));
  const [watchedEpisodes, setWatchedEpisodes] = useState<Set<string>>(() => loadSet("wc_episodes"));
  const [progressMap, setProgressMap] = useState<Map<string, SeasonProgress>>(() => loadMap("wc_progress"));
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(() => loadSet("wc_dismissed"));
  const [likedIds, setLikedIds] = useState<Set<string>>(() => loadSet("wc_liked"));
  const [watchlistIds, setWatchlistIds] = useState<Set<string>>(() => loadSet("wc_watchlist"));
  const [ownedMap, setOwnedMap] = useState<Record<string, { source: string; url: string | null }>>({});

  useEffect(() => { saveSet("wc_shows", watchedShows); }, [watchedShows]);
  useEffect(() => { saveSet("wc_episodes", watchedEpisodes); }, [watchedEpisodes]);
  useEffect(() => { saveMap("wc_progress", progressMap); }, [progressMap]);
  useEffect(() => { saveSet("wc_dismissed", dismissedIds); }, [dismissedIds]);
  useEffect(() => { saveSet("wc_liked", likedIds); }, [likedIds]);
  useEffect(() => { saveSet("wc_watchlist", watchlistIds); }, [watchlistIds]);

  // Load dismissals + watchlist from backend
  useEffect(() => {
    fetch("/api/watched/dismissed", { headers: pidHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        // Replace (not merge) so a re-synced account doesn't keep old dismissals.
        if (data) setDismissedIds(new Set((data.tmdb_ids ?? []).map(String)));
      })
      .catch(() => {});
    fetch("/api/watched/liked", { headers: pidHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setLikedIds(new Set((data.tmdb_ids ?? []).map(String))); })
      .catch(() => {});
    fetch("/api/watchlist/ids", { headers: pidHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        setWatchlistIds(new Set((data?.tmdb_ids ?? []).map(String)));
      })
      .catch(() => {});
    // What's already in the Jellyfin/Plex library (for the "in library" badge + play link)
    fetch("/api/library/owned", { headers: pidHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.items) setOwnedMap(data.items); })
      .catch(() => {});
  }, []);

  // Apply a watch-state payload. The DB is the source of truth, so we REPLACE the
  // local watch sets rather than merging — otherwise a wiped / re-synced (or
  // switched) account leaves the previous account's items in localStorage and they
  // keep showing in "Watching". Only called on a successful response.
  const applyWatchState = useCallback((data: any) => {
    if (!data) return;
    const fullIds = [...(data.tmdb_ids ?? []), ...(data.complete_tmdb_ids ?? [])];
    setWatchedShows(new Set(fullIds.map(String)));

    const eps = new Set<string>();
    (data.episodes ?? []).forEach((e: any) => eps.add(epKey(e.tmdb_id, e.season, e.episode)));
    setWatchedEpisodes(eps);

    setProgressMap(prev => {
      const m = new Map<string, SeasonProgress>();
      for (const [k, v] of prev) if (v.total > 0) m.set(k, { watched: 0, total: v.total });
      (data.seasons ?? []).forEach((s: any) => {
        const k = sKey(s.tmdb_id, s.season);
        m.set(k, { watched: s.episodes_watched, total: m.get(k)?.total ?? 0 });
      });
      return m;
    });
  }, []);

  // Fast read of the stored state.
  const loadHistory = useCallback(() => {
    fetch("/api/watched/history", { headers: pidHeaders() })
      .then(r => r.ok ? r.json() : null).then(applyWatchState).catch(() => {});
  }, [applyWatchState]);

  // Pull fresh from Jellyfin/Plex/Trakt, then apply. Debounced via lastSyncRef.
  const lastSyncRef = useRef(0);
  const syncNow = useCallback(() => {
    lastSyncRef.current = Date.now();
    fetch("/api/watched/sync", { method: "POST", headers: pidHeaders() })
      .then(r => r.ok ? r.json() : null).then(applyWatchState).catch(() => {});
  }, [applyWatchState]);

  useEffect(() => {
    loadHistory();   // instant paint from the DB
    syncNow();       // and check Jellyfin/Plex/Trakt right away
    // Re-check Jellyfin when the user returns to the app (debounced to ≤1/min),
    // and refresh the stored view every few minutes for a left-open tab.
    const onFocus = () => { if (Date.now() - lastSyncRef.current > 60_000) syncNow(); };
    const onVis = () => { if (!document.hidden) onFocus(); };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVis);
    const id = window.setInterval(loadHistory, 5 * 60_000);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVis);
      window.clearInterval(id);
    };
  }, [loadHistory, syncNow]);

  // ── Shows ──────────────────────────────────────────────────────────────────
  const isWatched = useCallback((id: number) => watchedShows.has(String(id)), [watchedShows]);
  const markWatched = useCallback((id: number) => setWatchedShows(p => new Set([...p, String(id)])), []);

  const markUnwatched = useCallback((id: number) => {
    setWatchedShows(p => { const s = new Set(p); s.delete(String(id)); return s; });
    // Also clear any season progress + episode marks for this show (clean undo)
    setWatchedEpisodes(p => {
      const s = new Set([...p].filter(k => !k.startsWith(`${id}_`)));
      return s;
    });
    setProgressMap(p => {
      const m = new Map([...p].filter(([k]) => !k.startsWith(`${id}_`)));
      return m;
    });
  }, []);

  // Mark a whole show complete: show flag + every season's progress + episode keys.
  // seasons: [{ season_number, total, watched: number[] }]
  const markShowComplete = useCallback((tmdbId: number, seasons: { season_number: number; total: number; watched: number[] }[]) => {
    setWatchedShows(p => new Set([...p, String(tmdbId)]));
    setProgressMap(p => {
      const m = new Map(p);
      for (const s of seasons) {
        m.set(sKey(tmdbId, s.season_number), { watched: s.watched.length, total: s.total || s.watched.length });
      }
      return m;
    });
    setWatchedEpisodes(p => {
      const set = new Set(p);
      for (const s of seasons) {
        for (const ep of s.watched) set.add(epKey(tmdbId, s.season_number, ep));
      }
      return set;
    });
  }, []);

  const showProgress = useCallback((tmdbId: number): "none" | "partial" | "full" => {
    if (watchedShows.has(String(tmdbId))) return "full";

    const hasAny = [...watchedEpisodes].some(k => k.startsWith(`${tmdbId}_`));
    if (!hasAny) return "none";

    // If all seasons with a known total are fully watched, treat the show as complete
    const showSeasons = [...progressMap.entries()]
      .filter(([k]) => k.startsWith(`${tmdbId}_`))
      .map(([, v]) => v);

    if (showSeasons.length > 0) {
      const allComplete = showSeasons.every(s => s.total > 0 && s.watched >= s.total);
      if (allComplete) return "full";
    }

    return "partial";
  }, [watchedShows, watchedEpisodes, progressMap]);

  const partiallyWatchedIds = (() => {
    const ids = new Set<number>();
    for (const k of watchedEpisodes) {
      const tmdbId = parseInt(k.split("_")[0]);
      if (!watchedShows.has(String(tmdbId))) ids.add(tmdbId);
    }
    return [...ids];
  })();

  // ── Season totals ──────────────────────────────────────────────────────────
  const initSeasonTotals = useCallback((
    tmdbId: number,
    seasons: { season_number: number; episode_count: number }[]
  ) => {
    setProgressMap(prev => {
      const m = new Map(prev);
      let changed = false;
      for (const s of seasons) {
        const k = sKey(tmdbId, s.season_number);
        const existing = m.get(k);
        if (!existing) {
          // No watch data at all — just record the total so progress bar works later
          m.set(k, { watched: 0, total: s.episode_count });
          changed = true;
        } else if (existing.total !== s.episode_count) {
          m.set(k, { ...existing, total: s.episode_count });
          changed = true;
        }
      }
      return changed ? m : prev;
    });
  }, []);

  const updateSeasonTotal = useCallback((tmdbId: number, season: number, total: number) => {
    setProgressMap(prev => {
      const k = sKey(tmdbId, season);
      const existing = prev.get(k);
      if (!existing || existing.total === total) return prev;
      return new Map([...prev, [k, { ...existing, total }]]);
    });
  }, []);

  // ── Season watched state (derived from progress, no separate set) ──────────
  const isSeasonWatched = useCallback((tmdbId: number, season: number): boolean => {
    const p = progressMap.get(sKey(tmdbId, season));
    if (!p) return false;
    if (p.total === 0) return false; // total unknown — can't confirm complete
    return p.watched >= p.total;
  }, [progressMap]);

  const seasonProgress = useCallback((tmdbId: number, season: number): SeasonProgress | null =>
    progressMap.get(sKey(tmdbId, season)) ?? null, [progressMap]);

  const markSeasonWatched = useCallback((tmdbId: number, season: number, total: number, episodeNumbers?: number[]) => {
    setProgressMap(p => new Map([...p, [sKey(tmdbId, season), { watched: total, total }]]));
    if (episodeNumbers?.length) {
      setWatchedEpisodes(prev => {
        const s = new Set(prev);
        episodeNumbers.forEach(ep => s.add(epKey(tmdbId, season, ep)));
        return s;
      });
    }
  }, []);

  const markSeasonUnwatched = useCallback((tmdbId: number, season: number) => {
    const k = sKey(tmdbId, season);
    setProgressMap(p => {
      const existing = p.get(k);
      if (!existing) return p;
      return new Map([...p, [k, { watched: 0, total: existing.total }]]);
    });
    setWatchedEpisodes(p => {
      const s = new Set(p);
      [...s].filter(e => e.startsWith(`${tmdbId}_${season}_`)).forEach(e => s.delete(e));
      return s;
    });
  }, []);

  // ── Episodes ───────────────────────────────────────────────────────────────
  const isEpisodeWatched = useCallback((tmdbId: number, season: number, episode: number) =>
    watchedEpisodes.has(epKey(tmdbId, season, episode)), [watchedEpisodes]);

  const markEpisodeWatched = useCallback((tmdbId: number, season: number, episode: number, totalEpisodes?: number) => {
    const key = epKey(tmdbId, season, episode);
    if (watchedEpisodes.has(key)) return; // already marked
    setWatchedEpisodes(p => new Set([...p, key]));
    setProgressMap(p => {
      const k = sKey(tmdbId, season);
      const current = p.get(k) ?? { watched: 0, total: totalEpisodes ?? 0 };
      return new Map([...p, [k, {
        watched: current.watched + 1,
        total: totalEpisodes ?? current.total,
      }]]);
    });
  }, [watchedEpisodes]);

  const markEpisodeUnwatched = useCallback((tmdbId: number, season: number, episode: number) => {
    const key = epKey(tmdbId, season, episode);
    if (!watchedEpisodes.has(key)) return;
    setWatchedEpisodes(p => { const s = new Set(p); s.delete(key); return s; });
    setProgressMap(p => {
      const k = sKey(tmdbId, season);
      const current = p.get(k);
      if (!current) return p;
      return new Map([...p, [k, { ...current, watched: Math.max(0, current.watched - 1) }]]);
    });
  }, [watchedEpisodes]);

  // ── Dismissals ─────────────────────────────────────────────────────────────
  const isDismissed = useCallback((id: number) => dismissedIds.has(String(id)), [dismissedIds]);

  const dismiss = useCallback((id: number, mediaType: string, title: string) => {
    setDismissedIds(p => new Set([...p, String(id)]));
    setLikedIds(p => { const s = new Set(p); s.delete(String(id)); return s; });  // 👎 clears 👍
    fetch("/api/watched/dismiss", {
      method: "POST", headers: pidHeaders(),
      body: JSON.stringify({ tmdb_id: id, media_type: mediaType, title }),
    }).catch(() => {});
  }, []);

  const undismiss = useCallback((id: number, mediaType: string) => {
    setDismissedIds(p => { const s = new Set(p); s.delete(String(id)); return s; });
    fetch("/api/watched/dismiss", {
      method: "DELETE", headers: pidHeaders(),
      body: JSON.stringify({ tmdb_id: id, media_type: mediaType }),
    }).catch(() => {});
  }, []);

  // ── Liked (👍) ───────────────────────────────────────────────────────────────
  const isLiked = useCallback((id: number) => likedIds.has(String(id)), [likedIds]);

  const like = useCallback((id: number, mediaType: string, title: string) => {
    setLikedIds(p => new Set([...p, String(id)]));
    setDismissedIds(p => { const s = new Set(p); s.delete(String(id)); return s; });  // 👍 clears 👎
    fetch("/api/watched/like", {
      method: "POST", headers: pidHeaders(),
      body: JSON.stringify({ tmdb_id: id, media_type: mediaType, title }),
    }).catch(() => {});
  }, []);

  const unlike = useCallback((id: number, mediaType: string) => {
    setLikedIds(p => { const s = new Set(p); s.delete(String(id)); return s; });
    fetch("/api/watched/like", {
      method: "DELETE", headers: pidHeaders(),
      body: JSON.stringify({ tmdb_id: id, media_type: mediaType }),
    }).catch(() => {});
  }, []);

  // ── Watchlist ──────────────────────────────────────────────────────────────
  const isWatchlisted = useCallback((id: number) => watchlistIds.has(String(id)), [watchlistIds]);

  const toggleWatchlist = useCallback((item: any) => {
    const id = item.id;
    const on = watchlistIds.has(String(id));
    if (on) {
      setWatchlistIds(p => { const s = new Set(p); s.delete(String(id)); return s; });
      fetch("/api/watchlist", {
        method: "DELETE", headers: pidHeaders(),
        body: JSON.stringify({ tmdb_id: id, media_type: item.media_type }),
      }).catch(() => {});
    } else {
      setWatchlistIds(p => new Set([...p, String(id)]));
      fetch("/api/watchlist", {
        method: "POST", headers: pidHeaders(),
        body: JSON.stringify({
          tmdb_id: id, media_type: item.media_type,
          title: item.title || item.name || "", poster_url: item.poster_url,
          vote_average: item.vote_average, overview: item.overview,
          release_date: item.release_date, first_air_date: item.first_air_date,
        }),
      }).catch(() => {});
    }
  }, [watchlistIds]);

  // ── Owned (in Jellyfin/Plex library) ────────────────────────────────────────
  const isOwned = useCallback((id: number) => Boolean(ownedMap[String(id)]), [ownedMap]);
  const ownedLink = useCallback((id: number) => ownedMap[String(id)] ?? null, [ownedMap]);

  return (
    <WatchedContext.Provider value={{
      isWatched, markWatched, markUnwatched, markShowComplete, showProgress, partiallyWatchedIds,
      initSeasonTotals, updateSeasonTotal,
      isSeasonWatched, seasonProgress, markSeasonWatched, markSeasonUnwatched,
      isEpisodeWatched, markEpisodeWatched, markEpisodeUnwatched,
      isDismissed, dismiss, undismiss,
      isLiked, like, unlike,
      isWatchlisted, toggleWatchlist,
      isOwned, ownedLink,
    }}>
      {children}
    </WatchedContext.Provider>
  );
}

export const useWatched = () => useContext(WatchedContext);
