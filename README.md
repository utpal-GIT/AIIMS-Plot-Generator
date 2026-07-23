# Method Comparison Plot Generator

Web app (Streamlit) that ports the desktop lab-plot tool. OLS regression only.

## Layout
Modern dashboard with sidebar navigation:

- **Dashboard** — pick a test parameter, enter/upload data (with auto Sl. No.),
  generate the plot + statistics, export a **PDF report**.
- **Configurations** — define test parameters, each with its own saved tolerances
  (threshold, below/above value or %). Any logged-in user can edit these.
- **Account** — change your own password; view your role.
- **Settings** — user management (admins/super admins only).
- **Logout**.

## Features
- Editable data table **or** Excel upload (columns: `Reference`, `Measured`),
  with an auto-populated **Sl. No.** column
- Per-parameter tolerances applied automatically from Configurations
- X-axis basis toggle: **Reference** or **Average** `(Reference + Measured)/2`
  (Average recomputes the full analysis against the average — Bland–Altman)
- Editable plot title and X / Y axis labels
- OLS regression line with 95% CI, mean difference + CI, Limits of Agreement,
  tolerance limits, and a light-green **valid-region** shade
- Four point categories: valid, outlier-in-range, within-tolerance-outside-range,
  outlier-outside-range
- Angle between the mean-difference line and the OLS line (data units)
- Outlier breakdown — total / overestimated / underestimated, each shown
  **overall** and **within the clinical valid range**, in count and %
- Export **PDF report** (logo, parameter, tolerances, plot, statistics) and PNG

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
Then open http://localhost:8501

## Files
- `app.py` — Streamlit UI
- `plot_logic.py` — pure computation + matplotlib figure (no Streamlit deps)
- `sample_data.csv` — example input

## Authentication
Username/password login via `streamlit-authenticator` (config in `auth_config.yaml`).

Roles (highest to lowest):

| Role | Can do |
|---|---|
| **Super admin** | Manage everyone — add/reset/delete/re-role users, admins, and other super admins |
| **Admin** | Manage **regular users only** (add / reset password / delete). Cannot touch admins or super admins, cannot promote anyone |
| **User** | Use the app; no Admin tab |

- **First launch** shows a one-time "create super admin account" screen (the
  owner) — no default password is stored anywhere.
- Super admins and admins get an **Admin** tab scoped to what their role allows.
- Guards: the **last super admin** can't be demoted or deleted, and you can't
  delete your own account while logged in.
- Passwords are bcrypt-hashed; the session cookie key is randomly generated on
  first run.

`auth_config.yaml` holds credentials and the cookie secret — do **not** commit it
to source control (add it to `.gitignore` before hosting).

## Deployment
Accounts are created at runtime, so storage adapts to the host:

- **`DATABASE_URL` set** → accounts persist in **Postgres** (needed for free hosts
  with an ephemeral filesystem). Recommended free stack: **Streamlit Community
  Cloud + Neon Postgres**.
- **`AUTH_CONFIG_PATH` set** → accounts persist in a YAML file on a **persistent
  disk** (paid container hosts; `Dockerfile` + `render.yaml` included).
- **neither** → local YAML file next to the code (offline dev).

See [DEPLOY.md](DEPLOY.md) for the step-by-step.

## Roadmap
- ~~Phase 3: authentication~~ ✅ done
- ~~Phase 4: hosting~~ ✅ done (free DB-backed stack + paid disk-backed option)
- Phase 5: input validation polish, tolerance presets, PDF report
