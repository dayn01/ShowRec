# Show Recommendation App — Setup Guide

## Prerequisites
- Python 3.11+
- Node.js 20+ (download from nodejs.org)

## 1. Get your API keys

| Service | Where to get it |
|---------|----------------|
| TMDB | themoviedb.org → Settings → API (free) |
| Trakt | trakt.tv/oauth/applications → New App (free) |
| Jellyfin API key | Jellyfin dashboard → Administration → API Keys |
| Jellyfin User ID | Jellyfin dashboard → Users → click your user → copy ID from URL |
| Plex token | See: support.plex.tv/articles/204059436 |
| Home Assistant token | HA → Profile → Long-Lived Access Tokens → Create |

## 2. Configure environment

```
cp .env.example .env
```

Edit `.env` and fill in your keys. You only need to fill in the services you use —
Jellyfin, Plex, and Home Assistant are all optional.

## 3. Get a Trakt access token

Run this once to authenticate with Trakt:

```
cd backend
pip install httpx python-dotenv
python -c "
import asyncio, httpx, os
from dotenv import load_dotenv
load_dotenv('../.env')
client_id = os.environ['TRAKT_CLIENT_ID']
client_secret = os.environ['TRAKT_CLIENT_SECRET']

async def auth():
    async with httpx.AsyncClient() as c:
        r = await c.post('https://api.trakt.tv/oauth/device/code',
            json={'client_id': client_id})
        data = r.json()
        print(f'Go to: {data[\"verification_url\"]}')
        print(f'Enter code: {data[\"user_code\"]}')
        input('Press Enter after authorizing...')
        r2 = await c.post('https://api.trakt.tv/oauth/device/token',
            json={'code': data['device_code'], 'client_id': client_id, 'client_secret': client_secret})
        token = r2.json()['access_token']
        print(f'TRAKT_ACCESS_TOKEN={token}')
        print('Copy this into your .env file')

asyncio.run(auth())
"
```

## 4. Start the backend

```
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

API runs at http://localhost:8000 — view docs at http://localhost:8000/docs

## 5. Start the frontend

```
cd frontend
npm install
npm run dev
```

App runs at http://localhost:5173

## Home Assistant notifications

The backend checks for new episodes daily at 08:00 and sends a push notification
via Home Assistant. Your `HA_NOTIFICATION_SERVICE` should be something like:
- `notify.mobile_app_your_phone` — phone notification
- `notify.persistent_notification` — shows in HA UI sidebar

You can also trigger it manually from the Upcoming page in the app.
