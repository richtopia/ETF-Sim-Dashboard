#!/usr/bin/env python3
"""
backtesting.py — Main entry point for S&P 500 stock selection backtests.

Runs two strategies:
  1. Top 10 by Market Capitalisation
  2. Top 10 by Momentum (12-1 factor)

Both use equal-weight portfolios with a 1-year capital gains hold rule.
"""

import argparse
import logging
import sys
import datetime as dt

import pandas as pd

from data_loader import load_all_data, get_constituents_on_date
from strategies import MarketCapStrategy, MomentumStrategy
from portfolio import Portfolio
from reporting import generate_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_rebalance_dates(
    prices: pd.DataFrame, start_date: str, end_date: str
) -> list[pd.Timestamp]:
    """
    Return the first trading day of each month within the date range.
    These are the dates on which we evaluate whether to rebalance.
    """
    all_dates = prices.index.sort_values()
    mask = (all_dates >= pd.Timestamp(start_date)) & (all_dates <= pd.Timestamp(end_date))
    trading_dates = all_dates[mask]

    if trading_dates.empty:
        return []

    # Group by year-month and take the first trading day
    monthly = trading_dates.to_series().groupby(
        [trading_dates.year, trading_dates.month]
    ).first()

    return sorted(pd.Timestamp(v) for v in monthly.values)


def run_backtest(
    strategy,
    constituents_df: pd.DataFrame,
    prices: pd.DataFrame,
    shares_outstanding: pd.Series,
    rebalance_dates: list[pd.Timestamp],
    initial_capital: float,
    enforce_tax_hold: bool = True,
    macro: pd.DataFrame | None = None,
    dividends: pd.DataFrame | None = None,
) -> dict:
    """
    Execute a backtest for a single strategy.

    Returns:
        {
            "values": pd.Series of daily portfolio values,
            "portfolio": Portfolio object with full state,
        }
    """
    portfolio = Portfolio(initial_capital=initial_capital, enforce_tax_hold=enforce_tax_hold)

    logger.info("Running backtest: %s (Tax Hold: %s)", strategy.name, enforce_tax_hold)
    logger.info(
        "  Period: %s to %s  (%d rebalance dates)",
        rebalance_dates[0].date(),
        rebalance_dates[-1].date(),
        len(rebalance_dates),
    )

    for i, date in enumerate(rebalance_dates):
        # Get S&P 500 constituents for this date
        constituents = get_constituents_on_date(constituents_df, date)
        if not constituents:
            logger.warning("  No constituents found for %s, skipping", date.date())
            continue

        # Get top stocks from strategy
        top_stocks = strategy.rank_stocks(
            date, constituents, prices, shares_outstanding,
            macro=macro, dividends=dividends
        )
        if not top_stocks:
            logger.warning("  Strategy returned no stocks for %s", date.date())
            portfolio.record_snapshot(date, prices)
            continue

        # Rebalance
        portfolio.rebalance(date, top_stocks, prices)
        portfolio.record_snapshot(date, prices)

        if (i + 1) % 12 == 0 or i == 0:
            value = portfolio.compute_value(date, prices)
            logger.info(
                "  %s  |  Value: $%s  |  Holdings: %d  |  Cash: $%s",
                date.date(), f"{value:,.0f}", len(portfolio.positions), f"{portfolio.cash:,.0f}",
            )

    # Also record daily values for smooth chart
    daily_values = _compute_daily_values(portfolio, prices, rebalance_dates)

    return {
        "values": daily_values,
        "portfolio": portfolio,
    }


def _compute_daily_values(
    portfolio_obj: Portfolio,
    prices: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
) -> pd.Series:
    """
    Reconstruct daily portfolio values from monthly snapshots.
    We re-run the portfolio forward day by day using the recorded
    value_history snapshots as checkpoints.
    """
    if not portfolio_obj.value_history:
        return pd.Series(dtype=float)

    # Use the monthly snapshot values directly
    dates = [h[0] for h in portfolio_obj.value_history]
    values = [h[1] for h in portfolio_obj.value_history]
    series = pd.Series(values, index=pd.DatetimeIndex(dates), name="portfolio_value")

    # Interpolate to daily using price movements
    # For simplicity, just return the monthly series — it's clean enough for charts
    return series


def main():
    parser = argparse.ArgumentParser(
        description="S&P 500 Top-10 Stock Selection Backtester",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--start-date", default="1996-01-01",
        help="Backtest start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date", default=dt.date.today().isoformat(),
        help="Backtest end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--initial-capital", type=float, default=100_000,
        help="Initial portfolio capital ($)",
    )
    parser.add_argument(
        "--top-n", type=int, default=10,
        help="Number of top stocks to select",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Force re-download of all data (ignore cache)",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  S&P 500 TOP-%d STOCK SELECTION BACKTEST", args.top_n)
    logger.info("=" * 60)
    logger.info("  Start date:      %s", args.start_date)
    logger.info("  End date:        %s", args.end_date)
    logger.info("  Initial capital: $%s", f"{args.initial_capital:,.0f}")
    logger.info("  Top N:           %d", args.top_n)
    logger.info("  Refresh data:    %s", args.refresh)
    logger.info("=" * 60)

    # --- Load data ---
    logger.info("Loading data...")
    data = load_all_data(
        start_date=args.start_date,
        end_date=args.end_date,
        refresh=args.refresh,
    )

    constituents_df = data["constituents"]
    prices = data["prices"]
    shares_outstanding = data["shares_outstanding"]
    benchmark = data["benchmark"]
    macro = data.get("macro")
    dividends = data.get("dividends")

    logger.info(
        "Data loaded: %d constituent snapshots, %d tickers with prices, benchmark %d days",
        len(constituents_df),
        prices.shape[1],
        len(benchmark),
    )

    # --- Determine rebalance dates ---
    rebalance_dates = get_rebalance_dates(prices, args.start_date, args.end_date)
    if not rebalance_dates:
        logger.error("No valid rebalance dates found. Check date range.")
        sys.exit(1)

    logger.info("Rebalance dates: %d (monthly)", len(rebalance_dates))

    # --- Run strategies ---
    from strategies import (
        Strategy, MarketCapStrategy, MomentumStrategy, 
        UnifiedStrategy, UnifiedBalancedStrategy, UnifiedDefensiveStrategy,
        HighDividendYieldStrategy, MacroRegimeSwitchingStrategy, UltimateStrategy
    )
    strategies = [
        (MarketCapStrategy(top_n=args.top_n), True),
        (MomentumStrategy(top_n=args.top_n), True),
        (UnifiedStrategy(top_n_mc=7, top_n_mom=3), True),
        (UnifiedBalancedStrategy(top_n_mc=5, top_n_mom=5), True),
        (UnifiedDefensiveStrategy(top_n_mc=5, top_n_mom=3, top_n_lv=2), True),
        (HighDividendYieldStrategy(top_n=args.top_n), True),
        (MacroRegimeSwitchingStrategy(top_n=args.top_n), True),
        (UltimateStrategy(top_n=10), True),
    ]

    results = {}
    for strategy, enforce_tax_hold in strategies:
        result = run_backtest(
            strategy=strategy,
            constituents_df=constituents_df,
            prices=prices,
            shares_outstanding=shares_outstanding,
            rebalance_dates=rebalance_dates,
            initial_capital=args.initial_capital,
            enforce_tax_hold=enforce_tax_hold,
            macro=macro,
            dividends=dividends,
        )
        name = strategy.name if enforce_tax_hold else strategy.name + " (No Tax Hold)"
        results[name] = result

    # --- Generate report ---
    logger.info("Generating report...")
    generate_report(results, benchmark)

    logger.info("Done! Results saved to results/ directory.")


if __name__ == "__main__":
    main()
