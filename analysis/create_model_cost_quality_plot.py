"""Create a paper-style cost-quality frontier for the judged hosted models."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter


ROOT = Path(__file__).parents[1]
OUT = ROOT / "results" / "linkedin"


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def main() -> None:
    judge = load("results/runs/l1-task-model-tier-judge.json")
    terra_run = load("results/runs/l1-mid-hosted-paid-sample.json")
    luna_run = load("results/runs/l1-small-hosted-paid-sample.json")
    repeat = load("results/runs/l1-mid-hosted-three-repetition-aggregate.json")

    baseline_cost = float(terra_run["baseline_cost_usd"])
    records = [
        {
            "model": "Sol",
            "cost_pct": 100.0,
            "saving_pct": 0.0,
            "quality_mean": judge["systems"]["baseline"]["mean_composite"],
            "delta": 0.0,
            "ci": None,
            "structural": 1.0,
            "passes": "32/32",
            "color": "#4B5563",
            "marker": "s",
        },
        {
            "model": "Terra",
            "cost_pct": float(terra_run["candidate_cost_usd"]) / baseline_cost * 100,
            "saving_pct": terra_run["cost_saving_percent"],
            "quality_mean": judge["systems"]["terra"]["mean_composite"],
            "delta": judge["systems"]["terra"]["mean_paired_delta_vs_baseline"],
            "ci": judge["systems"]["terra"]["paired_delta_bootstrap_95_percent_ci"],
            "structural": terra_run["candidate_structural_pass_rate"],
            "passes": "32/32",
            "color": "#0072B2",
            "marker": "o",
        },
        {
            "model": "Luna",
            "cost_pct": float(luna_run["candidate_cost_usd"]) / baseline_cost * 100,
            "saving_pct": luna_run["cost_saving_percent"],
            "quality_mean": judge["systems"]["luna"]["mean_composite"],
            "delta": judge["systems"]["luna"]["mean_paired_delta_vs_baseline"],
            "ci": judge["systems"]["luna"]["paired_delta_bootstrap_95_percent_ci"],
            "structural": luna_run["candidate_structural_pass_rate"],
            "passes": "31/32",
            "color": "#E69F00",
            "marker": "^",
        },
    ]

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titlesize": 14,
            "axes.labelsize": 13,
            "axes.edgecolor": "#9CA3AF",
            "axes.linewidth": 0.8,
            "xtick.color": "#374151",
            "ytick.color": "#374151",
            "text.color": "#111827",
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )

    fig = plt.figure(figsize=(14, 8.5), dpi=150, facecolor="white")
    grid = fig.add_gridspec(1, 2, width_ratios=(2.35, 1), wspace=0.30, left=0.08, right=0.96, top=0.76, bottom=0.24)
    ax = fig.add_subplot(grid[0, 0])
    reliability = fig.add_subplot(grid[0, 1])

    fig.suptitle(
        "Model routing cuts task-call cost without detectable semantic quality loss",
        x=0.08,
        y=0.94,
        ha="left",
        fontsize=21,
        fontweight="bold",
    )
    fig.text(
        0.08,
        0.885,
        "Same 32 Open WebUI background tasks; blinded judge scored task compliance, relevance and usefulness on a 1–5 scale.",
        ha="left",
        fontsize=12.5,
        color="#4B5563",
    )

    # Main cost-quality frontier.
    ax.set_xscale("log")
    ax.set_xlim(4.3, 130)
    ax.set_ylim(-0.30, 0.16)
    ax.axhspan(-0.25, 0.16, color="#E9F6EF", zorder=0)
    ax.axhline(0, color="#6B7280", linewidth=1.2, linestyle="--", zorder=1)
    ax.axhline(-0.25, color="#0F8A5F", linewidth=1.3, linestyle=":", zorder=1)
    ax.grid(axis="both", color="#E5E7EB", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_locator(FixedLocator([5, 10, 25, 50, 100]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}%"))
    ax.set_yticks([-0.25, -0.15, -0.05, 0.0, 0.05, 0.15])
    ax.set_xlabel("Task-call cost relative to Sol baseline  (lower is cheaper)", labelpad=12)
    ax.set_ylabel("Paired blinded-quality difference vs Sol  (5-point scale)", labelpad=12)
    ax.set_title("A. Cost–quality frontier", loc="left", fontweight="bold", pad=12)

    for row in records:
        if row["ci"] is not None:
            lower, upper = row["ci"]
            yerr = [[row["delta"] - lower], [upper - row["delta"]]]
            ax.errorbar(
                row["cost_pct"],
                row["delta"],
                yerr=yerr,
                fmt="none",
                ecolor=row["color"],
                elinewidth=2.2,
                capsize=6,
                capthick=2.2,
                zorder=3,
            )
        face = row["color"] if row["structural"] == 1.0 else "white"
        ax.scatter(
            row["cost_pct"],
            row["delta"],
            s=180,
            marker=row["marker"],
            facecolor=face,
            edgecolor=row["color"],
            linewidth=2.4,
            zorder=4,
        )

    ax.annotate(
        "Sol reference\n100% cost\nquality 4.417/5",
        xy=(100, 0),
        xytext=(118, -0.075),
        textcoords="data",
        ha="right",
        fontsize=11,
        fontweight="bold",
        color="#374151",
        arrowprops={"arrowstyle": "-", "color": "#6B7280", "linewidth": 1.0},
    )
    ax.annotate(
        f"Terra — recommended\n{records[1]['cost_pct']:.1f}% cost ({records[1]['saving_pct']:.1f}% saved)\nquality 4.396/5 • 32/32 valid",
        xy=(records[1]["cost_pct"], records[1]["delta"]),
        xytext=(56, 0.122),
        textcoords="data",
        fontsize=11,
        fontweight="bold",
        color=records[1]["color"],
        arrowprops={"arrowstyle": "-", "color": records[1]["color"], "linewidth": 1.2},
    )
    ax.annotate(
        f"Luna — semantic pass, reliability fail\n{records[2]['cost_pct']:.1f}% cost ({records[2]['saving_pct']:.1f}% saved)\nquality 4.406/5 • 31/32 valid",
        xy=(records[2]["cost_pct"], records[2]["delta"]),
        xytext=(7.3, -0.095),
        textcoords="data",
        fontsize=11,
        fontweight="bold",
        color="#9A6700",
        arrowprops={"arrowstyle": "-", "color": records[2]["color"], "linewidth": 1.2},
    )
    ax.text(5.0, -0.238, "Predeclared noninferiority limit: −0.25", color="#0F8A5F", fontsize=10.5, va="bottom")
    ax.text(5.0, 0.143, "Shaded region passes the semantic-quality criterion", color="#0F8A5F", fontsize=10.5, va="top")

    # Separate structural reliability panel: semantic similarity is insufficient if the UI cannot parse the output.
    models = [row["model"] for row in records]
    validity = [row["structural"] * 100 for row in records]
    colors = [row["color"] for row in records]
    y_positions = [2, 1, 0]
    reliability.barh(y_positions, validity, color=colors, height=0.52, alpha=0.92)
    reliability.set_xlim(0, 103)
    reliability.set_ylim(-0.65, 2.65)
    reliability.set_yticks(y_positions, models)
    reliability.set_xticks([0, 25, 50, 75, 100])
    reliability.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}%"))
    reliability.grid(axis="x", color="#E5E7EB", linewidth=0.8)
    reliability.set_axisbelow(True)
    reliability.set_xlabel("Structurally valid outputs", labelpad=12)
    reliability.set_title("B. Machine-readable reliability", loc="left", fontweight="bold", pad=12)
    for y, value, row in zip(y_positions, validity, records):
        reliability.text(
            min(value - 2.5, 96.5),
            y,
            f"{value:.1f}%  ({row['passes']})",
            ha="right",
            va="center",
            color="white" if value > 65 else "#111827",
            fontsize=11,
            fontweight="bold",
        )
    reliability.axvline(100, color="#0F8A5F", linestyle=":", linewidth=1.3)
    reliability.text(100, 2.48, "required", ha="right", va="bottom", color="#0F8A5F", fontsize=10.5)
    fig.text(
        0.08,
        0.125,
        f"Notes: Error bars are 95% paired bootstrap intervals (10,000 resamples). Terra cost in panel A is the judged run; its three-run mean saving was {repeat['cost_saving_percent']:.2f}% (SD {repeat['repeat_cost_saving_percent']['population_sd']:.2f} pp). Luna failed the 100% structural-validity requirement.",
        ha="left",
        fontsize=9.8,
        color="#4B5563",
    )
    fig.text(
        0.08,
        0.085,
        "Cost uses provider-reported tokens and the frozen 2026-09-14 price snapshot. Main-chat responses were not rerouted. Judge: gpt-4o-2024-11-20, blinded A/B/C ordering.",
        ha="left",
        fontsize=9.8,
        color="#4B5563",
    )

    OUT.mkdir(parents=True, exist_ok=True)
    stem = OUT / "04-model-cost-quality-frontier"
    fig.savefig(stem.with_suffix(".png"), dpi=150, facecolor="white")
    fig.savefig(stem.with_suffix(".svg"), facecolor="white")
    fig.savefig(stem.with_suffix(".pdf"), facecolor="white")
    plt.close(fig)
    print(json.dumps({"png": str(stem.with_suffix('.png')), "svg": str(stem.with_suffix('.svg')), "pdf": str(stem.with_suffix('.pdf'))}))


if __name__ == "__main__":
    main()
