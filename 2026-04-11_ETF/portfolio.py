"""
portfolio.py — Portfolio simulator with 1-year capital gains hold rule.

Simulates an equal-weighted portfolio of top-N stocks, where positions
are only sold after being held for more than one year (to qualify for
long-term capital gains tax treatment).
"""

import logging
import datetime as dt
from dataclasses import dataclass, field

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents a single stock position."""

    ticker: str
    entry_date: pd.Timestamp
    shares: float          # number of shares held
    entry_price: float     # price per share at entry


@dataclass
class TradeRecord:
    """Log of a buy or sell."""

    date: pd.Timestamp
    ticker: str
    action: str            # "BUY" or "SELL"
    shares: float
    price: float
    held_days: int = 0     # only for sells


class Portfolio:
    """
    Simulates an equal-weighted portfolio with a 1-year hold rule.

    Rules:
    - At each rebalance, the strategy produces a ranked list of top-N stocks.
    - Existing positions NOT in the new top-N:
        * If held > 1 year  → SELL (long-term capital gains)
        * If held ≤ 1 year → KEEP (avoid short-term capital gains)
    - Freed capital is distributed equally among new additions.
    - Between rebalances, positions drift with the market (no intra-month action).
    """

    ONE_YEAR = pd.Timedelta(days=365)

    def __init__(self, initial_capital: float = 100_000.0, enforce_tax_hold: bool = True):
        self.initial_capital = initial_capital
        self.cash: float = initial_capital
        self.positions: dict[str, Position] = {}   # ticker → Position
        self.trade_log: list[TradeRecord] = []
        self.enforce_tax_hold = enforce_tax_hold

        # Time series tracking
        self.value_history: list[tuple[pd.Timestamp, float]] = []
        self.holdings_history: list[tuple[pd.Timestamp, list[str]]] = []

    def _get_price(
        self, ticker: str, date: pd.Timestamp, prices: pd.DataFrame
    ) -> float | None:
        """Get the price of a ticker on the given date (or closest prior)."""
        if ticker not in prices.columns:
            return None
        col = prices[ticker].loc[:date].dropna()
        if col.empty:
            return None
        return float(col.iloc[-1])

    def rebalance(
        self,
        date: pd.Timestamp,
        target_tickers: list[str],
        prices: pd.DataFrame,
    ) -> None:
        """
        Rebalance the portfolio toward target_tickers on the given date.

        Logic:
        1. Sell positions no longer in target_tickers AND held > 1 year.
        2. Compute target allocation per position = total_value / top_n.
        3. Buy new target tickers using available cash, up to target allocation.
        """
        top_n = len(target_tickers)

        # --- Step 1: Sell eligible positions ---
        tickers_to_sell = []
        for ticker, pos in list(self.positions.items()):
            if ticker not in target_tickers:
                held_duration = date - pos.entry_date
                if not self.enforce_tax_hold or held_duration > self.ONE_YEAR:
                    tickers_to_sell.append(ticker)
                else:
                    logger.debug(
                        "  HOLD %s (held %d days, < 1 year)",
                        ticker,
                        held_duration.days,
                    )

        for ticker in tickers_to_sell:
            pos = self.positions[ticker]
            price = self._get_price(ticker, date, prices)
            if price is None:
                price = pos.entry_price
                logger.warning(
                    "  No price for %s on %s, using entry price %.2f",
                    ticker, date, price,
                )
            proceeds = pos.shares * price
            self.cash += proceeds
            held_days = (date - pos.entry_date).days
            self.trade_log.append(TradeRecord(
                date=date, ticker=ticker, action="SELL",
                shares=pos.shares, price=price, held_days=held_days,
            ))
            logger.debug(
                "  SELL %s: %.2f shares @ $%.2f = $%.2f (held %d days)",
                ticker, pos.shares, price, proceeds, held_days,
            )
            del self.positions[ticker]

        # --- Step 2: Compute target allocation ---
        total_value = self.compute_value(date, prices)
        target_per_position = total_value / top_n

        # --- Step 3: Buy new target tickers ---
        new_tickers = [t for t in target_tickers if t not in self.positions]

        if new_tickers and self.cash > 0:
            # Don't over-allocate: each new position gets at most target_per_position,
            # but we're limited by available cash
            alloc_per_stock = min(self.cash / len(new_tickers), target_per_position)

            for ticker in new_tickers:
                if self.cash <= 0:
                    break

                price = self._get_price(ticker, date, prices)
                if price is None or price <= 0:
                    logger.warning("  Cannot buy %s — no price on %s", ticker, date)
                    continue

                actual_alloc = min(alloc_per_stock, self.cash)
                shares = actual_alloc / price
                self.positions[ticker] = Position(
                    ticker=ticker,
                    entry_date=date,
                    shares=shares,
                    entry_price=price,
                )
                self.cash -= actual_alloc
                self.trade_log.append(TradeRecord(
                    date=date, ticker=ticker, action="BUY",
                    shares=shares, price=price,
                ))
                logger.debug(
                    "  BUY  %s: %.4f shares @ $%.2f = $%.2f",
                    ticker, shares, price, actual_alloc,
                )

    def compute_value(self, date: pd.Timestamp, prices: pd.DataFrame) -> float:
        """Compute total portfolio value (cash + positions) on a given date."""
        total = self.cash
        for ticker, pos in self.positions.items():
            price = self._get_price(ticker, date, prices)
            if price is not None:
                total += pos.shares * price
            else:
                # Use entry price as fallback for delisted
                total += pos.shares * pos.entry_price
        return total

    def record_snapshot(self, date: pd.Timestamp, prices: pd.DataFrame) -> None:
        """Record the portfolio value and holdings for the given date."""
        value = self.compute_value(date, prices)
        self.value_history.append((date, value))
        self.holdings_history.append(
            (date, list(self.positions.keys()))
        )

    def get_value_series(self) -> pd.Series:
        """Return the portfolio value as a time series."""
        if not self.value_history:
            return pd.Series(dtype=float)
        dates, values = zip(*self.value_history)
        return pd.Series(values, index=pd.DatetimeIndex(dates), name="portfolio_value")

    def get_trade_log_df(self) -> pd.DataFrame:
        """Return the trade log as a DataFrame."""
        if not self.trade_log:
            return pd.DataFrame(columns=["date", "ticker", "action", "shares", "price", "held_days"])
        records = [
            {
                "date": t.date,
                "ticker": t.ticker,
                "action": t.action,
                "shares": t.shares,
                "price": t.price,
                "held_days": t.held_days,
            }
            for t in self.trade_log
        ]
        return pd.DataFrame(records)
