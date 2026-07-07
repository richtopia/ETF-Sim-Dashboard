"""
strategies.py — Stock selection strategies for the S&P 500 backtest.

Two strategies:
  1. MarketCapStrategy: Select top N stocks by estimated market capitalisation.
  2. MomentumStrategy: Select top N stocks by trailing 12-month return
     (excluding the most recent 1 month to avoid short-term reversal).
"""

from abc import ABC, abstractmethod
import logging

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class Strategy(ABC):
    """Base class for stock-selection strategies."""

    def __init__(self, top_n: int = 10):
        self.top_n = top_n

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def rank_stocks(
        self,
        date: pd.Timestamp,
        constituents: list[str],
        prices: pd.DataFrame,
        shares_outstanding: pd.Series,
        **kwargs
    ) -> list[str]:
        """
        Return a list of top_n tickers ranked best-first for the given date.
        Only tickers present in both `constituents` and `prices.columns`
        should be considered.
        """
        ...


class MarketCapStrategy(Strategy):
    """
    Select the top N stocks by estimated market capitalisation.

    Market cap is approximated as:
        adjusted_close_price(date) × current_shares_outstanding

    This is imperfect (ignores historical share-count changes) but is
    the best available approach with free data and adequate for ranking.
    """

    @property
    def name(self) -> str:
        return f"Top {self.top_n} by Market Cap"

    def rank_stocks(
        self,
        date: pd.Timestamp,
        constituents: list[str],
        prices: pd.DataFrame,
        shares_outstanding: pd.Series,
        **kwargs
    ) -> list[str]:
        # Get tickers with both price and share data
        available = [
            t for t in constituents
            if t in prices.columns and t in shares_outstanding.index
        ]
        if not available:
            return []

        # Get the closest price on or before this date
        price_slice = prices.loc[:date, available]
        if price_slice.empty:
            return []

        latest_prices = price_slice.iloc[-1]
        shares = shares_outstanding.reindex(available)

        market_cap = latest_prices * shares
        market_cap = market_cap.dropna().sort_values(ascending=False)

        return market_cap.index[: self.top_n].tolist()


class MomentumStrategy(Strategy):
    """
    Select the top N stocks by trailing 12-month momentum.

    Momentum is defined as the total return over the past 12 months,
    excluding the most recent 1 month (to avoid short-term mean reversion).
    This is the standard academic "12-1" momentum factor.

    Stocks with fewer than 252 trading days of price history (≈12 months)
    before the evaluation date are excluded.
    """

    LOOKBACK_DAYS = 252    # ~12 months of trading days
    SKIP_DAYS = 21         # ~1 month of trading days to skip (recent month)

    @property
    def name(self) -> str:
        return f"Top {self.top_n} by Momentum (12-1)"

    def rank_stocks(
        self,
        date: pd.Timestamp,
        constituents: list[str],
        prices: pd.DataFrame,
        shares_outstanding: pd.Series,
        **kwargs
    ) -> list[str]:
        available = [t for t in constituents if t in prices.columns]
        if not available:
            return []

        # We need data from (date - 12 months) to (date - 1 month)
        price_slice = prices.loc[:date, available]
        if len(price_slice) < self.LOOKBACK_DAYS:
            logger.debug(
                "Not enough history for momentum on %s (%d rows available)",
                date,
                len(price_slice),
            )
            return []

        # Price at (date - 1 month)  ≈  skip the last SKIP_DAYS rows
        end_idx = len(price_slice) - self.SKIP_DAYS
        start_idx = end_idx - self.LOOKBACK_DAYS

        if start_idx < 0 or end_idx < 0:
            return []

        prices_end = price_slice.iloc[end_idx]
        prices_start = price_slice.iloc[start_idx]

        momentum = (prices_end / prices_start) - 1.0

        # Drop tickers where either price was NaN (insufficient history)
        momentum = momentum.dropna()
        momentum = momentum.sort_values(ascending=False)

        return momentum.index[: self.top_n].tolist()

class UnifiedStrategy(Strategy):
    """
    Select top 7 stocks by Market Cap and top 3 stocks by Momentum.
    If a stock appears in both, it's only included once.
    """

    def __init__(self, top_n_mc: int = 7, top_n_mom: int = 3):
        super().__init__(top_n_mc + top_n_mom)
        self.mc_strategy = MarketCapStrategy(top_n=top_n_mc)
        self.mom_strategy = MomentumStrategy(top_n=top_n_mom)

    @property
    def name(self) -> str:
        return f"Unified (Top {self.mc_strategy.top_n} MC + Top {self.mom_strategy.top_n} Momentum)"

    def rank_stocks(
        self,
        date: pd.Timestamp,
        constituents: list[str],
        prices: pd.DataFrame,
        shares_outstanding: pd.Series,
        **kwargs
    ) -> list[str]:
        mc_picks = self.mc_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)
        mom_picks = self.mom_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)

        # Combine, preserving order (MC first, then Mom), removing duplicates
        combined = []
        seen = set()
        for t in mc_picks + mom_picks:
            if t not in seen:
                combined.append(t)
                seen.add(t)

        return combined

class LowVolatilityStrategy(Strategy):
    """
    Select the top N stocks by lowest volatility over the trailing 12 months.
    """
    LOOKBACK_DAYS = 252

    @property
    def name(self) -> str:
        return f"Top {self.top_n} by Low Volatility"

    def rank_stocks(
        self,
        date: pd.Timestamp,
        constituents: list[str],
        prices: pd.DataFrame,
        shares_outstanding: pd.Series,
        **kwargs
    ) -> list[str]:
        available = [t for t in constituents if t in prices.columns]
        if not available:
            return []

        price_slice = prices.loc[:date, available]
        if len(price_slice) < self.LOOKBACK_DAYS:
            return []

        price_slice = price_slice.tail(self.LOOKBACK_DAYS)
        daily_returns = price_slice.pct_change(fill_method=None)
        volatility = daily_returns.std()
        
        # Sort ascending (lowest volatility first)
        volatility = volatility.dropna().sort_values(ascending=True)
        return volatility.index[: self.top_n].tolist()

class UnifiedBalancedStrategy(UnifiedStrategy):
    """
    Unified strategy with equal weight to Market Cap and Momentum (5 and 5).
    """
    def __init__(self, top_n_mc: int = 5, top_n_mom: int = 5):
        super().__init__(top_n_mc=top_n_mc, top_n_mom=top_n_mom)

    @property
    def name(self) -> str:
        return f"Unified Balanced ({self.mc_strategy.top_n} MC + {self.mom_strategy.top_n} Mom)"

class UnifiedDefensiveStrategy(Strategy):
    """
    Unified strategy adding a Defensive (Low Volatility) factor.
    5 Market Cap, 3 Momentum, 2 Low Volatility.
    """
    def __init__(self, top_n_mc: int = 5, top_n_mom: int = 3, top_n_lv: int = 2):
        super().__init__(top_n_mc + top_n_mom + top_n_lv)
        self.mc_strategy = MarketCapStrategy(top_n=top_n_mc)
        self.mom_strategy = MomentumStrategy(top_n=top_n_mom)
        self.lv_strategy = LowVolatilityStrategy(top_n=top_n_lv)

    @property
    def name(self) -> str:
        return f"Unified Defensive ({self.mc_strategy.top_n} MC + {self.mom_strategy.top_n} Mom + {self.lv_strategy.top_n} Low Vol)"

    def rank_stocks(
        self,
        date: pd.Timestamp,
        constituents: list[str],
        prices: pd.DataFrame,
        shares_outstanding: pd.Series,
        **kwargs
    ) -> list[str]:
        mc_picks = self.mc_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)
        mom_picks = self.mom_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)
        lv_picks = self.lv_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)

        combined = []
        seen = set()
        for t in mc_picks + mom_picks + lv_picks:
            if t not in seen:
                combined.append(t)
                seen.add(t)

        return combined

class HighDividendYieldStrategy(Strategy):
    """
    Select top N stocks by trailing 12-month dividend yield.
    """
    @property
    def name(self) -> str:
        return f"Top {self.top_n} by Dividend Yield"

    def rank_stocks(
        self,
        date: pd.Timestamp,
        constituents: list[str],
        prices: pd.DataFrame,
        shares_outstanding: pd.Series,
        **kwargs
    ) -> list[str]:
        dividends = kwargs.get("dividends")
        if dividends is None or dividends.empty:
            return []
        
        available = [t for t in constituents if t in prices.columns and t in dividends.columns]
        if not available:
            return []

        # Trailing 12 months (365 days)
        start_date = date - pd.Timedelta(days=365)
        # Sum dividends in the trailing 12 months
        div_slice = dividends.loc[start_date:date, available]
        ttm_dividends = div_slice.sum(axis=0)

        # Get latest price
        price_slice = prices.loc[:date, available]
        if price_slice.empty:
            return []
        latest_prices = price_slice.iloc[-1]

        # Calculate yield
        yields = ttm_dividends / latest_prices
        
        # Sort descending (highest yield)
        yields = yields.replace([np.inf, -np.inf], np.nan).dropna().sort_values(ascending=False)
        return yields.index[: self.top_n].tolist()

class MacroRegimeSwitchingStrategy(Strategy):
    """
    If T10Y2Y > 0 (Normal): Top 10 Momentum
    If T10Y2Y <= 0 (Risk-Off): Top 10 Low Volatility
    """
    def __init__(self, top_n: int = 10):
        super().__init__(top_n)
        self.mom_strategy = MomentumStrategy(top_n=top_n)
        self.lv_strategy = LowVolatilityStrategy(top_n=top_n)

    @property
    def name(self) -> str:
        return f"Macro Regime Switch (Mom / Low Vol)"

    def rank_stocks(
        self,
        date: pd.Timestamp,
        constituents: list[str],
        prices: pd.DataFrame,
        shares_outstanding: pd.Series,
        **kwargs
    ) -> list[str]:
        macro = kwargs.get("macro")
        if macro is None or macro.empty or "T10Y2Y" not in macro.columns:
            # Default to momentum if no macro
            return self.mom_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)

        macro_slice = macro.loc[:date, ["T10Y2Y"]].dropna()
        if macro_slice.empty:
            return self.mom_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)

        t10y2y = macro_slice.iloc[-1]["T10Y2Y"]
        
        # Positive = normal, Negative = inverted yield curve
        if t10y2y > 0:
            return self.mom_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)
        else:
            return self.lv_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)

class UltimateStrategy(Strategy):
    """
    Normal Regime (T10Y2Y > 0): 5 Momentum + 5 Market Cap
    Risk-Off Regime (T10Y2Y <= 0): 5 Low Volatility + 5 High Dividend
    """
    def __init__(self, top_n: int = 10):
        super().__init__(top_n)
        # Normal
        self.mom_strategy = MomentumStrategy(top_n=5)
        self.mc_strategy = MarketCapStrategy(top_n=5)
        # Risk Off
        self.lv_strategy = LowVolatilityStrategy(top_n=5)
        self.div_strategy = HighDividendYieldStrategy(top_n=5)

    @property
    def name(self) -> str:
        return "Ultimate Strategy (Regime Blending)"

    def rank_stocks(
        self,
        date: pd.Timestamp,
        constituents: list[str],
        prices: pd.DataFrame,
        shares_outstanding: pd.Series,
        **kwargs
    ) -> list[str]:
        macro = kwargs.get("macro")
        risk_on = True
        if macro is not None and not macro.empty and "T10Y2Y" in macro.columns:
            macro_slice = macro.loc[:date, ["T10Y2Y"]].dropna()
            if not macro_slice.empty:
                t10y2y = macro_slice.iloc[-1]["T10Y2Y"]
                if t10y2y <= 0:
                    risk_on = False

        if risk_on:
            p1 = self.mom_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)
            p2 = self.mc_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)
        else:
            p1 = self.lv_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)
            p2 = self.div_strategy.rank_stocks(date, constituents, prices, shares_outstanding, **kwargs)

        combined = []
        seen = set()
        for t in p1 + p2:
            if t not in seen:
                combined.append(t)
                seen.add(t)

        return combined

