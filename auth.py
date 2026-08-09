"""
Identity and roles, backed by Google sign-in.

Authentication itself is Streamlit's native OIDC (st.login / st.user), so this
module never sees or stores a password. Its job is the *account* record that
sits behind a Google identity: the role, when they first appeared and when they
last signed in.

Sign-in is open — any Google account may log in, and an account row is created
on first sight. Emails listed in the ADMIN_EMAILS secret are always super admin;
that is deliberately outside the database so a misconfiguration can never lock
every administrator out.

Storage mirrors config_store: Postgres when DATABASE_URL is configured (what a
host with an ephemeral filesystem needs), else a local YAML file for dev.
"""

import os

import streamlit as st

# AUTH_CONFIG_PATH overrides the local file location (e.g. a mounted volume).
CONFIG_PATH = os.environ.get("AUTH_CONFIG_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "auth_config.yaml"
)

ROLE_SUPERADMIN = "superadmin"
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_RANK = {ROLE_USER: 0, ROLE_ADMIN: 1, ROLE_SUPERADMIN: 2}
ROLE_LABELS = {ROLE_USER: "User", ROLE_ADMIN: "Admin", ROLE_SUPERADMIN: "Super admin"}


def _database_url():
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:  # only available inside a Streamlit runtime
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    return None


def admin_emails():
    """Emails that are always super admin — the break-glass list."""
    raw = os.environ.get("ADMIN_EMAILS")
    if raw is None:
        try:
            raw = st.secrets.get("ADMIN_EMAILS", "")
        except Exception:
            raw = ""
    if isinstance(raw, (list, tuple)):
        values = raw
    else:
        values = str(raw or "").replace(",", " ").split()
    return {e.strip().lower() for e in values if e.strip()}


def auth_configured():
    """True when Streamlit has an [auth] section, i.e. st.login can work."""
    try:
        return "auth" in st.secrets
    except Exception:
        return False


# --------------------------------------------------------------------------
# Storage: Postgres (shared with config_store) or a local YAML file
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _get_conn(url):
    import psycopg2
    conn = psycopg2.connect(url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_users (
                email       text PRIMARY KEY,
                sub         text,
                name        text,
                picture     text,
                role        text NOT NULL DEFAULT 'user',
                first_login timestamptz,
                last_login  timestamptz,
                login_count integer NOT NULL DEFAULT 0
            )""")
    return conn


def _db_run(url, fn):
    """Run fn(conn) with one reconnect retry if the cached connection went stale."""
    import psycopg2
    for attempt in range(2):
        conn = _get_conn(url)
        try:
            return fn(conn)
        except psycopg2.OperationalError:
            _get_conn.clear()
            if attempt == 1:
                raise


def _file_load():
    import yaml
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _file_save(data):
    import yaml
    parent = os.path.dirname(CONFIG_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


_COLUMNS = ("email", "sub", "name", "picture", "role",
            "first_login", "last_login", "login_count")


def _row_to_dict(row):
    return dict(zip(_COLUMNS, row))


# --------------------------------------------------------------------------
# Sign-in
# --------------------------------------------------------------------------
def sync_login(email, *, name=None, sub=None, picture=None):
    """Record a sign-in, creating the account on first sight.

    Returns the stored user record. Emails in ADMIN_EMAILS are forced to super
    admin on every login so that list always wins.
    """
    email = (email or "").strip().lower()
    if not email:
        return None
    forced = ROLE_SUPERADMIN if email in admin_emails() else None

    url = _database_url()
    if url:
        def _q(conn):
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO app_users (email, sub, name, picture, role,
                                           first_login, last_login, login_count)
                    VALUES (%s, %s, %s, %s, %s, now(), now(), 1)
                    ON CONFLICT (email) DO UPDATE SET
                        sub         = COALESCE(EXCLUDED.sub, app_users.sub),
                        name        = COALESCE(EXCLUDED.name, app_users.name),
                        picture     = COALESCE(EXCLUDED.picture, app_users.picture),
                        role        = COALESCE(%s, app_users.role),
                        last_login  = now(),
                        login_count = app_users.login_count + 1
                    RETURNING email, sub, name, picture, role,
                              first_login, last_login, login_count
                """, (email, sub, name, picture, forced or ROLE_USER, forced))
                return _row_to_dict(cur.fetchone())
        return _db_run(url, _q)

    # File fallback (dev)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    data = _file_load()
    users = data.setdefault("users", {})
    rec = users.get(email) or {"email": email, "role": ROLE_USER,
                               "first_login": now, "login_count": 0}
    rec.update({"sub": sub or rec.get("sub"), "name": name or rec.get("name"),
                "picture": picture or rec.get("picture"),
                "last_login": now, "login_count": int(rec.get("login_count", 0)) + 1})
    if forced:
        rec["role"] = forced
    users[email] = rec
    _file_save(data)
    return rec


# --------------------------------------------------------------------------
# Queries / mutations
# --------------------------------------------------------------------------
def list_users():
    url = _database_url()
    if url:
        def _q(conn):
            with conn.cursor() as cur:
                cur.execute("""SELECT email, sub, name, picture, role,
                                      first_login, last_login, login_count
                               FROM app_users ORDER BY last_login DESC NULLS LAST""")
                return [_row_to_dict(r) for r in cur.fetchall()]
        return _db_run(url, _q) or []
    users = _file_load().get("users", {})
    return sorted(users.values(), key=lambda r: r.get("last_login") or "", reverse=True)


def role_of(email):
    email = (email or "").strip().lower()
    if email in admin_emails():
        return ROLE_SUPERADMIN
    url = _database_url()
    if url:
        def _q(conn):
            with conn.cursor() as cur:
                cur.execute("SELECT role FROM app_users WHERE email = %s", (email,))
                row = cur.fetchone()
                return row[0] if row else None
        return _db_run(url, _q) or ROLE_USER
    rec = _file_load().get("users", {}).get(email)
    return (rec or {}).get("role", ROLE_USER)


def _count_role(role):
    return sum(1 for u in list_users() if u.get("role") == role)


def set_role(email, new_role, *, actor_role=None):
    email = (email or "").strip().lower()
    if new_role not in ROLE_RANK:
        return False, f"Unknown role '{new_role}'."
    if email in admin_emails():
        return False, "That account is pinned to super admin by ADMIN_EMAILS."
    current = role_of(email)
    if actor_role is not None:
        if not can_manage_target(actor_role, current) or not can_assign(actor_role, new_role):
            return False, "You are not allowed to change that user's role."
    if current == ROLE_SUPERADMIN and new_role != ROLE_SUPERADMIN and _count_role(ROLE_SUPERADMIN) <= 1:
        return False, "Cannot demote the last super admin."

    url = _database_url()
    if url:
        def _q(conn):
            with conn.cursor() as cur:
                cur.execute("UPDATE app_users SET role = %s WHERE email = %s", (new_role, email))
        _db_run(url, _q)
    else:
        data = _file_load()
        if email in data.get("users", {}):
            data["users"][email]["role"] = new_role
            _file_save(data)
    return True, f"'{email}' is now {ROLE_LABELS[new_role]}."


def delete_user(email, current_email, *, actor_role=None):
    email = (email or "").strip().lower()
    if email == (current_email or "").strip().lower():
        return False, "You cannot delete your own account while signed in."
    if email in admin_emails():
        return False, "That account is pinned to super admin by ADMIN_EMAILS."
    target_role = role_of(email)
    if actor_role is not None and not can_manage_target(actor_role, target_role):
        return False, "You are not allowed to delete that user."
    if target_role == ROLE_SUPERADMIN and _count_role(ROLE_SUPERADMIN) <= 1:
        return False, "Cannot delete the last super admin."

    url = _database_url()
    if url:
        def _q(conn):
            with conn.cursor() as cur:
                cur.execute("DELETE FROM app_users WHERE email = %s", (email,))
        _db_run(url, _q)
    else:
        data = _file_load()
        data.get("users", {}).pop(email, None)
        _file_save(data)
    return True, f"User '{email}' deleted."


# --------------------------------------------------------------------------
# Role helpers (unchanged semantics)
# --------------------------------------------------------------------------
def is_manager(role):
    return role in (ROLE_ADMIN, ROLE_SUPERADMIN)


def can_assign(actor_role, new_role):
    if actor_role == ROLE_SUPERADMIN:
        return True
    if actor_role == ROLE_ADMIN:
        return new_role == ROLE_USER
    return False


def can_manage_target(actor_role, target_role):
    if actor_role == ROLE_SUPERADMIN:
        return True
    if actor_role == ROLE_ADMIN:
        return target_role == ROLE_USER
    return False


def assignable_roles(actor_role):
    if actor_role == ROLE_SUPERADMIN:
        return [ROLE_USER, ROLE_ADMIN, ROLE_SUPERADMIN]
    if actor_role == ROLE_ADMIN:
        return [ROLE_USER]
    return []
