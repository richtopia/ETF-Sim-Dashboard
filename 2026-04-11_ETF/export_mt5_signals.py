#!/usr/bin/env python3
"""
export_mt5_signals.py — Export Python backtest signals for MT5.

This script runs the S&P 500 Ultimate Strategy and exports the daily/monthly
target allocations to a CSV file (mt5_signals.csv) formatted for our MT5 EA.
"""

import argparse
import logging
import sys
import datetime as dt
import pandas as pd

from data_loader import load_all_data, get_constituents_on_date
from backtesting import get_rebalance_dates
from strategies import UltimateStrategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Export MT5 Signals")
    parser.add_argument("--start-date", default="2020-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=dt.date.today().isoformat(), help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", default="mt5_signals.csv", help="Output CSV file path")
    
    args = parser.parse_args()
    logger.info("Loading data for MT5 signal export...")
    
    data = load_all_data(
        start_date=args.start_date,
        end_date=args.end_date,
        refresh=False,
    )

    constituents_df = data["constituents"]
    prices = data["prices"]
    shares_outstanding = data["shares_outstanding"]
    macro = data.get("macro")
    dividends = data.get("dividends")

    rebalance_dates = get_rebalance_dates(prices, args.start_date, args.end_date)
    if not rebalance_dates:
        logger.error("No valid rebalance dates found. Check date range.")
        sys.exit(1)

    strategy = UltimateStrategy(top_n=10)
    logger.info(f"Generating signals for {strategy.name}...")

    signals = []

    for date in rebalance_dates:
        constituents = get_constituents_on_date(constituents_df, date)
        if not constituents:
            continue

        # Get target stocks from strategy
        top_stocks = strategy.rank_stocks(
            date, constituents, prices, shares_outstanding,
            macro=macro, dividends=dividends
        )

        if not top_stocks:
            continue

        # Equal weight allocation for MT5
        weight = 1.0 / len(top_stocks)
        
        # We output the date formatted simply, e.g., YYYY-MM-DD
        date_str = date.strftime("%Y-%m-%d")
        
        for stock in top_stocks:
            signals.append({
                "Date": date_str,
                "Symbol": stock,
                "Weight": weight
            })

    # Convert to DataFrame and save
    df_signals = pd.DataFrame(signals)
    df_signals.to_csv(args.output, index=False)
    
    logger.info(f"Successfully exported {len(df_signals)} signal rows to {args.output}")

if __name__ == "__main__":
    main()
