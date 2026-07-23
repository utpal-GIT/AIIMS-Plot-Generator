"""
Core computation and plotting for the Method Comparison plot.

Pure logic — no Streamlit imports here so it can be unit-tested and reused.
OLS regression only (Theil-Sen path from the original desktop tool removed).
"""

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")  # headless backend for web/server rendering
import matplotlib.pyplot as plt
import statsmodels.api as sm
import scipy.stats as stats


# --- HELPER: INTERSECTIONS BETWEEN TWO DISCRETE CURVES ---
def find_intersections(x, y1, y2):
    """Find x-locations where two curves defined on the same x grid cross."""
    diff = y1 - y2
    signs = np.sign(diff)
    signs[signs == 0] = -1
    crossings = np.where(np.diff(signs))[0]

    intersect_x = []
    for i in crossings:
        x0, x1 = x[i], x[i + 1]
        y_diff0, y_diff1 = diff[i], diff[i + 1]
        if y_diff1 - y_diff0 != 0:
            t = -y_diff0 / (y_diff1 - y_diff0)
            intersect_x.append(x0 + t * (x1 - x0))
    return intersect_x


class PlotResult:
    """Container for the generated figure plus all computed statistics."""

    def __init__(self, fig, stats_dict, results_df):
        self.fig = fig
        self.stats = stats_dict
        self.results_df = results_df


def generate_plot(
    df,
    *,
    x_basis="Reference",          # "Reference" or "Average"
    threshold=1.0,
    val_below=0.15,
    type_below="Value Tolerance",
    val_above=15.0,
    type_above="Percentage Tolerance",
    title="Method Comparison",
    x_label=None,
    y_label="Difference (Measured - Reference)",
    show_normality=True,
):
    """
    Build the method-comparison plot from a dataframe with columns
    'Reference' and 'Measured'.

    x_basis == "Reference":  x = Reference        (original behaviour)
    x_basis == "Average":    x = (Reference + Measured) / 2   (Bland-Altman;
                             the FULL analysis is recomputed against x — Option A)

    Returns a PlotResult(fig, stats, results_df).
    """
    # ---- 1. Prepare data ----
    df = df.copy()
    df["Reference"] = pd.to_numeric(df["Reference"], errors="coerce")
    df["Measured"] = pd.to_numeric(df["Measured"], errors="coerce")
    df = df.dropna(subset=["Reference", "Measured"]).reset_index(drop=True)

    if len(df) < 3:
        raise ValueError("Need at least 3 valid rows (Reference & Measured) to fit a regression.")

    df["Diff"] = df["Measured"] - df["Reference"]

    # X axis basis — everything downstream keys off df['X'] (Option A).
    if x_basis == "Average":
        df["X"] = (df["Reference"] + df["Measured"]) / 2.0
    else:
        df["X"] = df["Reference"]

    df = df.sort_values(by="X").reset_index(drop=True)

    if x_label is None:
        x_label = "Average (Reference + Measured) / 2" if x_basis == "Average" else "Reference"

    # ---- 2. Aggregate statistics (mean diff, LoA, CIs) ----
    mean_diff = df["Diff"].mean()
    std_diff = df["Diff"].std()
    n_total = len(df)

    se_mean = std_diff / np.sqrt(n_total)
    ci_mean_upper = mean_diff + 1.96 * se_mean
    ci_mean_lower = mean_diff - 1.96 * se_mean

    loa_upper = mean_diff + 1.96 * std_diff
    loa_lower = mean_diff - 1.96 * std_diff

    # ---- 3. OLS regression: Diff ~ X ----
    reg_name = "OLS Regression"
    X_sm = sm.add_constant(df["X"])
    model = sm.OLS(df["Diff"], X_sm).fit()
    slope = model.params.iloc[1]

    # Angle between the (horizontal) mean-diff line and the OLS line,
    # in data units: mean-diff slope = 0, so angle = atan(OLS slope).
    ols_angle_deg = float(np.degrees(np.arctan(slope)))

    # Optional normality info (display only — model is always OLS now).
    is_normal = None
    p_value = None
    if show_normality:
        try:
            _, p_value = stats.shapiro(df["X"])
            is_normal = p_value >= 0.05
        except Exception:
            is_normal, p_value = None, None

    def get_reg_predictions(x_arr):
        x_arr = np.asarray(x_arr, dtype=float)
        if x_arr.size == 0:
            return np.array([]), np.array([]), np.array([])
        X_arr_sm = sm.add_constant(x_arr, has_constant="add")
        pred = model.get_prediction(X_arr_sm).summary_frame(alpha=0.05)
        return pred["mean"].values, pred["mean_ci_lower"].values, pred["mean_ci_upper"].values

    mean_vals, ci_lower_vals, ci_upper_vals = get_reg_predictions(df["X"].values)

    # ---- 4. Tolerance limits (value or percentage, split by threshold) ----
    def calculate_tolerance(x):
        if x <= threshold:
            return (val_below / 100 * x) if type_below == "Percentage Tolerance" else val_below
        return (val_above / 100 * x) if type_above == "Percentage Tolerance" else val_above

    df["Tol"] = df["X"].apply(calculate_tolerance)

    # ---- 5. Valid analysis range ----
    # The two boundary vertical lines are defined ONLY by:
    #   • intersection of the upper CI (OLS) with the upper tolerance limit
    #   • intersection of the lower CI (OLS) with the lower tolerance limit
    # Equivalently, x is inside the valid range when the upper CI stays within
    # the upper tolerance AND the lower CI stays within the lower tolerance.
    # Where a boundary has no such intersection on a side, it defaults to the
    # data minimum (left) or data maximum (right).
    x_min_data = df["X"].min()
    x_max_data = df["X"].max()

    x_dense_full = np.linspace(x_min_data, x_max_data, 2000)
    if x_min_data <= threshold <= x_max_data:
        x_dense_full = np.append(x_dense_full, [threshold, threshold + 1e-9])
    x_dense_full = np.sort(np.unique(x_dense_full))

    tol_upper_full = np.array([calculate_tolerance(x) for x in x_dense_full])
    tol_lower_full = -tol_upper_full
    _, ci_lower_full, ci_upper_full = get_reg_predictions(x_dense_full)

    # Only the two requested intersection types.
    up_ints = find_intersections(x_dense_full, ci_upper_full, tol_upper_full)
    lo_ints = find_intersections(x_dense_full, ci_lower_full, tol_lower_full)
    boundary_ints = sorted(up_ints + lo_ints)

    valid_mask = (ci_upper_full <= tol_upper_full) & (ci_lower_full >= tol_lower_full)
    valid_idx = np.where(valid_mask)[0]

    if valid_idx.size == 0:
        # No x satisfies both conditions -> no valid range.
        x_min, x_max = np.nan, np.nan
    else:
        i0, i1 = valid_idx[0], valid_idx[-1]
        # Left boundary
        if i0 == 0:
            x_min = x_min_data                       # valid up to the left data edge
        else:
            left_flip = x_dense_full[i0]
            cands = [b for b in boundary_ints if b <= left_flip + 1e-9]
            x_min = max(cands) if cands else x_min_data
        # Right boundary
        if i1 == len(x_dense_full) - 1:
            x_max = x_max_data                       # valid up to the right data edge
        else:
            right_flip = x_dense_full[i1]
            cands = [b for b in boundary_ints if b >= right_flip - 1e-9]
            x_max = min(cands) if cands else x_max_data

    # ---- 6. Tolerance-line segments for plotting (split at threshold) ----
    tol_upper_below = tol_lower_below = x_below = None
    tol_upper_above = tol_lower_above = x_above = None

    if x_min_data <= threshold:
        x_below = np.linspace(x_min_data, min(threshold, x_max_data), 500)
        tol_upper_below = np.array(
            [(val_below / 100 * x) if type_below == "Percentage Tolerance" else val_below for x in x_below]
        )
        tol_lower_below = -tol_upper_below

    if x_max_data >= threshold:
        x_above = np.linspace(max(threshold, x_min_data), x_max_data, 500)
        tol_upper_above = np.array(
            [(val_above / 100 * x) if type_above == "Percentage Tolerance" else val_above for x in x_above]
        )
        tol_lower_above = -tol_upper_above

    # ---- 7. Outlier categorisation (overall + within clinical valid range) ----
    in_tol_all = df["Diff"].abs() <= df["Tol"]
    df["is_outlier"] = ~in_tol_all

    mask_x_range = (df["X"] >= x_min) & (df["X"] <= x_max)
    df_in_x = df[mask_x_range].copy()
    df_out_x = df[~mask_x_range].copy()

    def _breakdown(sub, denom):
        out = sub[sub["is_outlier"]]
        over = out[out["Diff"] > 0]
        under = out[out["Diff"] < 0]
        pct = lambda k: (k / denom * 100.0) if denom > 0 else 0.0
        return {
            "n_points": len(sub),
            "outliers_n": len(out),
            "outliers_pct": pct(len(out)),
            "over_n": len(over),
            "over_pct": pct(len(over)),
            "under_n": len(under),
            "under_pct": pct(len(under)),
        }

    overall = _breakdown(df, n_total)
    valid_range = _breakdown(df_in_x, len(df_in_x))

    df_valid = df_in_x[~df_in_x["is_outlier"]]
    df_outliers_in = df_in_x[df_in_x["is_outlier"]]

    # ---- 8. Plot ----
    fig, ax = plt.subplots(figsize=(13, 7))

    ax.scatter(df_valid["X"], df_valid["Diff"], color="#5fad56", s=25,
               label="Valid (in analysis & tolerance ranges)", alpha=0.7, zorder=5)
    ax.scatter(df_outliers_in["X"], df_outliers_in["Diff"], color="#ec7d10", s=25,
               label="Outlier (in analysis, outside tolerance)", alpha=0.7, zorder=5)
    ax.scatter(df_out_x["X"], df_out_x["Diff"], color="grey", s=20,
               label="Excluded (out of analysis range)", alpha=0.7, zorder=4)

    ax.plot(df["X"], mean_vals, color="blue", lw=2, label=f"{reg_name} line")
    ax.fill_between(df["X"], ci_lower_vals, ci_upper_vals, color="blue",
                    alpha=0.15, label=f"95% {reg_name} CI")

    ax.axhline(mean_diff, color="red", lw=2, label=f"Mean difference ({mean_diff:.3f})")
    ax.axhspan(ci_mean_lower, ci_mean_upper, color="red", alpha=0.2, label="95% mean diff CI")

    ax.axhline(loa_upper, color="#9b5de5", linestyle="--", alpha=0.7, label="Upper LoA (1.96 SD)")
    ax.axhline(loa_lower, color="#6f1a07", linestyle="--", alpha=0.7, label="Lower LoA (1.96 SD)")

    if x_below is not None:
        ax.plot(x_below, tol_upper_below, color="#0ead69", lw=1.5, label="Tolerance limit")
        ax.plot(x_below, tol_lower_below, color="#0ead69", lw=1.5)
    if x_above is not None:
        label_above = "Tolerance limit" if x_below is None else None
        ax.plot(x_above, tol_upper_above, color="#0ead69", lw=1.5, label=label_above)
        ax.plot(x_above, tol_lower_above, color="#0ead69", lw=1.5)

    for bx in (x_min, x_max):
        if np.isfinite(bx):
            ax.axvline(x=bx, color="black", linestyle=":", alpha=0.6, zorder=2)
            ax.text(bx, 0.01, f" x={bx:.2f}", transform=ax.get_xaxis_transform(),
                    rotation=90, va="bottom", ha="right", color="black",
                    fontsize=9, fontweight="bold")

    ax.axhline(0, color="black", lw=1, zorder=1)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel(x_label, fontsize=12)
    ax.set_ylabel(y_label, fontsize=12)
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", borderaxespad=0.0)

    min_text = f"{x_min:.2f}" if np.isfinite(x_min) else "None"
    max_text = f"{x_max:.2f}" if np.isfinite(x_max) else "None"
    norm_line = ""
    if show_normality and p_value is not None:
        norm_line = f"Data distribution: {'Normal' if is_normal else 'Non-Normal'} (p={p_value:.3f})\n"

    info_text = (
        f"{norm_line}"
        f"Active model: {reg_name}\n"
        f"Mean-diff / OLS angle: {ols_angle_deg:.2f}°\n\n"
        f"Analysis range:\n"
        f"   • Min X: {min_text}\n"
        f"   • Max X: {max_text}\n\n"
        f"Total data points: {n_total}\n"
        f"Points in valid range: {len(df_in_x)}\n\n"
        f"Outliers (overall): {overall['outliers_n']} ({overall['outliers_pct']:.1f}%)\n"
        f"   • Over: {overall['over_n']} ({overall['over_pct']:.1f}%)\n"
        f"   • Under: {overall['under_n']} ({overall['under_pct']:.1f}%)\n"
        f"Outliers (valid range): {valid_range['outliers_n']} ({valid_range['outliers_pct']:.1f}%)\n"
        f"   • Over: {valid_range['over_n']} ({valid_range['over_pct']:.1f}%)\n"
        f"   • Under: {valid_range['under_n']} ({valid_range['under_pct']:.1f}%)"
    )
    ax.annotate(info_text, xy=(1.05, 0.55), xycoords="axes fraction",
                fontsize=10, color="#b35f00", weight="bold", va="top", ha="left",
                bbox=dict(facecolor="white", alpha=0.8, edgecolor="lightgray", pad=6),
                annotation_clip=False)

    ax.grid(False)
    fig.tight_layout()

    stats_dict = {
        "model": reg_name,
        "slope": float(slope),
        "intercept": float(model.params.iloc[0]),
        "ols_angle_deg": ols_angle_deg,
        "mean_diff": float(mean_diff),
        "std_diff": float(std_diff),
        "ci_mean_lower": float(ci_mean_lower),
        "ci_mean_upper": float(ci_mean_upper),
        "loa_lower": float(loa_lower),
        "loa_upper": float(loa_upper),
        "x_min": x_min,
        "x_max": x_max,
        "n_total": n_total,
        "n_in_range": len(df_in_x),
        "is_normal": is_normal,
        "p_value": None if p_value is None else float(p_value),
        "overall": overall,
        "valid_range": valid_range,
        "x_basis": x_basis,
    }

    results_df = df[["Reference", "Measured", "X", "Diff", "Tol", "is_outlier"]].copy()
    results_df = results_df.rename(columns={"X": x_basis, "is_outlier": "Outlier"})

    return PlotResult(fig, stats_dict, results_df)
