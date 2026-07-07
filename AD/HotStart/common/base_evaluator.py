from __future__ import annotations

import os

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


def anomaly_summary(
    df: pd.DataFrame,
    item_col: str = "item_id",
    extra_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Generic per-series anomaly summary. Domain evaluators pass extra_cols."""

    def _agg(g: pd.DataFrame) -> pd.Series:
        row: dict = {
            "total_points": len(g),
            "anomaly_count": int(g["is_anomaly"].sum()),
            "anomaly_rate": round(float(g["is_anomaly"].mean()), 4),
            "max_score": round(float(g["anomaly_score"].max()), 2),
        }
        for col in extra_cols or []:
            if col in g.columns:
                row[col] = g[col].iloc[0]
        return pd.Series(row)

    return (
        df.groupby(item_col)
        .apply(_agg, include_groups=False)
        .reset_index()
        .sort_values("anomaly_count", ascending=False)
    )


def plot_series(
    df: pd.DataFrame,
    item_id: str,
    item_col: str = "item_id",
    timestamp_col: str = "date",
    value_col: str = "value",
    q_low: float = 0.1,
    q_high: float = 0.9,
    output_dir: str = ".",
) -> None:
    """Generic time-series anomaly plot saved to output_dir."""
    data = df[df[item_col] == item_id].sort_values(timestamp_col).copy()
    data[timestamp_col] = pd.to_datetime(data[timestamp_col])

    anomalies = data[data["is_anomaly"]]
    pred_data = data[data["pred_median"].notna()]

    fig, ax = plt.subplots(figsize=(16, 5))

    ax.plot(
        data[timestamp_col], data[value_col],
        color="steelblue", linewidth=1, label="Actual", zorder=2,
    )

    if not pred_data.empty:
        ax.fill_between(
            pred_data[timestamp_col],
            pred_data["pred_low"],
            pred_data["pred_high"],
            alpha=0.25,
            color="orange",
            label=f"Chronos interval [q{int(q_low * 100)}–q{int(q_high * 100)}]",
        )
        ax.plot(
            pred_data[timestamp_col],
            pred_data["pred_median"],
            color="darkorange",
            linestyle="--",
            linewidth=1.5,
            label="Predicted median",
            zorder=3,
        )

    if not anomalies.empty:
        ax.scatter(
            anomalies[timestamp_col],
            anomalies[value_col],
            color="red",
            s=40,
            zorder=5,
            label=f"Anomaly ({len(anomalies)})",
        )

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=45)
    ax.set_title(f"Anomaly Detection — {item_id}", fontsize=13, fontweight="bold")
    ax.set_xlabel("Date")
    ax.set_ylabel(value_col)
    ax.legend()
    plt.tight_layout()

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"anomaly_{item_id}.png")
    plt.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"Saved: {out_path}")
