"""Generate MetaMorpho visualisations from user's actual run output."""
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

# Data extracted from the user's actual run output
# (vault, asset, TVL_M, score, red, yellow, green_watch, green_strong, unknown)
DATA = [
    ("Sentora PYUSD",            "PYUSD", 244.5, 0.56,  0.0,   8.8, 38.5, 35.4, 17.3),
    ("Sentora RLUSD",            "RLUSD", 166.0, 0.00,  0.0,   0.0,  0.0, 61.0, 39.0),
    ("Gauntlet USDC Prime",      "USDC",  150.9, 2.00,  0.0, 100.0,  0.0,  0.0,  0.0),
    ("Steakhouse USDC",          "USDC",  129.4, 1.94,  0.0,  96.8,  0.0,  0.0,  3.2),
    ("Steakhouse USDT",          "USDT",  125.2, 1.77,  0.0,  82.9, 11.7,  0.0,  5.4),
    ("Steakhouse Ethena USDtb",  "USDtb",  85.2, 0.00,  0.0,   0.0,  0.0,100.0,  0.0),
    ("Steakhouse EURCV",         "EURCV",  51.2, 0.00,  0.0,   0.0,  0.0,  0.0,100.0),
    ("Sentora PYUSD Core",       "PYUSD",  50.2, 1.01,  0.0,   1.5, 98.5,  0.0,  0.0),
    ("Vault Bridge USDC",        "USDC",   48.9, 2.00,  0.0, 100.0,  0.0,  0.0,  0.0),
    ("Gauntlet WETH Prime",      "WETH",   42.1, 0.99,  0.0,   0.0, 98.7,  0.0,  1.3),
    ("Vault Bridge WBTC",        "WBTC",   38.7, 0.00,  0.0,   0.0,  0.0,  0.0,100.0),
    ("Vault Bridge USDT",        "USDT",   33.0, 0.60,  0.0,   0.0, 60.0,  0.0, 40.0),
    ("Steakhouse ETH",           "WETH",   32.8, 0.62,  0.0,   0.0, 61.5, 36.8,  1.7),
    ("Vault Bridge WETH",        "WETH",   32.3, 0.90,  0.0,   0.0, 90.0,  0.0, 10.0),
    ("Smokehouse USDT",          "USDT",   27.6, 0.00,  0.0,   0.0,  0.0, 54.2, 45.8),
    ("Smokehouse USDC",          "USDC",   27.3, 0.50,  0.0,  25.0,  0.0, 50.0, 25.0),
    ("Gauntlet USDT Frontier",   "USDT",   26.8, 0.89,  0.0,  32.5, 24.5,  0.0, 43.0),
    ("Adpend USDC",              "USDC",   18.1, 0.00,  0.0,   0.0,  0.0,  0.0,100.0),
    ("Hakutora USDC",            "USDC",   16.4, 2.00,  0.0, 100.0,  0.0,  0.0,  0.0),
    ("Metronome msUSD Vault",    "msUSD",  14.9, 0.00,  0.0,   0.0,  0.0,  0.0,100.0),
]

# Sort by TVL descending (already sorted)
labels = [f"{v[0]} ({v[1]})" for v in DATA]
tvls = np.array([v[2] for v in DATA])
scores = np.array([v[3] for v in DATA])
red = np.array([v[4] for v in DATA])
yellow = np.array([v[5] for v in DATA])
gw = np.array([v[6] for v in DATA])
gs = np.array([v[7] for v in DATA])
unk = np.array([v[8] for v in DATA])

# Color scheme aligned with tier semantics
COLOR_RED = "#c0392b"
COLOR_YELLOW = "#f39c12"
COLOR_GREEN_WATCH = "#27ae60"
COLOR_GREEN_STRONG = "#1abc9c"
COLOR_UNKNOWN = "#95a5a6"
COLOR_BAR = "#2c3e50"

# Set up matplotlib for publication-quality output
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.8,
    "axes.labelsize": 9,
    "axes.titlesize": 11,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "legend.frameon": False,
})

# === FIGURE 1: Curator discipline score (horizontal bar chart) ===
fig, ax = plt.subplots(figsize=(11, 7))

# Color bars by score: red gradient
bar_colors = []
for s in scores:
    if s < 0.5:
        bar_colors.append("#1abc9c")  # very conservative
    elif s < 1.5:
        bar_colors.append("#f1c40f")  # moderate
    else:
        bar_colors.append("#e67e22")  # aggressive

# Reverse order for horizontal bars (largest TVL on top)
y_pos = np.arange(len(labels))[::-1]
bars = ax.barh(y_pos, scores, color=bar_colors, edgecolor="white", linewidth=0.5)

# Annotate each bar with score and TVL
for i, (bar, score, tvl) in enumerate(zip(bars, scores, tvls)):
    width = bar.get_width()
    ax.text(width + 0.04, bar.get_y() + bar.get_height()/2,
            f"{score:.2f}", va="center", ha="left", fontsize=8, fontweight="bold")
    # TVL on the left side, inside the bar if there's room
    if width > 0.3:
        ax.text(0.05, bar.get_y() + bar.get_height()/2,
                f"${tvl:.0f}M", va="center", ha="left", fontsize=7,
                color="white", fontweight="bold")

ax.set_yticks(y_pos)
ax.set_yticklabels(labels, fontsize=8)
ax.set_xlabel("Curator discipline score (lower = more conservative)", fontsize=10)
ax.set_title("MetaMorpho vault curator discipline — top 20 vaults by TVL\n"
             "Score = TVL-weighted exposure to framework severity tiers (red=4, yellow=2, green-watch=1, green-strong=0)",
             fontsize=11, loc="left", pad=15)
ax.set_xlim(0, 2.4)

# Reference lines
ax.axvline(x=0.5, color="gray", linestyle=":", linewidth=0.5, alpha=0.6)
ax.axvline(x=1.5, color="gray", linestyle=":", linewidth=0.5, alpha=0.6)
ax.text(0.5, len(labels) + 0.3, "conservative", ha="center", fontsize=7, color="gray")
ax.text(1.5, len(labels) + 0.3, "aggressive", ha="center", fontsize=7, color="gray")

ax.grid(True, axis="x", linestyle="-", linewidth=0.3, alpha=0.4)
ax.set_axisbelow(True)

plt.tight_layout()
plt.savefig("/tmp/viz/metamorpho_scores.png", dpi=200, bbox_inches="tight", facecolor="white")
print("Saved metamorpho_scores.png")

# === FIGURE 2: Tier breakdown stacked bar (horizontal) ===
fig, ax = plt.subplots(figsize=(11, 7))

y_pos = np.arange(len(labels))[::-1]

# Stacked horizontal bars
left = np.zeros(len(DATA))
ax.barh(y_pos, red, left=left, color=COLOR_RED, label="red", edgecolor="white", linewidth=0.4)
left += red
ax.barh(y_pos, yellow, left=left, color=COLOR_YELLOW, label="yellow", edgecolor="white", linewidth=0.4)
left += yellow
ax.barh(y_pos, gw, left=left, color=COLOR_GREEN_WATCH, label="green-watch", edgecolor="white", linewidth=0.4)
left += gw
ax.barh(y_pos, gs, left=left, color=COLOR_GREEN_STRONG, label="green-strong", edgecolor="white", linewidth=0.4)
left += gs
ax.barh(y_pos, unk, left=left, color=COLOR_UNKNOWN, label="unknown (out of roster)",
        edgecolor="white", linewidth=0.4, alpha=0.6)

ax.set_yticks(y_pos)
ax.set_yticklabels(labels, fontsize=8)
ax.set_xlabel("Allocation share by severity tier (% of vault TVL)", fontsize=10)
ax.set_title("MetaMorpho vault allocation by framework tier\n"
             "Each bar shows how the vault's TVL is distributed across the four severity tiers, plus 'unknown' (markets outside our 26-market roster)",
             fontsize=11, loc="left", pad=15)
ax.set_xlim(0, 100)
ax.grid(True, axis="x", linestyle="-", linewidth=0.3, alpha=0.4)
ax.set_axisbelow(True)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=5, fontsize=8)

# Add TVL on the right
for i, tvl in enumerate(tvls):
    ax.text(101, y_pos[i], f"${tvl:.0f}M", va="center", ha="left", fontsize=7, color="#555")

plt.tight_layout()
plt.savefig("/tmp/viz/metamorpho_breakdown.png", dpi=200, bbox_inches="tight", facecolor="white")
print("Saved metamorpho_breakdown.png")

# === FIGURE 3: Risk Panorama (the core finding) ===
# Stacked donut + bar with TVL and bd
fig, axes = plt.subplots(1, 2, figsize=(13, 6))

# Left: donut of TVL distribution by tier
tier_tvl = {"red": 23, "yellow": 737, "green-watch": 384, "green-strong": 552}
tier_colors = {"red": COLOR_RED, "yellow": COLOR_YELLOW,
               "green-watch": COLOR_GREEN_WATCH, "green-strong": COLOR_GREEN_STRONG}
labels_donut = [f"{t}\n${v}M ({v/sum(tier_tvl.values())*100:.1f}%)" for t, v in tier_tvl.items()]
colors_donut = [tier_colors[t] for t in tier_tvl]

wedges, texts = axes[0].pie(
    tier_tvl.values(), colors=colors_donut, startangle=90,
    wedgeprops={"width": 0.45, "edgecolor": "white", "linewidth": 2},
)
# Labels outside
for i, (wedge, label) in enumerate(zip(wedges, labels_donut)):
    angle = (wedge.theta2 + wedge.theta1) / 2
    x = np.cos(np.deg2rad(angle))
    y = np.sin(np.deg2rad(angle))
    axes[0].annotate(label, xy=(0.85*x, 0.85*y), xytext=(1.25*x, 1.25*y),
                     ha="center", va="center", fontsize=9,
                     arrowprops=dict(arrowstyle="-", color="#888", lw=0.5))
axes[0].set_title("Total Value Locked by tier\n(Forward-looking BCBS 238 stress, 26 markets, $1.7B aggregate)",
                  fontsize=11, loc="center", pad=15)
axes[0].text(0, 0, "$1.7B\nTVL", ha="center", va="center", fontsize=14, fontweight="bold")

# Right: Top markets by p99 bad debt
top_markets = [
    ("cbBTC/USDC", 268.0, 5.30, "yellow"),
    ("wstETH/USDT", 218.0, 4.78, "yellow"),
    ("WBTC/USDC", 156.1, 2.13, "yellow"),
    ("PT-apyUSD-18JUN/USDC", 23.1, 1.32, "red"),
    ("wstETH/USDC", 44.4, 1.05, "yellow"),
    ("PT-apxUSD-18JUN/USDC", 13.8, 0.51, "yellow"),
    ("PT-reUSD-25JUN/USDC", 14.8, 0.44, "yellow"),
    ("cbBTC/PYUSD", 22.2, 0.33, "yellow"),
]
mk_labels = [m[0] for m in top_markets]
mk_bd = np.array([m[2] for m in top_markets])
mk_colors = [tier_colors[m[3]] for m in top_markets]

y_pos2 = np.arange(len(top_markets))[::-1]
bars = axes[1].barh(y_pos2, mk_bd, color=mk_colors, edgecolor="white", linewidth=0.5)
for i, (bar, m) in enumerate(zip(bars, top_markets)):
    w = bar.get_width()
    pct = m[2] / m[1] * 100
    axes[1].text(w + 0.1, bar.get_y() + bar.get_height()/2,
                 f"${m[2]:.2f}M ({pct:.2f}% TVL)",
                 va="center", ha="left", fontsize=8)

axes[1].set_yticks(y_pos2)
axes[1].set_yticklabels(mk_labels, fontsize=8)
axes[1].set_xlabel("99th-percentile bad debt under nominal stress (millions of U.S. dollars)", fontsize=9)
axes[1].set_title("Top 8 markets by 99th-percentile bad debt\n(Nominal stress, BCBS 238-aligned 24-hour LCR)",
                  fontsize=11, loc="left", pad=15)
axes[1].set_xlim(0, 7.5)
axes[1].grid(True, axis="x", linestyle="-", linewidth=0.3, alpha=0.4)
axes[1].set_axisbelow(True)

plt.tight_layout()
plt.savefig("/tmp/viz/risk_panorama.png", dpi=200, bbox_inches="tight", facecolor="white")
print("Saved risk_panorama.png")

# === FIGURE 4: Extreme stress test result ===
fig, ax = plt.subplots(figsize=(11, 6))

# Data for the 8 FAIL markets + summary of PASS
fail_markets = [
    ("msY/USDC",                12.9,  16.18, 4),
    ("PT-reUSD-25JUN/USDC",     14.8,  15.03, 8),
    ("wstETH/USDC",             44.4,  14.44, 49),
    ("sUSDat/AUSD",             19.0,  12.26, 23),
    ("PT-apyUSD-18JUN/USDC",    23.1,  10.74, 66),
    ("wstETH/WETH (LLTV 96.5%)",90.6,  10.52, 18),
    ("weETH/WETH (LLTV 94.5%)", 52.9,  10.29, 18),
    ("wstETH/USDT",            218.0,  10.14, 21),
]

mk_names = [m[0] for m in fail_markets]
mk_bd_pct = np.array([m[2] for m in fail_markets])
mk_tvl = np.array([m[1] for m in fail_markets])

y = np.arange(len(fail_markets))[::-1]
ax.axvline(x=10.0, color="black", linestyle="--", linewidth=1.0, alpha=0.6, label="FAIL threshold (10% TVL)")
bars = ax.barh(y, mk_bd_pct, color=COLOR_RED, edgecolor="white", linewidth=0.5, alpha=0.85)

for i, (bar, m) in enumerate(zip(bars, fail_markets)):
    w = bar.get_width()
    ax.text(w + 0.2, bar.get_y() + bar.get_height()/2,
            f"{m[2]:.2f}% (${m[1]:.0f}M TVL, {m[3]} liq)",
            va="center", ha="left", fontsize=8)

ax.set_yticks(y)
ax.set_yticklabels(mk_names, fontsize=8)
ax.set_xlabel("99th-percentile bad debt as % of market TVL", fontsize=10)
ax.set_title("Extreme stress test — markets that FAIL the survival criterion\n"
             "Scenario: drawdown 25% + outflow alpha 35% (KelpDAO 2026 + USDC depeg 2023 hybrid)\n"
             "FAIL = LCR < 1 OR p99 bad debt > 10% TVL.   8 of 26 markets fail, $476M aggregate TVL (28.1% of analysed total)",
             fontsize=10, loc="left", pad=15)
ax.set_xlim(0, 22)
ax.legend(loc="lower right", fontsize=8)
ax.grid(True, axis="x", linestyle="-", linewidth=0.3, alpha=0.4)
ax.set_axisbelow(True)

plt.tight_layout()
plt.savefig("/tmp/viz/extreme_stress.png", dpi=200, bbox_inches="tight", facecolor="white")
print("Saved extreme_stress.png")

print("\nAll 4 figures generated.")
