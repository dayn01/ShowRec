# Running ShowRec in Docker (on your Jellyfin server)

Two containers:
- **showrec-backend** — FastAPI (internal only, port 8000)
- **showrec** — nginx serving the web UI + proxying `/api` to the backend (published on port **8087**)

---

## 1. Prerequisites

- Docker + Docker Compose on the server
- Your filled-in `.env` in the project root (TMDB key, Trakt, Jellyfin URL/key, etc.)

> The Jellyfin URL in `.env` must be reachable **from inside Docker**. If Jellyfin
> runs on the same host, use the server's LAN IP (e.g. `http://192.168.1.10:8096`)
> rather than `localhost` — `localhost` inside a container is the container itself.
> If Jellyfin is also in Docker on the same compose network, you can use its
> service name.

## 2. Keep your existing data (optional)

Your watch history / profiles / watchlist live in `showrec_cache.db`. To carry it
into the container, move it into the `data/` folder the compose file mounts:

```bash
mkdir -p data
mv showrec_cache.db data/        # skip this for a fresh start
```

## 3. Build & run

```bash
cd "/path/to/Show Recomendation App"
docker compose up -d --build
```

Open **http://<server-ip>:8087**. First run builds recommendations in the
background (watch `docker compose logs -f backend`).

Common commands:
```bash
docker compose logs -f            # follow logs
docker compose restart backend    # restart just the API
docker compose down               # stop
docker compose up -d --build      # rebuild after code changes
```

---

## 4. Give it a hostname on your router

So you can open **http://showrec** instead of an IP:port. Pick whichever fits your setup.

### Option A — Router / Pi-hole / AdGuard local DNS  (easiest, works everywhere)
Add a local DNS record pointing a name at the server's IP:
```
showrec.home   →   192.168.1.10     (your server's LAN IP)
```
- **Pi-hole:** Local DNS → DNS Records → add `showrec.home` → server IP
- **AdGuard Home:** Filters → DNS rewrites → add `showrec.home` → server IP
- **Most routers:** look for "Static DNS", "Local DNS", or "Host names" / "Address Reservation"

Then browse to `http://showrec.home:8087` (or set the published port to `80` in
`docker-compose.yml` — change `"8087:80"` to `"80:80"` — to drop the port: `http://showrec.home`).

### Option B — `.local` via mDNS  (no router config)
If the host runs Avahi (most Linux servers do), publish an alias so `showrec.local`
resolves to the server:
```bash
sudo apt install avahi-utils
# run in the background (or add to a systemd unit / @reboot cron):
avahi-publish -a -R showrec.local $(hostname -I | awk '{print $1}')
```
Then browse to `http://showrec.local:8087`.

### Option C — Dedicated LAN IP + hostname  (advanced, macvlan)
Gives the container its **own IP** on your LAN, which the router registers like a
real device. Edit `docker-compose.macvlan.yml` (subnet, gateway, parent interface,
and a free static IP), then:
```bash
docker compose -f docker-compose.yml -f docker-compose.macvlan.yml up -d --build
```
The UI is then at `http://<that-ip>` (port 80) and the container advertises hostname
`showrec`. Note: with macvlan the host itself can't talk to the container directly —
fine if you browse from other devices.

---

## 5. Updating

```bash
git pull          # or copy new files over
docker compose up -d --build
```

Your data in `data/showrec_cache.db` is preserved across rebuilds.
