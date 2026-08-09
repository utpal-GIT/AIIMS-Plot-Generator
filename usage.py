"""
Usage event log.

One row per action — who, what, when — so the admin dashboard can report
sign-ins, plot generations and the two download types. Deliberately minimal:
no payload beyond the event kind, per the agreed scope.

Same storage split as the rest of the app: Postgres when DATABASE_URL is
configured, else a local JSON-lines file for dev.
"""

import json
import os
from datetime import datetime, timezone

import streamlit as st

import auth  # reuse the backend detection + connection plumbing

LOGIN = "login"
GENERATE = "generate"
DOWNLOAD_PNG = "download_png"
DOWNLOAD_PDF = "download_pdf"
KINDS = (LOGIN, GENERATE, DOWNLOAD_PNG, DOWNLOAD_PDF)

EVENTS_PATH = os.environ.get("USAGE_EVENTS_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "usage_events.jsonl"
)


def _ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_events (
                id    bigserial PRIMARY KEY,
                email text NOT NULL,
                kind  text NOT NULL,
                ts    timestamptz NOT NULL DEFAULT now()
            )""")
        cur.execute("CREATE INDEX IF NOT EXISTS app_events_email_ts ON app_events (email, ts)")
        cur.execute("CREATE INDEX IF NOT EXISTS app_events_kind_ts ON app_events (kind, ts)")


def log(email, kind):
    """Record one event. Never raises — telemetry must not break the app."""
    email = (email or "").strip().lower()
    if not email or kind not in KINDS:
        return
    try:
        url = auth._database_url()
        if url:
            def _q(conn):
                _ensure_table(conn)
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO app_events (email, kind) VALUES (%s, %s)",
                                (email, kind))
            auth._db_run(url, _q)
            return
        with open(EVENTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"email": email, "kind": kind,
                                "ts": datetime.now(timezone.utc).isoformat()}) + "\n")
    except Exception:
        pass


def log_once(email, kind, token):
    """Log at most once per (kind, token) in this session.

    Streamlit reruns constantly, so a bare log() next to a button would count
    the same action many times. `token` identifies the specific occurrence —
    the session for a login, a click id for a download.
    """
    seen = st.session_state.setdefault("_usage_seen", set())
    key = (kind, token)
    if key in seen:
        return False
    seen.add(key)
    log(email, kind)
    return True


def _file_events():
    if not os.path.exists(EVENTS_PATH):
        return []
    out = []
    with open(EVENTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def counts_by_user():
    """{email: {kind: count}} across all recorded events."""
    url = auth._database_url()
    if url:
        def _q(conn):
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT email, kind, count(*) FROM app_events GROUP BY email, kind")
                rows = cur.fetchall()
            out = {}
            for email, kind, n in rows:
                out.setdefault(email, {})[kind] = int(n)
            return out
        try:
            return auth._db_run(url, _q) or {}
        except Exception:
            return {}
    out = {}
    for e in _file_events():
        out.setdefault(e.get("email"), {}).setdefault(e.get("kind"), 0)
        out[e.get("email")][e.get("kind")] += 1
    return out


def totals(days=None):
    """{kind: count}, optionally limited to the last `days`."""
    url = auth._database_url()
    if url:
        def _q(conn):
            _ensure_table(conn)
            with conn.cursor() as cur:
                if days:
                    cur.execute("SELECT kind, count(*) FROM app_events "
                                "WHERE ts >= now() - make_interval(days => %s) GROUP BY kind",
                                (int(days),))
                else:
                    cur.execute("SELECT kind, count(*) FROM app_events GROUP BY kind")
                return {k: int(n) for k, n in cur.fetchall()}
        try:
            return auth._db_run(url, _q) or {}
        except Exception:
            return {}
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)) if days else None
    out = {}
    for e in _file_events():
        if cutoff:
            try:
                if datetime.fromisoformat(e["ts"]) < cutoff:
                    continue
            except Exception:
                continue
        out[e.get("kind")] = out.get(e.get("kind"), 0) + 1
    return out


def active_users(days=30):
    """Distinct users with any event in the window."""
    url = auth._database_url()
    if url:
        def _q(conn):
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT count(DISTINCT email) FROM app_events "
                            "WHERE ts >= now() - make_interval(days => %s)", (int(days),))
                return int(cur.fetchone()[0])
        try:
            return auth._db_run(url, _q) or 0
        except Exception:
            return 0
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    seen = set()
    for e in _file_events():
        try:
            if datetime.fromisoformat(e["ts"]) >= cutoff:
                seen.add(e.get("email"))
        except Exception:
            pass
    return len(seen)
