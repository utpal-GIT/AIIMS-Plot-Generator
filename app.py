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

import numpy as np
import pandas as pd
import streamlit as st
from streamlit_option_menu import option_menu

import auth
import config_store
import report
from plot_logic import generate_plot

st.set_page_config(page_title="AIIMS Plotter", page_icon="📊", layout="wide")

TOL_OPTIONS = config_store.TOL_OPTIONS
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "primaryhealthtech_logo.jpg")


def _blank_data(n=6):
    # float64 columns (not object) so pasted/typed values keep full precision.
    return pd.DataFrame({"Reference": pd.Series([np.nan] * n, dtype="float64"),
                         "Measured": pd.Series([np.nan] * n, dtype="float64")})

st.markdown(
    """
    <style>
      /* Balanced spacing + smaller, consistent font sizes */
      .block-container{padding-top:1.8rem; padding-bottom:2rem; max-width:1360px;}
      [data-testid="stVerticalBlock"]{gap:0.7rem;}
      [data-testid="stHeading"]{margin-bottom:0.2rem;}
      h1{font-size:1.5rem !important; margin-bottom:0.2rem !important;}
      h2{font-size:1.1rem !important; margin:0.1rem 0 0.2rem !important;}
      h3{font-size:0.98rem !important; margin:0.1rem 0 0.2rem !important;}
      hr{margin:0.5rem 0 !important;}
      [data-testid="stExpander"]{margin-top:0.1rem;}
      /* smaller body text, labels, and input text app-wide */
      [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li{font-size:14px;}
      [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label{font-size:13px;}
      .stTextInput input, .stNumberInput input, .stTextArea textarea,
      .stDateInput input, [data-baseweb="select"]{font-size:14px !important;}
      [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p{font-size:12.5px;}
      .sc{background:#ffffff;border:1px solid #eef0f2;border-radius:10px;padding:9px 12px;}
      .scl{font-size:11px;font-weight:600;letter-spacing:.5px;color:#94a3b8;
           text-transform:uppercase;margin-bottom:3px;}
      .scv{font-size:19px;font-weight:600;color:#1f2937;line-height:1.15;}
      .scs{font-size:12px;color:#64748b;margin-top:2px;}
      .grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
      .tolwrap{display:flex;gap:8px;flex-wrap:wrap;align-items:stretch;}
      .tolchip{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:10px;
               padding:7px 12px;min-width:92px;}
      .tolchip .k{font-size:10.5px;color:#64748b;font-weight:600;
                  text-transform:uppercase;letter-spacing:.4px;}
      .tolchip .v{font-size:16px;color:#0f172a;font-weight:600;}
      .obreak{display:flex;gap:18px;margin-top:6px;}
      .obreak .n{font-size:19px;font-weight:600;line-height:1;}
      .obreak .t{font-size:11px;color:#64748b;margin-top:2px;}
      .tcard{border:1px solid #e2e8f0;border-radius:10px;padding:9px 14px;background:#fff;}
      .tcard .head{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
      .tcard .pname{font-size:16px;font-weight:600;color:#0f172a;}
      .tcard .punit{font-size:12px;color:#475569;background:#f1f5f9;border-radius:6px;padding:2px 8px;}
      .tcard .tlabel{font-size:11px;font-weight:600;letter-spacing:.5px;color:#94a3b8;
                     text-transform:uppercase;margin-left:auto;}
      .tcard .rules{display:flex;gap:10px;flex-wrap:wrap;}
      .tcard .rule{display:flex;align-items:center;gap:8px;background:#f8fafc;
                   border:1px solid #eef0f2;border-radius:8px;padding:7px 12px;}
      .tcard .cond{font-size:12.5px;color:#475569;font-weight:600;}
      .tcard .arrow{color:#cbd5e1;}
      .tcard .tval{font-size:15px;font-weight:600;color:#0f172a;}
      .tcard .note{font-size:11px;color:#94a3b8;}
      .rchip{display:inline-flex;align-items:center;gap:7px;background:#f1f5f9;
             border:1px solid #e2e8f0;border-radius:8px;padding:7px 13px;
             font-size:13px;color:#475569;font-weight:500;
             font-family:ui-monospace,"SFMono-Regular","Cascadia Code","Courier New",monospace;}
      .rchip b{color:#0f172a;font-weight:600;}
      .rchip .ar{color:#cbd5e1;}
      .mono{font-family:ui-monospace,"SFMono-Regular","Cascadia Code","Courier New",monospace;
            color:#475569;font-size:14px;}
      /* Configurations table row separators + icon-only edit/delete buttons */
      .st-key-cfgtable [data-testid="stHorizontalBlock"]{
        border-bottom:1px solid #eef0f2; padding-bottom:10px;}
      /* extra breathing room under the header row before its line */
      .st-key-cfgtable [data-testid="stHorizontalBlock"]:has(.scl){padding-bottom:16px;}
      [class*="st-key-cfg_edit"] button,[class*="st-key-cfg_del"] button{
        background:transparent !important; border:none !important; box-shadow:none !important;
        min-height:auto !important; padding:2px 6px !important; color:#94a3b8 !important;}
      [class*="st-key-cfg_edit"] button:hover{color:#2563eb !important;}
      [class*="st-key-cfg_del"] button{color:#f87171 !important;}
      [class*="st-key-cfg_del"] button:hover{color:#dc2626 !important;}
      .st-key-belowcard,.st-key-abovecard{background:#f8fafc !important;}
      .dash-title{font-size:1.55rem;font-weight:600;color:#0f172a;line-height:1.1;}
      .dash-sub{font-size:13px;color:#64748b;margin:4px 0 0;}
      /* Force inner padding on the control bar so labels clear the border
         (robust across Streamlit versions via the stable st-key class) */
      .st-key-ctrlbar{padding:16px 18px !important;}
      /* Vertical dividers: between parameter|tolerance and tolerance|generate */
      .st-key-ctrlbar [data-testid="stHorizontalBlock"] > div:nth-child(n+2){
        border-left:1px solid #e5e7eb; padding-left:1.4rem; margin-left:0.4rem;}
      /* White dropdown to match the control-bar design */
      .st-key-ctrlbar [data-baseweb="select"] > div{
        background-color:#ffffff !important; border:1px solid #d1d5db !important;}
      /* Sidebar: no scrollbars */
      [data-testid="stSidebarContent"]{overflow:hidden !important;}
      /* Sidebar bottom section pinned to the bottom (logout + user card) */
      section[data-testid="stSidebar"] .st-key-sbbottom{
        position:absolute; bottom:1.75rem; left:0.75rem; right:0.75rem;}
      section[data-testid="stSidebar"] .st-key-sbbottom button{
        width:100% !important; display:flex !important; align-items:center !important;
        justify-content:flex-start !important; text-align:left !important;
        background:transparent !important; border:none !important; box-shadow:none !important;
        color:#475569 !important; font-weight:500 !important; padding-left:26px !important;}
      /* the flex-centering lives on the button's inner content wrapper(s) */
      section[data-testid="stSidebar"] .st-key-sbbottom button > div{
        display:flex !important; justify-content:flex-start !important; width:100% !important;}
      section[data-testid="stSidebar"] .st-key-sbbottom button [data-has-shortcut]{
        margin-right:auto !important; margin-left:0 !important;}
      section[data-testid="stSidebar"] .st-key-sbbottom button p{text-align:left !important;}
      section[data-testid="stSidebar"] .st-key-sbbottom button:hover{
        background:#f1f5f9 !important; color:#0f172a !important;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def _logo_data_uri(path):
    with open(path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def _initials(name):
    titles = {"dr", "mr", "mrs", "ms", "prof", "miss"}
    parts = [p.strip(".") for p in (name or "").split() if p.strip(".").lower() not in titles]
    if not parts:
        parts = (name or "?").split()
    letters = [p[0] for p in parts[:2] if p]
    return ("".join(letters).upper() or "?")


def _auth_brand(subtitle, show_name=True):
    logo = ""
    if os.path.exists(LOGO_PATH):
        logo = (f"<img src='{_logo_data_uri(LOGO_PATH)}' "
                f"style='width:58px;height:58px;border-radius:12px;'>")
    name = ("<div style='font-size:27px;font-weight:700;color:#0f172a;margin-top:12px;'>"
            "AIIMS Plotter</div>") if show_name else ""
    sub = (f"<div style='font-size:14px;color:#64748b;margin-top:6px;'>{subtitle}</div>"
           if subtitle else "")
    st.markdown(
        f"<div style='text-align:center; padding:14px 0 18px;'>{logo}{name}{sub}</div>",
        unsafe_allow_html=True,
    )


def _hide_sidebar():
    st.markdown(
        "<style>section[data-testid='stSidebar']{display:none;}"
        "[data-testid='stSidebarCollapsedControl'],[data-testid='collapsedControl']{display:none;}"
        "</style>",
        unsafe_allow_html=True,
    )


# ==========================================================================
# Authentication gate  (branded, centered login / setup)
# ==========================================================================
config = auth.load_config()

if auth.needs_setup(config):
    _hide_sidebar()
    cols = st.columns([1, 1, 1])
    with cols[1]:
        _auth_brand("Welcome — create your administrator account", show_name=True)
        with st.container(border=True):
            auth.render_setup(config)
    st.stop()

authenticator = auth.build_authenticator(config)

if st.session_state.get("authentication_status") is not True:
    _hide_sidebar()
    cols = st.columns([1, 1, 1])
    with cols[1]:
        _auth_brand("Sign in to continue")
        flash = st.session_state.pop("_flash", None)
        if flash:
            st.success(flash)
        with st.container(border=True):
            authenticator.login(location="main",
                                fields={"Form name": "", "Login": "Sign in"})
            if st.session_state.get("authentication_status") is False:
                st.error("Incorrect username or password.")
            else:
                st.caption("Enter your credentials to access the dashboard.")
    st.stop()

current_username = st.session_state.get("username")
current_role = auth.role_of(config, current_username) or auth.ROLE_USER
is_manager = auth.is_manager(current_role)


# ==========================================================================
# Pages
# ==========================================================================
def page_dashboard():
    params = config_store.load_params()

    # ---- Header: title + Export report on one row, subtitle below ----
    hc = st.columns([5, 1.4], vertical_alignment="center")
    with hc[0]:
        st.markdown("<div class='dash-title'>Dashboard</div>", unsafe_allow_html=True)
    with hc[1]:
        pdf = st.session_state.get("pdf_bytes")
        st.download_button(
            "Export report", data=pdf if pdf else b"",
            file_name=st.session_state.get("pdf_name", "report.pdf"),
            mime="application/pdf", disabled=pdf is None,
            icon=":material/description:", use_container_width=True,
            help=None if pdf else "Generate a plot first",
        )
    st.markdown(
        "<div class='dash-sub'>Generate a method-comparison difference plot and statistics.</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)

    if not params:
        st.warning("No test parameters configured yet. Add one in **Configurations** "
                   "to set its tolerance limits, then return here to plot.")
        return

    # ---- Control bar: parameter · tolerance · generate ----
    lbl = "<div class='scl' style='margin-bottom:8px'>{}</div>"
    with st.container(border=True, key="ctrlbar"):
        cc = st.columns([2.4, 3.4, 1.8], vertical_alignment="top")
        with cc[0]:
            st.markdown(lbl.format("Test parameter"), unsafe_allow_html=True)
            param_name = st.selectbox(
                "Test parameter", list(params.keys()), label_visibility="collapsed",
                format_func=lambda k: k + (f" ({params[k]['unit']})" if params[k].get("unit") else ""),
            )
        p = params[param_name]
        with cc[1]:
            st.markdown(lbl.format("Tolerance limits"), unsafe_allow_html=True)
            b_val, _ = _tol_desc(p["val_below"], p["type_below"])
            a_val, _ = _tol_desc(p["val_above"], p["type_above"])
            thr = f"{p['threshold']:g}"
            st.markdown(
                "<div style='display:flex;gap:8px;flex-wrap:wrap;'>"
                f"<span class='rchip'>X ≤ {thr} <span class='ar'>→</span> <b>{b_val}</b></span>"
                f"<span class='rchip'>X &gt; {thr} <span class='ar'>→</span> <b>{a_val}</b></span>"
                "</div>",
                unsafe_allow_html=True,
            )
        with cc[2]:
            # invisible label so the button lines up with the boxes above
            st.markdown("<div class='scl' style='margin-bottom:8px;visibility:hidden'>&nbsp;</div>",
                        unsafe_allow_html=True)
            generate = st.button("Generate plot", type="primary",
                                 icon=":material/play_arrow:", use_container_width=True)

    st.divider()

    # --- Data (left)  +  Statistics (right) ---
    data_col, stats_col = st.columns(2, gap="large")
    with data_col:
        st.subheader("Data")
        mode = st.radio("Input mode", ["Table", "Upload Excel"], horizontal=True)

        if "data_df" not in st.session_state:
            st.session_state["data_df"] = _blank_data()

        if mode == "Upload Excel":
            up = st.file_uploader("Excel file (.xlsx / .xls)", type=["xlsx", "xls"])
            sheet = st.text_input("Sheet name", value="Sheet1")
            if up is not None:
                try:
                    udf = pd.read_excel(up, sheet_name=sheet, engine="openpyxl")
                    for col in ["Reference", "Measured"]:
                        if col not in udf.columns:
                            udf[col] = np.nan
                    st.session_state["data_df"] = udf[["Reference", "Measured"]].reset_index(drop=True)
                    st.success(f"Loaded {len(st.session_state['data_df'])} rows.")
                except Exception as e:
                    st.error(f"Could not read the file: {e}")

        base = st.session_state["data_df"].copy()
        for col in ["Reference", "Measured"]:
            if col not in base.columns:
                base[col] = np.nan
        base = base[["Reference", "Measured"]].reset_index(drop=True)
        base.insert(0, "Sl. No", range(1, len(base) + 1))

        edited = st.data_editor(
            base, num_rows="dynamic", use_container_width=True,
            column_config={
                "Sl. No": st.column_config.NumberColumn("Sl. No", disabled=True, width="small"),
                "Reference": st.column_config.NumberColumn("Reference", help="Reference / gold-standard value"),
                "Measured": st.column_config.NumberColumn("Measured", help="Value from the method under test"),
            },
        )
        # Store full-precision numeric values (no dtype ambiguity from pasting).
        store = edited.drop(columns=["Sl. No"]).reset_index(drop=True)
        for col in ["Reference", "Measured"]:
            store[col] = pd.to_numeric(store[col], errors="coerce")
        st.session_state["data_df"] = store
        edited_df = store

        # Data fingerprint — compare this between upload and paste to confirm
        # the table holds exactly the same numbers as your file.
        vd = edited_df.dropna(subset=["Reference", "Measured"])
        if len(vd):
            st.caption(
                f"**{len(vd)} complete rows** · Reference mean {vd['Reference'].mean():.4f} "
                f"(min {vd['Reference'].min():.3f}, max {vd['Reference'].max():.3f}) · "
                f"Measured mean {vd['Measured'].mean():.4f}"
            )

    stats_box = stats_col.container()  # filled after compute so it sits beside the table

    st.divider()

    # --- Plot: options (collapsible), then the plot ---
    st.subheader("Plot")
    with st.expander("Plot options — axis basis, title, labels"):
        oc = st.columns([1, 1.3, 1.3, 1.3])
        x_basis = oc[0].selectbox("X-axis basis", ["Reference", "Average"],
                                  help="Average = (Reference + Measured) / 2 (Bland–Altman).")
        default_x = "Average (Reference + Measured) / 2" if x_basis == "Average" else "Reference"
        title = oc[1].text_input("Plot title", value=param_name)
        x_label = oc[2].text_input("X-axis label", value=default_x)
        y_label = oc[3].text_input("Y-axis label", value="Difference (Measured - Reference)")

    plot_box = st.container()

    # --- Compute (after all inputs are defined) ---
    if generate:
        try:
            result = generate_plot(
                edited_df, x_basis=x_basis,
                threshold=p["threshold"], val_below=p["val_below"], type_below=p["type_below"],
                val_above=p["val_above"], type_above=p["type_above"],
                title=title, x_label=x_label, y_label=y_label,
            )
            st.session_state["result"] = result
            st.session_state["error"] = None
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
        st.rerun()  # refresh so the header "Export report" button picks up the new PDF

    result = st.session_state.get("result")
    error = st.session_state.get("error")

    # --- Statistics — rendered into the box beside the data table ---
    with stats_box:
        st.subheader("Statistics")
        if error:
            st.error("Couldn't compute — check the data and options.")
        elif result is None:
            st.info("Generate a plot to see the statistics.")
        else:
            _render_statistics(result.stats)

    # --- Plot output ---
    with plot_box:
        if error:
            st.error(f"Could not generate the plot: {error}")
        elif result is None:
            st.info("Enter data, then click **Generate plot** at the top.")
        else:
            st.pyplot(result.fig, use_container_width=True)
            png = io.BytesIO()
            result.fig.savefig(png, format="png", dpi=200, bbox_inches="tight")
            png.seek(0)
            st.download_button("Download plot (PNG)", png, file_name="method_comparison.png",
                               mime="image/png")


def _tol_desc(value, tol_type):
    """Return (value_text, note) describing a tolerance limit."""
    if str(tol_type).startswith("Percentage"):
        return f"± {value:g}%", "of value"
    return f"± {value:g}", "absolute"


def _stat_card(label, value):
    return f"<div class='sc'><div class='scl'>{label}</div><div class='scv'>{value}</div></div>"


# Point-category colors — identical to the plot markers.
CAT_COLORS = [
    ("Valid", "valid", "#16a34a"),
    ("Outlier · in valid region", "outlier_in_range", "#f59e0b"),
    ("Within tolerance · outside valid region", "within_tol_outside", "#0891b2"),
    ("Outlier · outside valid region", "outlier_outside", "#dc2626"),
]


def _cat_card(label, count, pct, color):
    dot = (f"<span style='display:inline-block;width:9px;height:9px;border-radius:50%;"
           f"background:{color};margin-right:6px;'></span>")
    return (f"<div class='sc'>"
            f"<div class='scl' style='margin-bottom:4px;'>{dot}{label}</div>"
            f"<div class='scv' style='color:{color}'>{count}"
            f"<span style='font-size:13px;color:#64748b;font-weight:500;'> · {pct:.1f}%</span>"
            f"</div></div>")


def _summary_row(label, value, color="#0f172a", indent=False):
    lead = ("<span style='color:#cbd5e1;margin:0 6px 0 14px;'>└</span>"
            if indent else "")
    return (
        "<div style='display:flex;justify-content:space-between;align-items:baseline;"
        "padding:4px 0;border-bottom:1px solid #f1f5f9;'>"
        f"<span style='color:#475569;font-size:13px;'>{lead}{label}</span>"
        f"<span style='color:{color};font-size:14px;font-weight:600;'>{value}</span></div>"
    )


def _summary_card(title, rows):
    body = "".join(_summary_row(*r) for r in rows)
    return f"<div class='sc'><div class='scl' style='margin-bottom:4px;'>{title}</div>{body}</div>"


def _render_statistics(s):
    import math
    rng = (f"{s['x_min']:.2f} – {s['x_max']:.2f}"
           if math.isfinite(s["x_min"]) and math.isfinite(s["x_max"]) else "No valid range")
    ov, vr = s["overall"], s["valid_range"]

    # Key metrics
    metrics = [
        _stat_card("Analysis range", rng),
        _stat_card("Mean-diff / OLS angle", f"{s['ols_angle_deg']:.2f}°"),
        _stat_card("OLS slope", f"{s['slope']:.4f}"),
        _stat_card("Mean difference", f"{s['mean_diff']:.3f}"),
    ]

    overall_rows = [
        ("Total data points", str(s["n_total"])),
        ("Outliers", f"{ov['outliers_n']} ({ov['outliers_pct']:.1f}%)", "#334155"),
        ("Overestimated", f"{ov['over_n']} ({ov['over_pct']:.1f}%)", "#334155", True),
        ("Underestimated", f"{ov['under_n']} ({ov['under_pct']:.1f}%)", "#334155", True),
    ]
    valid_rows = [
        ("Data points in valid range", f"{vr['n_points']} ({vr['n_points_pct']:.1f}%)", "#334155"),
        ("Outliers", f"{vr['outliers_n']} ({vr['outliers_pct']:.1f}%)", "#f59e0b"),
        ("Overestimated", f"{vr['over_n']} ({vr['over_pct']:.1f}%)", "#f59e0b", True),
        ("Underestimated", f"{vr['under_n']} ({vr['under_pct']:.1f}%)", "#f59e0b", True),
    ]

    n = s["n_total"] or 1
    cats = s.get("categories", {})
    cat_cards = "".join(
        _cat_card(lbl, cats.get(key, 0), cats.get(key, 0) / n * 100, col)
        for lbl, key, col in CAT_COLORS
    )

    st.markdown(
        "<div class='grid2'>" + "".join(metrics) + "</div>"
        "<div class='grid2' style='margin-top:12px;'>"
        + _summary_card("Overall plot summary", overall_rows)
        + _summary_card("Valid range summary", valid_rows)
        + "</div>"
        "<div class='scl' style='margin:14px 0 6px;'>Point categories</div>"
        "<div class='grid2'>" + cat_cards + "</div>"
        "<div class='scs' style='margin-top:8px;'>All percentages are out of the "
        "total data points in the plot.</div>",
        unsafe_allow_html=True,
    )


@st.dialog("Add or edit a parameter", width="large")
def _param_dialog(params, editing):
    preset = params.get(editing, {}) if editing else {}
    st.caption("Editable by any signed-in user.")
    with st.form("param_dialog_form"):
        c = st.columns(2)
        name = c[0].text_input("Parameter name", value=editing or "", placeholder="e.g. Creatinine")
        unit = c[1].text_input("Unit (optional)", value=preset.get("unit", ""), placeholder="e.g. mg/dL")
        threshold = st.number_input("Threshold (X-axis)", value=float(preset.get("threshold", 1.0)),
                                    step=0.1, format="%.4f")
        g = st.columns(2)
        with g[0], st.container(border=True, key="belowcard"):
            st.markdown("<div class='scl'>Below threshold</div>", unsafe_allow_html=True)
            bc = st.columns(2)
            val_below = bc[0].number_input("Value", value=float(preset.get("val_below", 0.15)),
                                           step=0.01, format="%.4f")
            type_below = bc[1].selectbox("Type", TOL_OPTIONS,
                                         index=TOL_OPTIONS.index(preset.get("type_below", TOL_OPTIONS[0])),
                                         format_func=lambda t: t.split()[0])
        with g[1], st.container(border=True, key="abovecard"):
            st.markdown("<div class='scl'>Above threshold</div>", unsafe_allow_html=True)
            ac = st.columns(2)
            val_above = ac[0].number_input("Value", value=float(preset.get("val_above", 15.0)),
                                           step=0.5, format="%.4f")
            type_above = ac[1].selectbox("Type", TOL_OPTIONS,
                                         index=TOL_OPTIONS.index(preset.get("type_above", TOL_OPTIONS[1])),
                                         format_func=lambda t: t.split()[0])
        saved = st.form_submit_button("Save parameter", type="primary", use_container_width=True)
    if saved:
        ok, msg = config_store.upsert_param(
            params, name, unit=unit, threshold=threshold,
            val_below=val_below, type_below=type_below,
            val_above=val_above, type_above=type_above)
        if ok:
            st.rerun()
        else:
            st.error(msg)


def page_configurations():
    hc = st.columns([5, 1.6], vertical_alignment="center")
    with hc[0]:
        st.markdown(
            "<div class='dash-title'>Configurations</div>"
            "<div class='dash-sub'>Define test parameters and their tolerance limits — "
            "shared across the lab and applied on the Dashboard.</div>",
            unsafe_allow_html=True,
        )
    with hc[1]:
        add_clicked = st.button("Add parameter", icon=":material/add:", type="primary",
                                use_container_width=True)
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    params = config_store.load_params()
    COLS = [2, 1.3, 1.1, 1.4, 1.4, 0.45, 0.45]
    edit_target = None

    # ---- Parameters table ----
    with st.container(border=True, key="cfgtable"):
        head = st.columns(COLS)
        for col, title in zip(head, ["Parameter", "Unit", "Threshold", "Below tol.", "Above tol.", "", ""]):
            col.markdown(f"<div class='scl'>{title}</div>", unsafe_allow_html=True)
        if not params:
            st.caption('No parameters yet — click "Add parameter".')
        for name, p in params.items():
            r = st.columns(COLS, vertical_alignment="center")
            r[0].markdown(f"<div style='font-weight:600;color:#0f172a;'>{name}</div>", unsafe_allow_html=True)
            r[1].markdown(f"<span class='mono'>{p.get('unit', '')}</span>", unsafe_allow_html=True)
            r[2].markdown(f"<span class='mono'>{p['threshold']:g}</span>", unsafe_allow_html=True)
            r[3].markdown(f"<span class='mono'>{_tol_desc(p['val_below'], p['type_below'])[0]}</span>", unsafe_allow_html=True)
            r[4].markdown(f"<span class='mono'>{_tol_desc(p['val_above'], p['type_above'])[0]}</span>", unsafe_allow_html=True)
            if r[5].button("", icon=":material/edit:", key=f"cfg_edit_{name}", help="Edit"):
                edit_target = name
            if r[6].button("", icon=":material/delete:", key=f"cfg_del_{name}", help="Delete"):
                config_store.delete_param(params, name)
                st.rerun()

    # ---- Open the modal for add / edit ----
    if add_clicked:
        _param_dialog(params, None)
    elif edit_target:
        _param_dialog(params, edit_target)


def page_account():
    outer = st.columns([1, 5, 1])
    with outer[1]:
        st.markdown(
            "<div class='dash-title'>Account</div>"
            "<div class='dash-sub'>Your profile and password.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        name = st.session_state.get("name", "")
        role_label = auth.ROLE_LABELS.get(current_role, current_role)

        # ---- Profile card (avatar + info, vertically centered) ----
        with st.container(border=True, key="acctprofile"):
            st.markdown(
                "<div style='display:flex; align-items:center; justify-content:space-between; gap:16px;'>"
                "<div style='display:flex; align-items:center; gap:12px;'>"
                f"<div style='width:44px; height:44px; border-radius:50%; background:#16a34a; "
                f"color:#fff; display:flex; align-items:center; justify-content:center; "
                f"font-weight:600; font-size:16px; flex:none;'>{_initials(name)}</div>"
                "<div style='line-height:1.3;'>"
                f"<div style='font-size:16px; font-weight:600; color:#0f172a;'>{name}</div>"
                f"<div class='mono' style='color:#94a3b8; font-size:12px;'>{current_username}</div>"
                "</div></div>"
                "<span style='background:#dcfce7; color:#16a34a; font-weight:600; font-size:12px; "
                f"padding:4px 11px; border-radius:999px; white-space:nowrap;'>{role_label}</span>"
                "</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # ---- Profile edit + Change password, side by side ----
        cols = st.columns(2, gap="medium")

        with cols[0]:
            with st.container(border=True, key="acctedit"):
                st.markdown("**Profile**")
                with st.form("profile_form"):
                    new_name = st.text_input("Display name", value=name)
                    new_un = st.text_input("Username", value=current_username,
                                           help="Changing your username will sign you out.")
                    saved = st.form_submit_button("Save profile", type="primary")
                if saved:
                    un_changed = new_un.strip() != current_username
                    name_changed = new_name.strip() != name and new_name.strip()
                    if un_changed:
                        if name_changed:
                            auth.change_display_name(config, current_username, new_name)
                        ok, msg = auth.change_username(config, current_username, new_un)
                        if ok:
                            st.session_state["_flash"] = "Username updated — please sign in with your new username."
                            authenticator.logout(location="unrendered")
                            for k in ("nav", "data_df", "result", "error", "pdf_bytes", "pdf_name"):
                                st.session_state.pop(k, None)
                            st.rerun()
                        else:
                            st.error(msg)
                    elif name_changed:
                        ok, msg = auth.change_display_name(config, current_username, new_name)
                        if ok:
                            st.session_state["name"] = new_name.strip()
                            st.success("Profile updated.")
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.info("No changes to save.")

        with cols[1]:
            with st.container(border=True, key="acctpw"):
                st.markdown("**Change password**")
                with st.form("change_pw", clear_on_submit=True):
                    old = st.text_input("Current password", type="password")
                    new1 = st.text_input("New password", type="password")
                    new2 = st.text_input("Confirm new password", type="password")
                    saved_pw = st.form_submit_button("Update password", type="primary")
                if saved_pw:
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
    logo_img = (f"<img src='{_logo_data_uri(LOGO_PATH)}' style='width:38px; height:38px; "
                f"border-radius:8px;'>") if os.path.exists(LOGO_PATH) else ""
    st.markdown(
        f"<div style='display:flex; align-items:center; gap:11px; padding:2px 2px 18px;'>"
        f"{logo_img}"
        f"<div style='line-height:1.15;'>"
        f"<div style='font-size:19px; font-weight:600; color:#1f2937;'>AIIMS Plotter</div>"
        f"<div style='font-size:12px; color:#94a3b8;'>Primary Health Tech</div>"
        f"</div></div>"
        f"<div style='font-size:11px; font-weight:600; color:#94a3b8; letter-spacing:.6px; "
        f"padding:0 2px 6px;'>MENU</div>",
        unsafe_allow_html=True,
    )
    selected = option_menu(
        menu_title=None,
        options=["Dashboard", "Configurations", "Account", "Settings"],
        icons=["speedometer2", "sliders", "person", "gear"],
        default_index=0,
        key="nav",
        styles={
            "container": {"padding": "0", "background-color": "transparent"},
            "nav-link": {"font-size": "14px", "padding": "8px 12px", "border-radius": "8px"},
            "nav-link-selected": {"background-color": "#2563eb"},
        },
    )

    # Bottom section (pinned to the sidebar bottom): logout + user card
    with st.container(key="sbbottom"):
        logout_clicked = st.button("Logout", icon=":material/logout:",
                                   use_container_width=True, key="logout_btn")
        st.markdown("<div style='border-top:1px solid #e5e7eb; margin:8px 0 10px;'></div>",
                    unsafe_allow_html=True)
        initials = _initials(st.session_state.get("name", ""))
        st.markdown(
            "<div style='display:flex; align-items:center; gap:10px;'>"
            f"<div style='width:38px; height:38px; border-radius:50%; background:#dcfce7; "
            f"color:#16a34a; display:flex; align-items:center; justify-content:center; "
            f"font-weight:600; font-size:13px; flex:none;'>{initials}</div>"
            "<div style='line-height:1.2; min-width:0;'>"
            f"<div style='font-size:14px; font-weight:600; color:#1f2937; white-space:nowrap; "
            f"overflow:hidden; text-overflow:ellipsis;'>{st.session_state.get('name')}</div>"
            f"<div style='font-size:12px; color:#94a3b8;'>{auth.ROLE_LABELS.get(current_role, current_role)}</div>"
            "</div></div>",
            unsafe_allow_html=True,
        )

if logout_clicked:
    authenticator.logout(location="unrendered")
    for k in ("nav", "data_df", "result", "error", "pdf_bytes", "pdf_name"):
        st.session_state.pop(k, None)
    st.rerun()

if selected == "Dashboard":
    page_dashboard()
elif selected == "Configurations":
    page_configurations()
elif selected == "Account":
    page_account()
elif selected == "Settings":
    page_settings()
