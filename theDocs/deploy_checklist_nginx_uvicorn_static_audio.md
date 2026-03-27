# Deployment Checklist: Nginx + Uvicorn + Static Audio

Use this after code updates or server restarts.

## 1) Activate project environment

```bash
cd /home/pock/.openclaw/workspace/mission_control
source .venv/bin/activate
```

## 2) Collect static assets

```bash
python manage.py collectstatic --noinput
```

Expected: static files copied/updated in `staticfiles/`.

## 3) Validate nginx config and reload

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 4) Restart app service

```bash
sudo systemctl restart uvicorn-django-nova-asgi.service
```

## 5) Confirm services are healthy

```bash
sudo systemctl status nginx --no-pager -l
sudo systemctl status uvicorn-django-nova-asgi.service --no-pager -l
ss -lntp | sed -n '1p;/:80\\s/p;/:443\\s/p;/:8001\\s/p'
```

Expected:
- nginx listening on `:80` and `:443`
- uvicorn listening on `127.0.0.1:8001`

## 6) Verify static + runtime audio URLs

```bash
curl -I https://novamission.cloud/static/css/cyber.css
curl -I https://novamission.cloud/static/nova_audio/128592e6-046e-4f53-884a-3544f242c3a7.mp3
```

Expected: `200 OK` (or `304 Not Modified`) for static files.

## 7) If `/static/css/*` or `/static/js/*` returns **403** (Forbidden)

nginx runs as `www-data`. It must **traverse** every directory in the path to `staticfiles/`. If `/home/pock/.openclaw` is mode `700` (`drwx------`), `www-data` cannot enter it → **403** for all collected static assets (even when `collectstatic` and nginx `alias` are correct).

**Fix (pick one):**

```bash
# A) World traverse only (simplest; same idea as nova_audio path fix)
chmod o+x /home/pock/.openclaw

# B) Tighter: ACL execute for www-data only (if setfacl exists)
# sudo setfacl -m u:www-data:x /home/pock/.openclaw
```

Verify as `www-data`:

```bash
sudo -u www-data test -r /home/pock/.openclaw/workspace/mission_control/staticfiles/css/cyber.css && echo OK
```

Then reload is not required for chmod; retry `curl` or the browser.

## 8) If `/static/css/*` or `/static/js/*` returns 404 (but files exist in `staticfiles/`)

**Cause:** `try_files $uri =404` inside a `location` that uses **`alias`** makes nginx look up the wrong path (it keeps the `/static/` prefix), so every asset 404s.

**Fix:** Remove `try_files` from both `/static/` and `/static/nova_audio/` blocks. Use the canonical file:

```bash
sudo cp /home/pock/.openclaw/workspace/mission_control/deploy/nginx-site-mission_control-v7-static-alias.conf /etc/nginx/sites-available/mission_control
sudo nginx -t && sudo systemctl reload nginx
```

Or edit by hand: delete the `try_files` lines under those `location` blocks.

## 9) If `/static/nova_audio/*.mp3` returns 404

1. Confirm nginx has this block **before** generic `/static/` (no `try_files` with `alias`):

```nginx
location /static/nova_audio/ {
    alias /home/pock/.openclaw/workspace/mission_control/static/nova_audio/;
}
```

2. Confirm nginx can traverse the path:

```bash
ls -ld /home/pock/.openclaw /home/pock/.openclaw/workspace/mission_control/static/nova_audio
```

3. If needed, allow traversal for nginx:

```bash
sudo chmod o+x /home/pock/.openclaw
```

4. Reload nginx and test again:

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -I https://novamission.cloud/static/nova_audio/<file>.mp3
```

