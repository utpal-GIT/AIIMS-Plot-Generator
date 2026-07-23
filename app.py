"""
Method Comparison Plot Generator — Streamlit dashboard.

Modern dashboard layout: sidebar navigation (Dashboard, Configurations,
Account, Settings, Logout); all plotting controls live on the main screen.
Per-parameter tolerances are defined in Configurations and applied on the
Dashboard. Reports are exported as PDF.
"""

import base64
import io
import os

import pandas as pd
import streamlit as st
from streamlit_option_menu import option_menu

import auth
import config_store
import report
from plot_logic import generate_plot

st.set_page_config(page_title="Method Comparison", page_icon="📊", layout="wide")

TOL_OPTIONS = config_store.TOL_OPTIONS
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "primaryhealthtech_logo.jpg")

st.markdown("<style>.block-container{padding-top:2.2rem;}</style>", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _logo_data_uri(path):
    with open(path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


# ==========================================================================
# Authentication gate
# ==========================================================================
config = auth.load_config()

if auth.needs_setup(config):
    auth.render_setup(config)
    st.stop()

authenticator = auth.build_authenticator(config)
authenticator.login(location="main")
auth_status = st.session_state.get("authentication_status")

if auth_status is False:
    st.error("Username or password is incorrect.")
    st.stop()
elif auth_status is None:
    st.info("Please log in to continue.")
    st.stop()

current_username = st.session_state.get("username")
current_role = auth.role_of(config, current_username) or auth.ROLE_USER
is_manager = auth.is_manager(current_role)


# ==========================================================================
# Pages
# ==========================================================================
def page_dashboard():
    st.header("Dashboard")
    params = config_store.load_params()

    if not params:
        st.warning("No test parameters configured yet. Add one in **Configurations** "
                   "to set its tolerance limits, then return here to plot.")
        return

    # --- Test parameter + options ---
    top = st.columns([2, 1, 2])
    with top[0]:
        param_name = st.selectbox("Test parameter", list(params.keys()))
    p = params[param_name]
    with top[1]:
        x_basis = st.selectbox("X-axis basis", ["Reference", "Average"],
                               help="Average = (Reference + Measured) / 2 (Bland-Altman).")
    with top[2]:
        unit_txt = f" ({p['unit']})" if p.get("unit") else ""
        st.caption(f"**Tolerance for {param_name}{unit_txt}**")
        st.caption(
            f"Threshold {p['threshold']:g} · "
            f"below: {p['val_below']:g} {p['type_below'].split()[0]} · "
            f"above: {p['val_above']:g} {p['type_above'].split()[0]}"
        )

    with st.expander("Labels & title"):
        lc = st.columns(3)
        default_x = "Average (Reference + Measured) / 2" if x_basis == "Average" else "Reference"
        title = lc[0].text_input("Plot title", value=param_name)
        x_label = lc[1].text_input("X-axis label", value=default_x)
        y_label = lc[2].text_input("Y-axis label", value="Difference (Measured - Reference)")

    st.divider()

    # --- Data ---
    st.subheader("Data")
    mode = st.radio("Input mode", ["Table", "Upload Excel"], horizontal=True)

    if "data_df" not in st.session_state:
        st.session_state["data_df"] = pd.DataFrame({"Reference": [None] * 8, "Measured": [None] * 8})

    if mode == "Upload Excel":
        up = st.file_uploader("Excel file (.xlsx / .xls)", type=["xlsx", "xls"])
        sheet = st.text_input("Sheet name", value="Sheet1")
        if up is not None:
            try:
                udf = pd.read_excel(up, sheet_name=sheet, engine="openpyxl")
                for col in ["Reference", "Measured"]:
                    if col not in udf.columns:
                        udf[col] = None
                st.session_state["data_df"] = udf[["Reference", "Measured"]].reset_index(drop=True)
                st.success(f"Loaded {len(st.session_state['data_df'])} rows.")
            except Exception as e:
                st.error(f"Could not read the file: {e}")

    base = st.session_state["data_df"].copy()
    for col in ["Reference", "Measured"]:
        if col not in base.columns:
            base[col] = None
    base = base[["Reference", "Measured"]].reset_index(drop=True)
    base.insert(0, "Sl. No", range(1, len(base) + 1))

    edited = st.data_editor(
        base,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Sl. No": st.column_config.NumberColumn("Sl. No", disabled=True, width="small"),
            "Reference": st.column_config.NumberColumn("Reference", help="Reference / gold-standard value"),
            "Measured": st.column_config.NumberColumn("Measured", help="Value from the method under test"),
        },
    )
    st.session_state["data_df"] = edited.drop(columns=["Sl. No"]).reset_index(drop=True)
    edited_df = st.session_state["data_df"]

    if st.button("Generate plot", type="primary"):
        try:
            result = generate_plot(
                edited_df, x_basis=x_basis,
                threshold=p["threshold"], val_below=p["val_below"], type_below=p["type_below"],
                val_above=p["val_above"], type_above=p["type_above"],
                title=title, x_label=x_label, y_label=y_label,
            )
            st.session_state["result"] = result
            st.session_state["error"] = None
            # Build the PDF once, up front, so download is instant.
            try:
                st.session_state["pdf_bytes"] = report.build_pdf(
                    result.fig, result.stats, parameter=param_name, unit=p.get("unit", ""),
                    tol=p, username=current_username,
                    logo_path=LOGO_PATH if os.path.exists(LOGO_PATH) else None)
            except Exception:
                st.session_state["pdf_bytes"] = None
            st.session_state["pdf_name"] = f"{param_name}_report.pdf"
        except Exception as e:
            st.session_state["result"] = None
            st.session_state["error"] = str(e)

    result = st.session_state.get("result")
    error = st.session_state.get("error")

    # --- Plot ---
    st.divider()
    st.subheader("Plot")
    if error:
        st.error(f"Could not generate the plot: {error}")
    elif result is None:
        st.info("Fill in the table (or upload a file), then click **Generate plot**.")
    else:
        st.pyplot(result.fig, use_container_width=True)
        dl = st.columns(2)
        with dl[0]:
            png = io.BytesIO()
            result.fig.savefig(png, format="png", dpi=200, bbox_inches="tight")
            png.seek(0)
            st.download_button("Download plot (PNG)", png, file_name="method_comparison.png",
                               mime="image/png", use_container_width=True)
        with dl[1]:
            if st.session_state.get("pdf_bytes"):
                st.download_button("Generate report (PDF)", st.session_state["pdf_bytes"],
                                   file_name=st.session_state.get("pdf_name", "report.pdf"),
                                   mime="application/pdf", use_container_width=True)
            else:
                st.caption("PDF report unavailable.")

        # --- Statistics ---
        st.divider()
        st.subheader("Statistics")
        _render_statistics(result.stats)


def _render_statistics(s):
    import math
    rng = (f"{s['x_min']:.2f} – {s['x_max']:.2f}"
           if math.isfinite(s["x_min"]) and math.isfinite(s["x_max"]) else "No valid range")
    with st.container(border=True):
        m = st.columns(3)
        m[0].metric("Valid analysis range", rng)
        m[1].metric("Mean-diff / OLS angle", f"{s['ols_angle_deg']:.2f}°")
        m[2].metric("OLS slope", f"{s['slope']:.4f}")
        m = st.columns(3)
        m[0].metric("Mean difference", f"{s['mean_diff']:.3f}")
        m[1].metric("Total points", s["n_total"])
        m[2].metric("Points in valid range", s["n_in_range"])

    ov, vr = s["overall"], s["valid_range"]
    cols = st.columns(2)
    for col, (label, sub, d) in zip(cols, [
        ("Outliers — overall", "Across all data points", ov),
        ("Outliers — valid range", "Inside the analysis range", vr),
    ]):
        with col, st.container(border=True):
            st.markdown(f"**{label}**")
            st.caption(sub)
            t = st.columns(3)
            t[0].metric("Total", d["outliers_n"], f"{d['outliers_pct']:.1f}%", delta_color="off")
            t[1].metric("Over", d["over_n"], f"{d['over_pct']:.1f}%", delta_color="off")
            t[2].metric("Under", d["under_n"], f"{d['under_pct']:.1f}%", delta_color="off")


def page_configurations():
    st.header("Configurations")
    st.caption("Define test parameters and their tolerance limits. These are shared "
               "across the app and applied on the Dashboard.")
    params = config_store.load_params()

    if params:
        rows = [{
            "Parameter": name, "Unit": p.get("unit", ""), "Threshold": p["threshold"],
            "Below": f"{p['val_below']:g} {p['type_below'].split()[0]}",
            "Above": f"{p['val_above']:g} {p['type_above'].split()[0]}",
        } for name, p in params.items()]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No parameters yet. Add one below.")

    st.divider()
    st.markdown("**Add or edit a parameter**")
    existing = ["<new>"] + list(params.keys())
    pick = st.selectbox("Edit existing (or add new)", existing)
    preset = params.get(pick, {}) if pick != "<new>" else {}

    with st.form("param_form"):
        c = st.columns(2)
        name = c[0].text_input("Parameter name", value="" if pick == "<new>" else pick)
        unit = c[1].text_input("Unit (optional)", value=preset.get("unit", ""))
        threshold = st.number_input("Threshold (X-axis)", value=float(preset.get("threshold", 1.0)),
                                    step=0.1, format="%.4f")
        c2 = st.columns(2)
        val_below = c2[0].number_input("Tolerance below threshold",
                                       value=float(preset.get("val_below", 0.15)), step=0.01, format="%.4f")
        type_below = c2[1].selectbox("Type (below)", TOL_OPTIONS,
                                     index=TOL_OPTIONS.index(preset.get("type_below", TOL_OPTIONS[0])))
        c3 = st.columns(2)
        val_above = c3[0].number_input("Tolerance above threshold",
                                       value=float(preset.get("val_above", 15.0)), step=0.5, format="%.4f")
        type_above = c3[1].selectbox("Type (above)", TOL_OPTIONS,
                                     index=TOL_OPTIONS.index(preset.get("type_above", TOL_OPTIONS[1])))
        if st.form_submit_button("Save parameter", type="primary"):
            ok, msg = config_store.upsert_param(
                params, name, unit=unit, threshold=threshold,
                val_below=val_below, type_below=type_below,
                val_above=val_above, type_above=type_above)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    if params:
        st.divider()
        st.markdown("**Delete a parameter**")
        with st.form("param_delete"):
            d_name = st.selectbox("Parameter", list(params.keys()), key="del_param")
            if st.form_submit_button("Delete parameter"):
                ok, msg = config_store.delete_param(params, d_name)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()


def page_account():
    st.header("Account")
    with st.container(border=True):
        st.write(f"**Name:** {st.session_state.get('name')}")
        st.write(f"**Username:** {current_username}")
        st.write(f"**Role:** {auth.ROLE_LABELS.get(current_role, current_role)}")

    st.divider()
    st.markdown("**Change password**")
    with st.form("change_pw", clear_on_submit=True):
        old = st.text_input("Current password", type="password")
        new1 = st.text_input("New password", type="password")
        new2 = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Update password", type="primary"):
            if new1 != new2:
                st.error("New passwords do not match.")
            else:
                ok, msg = auth.change_own_password(config, current_username, old, new1)
                (st.success if ok else st.error)(msg)


def page_settings():
    st.header("Settings")
    if is_manager:
        auth.render_admin_panel(config, current_username, current_role)
    else:
        st.info("No settings are available for your role. Contact an administrator "
                "to manage users.")


# ==========================================================================
# Sidebar navigation + routing
# ==========================================================================
with st.sidebar:
    if os.path.exists(LOGO_PATH):
        st.markdown(
            f"<div style='text-align:center; padding:2px 0 12px;'>"
            f"<img src='{_logo_data_uri(LOGO_PATH)}' style='width:120px; max-width:65%;'></div>",
            unsafe_allow_html=True,
        )
    selected = option_menu(
        menu_title=None,
        options=["Dashboard", "Configurations", "Account", "Settings", "Logout"],
        icons=["speedometer2", "sliders", "person", "gear", "box-arrow-right"],
        default_index=0,
        key="nav",
        styles={
            "container": {"padding": "0", "background-color": "transparent"},
            "nav-link": {"font-size": "14px", "padding": "8px 12px", "border-radius": "8px"},
            "nav-link-selected": {"background-color": "#2563eb"},
        },
    )
    st.caption(f"{st.session_state.get('name')} · {auth.ROLE_LABELS.get(current_role, current_role)}")

if selected == "Logout":
    authenticator.logout(location="unrendered")
    for k in ("nav", "data_df", "result", "error", "pdf_bytes", "pdf_name"):
        st.session_state.pop(k, None)
    st.rerun()
elif selected == "Dashboard":
    page_dashboard()
elif selected == "Configurations":
    page_configurations()
elif selected == "Account":
    page_account()
elif selected == "Settings":
    page_settings()
