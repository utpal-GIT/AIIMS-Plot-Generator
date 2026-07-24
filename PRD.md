# AIIMS Plotter — Product Requirements Document

| | |
|---|---|
| **Product** | AIIMS Plotter — Method Comparison Plot Generator |
| **Owner** | Primary Health Tech |
| **Repository** | https://github.com/utpal-GIT/AIIMS-Plot-Generator |
| **Status** | Live (iterating) |
| **Last updated** | 2026-07-24 |
| **Document version** | 1.0 |

---

## 1. Overview

AIIMS Plotter is a secure, multi-user web application for generating **method-comparison
(difference) plots** used in clinical laboratory method validation. A user enters paired
**Reference** and **Measured** values for an analyte, and the app produces a
Bland–Altman-style difference plot annotated with OLS regression, limits of agreement,
per-analyte tolerance limits, a computed "Clinically Valid Region", categorised data
points, a full statistical summary, and an exportable PDF report.

It is a web port of an original Python/Tkinter desktop tool, redesigned as a modern,
authenticated, cloud-hosted dashboard.

## 2. Problem statement & background

Clinical labs must validate that a new/measured method agrees with a reference method
within clinically acceptable tolerances. The original desktop tool required a local Python
environment, manual Excel file paths, and produced a single static plot. It was
single-user, not shareable, and hard to standardise across staff.

**Needs addressed:**
- Run the analysis from any browser, no local setup.
- Centralised, reusable **tolerance configurations per analyte**.
- Controlled access (authentication + roles) for a shared lab.
- Consistent, presentable output (on-screen + PDF report).

## 3. Goals & non-goals

### Goals
- Reproduce the desktop tool's analysis (OLS-only) on the web with identical math.
- Let non-technical lab staff generate a validated plot in minutes.
- Persist per-analyte tolerance settings shared across the team.
- Provide authentication with a clear role hierarchy.
- Free-tier hostable while remaining persistent and private.
- Export a self-contained PDF report.

### Non-goals (current release)
- Non-OLS regression (Theil–Sen/Deming/Passing–Bablok) — intentionally removed; OLS only.
- Automated instrument/LIS data ingestion.
- Longitudinal storage of datasets or a report history.
- Statistical inference beyond the described method (e.g., t-based CIs).
- Mobile-first / native app.

## 4. Users & roles

**Persona:** Clinical lab staff and administrators validating analyte methods. Comfortable
with lab concepts (tolerance, bias); not necessarily technical.

Three-tier role hierarchy (highest to lowest):

| Role | Capabilities |
|---|---|
| **Super admin** (owner) | Everything, incl. managing admins and other super admins. At least one must always exist. |
| **Admin** | Manage **regular users only** (add / reset password / delete). Cannot manage admins/super admins or promote anyone. |
| **User** | Use the Dashboard, Configurations, and Account. No user management. |

The **first launch** creates the super admin via a one-time setup screen (no default
password stored). Any logged-in user can create/edit tolerance Configurations.

## 5. User stories

- As a **lab user**, I select an analyte, enter/upload Reference/Measured data, and generate
  the difference plot with statistics.
- As a **lab user**, I export a PDF report of the plot + statistics for records.
- As **any user**, I define an analyte's tolerance limits once in Configurations so everyone
  uses the same thresholds.
- As an **admin**, I add lab staff and reset their passwords.
- As a **super admin**, I set up the app, appoint admins, and manage all accounts.
- As **any user**, I change my own password.

## 6. Functional requirements

### 6.1 Authentication & access
- Username/password login (`streamlit-authenticator`), signed session cookie.
- First-run **super admin setup** screen; no hardcoded credentials.
- Passwords **bcrypt-hashed**; cookie secret randomly generated on first run.
- Branded, centered login/setup screens (logo + "AIIMS Plotter").
- Role-gated navigation and actions (see §4).
- Guards: cannot demote/delete the **last super admin**; cannot delete your own account
  while logged in; username ≥3 chars; password ≥8 chars.

### 6.2 Navigation (sidebar)
Modern sidebar nav (icon menu): **Dashboard · Configurations · Account · Settings · Logout**.
Logo + app name at top. All analysis controls live on the main screen (not the sidebar).

### 6.3 Configurations
- Define **test parameters (analytes)**, each with:
  - Name, optional **unit** (case-sensitive display, e.g. `mg/dL`).
  - **Threshold** on the X-axis.
  - **Below-threshold tolerance**: value + type (Value / Percentage).
  - **Above-threshold tolerance**: value + type (Value / Percentage).
- Add / edit / delete parameters. Shared app-wide and persisted.
- Editable by any logged-in user.

### 6.4 Dashboard
- **Test parameter** selector; the selected parameter's tolerances are auto-applied and
  shown as a compact **tolerance card** (Threshold; `X ≤ t → ± v`; `X > t → ± v%`).
- **Data entry** (left column):
  - Editable table with auto **Sl. No.**, `Reference`, `Measured` columns; dynamic rows.
  - **Excel upload** (.xlsx/.xls) alternative that pre-fills the table.
  - **Data fingerprint** caption (row count + Reference/Measured means) to verify the table
    matches the source file.
- **Statistics** (right column) — see §6.6.
- **Plot customization** (top of plot): X-axis basis (Reference / Average), editable plot
  title and axis labels.
- **Generate plot** action renders the plot and computes statistics.
- **Downloads**: plot as **PNG**, and **Generate report (PDF)**.

### 6.5 The plot (methodology)
Difference plot of `Diff = Measured − Reference` (Y) against the chosen X basis:
- **X basis = Reference** — classic method-comparison difference plot.
- **X basis = Average** — `(Reference + Measured)/2` (Bland–Altman); the **entire analysis is
  recomputed against the average**.

Plot elements:
- **OLS regression** line of `Diff ~ X`, with **95% confidence band** (mean CI).
- **Mean difference** line + 95% CI band.
- **Limits of Agreement** = `mean ± 1.96·SD` (dashed).
- **Tolerance limits** (`± tolerance`, split at the threshold; value or percentage).
- **Clinically Valid Region** — shaded band between two boundaries defined **only** by:
  1. upper CI × upper tolerance intersection, and
  2. lower CI × lower tolerance intersection.
  Where a boundary has no intersection, it defaults to the data min (left) / max (right).
- **Mean-diff / OLS angle** = `degrees(atan(OLS slope))`.
- **Four point categories** (colour-coded, white-edged markers):
  | Category | Colour |
  |---|---|
  | Valid (in region, within tolerance) | green |
  | Outlier · in valid region | amber |
  | Within tolerance · outside valid region | cyan |
  | Outlier · outside valid region | red |
- Seaborn "whitegrid" styling; on-plot **summary box** (see §6.6).

### 6.6 Statistics & summaries
Presented on the Dashboard and in the on-plot summary box, grouped as:

- **Overall summary**: Total data points; Outliers; Overestimated; Underestimated.
- **Valid range summary**: Data points in valid range; Outliers; Overestimated;
  Underestimated.
- **Point categories**: counts + % for the four categories.
- Key metrics: analysis range, mean-diff/OLS angle, OLS slope, mean difference.

**Percentage convention:** every percentage is expressed **out of the total data points**.
Colour convention: overall summary is neutral (overall outliers span multiple marker
colours); valid-range outliers/over/under are amber (their single marker colour).

### 6.7 PDF report
Self-contained report (reportlab) containing: logo, report title, analyte + unit, generator
and timestamp, tolerance settings, the plot image, and the statistics tables. Downloaded on
demand; not stored server-side.

### 6.8 Account & Settings
- **Account**: view name/username/role; change own password (verifies current password).
- **Settings**: user administration (admins/super admins only) — add users, reset passwords,
  change roles, delete users, subject to the guards in §6.1.

## 7. Non-functional requirements

- **Security**: bcrypt password hashing; credentials never in the repo; DB connection
  string and cookie secret kept out of source control; HTTPS via host; data behind login.
- **Privacy**: lab data entered at runtime is stored only in the app's private database
  (or in-session); not committed to the repo.
- **Persistence**: user accounts and analyte configs must survive restarts/redeploys.
- **Performance**: interactive for typical datasets (hundreds of points); PDF/plot generation
  in a few seconds.
- **Portability**: runs identically locally and on the host (containerised).
- **Usability**: modern, professional dashboard; theme = light.

## 8. Technical architecture

**Stack:** Python + Streamlit. Pure-Python statistics (`pandas`, `numpy`, `statsmodels`,
`scipy`), plotting via `matplotlib`, auth via `streamlit-authenticator`, sidebar nav via
`streamlit-option-menu`, PDF via `reportlab`, DB via `psycopg2`.

**Modules:**
- `app.py` — Streamlit UI: auth gate, sidebar nav, Dashboard/Configurations/Account/Settings
  pages, statistics rendering, downloads.
- `plot_logic.py` — pure computation + matplotlib figure (`generate_plot`); no Streamlit
  imports (unit-testable). Returns figure + stats dict + per-point results.
- `auth.py` — authentication, role model, user CRUD, config load/save (DB or file backend).
- `config_store.py` — per-analyte tolerance persistence (reuses auth's DB plumbing).
- `report.py` — PDF report builder.
- `assets/` — logo. `render.yaml`, `Dockerfile`, `.streamlit/config.toml` — deployment.

**Storage backend (adaptive):**
- `DATABASE_URL` set → **PostgreSQL**: entire config stored as one JSON row per key in an
  `app_config(id, data jsonb)` table (id=1 credentials, id=2 analyte configs). Connection
  cached, with reconnect-on-failure.
- `AUTH_CONFIG_PATH` set → YAML file on a **persistent disk**.
- Neither → local YAML file (offline dev).

## 9. Data model

- **Input**: rows of `Reference` (float) and `Measured` (float); table stores float64.
- **Derived per point**: `Diff = Measured − Reference`; `X` (Reference or Average);
  tolerance; outlier flag (`|Diff| > tolerance`); category.
- **Analyte config**: `{ unit, threshold, val_below, type_below, val_above, type_above }`.
- **User record**: `{ email, name, password (bcrypt), roles: [role] }` + cookie config.

## 10. Statistical specification (verified)

- `SD` uses sample ddof=1; `Mean-diff 95% CI = mean ± 1.96·SD/√n`;
  `LoA = mean ± 1.96·SD` (1.96 normal approximation, matching the original tool).
- OLS via `statsmodels`; **95% band** is the confidence interval of the fitted mean.
- **Valid region** = the x-interval where `upperCI ≤ upperTol AND lowerCI ≥ −lowerTol`,
  bounded by those two intersections (data-extreme fallback).
- All computed values were **independently cross-checked** and confirmed correct, including
  against a real 165-point Creatinine dataset.

> **Known sensitivity:** the valid-region boundary is a hard cut; when many points sit at a
> single X value near the boundary, a small change in input data can shift the boundary
> across the cluster and change "points in valid range" substantially. This is inherent to a
> hard boundary, not a defect. The data-fingerprint caption helps users confirm identical
> inputs across entry methods.

## 11. Deployment

- **Recommended (free):** Streamlit Community Cloud + **Neon Postgres** (free, no card).
  `DATABASE_URL` (pooled, `sslmode=require`) supplied via Streamlit secrets; public repo is
  safe (no secrets committed; data lives in the private DB behind login).
- **Alternative (paid):** any container host with a persistent disk — `Dockerfile` +
  `render.yaml` (Render blueprint, 1 GB disk at `/data`, `AUTH_CONFIG_PATH` set).
- App auto-redeploys on push to `main`.

See `DEPLOY.md` for step-by-step instructions.

## 12. Assumptions, constraints & risks

- **Assumption:** input columns are `Reference` and `Measured`; ≥3 valid rows required.
- **Constraint:** free Streamlit Cloud apps sleep on inactivity (wake in seconds); public
  repo required on the free tier.
- **Risk:** manual paste into the table can introduce values that differ from the source
  file; mitigated by the data-fingerprint caption and Excel upload path.
- **Risk:** single-writer, last-write-wins on the shared config document (acceptable for a
  small lab).

## 13. Future enhancements (candidates)

- Reports history (save/re-download past PDFs).
- Reliable bulk-paste text box (parse TSV/CSV at full precision).
- Optional t-distribution CIs for small samples.
- Per-user or per-analyte audit trail.
- Export of the categorised per-point table.

## 14. Glossary

- **Reference** — gold-standard/comparator value. **Measured** — value from the method
  under test. **Diff** — Measured − Reference (bias).
- **Tolerance** — clinically allowable difference; absolute (Value) or Percentage of X,
  split at a Threshold.
- **Clinically Valid Region** — X-range where the regression's confidence band stays within
  the tolerance limits.
- **LoA** — Limits of Agreement (mean ± 1.96·SD).
- **Overestimated / Underestimated** — outliers with Diff > 0 / Diff < 0.
