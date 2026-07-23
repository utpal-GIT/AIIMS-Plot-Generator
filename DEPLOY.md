# Deployment guide

The app stores user accounts, and they're created/edited at runtime. Free hosts
have an **ephemeral filesystem**, so accounts are persisted to a **database**
instead of a file. When `DATABASE_URL` is set, the app uses the database; with no
`DATABASE_URL` it falls back to a local YAML file (handy for offline dev).

---

## Recommended: free stack — Streamlit Community Cloud + Neon Postgres

Fully free, persistent, and keeps the full admin-adds-users flow. ~10 minutes.

### 1. Create a free Postgres (Neon)
1. Sign up at neon.tech (free tier, no card).
2. Create a project → it gives you a **connection string**. Use the **pooled**
   one and make sure it ends with `?sslmode=require`, e.g.
   `postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech/dbname?sslmode=require`
3. That's it — the app creates its own table (`app_config`) on first run.

(Supabase works too: Project → Settings → Database → Connection string → URI.)

### 2. Push the code to a public GitHub repo
- Streamlit Community Cloud needs a **public** repo. That's safe here: no secrets
  are in the code — the DB string goes in Streamlit's secrets box, and
  `auth_config.yaml` / `secrets.toml` are gitignored. Lab data lives in the
  private DB behind the login.

### 3. Deploy on Streamlit Community Cloud
1. Sign in at share.streamlit.io with GitHub.
2. **New app** → pick the repo/branch → main file `app.py`.
3. **Advanced settings → Secrets**, paste:
   ```toml
   DATABASE_URL = "postgresql://...pooler...?sslmode=require"
   ```
4. Deploy. First visit shows the **create super admin** screen → make the owner
   account → log in → add lab users from the Admin tab. HTTPS is automatic.

Note: free Community Cloud apps sleep after inactivity and wake on the next visit
(a few seconds). Accounts persist in Neon regardless of sleeps/redeploys.

### Test the DB locally first (optional)
Put the same string in `.streamlit/secrets.toml` (copy from
`.streamlit/secrets.toml.example`) or `export DATABASE_URL=...`, then
`streamlit run app.py`.

---

## Alternative: container host with a persistent disk (paid)

If you'd rather not use a database, a paid host with a persistent disk keeps the
file-based approach. Included: `Dockerfile` + `render.yaml` (Render blueprint,
1 GB disk at `/data`, `AUTH_CONFIG_PATH=/data/auth_config.yaml`). Also works on
Railway (Volume) and Azure App Service (Azure Files). Set `AUTH_CONFIG_PATH` to
the mounted path. See `render.yaml` and the env table below.

| Var | Value | Why |
|---|---|---|
| `DATABASE_URL` | Postgres pooled URL | DB persistence (free-host path) |
| `AUTH_CONFIG_PATH` | e.g. `/data/auth_config.yaml` | file persistence (paid-disk path) |
| `PORT` | set by the host | Streamlit binds to it |

`DATABASE_URL` takes precedence if both are set.

---

## Backups
- **DB path:** the `app_config` table holds one JSON row (hashed credentials +
  cookie secret). Neon/Supabase keep automatic backups; you can also
  `SELECT data FROM app_config` to export it.
- **File path:** back up `auth_config.yaml`.
- Clearing the store resets the app to first-run setup.

## Local run (no DB, no Docker)
```bash
pip install -r requirements.txt
streamlit run app.py
```
