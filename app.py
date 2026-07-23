"""
Method Comparison Plot Generator — Streamlit web app (Phase 1).

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

Auth (Phase 3) and hosting (Phase 4) are added later; this phase is the
core port of the desktop tool to the web, OLS-only.
"""

import contextlib
import io
import math

import pandas as pd
import streamlit as st

import auth
from plot_logic import generate_plot

st.set_page_config(page_title="Lab Plot Generator", page_icon="📊", layout="wide")

TOL_OPTIONS = ["Value Tolerance", "Percentage Tolerance"]
DEFAULT_DATA = pd.DataFrame({"Reference": [None] * 8, "Measured": [None] * 8})


# --------------------------------------------------------------------------
# Authentication gate
# --------------------------------------------------------------------------
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

# --- Authenticated from here on ---
current_username = st.session_state.get("username")
current_role = auth.role_of(config, current_username) or auth.ROLE_USER
is_manager = auth.is_manager(current_role)

with st.sidebar:
    st.write(f"Signed in as **{st.session_state.get('name')}**"
             f" · {auth.ROLE_LABELS.get(current_role, current_role)}")
    authenticator.logout("Log out", "sidebar")
    st.divider()


# --------------------------------------------------------------------------
# Sidebar — all controls
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Controls")

    st.subheader("Data input")
    input_mode = st.radio("Input mode", ["Table", "Upload Excel"], horizontal=True)

    uploaded_df = None
    if input_mode == "Upload Excel":
        up = st.file_uploader("Excel file (.xlsx / .xls)", type=["xlsx", "xls"])
        sheet = st.text_input("Sheet name", value="Sheet1")
        if up is not None:
            try:
                uploaded_df = pd.read_excel(up, sheet_name=sheet, engine="openpyxl")
                st.success(f"Loaded {len(uploaded_df)} rows.")
            except Exception as e:
                st.error(f"Could not read the file: {e}")

    st.subheader("X-axis basis")
    x_basis = st.radio(
        "Plot difference against",
        ["Reference", "Average"],
        help="Average = (Reference + Measured) / 2 (Bland-Altman). "
             "The full analysis is recomputed against the chosen axis.",
        horizontal=True,
    )

    st.subheader("Labels")
    title = st.text_input("Plot title", value="Method Comparison")
    default_xlabel = "Average (Reference + Measured) / 2" if x_basis == "Average" else "Reference"
    x_label = st.text_input("X-axis label", value=default_xlabel)
    y_label = st.text_input("Y-axis label", value="Difference (Measured - Reference)")

    st.subheader("Tolerance")
    threshold = st.number_input("Threshold (X-axis)", value=1.0, step=0.1, format="%.4f")

    c1, c2 = st.columns(2)
    with c1:
        val_below = st.number_input("Tol < threshold", value=0.15, step=0.01, format="%.4f")
    with c2:
        type_below = st.selectbox("Type <", TOL_OPTIONS, index=0)

    c3, c4 = st.columns(2)
    with c3:
        val_above = st.number_input("Tol > threshold", value=15.0, step=0.5, format="%.4f")
    with c4:
        type_above = st.selectbox("Type >", TOL_OPTIONS, index=1)

    generate = st.button("Generate plot", type="primary", use_container_width=True)


# --------------------------------------------------------------------------
# Main area
# --------------------------------------------------------------------------
st.title("Method Comparison Plot Generator")

# Managers get an Admin tab; everyone sees Data + Plot + Statistics stacked on
# one scrolling page (no tabs among the three).
if is_manager:
    main_tab, admin_tab = st.tabs(["Plot generator", "Admin"])
else:
    main_tab, admin_tab = contextlib.nullcontext(), None

with main_tab:
    # ---------------- Data ----------------
    st.header("Data")
    st.caption("Enter or edit the data below. Two numeric columns are required: "
               "**Reference** and **Measured**. Uploading an Excel file pre-fills this table.")
    seed_df = uploaded_df if uploaded_df is not None else DEFAULT_DATA
    # Keep only the required columns if the upload has extras; add missing ones.
    for col in ["Reference", "Measured"]:
        if col not in seed_df.columns:
            seed_df[col] = None
    seed_df = seed_df[["Reference", "Measured"]]

    edited_df = st.data_editor(
        seed_df,
        num_rows="dynamic",
        use_container_width=True,
        key="data_editor",
        column_config={
            "Reference": st.column_config.NumberColumn("Reference", help="Reference / gold-standard value"),
            "Measured": st.column_config.NumberColumn("Measured", help="Value from the method under test"),
        },
    )

    # Compute on demand and stash the result in session.
    if generate:
        try:
            result = generate_plot(
                edited_df,
                x_basis=x_basis,
                threshold=float(threshold),
                val_below=float(val_below),
                type_below=type_below,
                val_above=float(val_above),
                type_above=type_above,
                title=title,
                x_label=x_label,
                y_label=y_label,
            )
            st.session_state["result"] = result
            st.session_state["error"] = None
        except Exception as e:
            st.session_state["result"] = None
            st.session_state["error"] = str(e)

    result = st.session_state.get("result")
    error = st.session_state.get("error")

    # ---------------- Plot ----------------
    st.divider()
    st.header("Plot")
    if error:
        st.error(f"Could not generate the plot: {error}")
    elif result is None:
        st.info("Fill in the table (or upload a file), set your options, then click **Generate plot**.")
    else:
        st.pyplot(result.fig, use_container_width=True)

        png = io.BytesIO()
        result.fig.savefig(png, format="png", dpi=200, bbox_inches="tight")
        png.seek(0)

        d1, d2 = st.columns(2)
        with d1:
            st.download_button("Download plot (PNG)", data=png,
                               file_name="method_comparison.png", mime="image/png",
                               use_container_width=True)
        with d2:
            csv = result.results_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download data (CSV)", data=csv,
                               file_name="method_comparison_data.csv", mime="text/csv",
                               use_container_width=True)

    # ---------------- Statistics ----------------
    st.divider()
    st.header("Statistics")
    if result is None:
        st.info("Generate a plot to see the statistics.")
    else:
        s = result.stats
        rng = (f"{s['x_min']:.2f} – {s['x_max']:.2f}"
               if math.isfinite(s["x_min"]) and math.isfinite(s["x_max"]) else "No valid range")

        with st.container(border=True):
            m1, m2, m3 = st.columns(3)
            m1.metric("Valid analysis range", rng)
            m2.metric("Mean-diff / OLS angle", f"{s['ols_angle_deg']:.2f}°")
            m3.metric("OLS slope", f"{s['slope']:.4f}")
            m4, m5, m6 = st.columns(3)
            m4.metric("Mean difference", f"{s['mean_diff']:.3f}")
            m5.metric("Total points", s["n_total"])
            m6.metric("Points in valid range", s["n_in_range"])

        ov, vr = s["overall"], s["valid_range"]
        c_over, c_valid = st.columns(2)
        with c_over:
            with st.container(border=True):
                st.markdown("**Outliers — overall**")
                st.caption("Across all data points")
                a, b, c = st.columns(3)
                a.metric("Total", ov["outliers_n"], f"{ov['outliers_pct']:.1f}%", delta_color="off")
                b.metric("Over", ov["over_n"], f"{ov['over_pct']:.1f}%", delta_color="off")
                c.metric("Under", ov["under_n"], f"{ov['under_pct']:.1f}%", delta_color="off")
        with c_valid:
            with st.container(border=True):
                st.markdown("**Outliers — valid range**")
                st.caption("Inside the analysis range")
                a, b, c = st.columns(3)
                a.metric("Total", vr["outliers_n"], f"{vr['outliers_pct']:.1f}%", delta_color="off")
                b.metric("Over", vr["over_n"], f"{vr['over_pct']:.1f}%", delta_color="off")
                c.metric("Under", vr["under_n"], f"{vr['under_pct']:.1f}%", delta_color="off")

if admin_tab is not None:
    with admin_tab:
        auth.render_admin_panel(config, current_username, current_role)
