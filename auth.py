"""
Authentication + user management for the Lab Plot Generator (Phase 3).

Uses streamlit-authenticator 0.4.x. Credentials and cookie settings live in
`auth_config.yaml` next to this file. There are NO hardcoded passwords: on the
very first launch the app shows a one-time setup screen to create the first
SUPER ADMIN (the owner). Managers can then add / reset / remove users in-app.

Role hierarchy (highest to lowest):
  • superadmin — full control; can manage everyone incl. admins & super admins.
                 At least one super admin must always exist.
  • admin      — can manage regular USERS only (add / reset / delete). Cannot
                 touch admins or super admins and cannot promote anyone.
  • user       — uses the app; no admin tab.
"""

import json
import os
import re
import secrets

import streamlit as st
import streamlit_authenticator as stauth
import yaml

# Storage backend
# ----------------
# If a database is configured (env DATABASE_URL or Streamlit secret DATABASE_URL),
# the whole config is persisted as one JSON row — this is what free hosts with an
# ephemeral filesystem (e.g. Streamlit Community Cloud) need. Otherwise it falls
# back to a local YAML file (simple offline/dev use).
#
# AUTH_CONFIG_PATH overrides the local file location (e.g. a mounted volume).
CONFIG_PATH = os.environ.get("AUTH_CONFIG_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "auth_config.yaml"
)


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
COOKIE_NAME = "lab_plot_auth"
MIN_PASSWORD_LEN = 8
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,}$")

ROLE_SUPERADMIN = "superadmin"
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_RANK = {ROLE_USER: 0, ROLE_ADMIN: 1, ROLE_SUPERADMIN: 2}
ROLE_LABELS = {ROLE_USER: "User", ROLE_ADMIN: "Admin", ROLE_SUPERADMIN: "Super admin"}


# --------------------------------------------------------------------------
# Config load / save
# --------------------------------------------------------------------------
# --- Database backend (Postgres via psycopg2), lazily imported ---
@st.cache_resource(show_spinner=False)
def _get_conn(url):
    import psycopg2
    conn = psycopg2.connect(url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS app_config (id int PRIMARY KEY, data jsonb NOT NULL)")
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


def _db_load(url):
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT data FROM app_config WHERE id = 1")
            row = cur.fetchone()
        if not row or row[0] is None:
            return {}
        data = row[0]
        return json.loads(data) if isinstance(data, str) else data
    return _db_run(url, _q) or {}


def _db_save(url, config):
    payload = json.dumps(config)
    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_config (id, data) VALUES (1, %s::jsonb) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                (payload,),
            )
    _db_run(url, _q)


def _file_load():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _file_save(config):
    parent = os.path.dirname(CONFIG_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)


def load_config():
    """Return the config dict, or a fresh skeleton if nothing is stored yet."""
    url = _database_url()
    config = _db_load(url) if url else _file_load()

    config.setdefault("cookie", {
        "name": COOKIE_NAME,
        "key": secrets.token_hex(16),
        "expiry_days": 30,
    })
    config.setdefault("credentials", {"usernames": {}})
    config["credentials"].setdefault("usernames", {})
    return config


def save_config(config):
    url = _database_url()
    if url:
        _db_save(url, config)
    else:
        _file_save(config)


def needs_setup(config):
    """True when no user accounts exist yet (first launch)."""
    return not config["credentials"]["usernames"]


# --------------------------------------------------------------------------
# Role helpers
# --------------------------------------------------------------------------
def primary_role(info):
    """Highest role held by a user record."""
    roles = info.get("roles") or [ROLE_USER]
    return max(roles, key=lambda r: ROLE_RANK.get(r, 0))


def role_of(config, username):
    users = config["credentials"]["usernames"]
    if username not in users:
        return None
    return primary_role(users[username])


def is_manager(role):
    """Roles that see the Admin tab."""
    return role in (ROLE_ADMIN, ROLE_SUPERADMIN)


def _count_role(config, role):
    return sum(
        1 for info in config["credentials"]["usernames"].values()
        if primary_role(info) == role
    )


def can_assign(actor_role, new_role):
    """Can an actor create/assign the given role?"""
    if actor_role == ROLE_SUPERADMIN:
        return True
    if actor_role == ROLE_ADMIN:
        return new_role == ROLE_USER
    return False


def can_manage_target(actor_role, target_role):
    """Can an actor act on a user holding target_role?"""
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


def manageable_usernames(config, actor_role):
    """Usernames the actor is allowed to act upon."""
    out = []
    for u, info in config["credentials"]["usernames"].items():
        if can_manage_target(actor_role, primary_role(info)):
            out.append(u)
    return out


def list_users(config):
    users = config["credentials"]["usernames"]
    return [
        {
            "username": u,
            "name": info.get("name", ""),
            "email": info.get("email", ""),
            "role": ROLE_LABELS.get(primary_role(info), primary_role(info)),
        }
        for u, info in users.items()
    ]


# --------------------------------------------------------------------------
# Validation + mutation helpers  (return (ok, message))
# actor_role=None means an unrestricted/bootstrap call (first-run setup, tests).
# --------------------------------------------------------------------------
def _validate_new_user(config, username, name, password):
    if not USERNAME_RE.match(username or ""):
        return False, "Username must be 3+ characters (letters, numbers, . _ - only)."
    if username in config["credentials"]["usernames"]:
        return False, f"Username '{username}' already exists."
    if not (name or "").strip():
        return False, "Full name is required."
    if len(password or "") < MIN_PASSWORD_LEN:
        return False, f"Password must be at least {MIN_PASSWORD_LEN} characters."
    return True, ""


def add_user(config, username, name, email, password, role=ROLE_USER, actor_role=None):
    if role not in ROLE_RANK:
        return False, f"Unknown role '{role}'."
    if actor_role is not None and not can_assign(actor_role, role):
        return False, "You are not allowed to create a user with that role."
    ok, msg = _validate_new_user(config, username, name, password)
    if not ok:
        return False, msg
    config["credentials"]["usernames"][username] = {
        "email": (email or "").strip(),
        "name": name.strip(),
        "password": stauth.Hasher.hash(password),
        "roles": [role],
        "failed_login_attempts": 0,
        "logged_in": False,
    }
    save_config(config)
    return True, f"User '{username}' created as {ROLE_LABELS[role]}."


def reset_password(config, username, new_password, actor_role=None):
    users = config["credentials"]["usernames"]
    if username not in users:
        return False, "User not found."
    if actor_role is not None and not can_manage_target(actor_role, primary_role(users[username])):
        return False, "You are not allowed to manage that user."
    if len(new_password or "") < MIN_PASSWORD_LEN:
        return False, f"Password must be at least {MIN_PASSWORD_LEN} characters."
    users[username]["password"] = stauth.Hasher.hash(new_password)
    save_config(config)
    return True, f"Password reset for '{username}'."


def set_role(config, username, new_role, actor_role=None):
    users = config["credentials"]["usernames"]
    if username not in users:
        return False, "User not found."
    if new_role not in ROLE_RANK:
        return False, f"Unknown role '{new_role}'."
    current = primary_role(users[username])
    if actor_role is not None:
        if not can_manage_target(actor_role, current) or not can_assign(actor_role, new_role):
            return False, "You are not allowed to change that user's role."
    if current == ROLE_SUPERADMIN and new_role != ROLE_SUPERADMIN and _count_role(config, ROLE_SUPERADMIN) <= 1:
        return False, "Cannot demote the last super admin."
    users[username]["roles"] = [new_role]
    save_config(config)
    return True, f"'{username}' is now {ROLE_LABELS[new_role]}."


def change_own_password(config, username, old_password, new_password):
    """Let a logged-in user change their own password (verifies the old one)."""
    users = config["credentials"]["usernames"]
    if username not in users:
        return False, "User not found."
    if not stauth.Hasher.check_pw(old_password, users[username]["password"]):
        return False, "Current password is incorrect."
    if len(new_password or "") < MIN_PASSWORD_LEN:
        return False, f"Password must be at least {MIN_PASSWORD_LEN} characters."
    users[username]["password"] = stauth.Hasher.hash(new_password)
    save_config(config)
    return True, "Password updated."


def delete_user(config, username, current_username, actor_role=None):
    users = config["credentials"]["usernames"]
    if username not in users:
        return False, "User not found."
    if username == current_username:
        return False, "You cannot delete your own account while logged in."
    target_role = primary_role(users[username])
    if actor_role is not None and not can_manage_target(actor_role, target_role):
        return False, "You are not allowed to delete that user."
    if target_role == ROLE_SUPERADMIN and _count_role(config, ROLE_SUPERADMIN) <= 1:
        return False, "Cannot delete the last super admin."
    del users[username]
    save_config(config)
    return True, f"User '{username}' deleted."


# --------------------------------------------------------------------------
# Authenticator factory
# --------------------------------------------------------------------------
def build_authenticator(config):
    # auto_hash=False: passwords in the config are already bcrypt-hashed.
    return stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
        auto_hash=False,
    )


# --------------------------------------------------------------------------
# UI: first-run setup (creates the super admin / owner)
# --------------------------------------------------------------------------
def render_setup(config):
    st.markdown("**Create administrator account**")
    st.caption("This one-time step creates the owner (super admin). "
               "No default password is stored.")
    with st.form("setup_form"):
        name = st.text_input("Full name")
        username = st.text_input("Username", help="3+ chars: letters, numbers, . _ -")
        email = st.text_input("Email (optional)")
        pw1 = st.text_input("Password", type="password", help=f"At least {MIN_PASSWORD_LEN} characters")
        pw2 = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create super admin account", type="primary")
    if submitted:
        if pw1 != pw2:
            st.error("Passwords do not match.")
            return
        ok, msg = add_user(config, username, name, email, pw1, role=ROLE_SUPERADMIN)
        if ok:
            st.success("Super admin account created. Please log in.")
            st.rerun()
        else:
            st.error(msg)


# --------------------------------------------------------------------------
# UI: admin panel
# --------------------------------------------------------------------------
def render_admin_panel(config, current_username, current_role):
    st.subheader("User administration")
    if current_role == ROLE_SUPERADMIN:
        st.caption("Super admin — you can manage all users, including admins and super admins.")
    else:
        st.caption("Admin — you can manage regular users only.")

    st.markdown("**Existing users**")
    st.dataframe(list_users(config), use_container_width=True, hide_index=True)

    roles_for_actor = assignable_roles(current_role)
    targets = manageable_usernames(config, current_role)

    st.divider()
    st.markdown("**Add a user**")
    with st.form("add_user_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            new_name = st.text_input("Full name")
            new_username = st.text_input("Username")
        with c2:
            new_email = st.text_input("Email (optional)")
            if len(roles_for_actor) > 1:
                new_role = st.selectbox("Role", roles_for_actor,
                                        format_func=lambda r: ROLE_LABELS[r])
            else:
                new_role = ROLE_USER
                st.caption("New accounts are created as **User**.")
        new_pw = st.text_input("Temporary password", type="password",
                               help=f"At least {MIN_PASSWORD_LEN} characters")
        if st.form_submit_button("Add user", type="primary"):
            ok, msg = add_user(config, new_username, new_name, new_email, new_pw,
                               role=new_role, actor_role=current_role)
            (st.success if ok else st.error)(msg)

    if not targets:
        st.divider()
        st.info("There are no users you can manage yet.")
        return

    st.divider()
    st.markdown("**Reset a password**")
    with st.form("reset_pw_form", clear_on_submit=True):
        r_user = st.selectbox("User", targets, key="reset_user")
        r_pw = st.text_input("New password", type="password")
        if st.form_submit_button("Reset password"):
            ok, msg = reset_password(config, r_user, r_pw, actor_role=current_role)
            (st.success if ok else st.error)(msg)

    if len(roles_for_actor) > 1:
        st.divider()
        st.markdown("**Change role**")
        with st.form("role_form"):
            g_user = st.selectbox("User", targets, key="role_user")
            g_role = st.selectbox("New role", roles_for_actor,
                                  format_func=lambda r: ROLE_LABELS[r], key="role_new")
            if st.form_submit_button("Update role"):
                ok, msg = set_role(config, g_user, g_role, actor_role=current_role)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

    st.divider()
    st.markdown("**Delete a user**")
    with st.form("delete_user_form"):
        d_user = st.selectbox("User", targets, key="delete_user")
        confirm = st.checkbox("I understand this permanently removes the account.")
        if st.form_submit_button("Delete user"):
            if not confirm:
                st.warning("Tick the confirmation box first.")
            else:
                ok, msg = delete_user(config, d_user, current_username, actor_role=current_role)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
