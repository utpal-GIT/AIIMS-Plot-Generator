"""
Persistence for per-parameter tolerance configurations.

A "parameter" (analyte / test) has its own tolerance settings. These are stored
in the SAME backend as user accounts (Postgres row id=2 when DATABASE_URL is set,
else a local YAML file), reusing auth.py's DB plumbing.

Configurations are private to each user, so the stored document is keyed by
owner — the signed-in Google email:
{
  "a.menon@example.com": {
    "Glucose": {
      "unit": "mmol/L",
      "has_threshold": True,
      "threshold": 1.0,
      "val_below": 0.15, "type_below": "Value Tolerance",
      "val_above": 15.0, "type_above": "Percentage Tolerance",
    },
    ...
  },
  ...
}

Documents written under the old username identities are simply never read,
since no one signs in under those keys any more.
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


def _load_all():
    """The whole document: {owner: {param: {...}}} (or a legacy flat map)."""
    url = auth._database_url()
    if url:
        return _db_load(url)
    import yaml
    if os.path.exists(PARAMS_PATH):
        with open(PARAMS_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_all(data):
    url = auth._database_url()
    if url:
        _db_save(url, data)
        return
    import yaml
    parent = os.path.dirname(PARAMS_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(PARAMS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


def load_params(username):
    """This user's parameters only."""
    owned = _load_all().get(username)
    return dict(owned) if isinstance(owned, dict) else {}


def save_params(username, params):
    data = _load_all()
    data[username] = params
    _save_all(data)


def rename_owner(old_username, new_username):
    """Follow a username change so the user keeps their configurations."""
    data = _load_all()
    if old_username not in data:
        return
    data[new_username] = data.pop(old_username)
    _save_all(data)


def delete_owner(username):
    """Drop a deleted user's configurations."""
    data = _load_all()
    if username not in data:
        return
    del data[username]
    _save_all(data)


# --------------------------------------------------------------------------
# CRUD helpers  (return (ok, message))
# --------------------------------------------------------------------------
def upsert_param(username, params, name, *, unit, has_threshold=True,
                 threshold=None, val_below=None, type_below=None,
                 val_above=None, type_above=None,
                 val=None, tol_type=None):
    """Create/update a parameter in `username`'s own set.

    Two shapes are supported:
      • has_threshold=True  → threshold + below/above tolerances (default).
      • has_threshold=False → a single uniform tolerance (value or % bias).
    """
    name = (name or "").strip()
    if not name:
        return False, "Parameter name is required."
    if has_threshold:
        if type_below not in TOL_OPTIONS or type_above not in TOL_OPTIONS:
            return False, "Invalid tolerance type."
        params[name] = {
            "unit": (unit or "").strip(),
            "has_threshold": True,
            "threshold": float(threshold),
            "val_below": float(val_below),
            "type_below": type_below,
            "val_above": float(val_above),
            "type_above": type_above,
        }
    else:
        if tol_type not in TOL_OPTIONS:
            return False, "Invalid tolerance type."
        params[name] = {
            "unit": (unit or "").strip(),
            "has_threshold": False,
            "val": float(val),
            "type": tol_type,
        }
    save_params(username, params)
    return True, f"Saved parameter '{name}'."


def has_threshold(p):
    """Whether a parameter uses a threshold-based below/above split.

    Parameters saved before this feature have no flag and are threshold-based.
    """
    return p.get("has_threshold", True)


def param_plot_args(p):
    """Tolerance keyword args for plot_logic.generate_plot()."""
    if has_threshold(p):
        return dict(threshold=float(p["threshold"]),
                    val_below=float(p["val_below"]), type_below=p["type_below"],
                    val_above=float(p["val_above"]), type_above=p["type_above"])
    # Single uniform tolerance: push the threshold below all data so every
    # point falls on one side and uses the same value.
    val, typ = float(p["val"]), p["type"]
    return dict(threshold=float("-inf"),
                val_below=val, type_below=typ,
                val_above=val, type_above=typ)


def delete_param(username, params, name):
    if name not in params:
        return False, "Parameter not found."
    del params[name]
    save_params(username, params)
    return True, f"Deleted parameter '{name}'."
