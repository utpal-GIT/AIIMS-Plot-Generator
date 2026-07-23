"""
Persistence for per-parameter tolerance configurations.

A "parameter" (analyte / test) has its own tolerance settings. These are stored
in the SAME backend as user accounts (Postgres row id=2 when DATABASE_URL is set,
else a local YAML file), reusing auth.py's DB plumbing.

params structure:
{
  "Glucose": {
    "unit": "mmol/L",
    "threshold": 1.0,
    "val_below": 0.15, "type_below": "Value Tolerance",
    "val_above": 15.0, "type_above": "Percentage Tolerance",
  },
  ...
}
"""

import json
import os

import auth  # reuse backend detection + DB connection plumbing

TOL_OPTIONS = ["Value Tolerance", "Percentage Tolerance"]
PARAMS_ID = 2  # app_config row id reserved for parameter configs
PARAMS_PATH = os.environ.get("PARAMS_CONFIG_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "params_config.yaml"
)


# --------------------------------------------------------------------------
# Load / save (DB or file)
# --------------------------------------------------------------------------
def _db_load(url):
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS app_config (id int PRIMARY KEY, data jsonb NOT NULL)")
            cur.execute("SELECT data FROM app_config WHERE id = %s", (PARAMS_ID,))
            row = cur.fetchone()
        if not row or row[0] is None:
            return {}
        data = row[0]
        return json.loads(data) if isinstance(data, str) else data
    return auth._db_run(url, _q) or {}


def _db_save(url, params):
    payload = json.dumps(params)
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_config (id, data) VALUES (%s, %s::jsonb) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                (PARAMS_ID, payload),
            )
    auth._db_run(url, _q)


def load_params():
    url = auth._database_url()
    if url:
        return _db_load(url)
    import yaml
    if os.path.exists(PARAMS_PATH):
        with open(PARAMS_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_params(params):
    url = auth._database_url()
    if url:
        _db_save(url, params)
        return
    import yaml
    parent = os.path.dirname(PARAMS_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(PARAMS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(params, f, default_flow_style=False, sort_keys=False)


# --------------------------------------------------------------------------
# CRUD helpers  (return (ok, message))
# --------------------------------------------------------------------------
def upsert_param(params, name, *, unit, threshold, val_below, type_below,
                 val_above, type_above, allow_overwrite=True):
    name = (name or "").strip()
    if not name:
        return False, "Parameter name is required."
    if name not in params and not allow_overwrite and name in params:
        return False, f"Parameter '{name}' already exists."
    if type_below not in TOL_OPTIONS or type_above not in TOL_OPTIONS:
        return False, "Invalid tolerance type."
    params[name] = {
        "unit": (unit or "").strip(),
        "threshold": float(threshold),
        "val_below": float(val_below),
        "type_below": type_below,
        "val_above": float(val_above),
        "type_above": type_above,
    }
    save_params(params)
    return True, f"Saved parameter '{name}'."


def delete_param(params, name):
    if name not in params:
        return False, "Parameter not found."
    del params[name]
    save_params(params)
    return True, f"Deleted parameter '{name}'."
