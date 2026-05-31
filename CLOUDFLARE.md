# Exposing ShowRec to the internet with Cloudflare Tunnel + Access

This gives you a secure public URL (e.g. `https://showrec.doengineering.com.au`)
with a **login gate** in front of it — no port forwarding, free TLS, and the
tunnel connects *outbound* so nothing is exposed on your router.

You'll do three things:
1. Create a **Tunnel** (the secure pipe from your server to Cloudflare)
2. Add a **public hostname** that routes to the app
3. Add an **Access policy** so only you/your family can log in

---

## Prerequisites

- Your domain (`doengineering.com.au`) is on Cloudflare (it is — your Jellyfin uses it)
- A free **Cloudflare Zero Trust** team set up (dash.cloudflare.com → Zero Trust → follow the one-time onboarding; the free plan covers up to 50 users)

---

## 1. Create the tunnel

1. Go to **Cloudflare dashboard → Zero Trust → Networks → Tunnels → Create a tunnel**
2. Choose **Cloudflared**, name it `showrec`, **Save**
3. On the "Install connector" screen, **copy the token** — it's the long
   `eyJ...` string in the install command (just the token, not the whole command)
4. On your server, add it to `.env`:
   ```bash
   cd ~/showrec
   echo "TUNNEL_TOKEN=eyJ...paste-your-token..." >> .env
   ```

## 2. Start the tunnel container

```bash
cd ~/showrec
docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml up -d
```

Back in the dashboard the tunnel should flip to **HEALTHY** within ~30 seconds.

## 3. Add the public hostname (routing)

Still in the tunnel's config (**Public Hostname → Add a public hostname**):
- **Subdomain:** `showrec`
- **Domain:** `doengineering.com.au`
- **Type:** `HTTP`
- **URL:** `frontend:80`

> `frontend:80` works because the tunnel container runs on the same Docker
> network as the app and resolves the `frontend` service by name. Cloudflare
> terminates HTTPS for you, so plain HTTP here is correct.

Save. `https://showrec.doengineering.com.au` is now live — but **lock it down before sharing it** (next step).

## 4. Put a login gate in front (Access)

1. **Zero Trust → Access → Applications → Add an application → Self-hosted**
2. **Application name:** ShowRec
3. **Subdomain/domain:** `showrec` / `doengineering.com.au`
4. **Add a policy:**
   - **Policy name:** Allow household
   - **Action:** Allow
   - **Include → Emails** → add the email addresses allowed in (yours + family),
     or **Emails ending in** `@yourdomain` if you have your own email domain
5. Save. Configure the login method under **Settings → Authentication** — the
   built-in **One-time PIN** (emailed code) needs no setup; or add Google/GitHub.

Now visiting `https://showrec.doengineering.com.au` shows a Cloudflare login;
only the allowed emails get through to the app.

---

## Tidy up (optional)

Once the tunnel works you don't need the local port published. In
`docker-compose.yml`, remove or comment the frontend `ports:` block:
```yaml
  frontend:
    # ports:
    #   - "8087:80"
```
and re-run `docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml up -d`.
You'll still reach it locally via the LAN/hostname options in DOCKER.md if you
keep the port; drop it for "Cloudflare-only" access.

## Updating / restarting

Always include both compose files so the tunnel comes up too:
```bash
docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml up -d --build
```
Tip: set `COMPOSE_FILE=docker-compose.yml:docker-compose.cloudflare.yml` in `.env`
and you can just run `docker compose up -d` as normal.

---

## Security notes

- **Cloudflare Access is the lock.** Without the Access policy, the public URL is
  open to anyone — always add the policy before sharing the link.
- The in-app profile switcher is **not** a security boundary (anyone who's past
  the Access gate can switch profiles). That's fine for a trusted household; if
  you need people locked out of each other's profiles, that's the "built-in
  per-user auth" route instead.
- Your API keys/tokens live in `.env` on the server and are never exposed to the
  browser — the tunnel only serves the web UI + proxied API.
