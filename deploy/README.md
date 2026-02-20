# PyFoswiki — Server Deployment

**Domain:** `py-foswiki.performiq.com`
- Web UI: `https://py-foswiki.performiq.com` → `127.0.0.1:8121`
- API:    `https://py-foswiki.performiq.com:8443` → `127.0.0.1:8443`

---

## 1. Create system user and directory

```bash
sudo useradd -r -s /bin/false -d /opt/pyfoswiki pyfoswiki
sudo mkdir -p /opt/pyfoswiki/data/attachments
sudo chown -R pyfoswiki:pyfoswiki /opt/pyfoswiki
```

## 2. Deploy application code

```bash
sudo -u pyfoswiki git clone <repo-url> /opt/pyfoswiki
# or rsync from dev machine:
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='.env' \
    ./ pyfoswiki@<server>:/opt/pyfoswiki/
```

## 3. Create virtual environment and install dependencies

```bash
sudo -u pyfoswiki bash -c "
  cd /opt/pyfoswiki
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
"
```

## 4. Configure environment

```bash
sudo cp /opt/pyfoswiki/deploy/.env.example /opt/pyfoswiki/.env
sudo nano /opt/pyfoswiki/.env
```

Key values to set:
- `DATABASE_URL` — PostgreSQL connection string with real password
- `SECRET_KEY` — generate with: `python3 -c "import secrets; print(secrets.token_hex(64))"`
- `BASE_URL=https://py-foswiki.performiq.com:8443`
- `CORS_ORIGINS=["https://py-foswiki.performiq.com"]`
- `ALLOW_REGISTRATION=false`

```bash
sudo chown pyfoswiki:pyfoswiki /opt/pyfoswiki/.env
sudo chmod 600 /opt/pyfoswiki/.env
```

## 5. Run database migrations

```bash
sudo -u pyfoswiki bash -c "
  cd /opt/pyfoswiki
  PYTHONPATH=. .venv/bin/alembic upgrade head
"
```

## 6. Bootstrap first admin user

Register via the web UI first, then promote via psql:

```bash
psql -h 127.0.0.1 -U pyfoswiki -d pyfoswiki \
  -c "UPDATE users SET is_admin = TRUE WHERE username = 'your-username';"
```

## 7. Install systemd services

```bash
sudo cp /opt/pyfoswiki/deploy/pyfoswiki-api.service /etc/systemd/system/
sudo cp /opt/pyfoswiki/deploy/pyfoswiki-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pyfoswiki-api pyfoswiki-web
sudo systemctl start  pyfoswiki-api pyfoswiki-web
sudo systemctl status pyfoswiki-api pyfoswiki-web
```

## 8. Install nginx config

```bash
sudo cp /opt/pyfoswiki/deploy/nginx-py-foswiki.conf \
    /etc/nginx/sites-available/py-foswiki.performiq.com
sudo ln -s /etc/nginx/sites-available/py-foswiki.performiq.com \
    /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

> **SSL certificates** must already exist. If not, obtain them first:
> ```bash
> sudo certbot --nginx -d py-foswiki.performiq.com
> ```
> Then replace the `ssl_certificate` paths in the nginx config if certbot
> didn't already update them.

## 9. Open firewall ports

```bash
sudo ufw allow 443/tcp
sudo ufw allow 8443/tcp
```

Port 80 should already be open for HTTP→HTTPS redirect and certbot renewals.

## Useful commands

```bash
# View logs
sudo journalctl -u pyfoswiki-api -f
sudo journalctl -u pyfoswiki-web -f

# Restart after code update
sudo systemctl restart pyfoswiki-api pyfoswiki-web

# Run migrations after update
sudo -u pyfoswiki bash -c "cd /opt/pyfoswiki && PYTHONPATH=. .venv/bin/alembic upgrade head"
```
