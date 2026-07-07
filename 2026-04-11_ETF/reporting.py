"""
reporting.py — Performance analysis, metrics, and chart generation.

Generates:
  - Cumulative return charts (strategies vs benchmark)
  - Annual return comparison (bar chart)
  - Drawdown chart
  - Performance summary table (CAGR, Sharpe, max drawdown, etc.)
  - Holdings frequency table
"""

import os
import logging

import pandas as pd
import numpy as np
import matplotlib

matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

logger = logging.getLogger(__name__)

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def ensure_results_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Performance Metrics
# ---------------------------------------------------------------------------

def compute_metrics(values: pd.Series, risk_free_rate: float = 0.0) -> dict:
    """
    Compute key performance metrics from a time series of portfolio values.

    Args:
        values: Time series of portfolio values (DatetimeIndex).
        risk_free_rate: Annualised risk-free rate (default 0).

    Returns:
        dict with keys: total_return, cagr, volatility, sharpe, max_drawdown,
                        max_drawdown_start, max_drawdown_end
    """
    if values.empty or len(values) < 2:
        return {}

    # Daily returns
    returns = values.pct_change().dropna()

    # Total return
    total_return = (values.iloc[-1] / values.iloc[0]) - 1.0

    # CAGR
    n_years = (values.index[-1] - values.index[0]).days / 365.25
    if n_years <= 0:
        cagr = 0.0
    else:
        cagr = (values.iloc[-1] / values.iloc[0]) ** (1.0 / n_years) - 1.0

    # Determine data frequency for correct annualisation
    # Estimate median gap between observations
    if len(returns) > 1:
        median_gap_days = returns.index.to_series().diff().median().days
    else:
        median_gap_days = 1

    if median_gap_days <= 2:
        periods_per_year = 252   # daily
    elif median_gap_days <= 10:
        periods_per_year = 52    # weekly
    else:
        periods_per_year = 12    # monthly

    # Annualised volatility
    volatility = returns.std() * np.sqrt(periods_per_year)

    # Sharpe ratio
    excess = returns - risk_free_rate / periods_per_year
    sharpe = (excess.mean() / excess.std()) * np.sqrt(periods_per_year) if excess.std() > 0 else 0.0

    # Max drawdown
    cummax = values.cummax()
    drawdown = (values - cummax) / cummax
    max_dd = drawdown.min()
    max_dd_end = drawdown.idxmin()
    max_dd_start = values.loc[:max_dd_end].idxmax()

    return {
        "total_return": total_return,
        "cagr": cagr,
        "volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "max_drawdown_start": max_dd_start,
        "max_drawdown_end": max_dd_end,
        "n_years": n_years,
    }


def metrics_to_string(name: str, metrics: dict) -> str:
    """Format metrics dict as a readable string."""
    if not metrics:
        return f"{name}: (no data)\n"
    lines = [
        f"{'═' * 50}",
        f"  {name}",
        f"{'═' * 50}",
        f"  Period:          {metrics.get('n_years', 0):.1f} years",
        f"  Total Return:    {metrics['total_return']:>10.2%}",
        f"  CAGR:            {metrics['cagr']:>10.2%}",
        f"  Volatility:      {metrics['volatility']:>10.2%}",
        f"  Sharpe Ratio:    {metrics['sharpe']:>10.2f}",
        f"  Max Drawdown:    {metrics['max_drawdown']:>10.2%}",
        f"  Max DD Period:   {metrics.get('max_drawdown_start', 'N/A')} → {metrics.get('max_drawdown_end', 'N/A')}",
        f"{'─' * 50}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _style_axis(ax: plt.Axes) -> None:
    """Apply consistent styling to a matplotlib axis."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(framealpha=0.9, fontsize=9)


def plot_cumulative_returns(
    series_dict: dict[str, pd.Series],
    title: str = "Cumulative Returns",
    filename: str = "cumulative_returns.png",
) -> str:
    """
    Plot cumulative returns for multiple strategies on one chart.

    Args:
        series_dict: {label: pd.Series of portfolio values}
    Returns:
        Path to saved chart.
    """
    ensure_results_dir()
    fig, ax = plt.subplots(figsize=(14, 7))

    colours = ["#2196F3", "#FF5722", "#4CAF50", "#9C27B0", "#FF9800"]
    for idx, (label, values) in enumerate(series_dict.items()):
        if values.empty:
            continue
        normalised = values / values.iloc[0]
        colour = colours[idx % len(colours)]
        ax.plot(normalised.index, normalised.values, label=label, color=colour, linewidth=1.5)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_ylabel("Growth of $1", fontsize=11)
    ax.set_xlabel("")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("$%.1f"))
    _style_axis(ax)

    path = os.path.join(RESULTS_DIR, filename)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved chart: %s", path)
    return path


def plot_annual_returns(
    series_dict: dict[str, pd.Series],
    title: str = "Annual Returns Comparison",
    filename: str = "annual_returns.png",
) -> str:
    """Bar chart of annual returns for each strategy."""
    ensure_results_dir()

    annual_data = {}
    for label, values in series_dict.items():
        if values.empty:
            continue
        annual = values.resample("A").last().pct_change().dropna()
        annual.index = annual.index.year
        annual_data[label] = annual

    if not annual_data:
        return ""

    df = pd.DataFrame(annual_data)
    fig, ax = plt.subplots(figsize=(14, 7))

    colours = ["#2196F3", "#FF5722", "#4CAF50", "#9C27B0", "#FF9800"]
    bar_width = 0.8 / len(df.columns)
    x = np.arange(len(df.index))

    for idx, col in enumerate(df.columns):
        offset = (idx - len(df.columns) / 2 + 0.5) * bar_width
        bars = ax.bar(
            x + offset,
            df[col].values * 100,
            bar_width,
            label=col,
            color=colours[idx % len(colours)],
            alpha=0.85,
        )

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_ylabel("Return (%)", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels(df.index.astype(str), rotation=45, ha="right", fontsize=8)
    ax.axhline(y=0, color="black", linewidth=0.5)
    _style_axis(ax)

    path = os.path.join(RESULTS_DIR, filename)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved chart: %s", path)
    return path


def plot_drawdowns(
    series_dict: dict[str, pd.Series],
    title: str = "Drawdowns",
    filename: str = "drawdowns.png",
) -> str:
    """Plot drawdown curves for each strategy."""
    ensure_results_dir()
    fig, ax = plt.subplots(figsize=(14, 5))

    colours = ["#2196F3", "#FF5722", "#4CAF50", "#9C27B0", "#FF9800"]
    for idx, (label, values) in enumerate(series_dict.items()):
        if values.empty:
            continue
        cummax = values.cummax()
        dd = (values - cummax) / cummax * 100
        colour = colours[idx % len(colours)]
        ax.fill_between(dd.index, dd.values, 0, alpha=0.25, color=colour)
        ax.plot(dd.index, dd.values, label=label, color=colour, linewidth=1.0)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_ylabel("Drawdown (%)", fontsize=11)
    _style_axis(ax)

    path = os.path.join(RESULTS_DIR, filename)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved chart: %s", path)
    return path


def plot_holdings_count(
    holdings_histories: dict[str, list[tuple]],
    title: str = "Number of Holdings Over Time",
    filename: str = "holdings_count.png",
) -> str:
    """Plot how many holdings each strategy had over time."""
    ensure_results_dir()
    fig, ax = plt.subplots(figsize=(14, 5))

    colours = ["#2196F3", "#FF5722", "#4CAF50", "#9C27B0", "#FF9800"]
    for idx, (label, history) in enumerate(holdings_histories.items()):
        if not history:
            continue
        dates = [h[0] for h in history]
        counts = [len(h[1]) for h in history]
        colour = colours[idx % len(colours)]
        ax.plot(dates, counts, label=label, color=colour, linewidth=1.0, marker=".", markersize=2)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_ylabel("# Holdings", fontsize=11)
    _style_axis(ax)

    path = os.path.join(RESULTS_DIR, filename)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved chart: %s", path)
    return path


# ---------------------------------------------------------------------------
# Summary Report
# ---------------------------------------------------------------------------

def generate_report(
    results: dict,
    benchmark_values: pd.Series,
) -> str:
    """
    Generate a full performance report.

    Args:
        results: dict of {strategy_name: {
            "values": pd.Series,
            "portfolio": Portfolio,
        }}
        benchmark_values: pd.Series of S&P 500 index values.

    Returns:
        Summary text printed to console.
    """
    ensure_results_dir()

    # --- Metrics ---
    all_metrics = {}
    series_for_charts = {}

    for strat_name, data in results.items():
        values = data["values"]
        if values.empty:
            continue
        m = compute_metrics(values)
        all_metrics[strat_name] = m
        series_for_charts[strat_name] = values

    # Benchmark metrics
    if not benchmark_values.empty:
        # Align benchmark to the common date range
        earliest = min(v.index[0] for v in series_for_charts.values())
        latest = max(v.index[-1] for v in series_for_charts.values())
        bench_aligned = benchmark_values.loc[earliest:latest].dropna()
        if not bench_aligned.empty:
            all_metrics["S&P 500 (Benchmark)"] = compute_metrics(bench_aligned)
            series_for_charts["S&P 500 (Benchmark)"] = bench_aligned

    # --- Print metrics ---
    summary_lines = ["\n" + "=" * 60, "  BACKTEST RESULTS SUMMARY", "=" * 60]
    for name, m in all_metrics.items():
        summary_lines.append(metrics_to_string(name, m))

    summary_text = "\n".join(summary_lines)
    print(summary_text)

    # --- Save metrics to CSV ---
    metrics_df = pd.DataFrame(all_metrics).T
    metrics_path = os.path.join(RESULTS_DIR, "performance_metrics.csv")
    metrics_df.to_csv(metrics_path)
    logger.info("Saved metrics to %s", metrics_path)

    # --- Charts ---
    plot_cumulative_returns(series_for_charts)
    plot_annual_returns(series_for_charts)
    plot_drawdowns(series_for_charts)

    # Holdings count
    holdings_histories = {}
    for strat_name, data in results.items():
        portfolio = data["portfolio"]
        holdings_histories[strat_name] = portfolio.holdings_history
    plot_holdings_count(holdings_histories)

    # --- Top holdings by frequency ---
    for strat_name, data in results.items():
        portfolio = data["portfolio"]
        _save_holdings_frequency(strat_name, portfolio)
        _save_trade_log(strat_name, portfolio)

    return summary_text


def _save_holdings_frequency(strat_name: str, portfolio) -> None:
    """Save a table of most frequently held stocks."""
    from collections import Counter

    counter = Counter()
    for _, holdings in portfolio.holdings_history:
        counter.update(holdings)

    if not counter:
        return

    df = pd.DataFrame(
        counter.most_common(30),
        columns=["ticker", "months_held"],
    )
    safe_name = strat_name.replace(" ", "_").replace("/", "_").lower()
    path = os.path.join(RESULTS_DIR, f"top_holdings_{safe_name}.csv")
    df.to_csv(path, index=False)
    logger.info("Saved holdings frequency: %s", path)


def _save_trade_log(strat_name: str, portfolio) -> None:
    """Save the complete trade log."""
    trade_df = portfolio.get_trade_log_df()
    if trade_df.empty:
        return
    safe_name = strat_name.replace(" ", "_").replace("/", "_").lower()
    path = os.path.join(RESULTS_DIR, f"trade_log_{safe_name}.csv")
    trade_df.to_csv(path, index=False)
    logger.info("Saved trade log: %s", path)
