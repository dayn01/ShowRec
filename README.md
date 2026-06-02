# ShowRec

A self-hosted TV & film recommendation app that links to your **Jellyfin / Plex /
Trakt** history and **TMDB**, gives you personalised "For You" picks (optionally
AI-enhanced), tracks what you're watching, shows upcoming episodes, and supports
multiple **profiles** for a household.

It runs as two small Docker containers (a FastAPI backend + an nginx-served web
UI) and stores everything in a local SQLite file. No external database needed.

---

## What you'll need

- A machine to run it on (any Linux box, a NAS, or a Raspberry Pi 4/5 with 64-bit OS)
- **Docker** and **Docker Compose** installed
- A free **TMDB API key** (required)
- Optionally: a **Jellyfin** and/or **Plex** server, a **Trakt** account, and an
  **Anthropic** key for the AI features — all optional, the app works without them

---

## 1. Get a TMDB API key (required)

1. Create a free account at <https://www.themoviedb.org/>
2. **Settings → API → Create → Developer**, fill in the short form
   (for "Application URL" you can put `http://localhost`)
3. Copy the **API Key (v3 auth)** — a 32-character string

That's the only mandatory key. Everything else is optional.

## 2. Clone the repo

```bash
git clone <THIS_REPO_URL> showrec
cd showrec
```

## 3. Create your `.env`

```bash
cp .env.example .env
nano .env
```

Fill in what you have. **Only `TMDB_API_KEY` is required** — leave the rest blank
to skip those integrations.

```ini
# Required
TMDB_API_KEY=your_tmdb_key

# Optional — connect your media server (use a LAN IP or domain, NOT localhost,
# because the app runs inside Docker)
JELLYFIN_URL=http://192.168.1.10:8096
JELLYFIN_API_KEY=...
JELLYFIN_USER_ID=...

# Optional — Plex
PLEX_URL=http://192.168.1.10:32400
PLEX_TOKEN=...

# Optional — Overseerr/Jellyseerr: adds a "Request" button + availability badges
# that auto-request via Sonarr/Radarr. Works with either (same API). For TV, only
# your unwatched seasons are requested.
OVERSEERR_URL=http://192.168.1.10:5055
OVERSEERR_API_KEY=...

# Optional — Trakt (community ratings + your history/calendar)
TRAKT_CLIENT_ID=...
TRAKT_CLIENT_SECRET=...
TRAKT_ACCESS_TOKEN=...

# Optional — AI picks (pay-as-you-go). Leave blank to disable AI entirely.
ANTHROPIC_API_KEY=...

# Optional — TasteDive: adds a "More Like This" row of similar titles when you
# open a show/film's details. Leave blank to hide it.
TASTEDIVE_API_KEY=...

# Optional — Home Assistant episode notifications (use a LAN IP, not .local)
HA_URL=http://192.168.1.10:8123
HA_TOKEN=...
HA_NOTIFICATION_SERVICE=notify.mobile_app_yourphone
```

<details>
<summary><strong>Where to find the optional keys</strong></summary>

- **Jellyfin API key:** Jellyfin dashboard → Administration → API Keys → +
- **Jellyfin user ID:** Dashboard → Users → click your user → the ID is in the URL,
  or open `http://<jellyfin>/Users` with your API key
- **Plex token:** <https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/>
- **Overseerr/Jellyseerr API key:** in either app → Settings → General → **API Key**.
  Use Jellyseerr if your media server is Jellyfin, Overseerr if it's Plex — the app
  treats them identically (both fill the `OVERSEERR_*` vars). Optional; omit it and
  the Request button + availability badges simply don't appear.
- **Trakt:** create an app at <https://trakt.tv/oauth/applications> (redirect URI
  `urn:ietf:wg:oauth:2.0:oob`) for the client id/secret; the access token needs a
  one-time OAuth exchange (see `get_trakt_token.ps1` for the flow, or any Trakt
  device-code helper). Trakt is **optional** — Jellyfin/Plex alone work fine.
- **Anthropic:** <https://platform.anthropic.com> → API Keys. Pay-as-you-go; a few
  cents per refresh. Omit it and the app simply hides the AI features.
- **TasteDive:** sign in at <https://tastedive.com/account/api_access> and copy
  your free API key. Powers the "More Like This" suggestions on the details
  screen; omit it and that row just doesn't appear.
</details>

> 💡 **Jellyfin/Plex/HA URLs must be reachable from inside Docker.** Use the
> server's **LAN IP** or a domain — never `localhost` (that points at the
> container itself). `.local` mDNS names don't resolve inside Docker either.

## 4. Build and run

```bash
docker compose up -d --build
```

First build takes a few minutes. Then open:

```
http://<your-server-ip>:8087
```

The app starts syncing your history and building recommendations in the
background — watch it with `docker compose logs -f backend` (look for
`Prefetch complete`).

## 5. Set up profiles

Click the **🍿 profile button** (top-right) → **Add profile**. Link each profile
to a Jellyfin/Plex user (or leave it standalone and mark things watched manually).
Each profile gets its own recommendations, watchlist, and watch history.

---

## That's it 🎉

Everyday commands:

```bash
docker compose logs -f             # follow logs
docker compose restart backend     # restart the API
docker compose down                # stop
git pull && docker compose up -d --build   # update to the latest
```

Your data lives in `./data/showrec_cache.db` — back up that file and you've backed
up everything (profiles, watchlist, watch state).

---

## Optional extras

| Want to… | See |
|---|---|
| Reach it by a name like `http://showrec.home` instead of an IP:port | [`DOCKER.md`](DOCKER.md) → "Give it a hostname" |
| Run it on a Raspberry Pi | [`DOCKER.md`](DOCKER.md) — it's ARM-ready (use 64-bit OS) |
| Access it securely over the internet with a login gate | [`CLOUDFLARE.md`](CLOUDFLARE.md) |
| Import your Netflix viewing history | [see below](#import-your-netflix-history) |

### Import your Netflix history

If you've watched on Netflix, you can bulk-import that history so it counts toward
recommendations and shows up as watched.

1. **Download your history from Netflix:**
   <https://www.netflix.com/viewingactivity> → scroll down → **Download all**.
   You get a `NetflixViewingActivity.csv`.

2. **Copy the CSV into the app's data folder** (`./data` is mounted into the
   container). From the machine that has the file:
   ```bash
   # if it's already on the server:
   cp NetflixViewingActivity.csv ~/showrec/data/netflix.csv

   # or copy it from another machine over SSH (run from where the file is):
   scp NetflixViewingActivity.csv USER@SERVER:~/showrec/data/netflix.csv
   ```

3. **Run the importer** — the last number is the **profile id** to import into
   (`1` is the default profile; check the profile menu if you have several):
   ```bash
   docker compose exec backend python import_netflix.py /data/netflix.csv 1
   ```
   It resolves each title against TMDB and prints a summary of how many movies and
   episodes it matched, plus any rows it couldn't match.

4. **Refresh the profile** so "seen" state and recommendations update:
   ```bash
   curl -X POST http://localhost:8087/api/profiles/1/refresh
   ```

> Netflix's export only gives episode *titles* (not numbers) and inconsistent
> season labels, so matching is best-effort — expect a handful of unmatched rows
> (they're listed in the report). It only *adds* watched items and is safe to
> re-run. Watch dates aren't preserved (everything imports as "watched").

---

## How it works (brief)

- **Backend** (FastAPI, port 8000, internal) — syncs your watch history into
  SQLite, builds recommendations from TMDB + your taste profile (genres, themes,
  cast), and optionally re-ranks with Claude.
- **Frontend** (nginx, port 8087) — serves the web UI and proxies `/api` to the
  backend.
- **Sync cadence** — watched state refreshes from your media server **hourly**;
  the full recommendation rebuild runs **every 6 hours** (or on demand via the ↻
  button).
- **AI is optional** — with no `ANTHROPIC_API_KEY` the app runs purely on
  TMDB + your media server, and the AI features are hidden.
- **TasteDive is optional** — with a `TASTEDIVE_API_KEY` set, opening a title's
  details shows a "More Like This" row of similar shows/films (each clickable to
  open its own details); without a key the row is hidden.
- **Requests are optional** — set `OVERSEERR_URL` + `OVERSEERR_API_KEY` (Overseerr
  or Jellyseerr) and each title gains a **Request** button plus availability
  badges (⏳ Requested → ⬇ Downloading → ✓ In Library). Requesting a TV show only
  asks for the seasons you haven't watched. Without the keys, none of it appears.

## Troubleshooting

- **Status dots (top-right) are red** — that integration can't be reached. Most
  often the URL in `.env` uses `localhost`/`.local`; switch to the LAN IP and
  `docker compose up -d --force-recreate`.
- **Backend won't start after editing `.env`** — check for mashed-together lines
  or Windows line endings (`sed -i 's/\r$//' .env`).
- **A profile shows no data** — link it to an account (✎ edit) or hit ↻ to sync;
  standalone profiles stay empty until you mark things watched.
