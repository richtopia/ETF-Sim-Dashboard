"""
Run ETF Backtest

CLI entry point for the backtesting engine.
Usage:
    python run_backtest.py --config etf_definitions.yaml --start 2021-04-01 --end 2026-04-01 --output dashboard/results.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

from backtest_engine import run_backtest


def main():
    parser = argparse.ArgumentParser(description="ETF Backtesting Simulator")
    parser.add_argument(
        "--config",
        default="etf_definitions.yaml",
        help="Path to ETF definitions YAML file",
    )
    parser.add_argument(
        "--start",
        default="2004-01-01",
        help="Backtest start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Backtest end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output",
        default="dashboard/results.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable price data caching",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    logger = logging.getLogger(__name__)
    logger.info("=" * 70)
    logger.info("ETF Backtesting Simulator")
    logger.info("=" * 70)
    logger.info(f"Config: {args.config}")
    logger.info(f"Period: {args.start} to {args.end}")
    logger.info(f"Output: {args.output}")

    try:
        results = run_backtest(args.config, args.start, args.end)

        # Ensure output directory exists
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write results
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        logger.info(f"\nResults written to {output_path}")
        logger.info(f"File size: {output_path.stat().st_size / 1024:.1f} KB")

        # Print summary
        print("\n" + "=" * 70)
        print("BACKTEST SUMMARY")
        print("=" * 70)
        print(f"{'Name':<25} {'Total Return':>13} {'Annual':>8} {'MaxDD':>8} {'Sharpe':>8} {'Vol':>8}")
        print("-" * 70)

        for etf in results["etfs"]:
            m = etf["metrics"]
            print(
                f"{etf['name']:<25} "
                f"{m['total_return_pct']:>12.1f}% "
                f"{m['annualized_return_pct']:>7.1f}% "
                f"{m['max_drawdown_pct']:>7.1f}% "
                f"{m['sharpe_ratio']:>7.2f} "
                f"{m['volatility_pct']:>7.1f}%"
            )

        print("-" * 70)
        for bench in results["benchmarks"]:
            m = bench["metrics"]
            print(
                f"{bench['name']:<25} "
                f"{m['total_return_pct']:>12.1f}% "
                f"{m['annualized_return_pct']:>7.1f}% "
                f"{m['max_drawdown_pct']:>7.1f}% "
                f"{m['sharpe_ratio']:>7.2f} "
                f"{m['volatility_pct']:>7.1f}%"
            )
        print("=" * 70)

    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
