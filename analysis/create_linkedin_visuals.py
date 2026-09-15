"""Create square LinkedIn visuals from the committed benchmark results."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).parents[1]
OUT = ROOT / "results" / "linkedin"

BG = "#F6F8FB"
INK = "#101828"
MUTED = "#5C667A"
GRID = "#D9DEE8"
BLUE = "#0A66C2"
BLUE_LIGHT = "#DCEEFF"
GREEN = "#008F6B"
GREEN_LIGHT = "#DDF5EC"
ORANGE = "#E58A00"
ORANGE_LIGHT = "#FFF0D1"
RED = "#C43D4B"
RED_LIGHT = "#FBE4E7"
WHITE = "#FFFFFF"


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def setup() -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(12, 12), dpi=100)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def text(ax, x, y, value, *, size=18, weight="normal", color=INK, ha="left", va="top"):
    return ax.text(
        x,
        y,
        value,
        transform=ax.transAxes,
        fontsize=size,
        fontweight=weight,
        color=color,
        ha=ha,
        va=va,
        family="DejaVu Sans",
    )


def box(ax, x, y, w, h, *, face=WHITE, edge="none", radius=0.018, lw=1):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.012,rounding_size={radius}",
        transform=ax.transAxes,
        facecolor=face,
        edgecolor=edge,
        linewidth=lw,
    )
    ax.add_patch(patch)
    return patch


def save(fig, stem: str):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{stem}.png", dpi=100, facecolor=fig.get_facecolor(), bbox_inches=None)
    fig.savefig(OUT / f"{stem}.svg", facecolor=fig.get_facecolor(), bbox_inches=None)
    plt.close(fig)


def hero_result():
    agg = load("results/runs/l1-mid-hosted-three-repetition-aggregate.json")
    fig, ax = setup()

    text(ax, 0.07, 0.95, "OPEN WEBUI COST BENCHMARK", size=14, weight="bold", color=BLUE)
    text(ax, 0.07, 0.885, "53.95% cheaper", size=48, weight="bold")
    text(ax, 0.07, 0.825, "background task calls", size=34, weight="bold")
    text(ax, 0.07, 0.775, "No measurable quality regression. Main chat model unchanged.", size=18, color=MUTED)

    box(ax, 0.06, 0.47, 0.55, 0.245)
    text(ax, 0.09, 0.69, "COST PER 32 IDENTICAL TASK CALLS", size=13, weight="bold", color=MUTED)
    baseline = float(agg["baseline"]["mean_cost_per_run_usd"])
    candidate = float(agg["candidate"]["mean_cost_per_run_usd"])
    maximum = baseline * 1.05
    labels = [("Sol baseline", baseline, BLUE), ("Terra", candidate, GREEN)]
    for i, (label, value, color) in enumerate(labels):
        yy = 0.615 - i * 0.09
        text(ax, 0.09, yy + 0.024, label, size=16, weight="bold", va="center")
        ax.add_patch(
            FancyBboxPatch(
                (0.25, yy),
                0.29,
                0.045,
                boxstyle="round,pad=0,rounding_size=0.012",
                transform=ax.transAxes,
                facecolor="#E7EBF1",
                edgecolor="none",
            )
        )
        ax.add_patch(
            FancyBboxPatch(
                (0.25, yy),
                0.29 * value / maximum,
                0.045,
                boxstyle="round,pad=0,rounding_size=0.012",
                transform=ax.transAxes,
                facecolor=color,
                edgecolor="none",
            )
        )
        text(ax, 0.565, yy + 0.023, f"{value * 100:.2f}¢", size=18, weight="bold", ha="right", va="center")

    box(ax, 0.65, 0.47, 0.29, 0.245, face=GREEN_LIGHT)
    text(ax, 0.685, 0.685, "QUALITY GUARD", size=13, weight="bold", color=GREEN)
    text(ax, 0.685, 0.63, "PASS", size=35, weight="bold", color=GREEN)
    text(ax, 0.685, 0.57, "Sol", size=13, color=MUTED)
    text(ax, 0.91, 0.57, "4.417 / 5", size=17, weight="bold", ha="right")
    text(ax, 0.685, 0.525, "Terra", size=13, color=MUTED)
    text(ax, 0.91, 0.525, "4.396 / 5", size=17, weight="bold", ha="right")
    text(ax, 0.685, 0.49, "Blind 32-case judge", size=12, color=MUTED)

    text(ax, 0.07, 0.405, "PAIRED QUALITY DIFFERENCE", size=13, weight="bold", color=MUTED)
    ci_low, ci_high = agg["semantic_quality"]["paired_delta_bootstrap_95_percent_ci"]
    delta = agg["semantic_quality"]["mean_paired_delta_vs_baseline"]
    x0, x1, y = 0.09, 0.91, 0.335
    domain_low, domain_high = -0.30, 0.15
    scale = lambda value: x0 + (value - domain_low) / (domain_high - domain_low) * (x1 - x0)
    ax.plot([x0, x1], [y, y], transform=ax.transAxes, color=GRID, linewidth=3, solid_capstyle="round")
    ax.axvspan(scale(-0.25), scale(0.15), ymin=0.31, ymax=0.36, facecolor=GREEN_LIGHT, alpha=1)
    for tick in (-0.25, 0.0, 0.15):
        xx = scale(tick)
        ax.plot([xx, xx], [y - 0.012, y + 0.012], transform=ax.transAxes, color=MUTED, linewidth=1.5)
        text(ax, xx, y - 0.032, f"{tick:+.2f}", size=12, color=MUTED, ha="center")
    ax.plot([scale(ci_low), scale(ci_high)], [y, y], transform=ax.transAxes, color=BLUE, linewidth=7, solid_capstyle="round")
    ax.scatter([scale(delta)], [y], transform=ax.transAxes, s=190, color=INK, zorder=5)
    text(ax, scale(-0.25), y + 0.055, "noninferiority limit", size=11, color=MUTED, ha="center")
    text(ax, scale(delta), y + 0.055, f"mean {delta:+.3f}", size=13, weight="bold", ha="center")
    text(ax, 0.07, 0.255, f"95% CI  [{ci_low:+.3f}, {ci_high:+.3f}]  stays above the −0.25 limit", size=16, color=MUTED)

    cards = [
        ("96 / 96", "valid outputs", GREEN_LIGHT, GREEN),
        ("−18.2%", "p50 latency", BLUE_LIGHT, BLUE),
        ("−22.9%", "p95 latency", BLUE_LIGHT, BLUE),
    ]
    for i, (value, label, face, color) in enumerate(cards):
        xx = 0.06 + i * 0.30
        box(ax, xx, 0.085, 0.27, 0.115, face=face)
        text(ax, xx + 0.025, 0.175, value, size=27, weight="bold", color=color)
        text(ax, xx + 0.025, 0.125, label, size=14, color=MUTED)

    text(ax, 0.94, 0.025, "3 repeated hosted runs • frozen 32-task sample", size=11, color=MUTED, ha="right", va="bottom")
    save(fig, "01-terra-hero-result")


def decision_chart():
    fig, ax = setup()
    text(ax, 0.07, 0.95, "THE OPTIMIZATION FRONTIER", size=14, weight="bold", color=BLUE)
    text(ax, 0.07, 0.89, "Savings are easy.", size=42, weight="bold")
    text(ax, 0.07, 0.837, "Savings that survive quality checks are rare.", size=26, weight="bold")
    text(ax, 0.07, 0.785, "Cost and task-specific performance were measured independently.", size=17, color=MUTED)

    rows = [
        ("Terra task routing", "DEPLOY", "53.95%", "cost saved", "Quality −0.42 pp • 96/96 valid", GREEN, GREEN_LIGHT),
        ("Query reuse", "DEPLOY", "27.73%", "cost saved", "Answer score unchanged • 33% fewer calls", GREEN, GREEN_LIGHT),
        ("Luna task routing", "GUARDED", "94.04%", "cost saved", "1 malformed output • use Terra fallback", ORANGE, ORANGE_LIGHT),
        ("Global cap 128", "REJECT", "1.62%", "saved on valid subset", "Only 23/30 structurally valid", RED, RED_LIGHT),
        ("Last 6 turns", "REJECT", "1.15%", "cost saved", "Context recall fell 100 percentage points", RED, RED_LIGHT),
        ("Forced compaction", "REJECT", "+120.64%", "cost increase", "Context score fell 20 percentage points", RED, RED_LIGHT),
    ]
    for i, (name, status, value, value_label, evidence, color, face) in enumerate(rows):
        col, row = i % 2, i // 2
        x = 0.06 + col * 0.46
        y = 0.57 - row * 0.18
        box(ax, x, y, 0.42, 0.14, face=WHITE, edge=GRID, radius=0.016, lw=1)
        text(ax, x + 0.025, y + 0.115, name, size=17, weight="bold")
        box(ax, x + 0.285, y + 0.093, 0.105, 0.037, face=face, radius=0.01)
        text(ax, x + 0.3375, y + 0.111, status, size=9.5, weight="bold", color=color, ha="center", va="center")
        text(ax, x + 0.025, y + 0.074, value, size=27, weight="bold", color=color)
        text(ax, x + 0.025, y + 0.044, value_label, size=11, color=MUTED)
        text(ax, x + 0.025, y + 0.013, evidence, size=10.5, color=MUTED, va="bottom")

    box(ax, 0.06, 0.035, 0.88, 0.075, face=BLUE_LIGHT)
    text(ax, 0.085, 0.088, "DECISION RULE", size=11, weight="bold", color=BLUE)
    text(ax, 0.085, 0.058, "Deploy the saving only after its relevant quality and reliability checks pass.", size=16, weight="bold")
    save(fig, "02-optimization-frontier")


def methodology():
    fig, ax = setup()
    text(ax, 0.07, 0.95, "HOW THE BENCHMARK WORKED", size=14, weight="bold", color=BLUE)
    text(ax, 0.07, 0.89, "Cost was never the only metric.", size=38, weight="bold")
    text(ax, 0.07, 0.83, "Every saving had to pass the performance checks relevant to its task.", size=18, color=MUTED)

    steps = [
        ("1", "Freeze the workload", "30 conversations  •  349 actions  •  32 hosted tasks  •  115 eval cases", BLUE_LIGHT, BLUE),
        ("2", "Run controlled A/B", "Same inputs and order  •  real endpoints  •  temperature 0  •  Terra repeated 3×", ORANGE_LIGHT, ORANGE),
        ("3", "Apply the decision gates", "A saving counts only if cost, reliability, quality and latency all hold up", GREEN_LIGHT, GREEN),
    ]
    for i, (num, heading, detail, face, color) in enumerate(steps):
        y = 0.68 - i * 0.15
        box(ax, 0.06, y, 0.88, 0.105, face=WHITE, edge=GRID, radius=0.016, lw=1.2)
        box(ax, 0.085, y + 0.022, 0.06, 0.06, face=face, radius=0.025)
        text(ax, 0.115, y + 0.052, num, size=19, weight="bold", color=color, ha="center", va="center")
        text(ax, 0.175, y + 0.075, heading, size=19, weight="bold")
        text(ax, 0.175, y + 0.038, detail, size=13, color=MUTED)
        if i < 2:
            ax.add_patch(FancyArrowPatch((0.50, y - 0.012), (0.50, y - 0.035), transform=ax.transAxes, arrowstyle="-|>", mutation_scale=15, linewidth=1.4, color=MUTED))

    text(ax, 0.07, 0.30, "THE FOUR PERFORMANCE METRICS", size=13, weight="bold", color=MUTED)
    metrics = [
        ("01", "COST", "Provider tokens × frozen prices", BLUE),
        ("02", "RELIABILITY", "Valid JSON and required schema", ORANGE),
        ("03", "QUALITY", "Blind judge + objective task metrics", GREEN),
        ("04", "LATENCY", "p50 / p95 completion time", "#6B56C9"),
    ]
    for i, (num, title, detail, color) in enumerate(metrics):
        x = 0.06 + (i % 2) * 0.46
        y = 0.20 - (i // 2) * 0.095
        box(ax, x, y, 0.42, 0.065, face=WHITE, edge=GRID, radius=0.015, lw=1)
        text(ax, x + 0.025, y + 0.065, num, size=12, weight="bold", color=color)
        text(ax, x + 0.085, y + 0.052, title, size=14, weight="bold")
        text(ax, x + 0.085, y + 0.024, detail, size=11.5, color=MUTED)

    box(ax, 0.06, 0.015, 0.88, 0.06, face=GREEN_LIGHT)
    text(ax, 0.085, 0.064, "HOSTED MODEL PASS RULE", size=10, weight="bold", color=GREEN)
    text(ax, 0.085, 0.038, "95% CI lower bound ≥ −0.25  +  100% structural validity", size=16, weight="bold", color=INK)
    save(fig, "03-benchmark-methodology")


def main():
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.unicode_minus": True,
        "svg.fonttype": "none",
    })
    hero_result()
    decision_chart()
    methodology()
    print(json.dumps({"output_directory": str(OUT), "images": sorted(path.name for path in OUT.glob("*.png"))}))


if __name__ == "__main__":
    main()
