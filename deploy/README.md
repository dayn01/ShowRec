# Deploying ShowRec on a Raspberry Pi 3 Model B

This runs the app as **one process**: uvicorn serves the FastAPI backend *and*
the built React frontend from `frontend/dist`. No Docker, no nginx — the lightest
footprint for the Pi's 1 GB of RAM.

- **OS:** Raspberry Pi OS **Lite (64-bit)**, Bookworm — headless, no desktop.
- **Access:** open `http://<pi-ip>` from any device on your network (port 80).

You build the frontend on your PC (fast) and copy the result to the Pi. The Pi
only ever runs Python.

---

## 1. Flash & first boot (on your PC)

Use **Raspberry Pi Imager** → choose *Raspberry Pi OS Lite (64-bit)*. Click the
gear (⚙) before writing and set:

- hostname (e.g. `showrec`)
- **Enable SSH** + create your user (these instructions assume user `pi`)
- Wi-Fi SSID/password (or use Ethernet)

Boot the Pi, then from your PC:

```powershell
ssh pi@showrec.local      # or ssh pi@<pi-ip>
```

## 2. Prepare the Pi (over SSH)

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3-venv python3-pip git

# A little swap is cheap insurance on a 1 GB board.
sudo dphys-swapconfig                                 # (optional) review settings
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo systemctl restart dphys-swapfile

mkdir -p ~/show-rec/data
```

## 3. Build the frontend (on your PC)

```powershell
cd "D:\My Docks\Show Recomendation App\frontend"
npm install
npm run build          # outputs frontend\dist
```

> Tip: building on the Pi 3 works but is slow and RAM-hungry. Build on the PC.

## 4. Copy the code to the Pi (from your PC)

Run the helper, or do it by hand:

```powershell
cd "D:\My Docks\Show Recomendation App"
./deploy/copy-to-pi.ps1 -PiHost pi@showrec.local
```

What it copies: `backend/` (minus its venv), `frontend/dist/`, and `.env`.

## 5. Install Python deps & the service (on the Pi, over SSH)

```bash
cd ~/show-rec/backend
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt        # prebuilt ARM64 wheels — no compiling

# Install the systemd unit
sudo cp ~/show-rec/deploy/showrec.service /etc/systemd/system/showrec.service
#  ↳ open it and check the User / paths match if you didn't use pi + /home/pi/show-rec
sudo systemctl daemon-reload
sudo systemctl enable --now showrec.service
```

Check it:

```bash
systemctl status showrec.service
journalctl -u showrec.service -f        # live logs (Ctrl-C to stop watching)
```

Then browse to **http://showrec.local** (or `http://<pi-ip>`) — no port needed.

---

## Updating later

After changing code:

```powershell
# PC: rebuild frontend if you touched it, then re-copy
cd "D:\My Docks\Show Recomendation App\frontend"; npm run build
cd "D:\My Docks\Show Recomendation App"; ./deploy/copy-to-pi.ps1 -PiHost pi@showrec.local
```

```bash
# Pi: pick up new backend deps (if requirements changed) and restart
cd ~/show-rec/backend && ./venv/bin/pip install -r requirements.txt
sudo systemctl restart showrec.service
```

## First-run setup wizard

On a **fresh** install (no `.env`, or no TMDB key yet), opening the app shows a
one-time setup wizard instead of the dashboard. It starts with a **checklist**
of which integrations to configure, then shows a page only for the ones you tick:

1. **TMDB key** (required) — with a "Test key" button.
2. **Jellyfin** (optional) — enter the URL + API key, hit *Connect*, then pick
   **which account is yours** from the dropdown.
3. **Optional** — Anthropic (AI picks), Trakt, Plex, Overseerr, Home Assistant,
   TasteDive — only the ones you ticked.

On finish it writes everything to `~/show-rec/.env` and starts the first sync.
A TMDB key now being present is what marks the app as configured, so the wizard
never reappears — a freshly-deployed Pi is configured entirely from the browser.

Notes:
- "Configured" == a TMDB key is present. No flag is written to `.env`, so this
  is safe even where `.env` is mounted read-only (the Docker stack).
- If you deployed with an `.env` already filled in (like this guide does), the
  app is already configured, so the wizard is skipped.
- Changing the **Jellyfin account** in the wizard auto-wipes the old synced data
  and re-syncs the new account cleanly.
- **To re-run setup later**, SSH in, clear `.env`, and restart:
  ```bash
  mv ~/show-rec/.env ~/show-rec/.env.old
  sudo systemctl restart showrec
  ```
- Day-to-day account relinking doesn't need the wizard — the profile dropdown
  (✎ edit a profile) lets you pick a Jellyfin/Plex account anytime.

## Importing Netflix history

`import_netflix.py` is a one-off CLI script — it works on the Pi, but it **must
write to the same database the service uses**, so pass the matching `DB_PATH`:

```bash
# copy your Netflix "Viewing Activity" CSV to ~/show-rec/data/ first, then:
cd ~/show-rec/backend
DB_PATH=~/show-rec/data/showrec_cache.db ./venv/bin/python import_netflix.py ~/show-rec/data/netflix.csv 1
#                                                                            ^CSV path        ^profile id
curl -X POST http://localhost/api/profiles/1/refresh      # rebuild recs with the new 'seen' state
```

The app and the import share one SQLite file. The import is quick, but if you hit
a transient `database is locked`, stop the service first, import, then start it:

```bash
sudo systemctl stop showrec && \
  DB_PATH=~/show-rec/data/showrec_cache.db ./venv/bin/python import_netflix.py ~/show-rec/data/netflix.csv 1 && \
  sudo systemctl start showrec
```

## Notes

- **Port 80** is set in the unit. Binding a port below 1024 as the non-root `pi`
  user is allowed via `AmbientCapabilities=CAP_NET_BIND_SERVICE` (already in the
  unit). If something else already uses port 80 (another web server), either stop
  it or change `--port 80` back to a high port like `--port 8000` and drop the
  `AmbientCapabilities` line.
- **The `.env`** holds your API keys / Plex URL. `config.py` reads it from the
  project root (`~/show-rec/.env`), so keep it there.
- **Data persists** in `~/show-rec/data/showrec_cache.db` across restarts and
  redeploys (it's outside the copied folders).
- **CORS:** unchanged — same-origin in this setup, and the existing rule already
  allows LAN origins, so nothing to configure.
