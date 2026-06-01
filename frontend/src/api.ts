const BASE = "/api";

// Active profile id (per-device), sent on every request.
export function getProfileId(): number {
  return parseInt(localStorage.getItem("activeProfileId") || "1") || 1;
}
export function setProfileId(id: number) {
  localStorage.setItem("activeProfileId", String(id));
}
function profileHeaders(): Record<string, string> {
  return { "X-Profile-Id": String(getProfileId()) };
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { headers: profileHeaders() });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function post<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { method: "POST", headers: profileHeaders() });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export interface Profile {
  id: number;
  name: string;
  emoji: string;
  jellyfin_user_id: string | null;
  plex_token: string | null;
  trakt_token: string | null;
}

export interface Recommendation {
  id: number;
  title?: string;
  name?: string;
  overview: string;
  poster_url: string | null;
  vote_average: number;
  media_type: string;
  score: number;
  release_date?: string;
  first_air_date?: string;
  reason?: string;        // AI explanation, when AI-endorsed
  ai_endorsed?: boolean;
}

export interface UpcomingEpisode {
  first_aired: string;
  show: { title: string; ids: { tmdb?: number } };
  episode: { title: string; season: number; number: number; overview: string };
}

export interface Status {
  jellyfin: boolean | null;
  plex: boolean | null;
  home_assistant: boolean | null;
  trakt: boolean;
  tmdb: boolean;
  ai_enabled: boolean;
  tastedive: boolean;
}

export interface DetailedMedia {
  id: number;
  title: string;
  tagline?: string;
  overview: string;
  poster_url: string | null;
  backdrop_url: string | null;
  vote_average: number;
  vote_count: number;
  genres: string[];
  media_type: string;
  status: string;
  homepage?: string;
  // movie
  release_date?: string;
  runtime?: number;
  budget?: number;
  revenue?: number;
  // tv
  first_air_date?: string;
  last_air_date?: string;
  next_episode_to_air?: {
    season_number: number;
    episode_number: number;
    name: string;
    air_date: string;
    overview?: string;
  } | null;
  number_of_seasons?: number;
  number_of_episodes?: number;
  episode_run_time?: number[];
  networks?: string[];
  seasons?: {
    season_number: number;
    name: string;
    episode_count: number;
    air_date?: string;
    poster_url: string | null;
    overview?: string;
  }[];
  cast?: { name: string; character: string; profile_url: string | null }[];
}

export const api = {
  getCustomRecommendations: (body: { media_type: string; genres: string[]; prompt: string }) =>
    fetch("/api/ai-recommendations/custom", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify(body),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),
  getAiRecommendations: () =>
    get<{
      taste_profile: string;
      picks: (Recommendation & { reason: string; reddit_buzz: string | null })[];
      reddit_posts_used: number;
      candidates_analysed: number;
    }>("/ai-recommendations"),
  getRecommendations: (limit = 30) =>
    get<{ recommendations: Recommendation[]; based_on: number; top_genres?: string[]; trakt_blended?: boolean; tastedive_blended?: boolean }>(
      `/recommendations?limit=${limit}`
    ),
  getTrending: (type: "shows" | "movies" = "shows", page = 1) =>
    get<{ trending: any[]; page: number }>(`/recommendations/trending?media_type=${type}&page=${page}`),
  getUpcoming: (days = 30) =>
    get<{ episodes: UpcomingEpisode[]; days: number }>(`/upcoming?days=${days}`),
  triggerNotification: () => post<{ status: string }>("/upcoming/notify-now"),
  getStatus: () => get<Status>("/status"),
  getDetails: (mediaType: string, tmdbId: number) =>
    get<DetailedMedia>(`/details/${mediaType}/${tmdbId}`),
  getSimilar: (mediaType: string, tmdbId: number) =>
    get<{ enabled: boolean; results: Recommendation[] }>(`/details/${mediaType}/${tmdbId}/similar`),
  markWatched: (tmdbId: number, mediaType: string, title: string, year?: number) =>
    fetch(`/api/watched`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify({ tmdb_id: tmdbId, media_type: mediaType, title, year }),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),
  markUnwatched: (tmdbId: number, mediaType: string, title: string) =>
    fetch(`/api/watched`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify({ tmdb_id: tmdbId, media_type: mediaType, title }),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),

  dismiss: (tmdbId: number, mediaType: string, title: string) =>
    fetch(`/api/watched/dismiss`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify({ tmdb_id: tmdbId, media_type: mediaType, title }),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),
  undismiss: (tmdbId: number, mediaType: string) =>
    fetch(`/api/watched/dismiss`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify({ tmdb_id: tmdbId, media_type: mediaType }),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),
  getDismissed: () => get<{ tmdb_ids: number[] }>(`/watched/dismissed`),
  getDismissedList: () => get<{ items: { tmdb_id: number; media_type: string; title: string; poster_url: string | null }[] }>(`/watched/dismissed/list`),

  searchTitles: (query: string, type: "multi" | "tv" | "movie" = "multi") =>
    get<{ results: Recommendation[] }>(`/search?q=${encodeURIComponent(query)}&type=${type}`),

  getWatchedLibrary: () => get<{ items: Recommendation[] }>(`/watched/library`),
  getWatchlist: () => get<{ items: Recommendation[] }>(`/watchlist`),
  getWatchlistIds: () => get<{ tmdb_ids: number[] }>(`/watchlist/ids`),
  addWatchlist: (item: Recommendation) =>
    fetch(`/api/watchlist`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify({
        tmdb_id: item.id, media_type: item.media_type,
        title: item.title || item.name || "", poster_url: item.poster_url,
        vote_average: item.vote_average, overview: item.overview,
        release_date: item.release_date, first_air_date: item.first_air_date,
      }),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),
  removeWatchlist: (tmdbId: number, mediaType: string) =>
    fetch(`/api/watchlist`, {
      method: "DELETE", headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify({ tmdb_id: tmdbId, media_type: mediaType }),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),

  getSeasonEpisodes: (tmdbId: number, seasonNumber: number) =>
    get<{
      season_number: number; name: string; overview: string;
      episodes: {
        id: number; episode_number: number; name: string;
        overview: string; air_date?: string; runtime?: number;
        still_url: string | null; vote_average: number;
      }[];
    }>(`/details/tv/${tmdbId}/season/${seasonNumber}`),

  markSeasonWatched: (tmdbId: number, title: string, seasonNumber: number, episodeNumbers?: number[]) =>
    fetch(`/api/watched/season`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify({ tmdb_id: tmdbId, title, season_number: seasonNumber, episode_numbers: episodeNumbers }),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),

  markSeasonUnwatched: (tmdbId: number, title: string, seasonNumber: number) =>
    fetch(`/api/watched/season`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify({ tmdb_id: tmdbId, title, season_number: seasonNumber }),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),

  markEpisodeWatched: (tmdbId: number, title: string, seasonNumber: number, episodeNumber: number) =>
    fetch(`/api/watched/episode`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify({ tmdb_id: tmdbId, title, season_number: seasonNumber, episode_number: episodeNumber }),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),

  markEpisodeUnwatched: (tmdbId: number, title: string, seasonNumber: number, episodeNumber: number) =>
    fetch(`/api/watched/episode`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify({ tmdb_id: tmdbId, title, season_number: seasonNumber, episode_number: episodeNumber }),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),

  // ── Profiles ──
  getProfiles: () => get<{ profiles: Profile[] }>(`/profiles`),
  getPlexUsers: () => get<{ users: { id: string; title: string; owner: boolean }[] }>(`/plex-users`),
  createProfile: (body: { name: string; emoji: string; jellyfin_user_id?: string | null; plex_user?: string | null }) =>
    fetch(`/api/profiles`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify(body),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() as Promise<Profile>; }),
  updateProfile: (id: number, body: { name?: string; emoji?: string; jellyfin_user_id?: string | null; plex_user?: string | null }) =>
    fetch(`/api/profiles/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "X-Profile-Id": String(getProfileId()) },
      body: JSON.stringify(body),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() as Promise<Profile>; }),
  deleteProfile: (id: number) =>
    fetch(`/api/profiles/${id}`, {
      method: "DELETE",
      headers: { "X-Profile-Id": String(getProfileId()) },
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); }),
  refreshProfile: (id: number, force = true) =>
    fetch(`/api/profiles/${id}/refresh?force=${force}`, {
      method: "POST", headers: { "X-Profile-Id": String(getProfileId()) },
    }).then(r => r.json()),
};
