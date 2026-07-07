"""
ETF Backtesting Engine

Core logic for:
- Fetching historical price data from yfinance
- Computing approximate market caps for ranking
- Monthly rebalancing with configurable selection rules
- Computing portfolio performance metrics
"""

import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
import yaml
import io
import requests

from universes import get_universe, get_all_ticker_names

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.04  # approximate risk-free rate

# Companies with multiple share classes that should be treated as one entity.
# Maps the "primary" ticker to a list of alternate tickers whose market cap
# should be combined with the primary for ranking purposes.
COMPANY_GROUPS = {
    "GOOGL": ["GOOG"],   # Alphabet Class A + Class C
}


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _cache_path(tickers: list[str], start: str, end: str) -> Path:
    """Generate a cache file path based on tickers and date range."""
    key = hashlib.md5(f"{sorted(tickers)}_{start}_{end}".encode()).hexdigest()
    return CACHE_DIR / f"prices_{key}.csv"


def fetch_macro_data(start: str, end: str) -> pd.DataFrame:
    """Fetch T10Y2Y yield curve data from FRED."""
    cache_file = CACHE_DIR / "macro_T10Y2Y.csv"
    if cache_file.exists():
        df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
        # Check if cache is sufficient
        if df.index[0] <= pd.Timestamp(start) and df.index[-1] >= pd.Timestamp(end) - timedelta(days=5):
            return df

    logger.info("Downloading T10Y2Y macro data from FRED...")
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10Y2Y"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), index_col=0, parse_dates=True)
        # Clean data (FRED uses '.' for missing values)
        df = df.replace(".", np.nan)
        df = df.astype(float)
        df = df.ffill().bfill()
        CACHE_DIR.mkdir(exist_ok=True)
        df.to_csv(cache_file)
        return df
    except Exception as e:
        logger.error(f"Failed to fetch FRED macro data: {e}")
        return pd.DataFrame(columns=["T10Y2Y"], index=pd.DatetimeIndex([]))


def fetch_prices_and_dividends(
    tickers: list[str], start: str, end: str, use_cache: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fetch adjusted close prices and dividends for a list of tickers.
    Returns: (prices_df, dividends_df)
    """
    key = hashlib.md5(f"{sorted(tickers)}_{start}_{end}".encode()).hexdigest()
    prices_cache = CACHE_DIR / f"prices_{key}.csv"
    div_cache = CACHE_DIR / f"dividends_{key}.csv"

    if use_cache and prices_cache.exists() and div_cache.exists():
        logger.info(f"Loading cached prices and dividends")
        prices_df = pd.read_csv(prices_cache, index_col=0, parse_dates=True)
        dividends_df = pd.read_csv(div_cache, index_col=0, parse_dates=True)
        return prices_df, dividends_df

    logger.info(f"Downloading prices and dividends for {len(tickers)} tickers from {start} to {end}...")

    batch_size = 50
    all_prices = []
    all_dividends = []

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        logger.info(f"  Batch {i // batch_size + 1}: {len(batch)} tickers")
        try:
            data = yf.download(
                batch,
                start=start,
                end=end,
                auto_adjust=True,
                actions=True,
                progress=False,
                threads=True,
            )
            if data.empty:
                continue

            if isinstance(data.columns, pd.MultiIndex):
                closes = data["Close"]
                divs = data["Dividends"]
            else:
                closes = data[["Close"]].rename(columns={"Close": batch[0]})
                divs = data[["Dividends"]].rename(columns={"Dividends": batch[0]})

            all_prices.append(closes)
            all_dividends.append(divs)
        except Exception as e:
            logger.error(f"  Error downloading batch: {e}")

    if not all_prices:
        raise RuntimeError("No price data could be downloaded")

    prices_df = pd.concat(all_prices, axis=1)
    prices_df = prices_df.sort_index()

    # Drop columns that are entirely NaN in prices
    valid_cols = prices_df.dropna(how="all", axis=1).columns
    dropped = set(prices_df.columns) - set(valid_cols)
    if dropped:
        logger.warning(f"Dropped {len(dropped)} tickers with no price data: {dropped}")
    prices_df = prices_df[valid_cols]

    # Clean prices
    prices_df = prices_df.ffill(limit=5).bfill(limit=5)

    if all_dividends:
        dividends_df = pd.concat(all_dividends, axis=1)
        dividends_df = dividends_df.sort_index()
        # Keep only columns that exist in prices_df and fill NaNs
        dividends_df = dividends_df.reindex(columns=prices_df.columns).fillna(0.0)
    else:
        dividends_df = pd.DataFrame(0.0, index=prices_df.index, columns=prices_df.columns)

    # Cache
    CACHE_DIR.mkdir(exist_ok=True)
    prices_df.to_csv(prices_cache)
    dividends_df.to_csv(div_cache)
    logger.info(f"Cached prices and dividends to cache directory")

    return prices_df, dividends_df


def fetch_prices(tickers: list[str], start: str, end: str, use_cache: bool = True) -> pd.DataFrame:
    """Fetch close prices (fallback wrapper)."""
    prices_df, _ = fetch_prices_and_dividends(tickers, start, end, use_cache)
    return prices_df


def fetch_shares_outstanding(tickers: list[str]) -> dict[str, float]:
    """
    Fetch current shares outstanding for market cap estimation.
    Returns dict of ticker -> shares outstanding.
    """
    cache_file = CACHE_DIR / "shares_outstanding.json"
    cached = {}
    if cache_file.exists():
        with open(cache_file) as f:
            cached = json.load(f)

    result = {}
    missing = [t for t in tickers if t not in cached]

    if missing:
        logger.info(f"Fetching shares outstanding for {len(missing)} tickers...")
        for ticker in missing:
            try:
                info = yf.Ticker(ticker).info
                shares = info.get("sharesOutstanding", None)
                if shares and shares > 0:
                    result[ticker] = float(shares)
                    cached[ticker] = float(shares)
                else:
                    logger.warning(f"  No shares outstanding for {ticker}")
            except Exception as e:
                logger.warning(f"  Error fetching info for {ticker}: {e}")

        # Update cache
        CACHE_DIR.mkdir(exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(cached, f, indent=2)

    for t in tickers:
        if t in cached:
            result[t] = cached[t]

    logger.info(f"Got shares outstanding for {len(result)}/{len(tickers)} tickers")
    return result


# ---------------------------------------------------------------------------
# Rebalancing logic
# ---------------------------------------------------------------------------

def get_rebalance_dates(price_index: pd.DatetimeIndex, frequency: str) -> list[pd.Timestamp]:
    """Get the rebalance dates from the price index based on frequency."""
    dates = pd.Series(price_index)
    monthly = dates.groupby([dates.dt.year, dates.dt.month]).first()
    monthly_dates = monthly.tolist()
    
    if frequency == "monthly":
        return monthly_dates
    elif frequency == "yearly":
        return monthly_dates[::12]
    elif frequency == "13_months":
        return monthly_dates[::13]
    else:
        raise ValueError(f"Unknown frequency: {frequency}")


def select_top_n_by_market_cap(
    prices: pd.DataFrame,
    shares: dict[str, float],
    date: pd.Timestamp,
    n: int,
) -> list[str]:
    """
    Select the top N tickers by approximate market cap on a given date.
    Market cap = price × shares outstanding (using current shares as proxy).

    Companies with multiple share classes (e.g. Alphabet GOOGL/GOOG) are
    combined into a single entity for ranking. Only the primary ticker is
    included in the result.
    """
    available_tickers = [t for t in prices.columns if t in shares]

    # Get prices on or just before the target date
    mask = prices.index <= date
    if not mask.any():
        return []

    latest_prices = prices.loc[mask].iloc[-1]

    # Approximate FX rates to USD mapped by ticker suffix
    # This prevents local currencies (e.g. KRW, JPY, SAR) from inflating the MC ranking
    fx_multipliers = {
        ".KS": 0.00075,
        ".HK": 0.13,
        ".NS": 0.012,
        ".SR": 0.27,
        ".TW": 0.031,
        ".T":  0.0066,
        ".AX": 0.65,
        ".L":  1.26,
        ".DE": 1.08,
        ".PA": 1.08,
        ".MI": 1.08,
        ".MC": 1.08,
        ".SW": 1.11,
        ".CO": 0.14,
        ".BK": 0.027,
        ".JO": 0.053,
    }

    # Compute individual market caps normalized to USD
    individual_caps = {}
    for ticker in available_tickers:
        price = latest_prices.get(ticker, np.nan)
        if pd.notna(price) and price > 0:
            raw_mc = price * shares[ticker]
            # Extract suffix
            suffix = ticker[ticker.rfind("."):] if "." in ticker else ""
            multiplier = fx_multipliers.get(suffix, 1.0)
            individual_caps[ticker] = raw_mc * multiplier

    # Build set of alternate tickers that should be folded into a primary
    alt_to_primary = {}
    for primary, alts in COMPANY_GROUPS.items():
        for alt in alts:
            alt_to_primary[alt] = primary

    # Combine market caps for grouped companies
    market_caps = {}
    for ticker, cap in individual_caps.items():
        if ticker in alt_to_primary:
            # Add this cap to the primary ticker's total
            primary = alt_to_primary[ticker]
            market_caps[primary] = market_caps.get(primary, 0) + cap
        else:
            market_caps[ticker] = market_caps.get(ticker, 0) + cap

    # Sort and return top N
    sorted_tickers = sorted(market_caps.keys(), key=lambda t: market_caps[t], reverse=True)
    top_n = sorted_tickers[:n]

    return top_n


def select_top_n_by_momentum(
    prices: pd.DataFrame,
    date: pd.Timestamp,
    n: int,
) -> list[str]:
    """
    Select the top N stocks by trailing 12-month momentum, skipping the most recent month.
    """
    available = list(prices.columns)
    if not available:
        return []

    # Get prices up to target date
    price_slice = prices.loc[:date]
    if len(price_slice) < 252:
        return []

    # Prices at end of skip window (~1 month / 21 trading days back) and start of lookback (~12 months back)
    prices_end = price_slice.iloc[-21]
    prices_start = price_slice.iloc[-252]

    # Filter out invalid prices
    valid_mask = (prices_start > 0) & (prices_end > 0)
    prices_start = prices_start[valid_mask]
    prices_end = prices_end[valid_mask]

    momentum = (prices_end / prices_start) - 1.0
    momentum = momentum.dropna().sort_values(ascending=False)
    return momentum.index[:n].tolist()


def select_top_n_by_low_volatility(
    prices: pd.DataFrame,
    date: pd.Timestamp,
    n: int,
) -> list[str]:
    """
    Select the top N stocks by lowest standard deviation of daily returns over the trailing 12 months.
    """
    price_slice = prices.loc[:date]
    if len(price_slice) < 252:
        return []

    price_slice = price_slice.tail(252)
    daily_returns = price_slice.pct_change(fill_method=None)
    volatility = daily_returns.std()
    volatility = volatility.dropna().sort_values(ascending=True)
    return volatility.index[:n].tolist()


def select_top_n_by_high_dividend(
    prices: pd.DataFrame,
    dividends: pd.DataFrame,
    date: pd.Timestamp,
    n: int,
) -> list[str]:
    """
    Select the top N stocks by trailing 12-month dividend yield.
    """
    if dividends is None or dividends.empty:
        return []

    # Trailing 12 months (365 days)
    start_date = date - pd.Timedelta(days=365)
    # Sum dividends in the trailing 12 months
    div_slice = dividends.loc[start_date:date]
    ttm_dividends = div_slice.sum(axis=0)

    # Get latest price on or before date
    price_slice = prices.loc[:date]
    if price_slice.empty:
        return []
    latest_prices = price_slice.iloc[-1]

    # Calculate yield: TTM Dividends / Price
    valid_prices = latest_prices[latest_prices > 0]
    yields = ttm_dividends.reindex(valid_prices.index) / valid_prices
    yields = yields.replace([np.inf, -np.inf], np.nan).dropna().sort_values(ascending=False)
    return yields.index[:n].tolist()


def select_ult_yield(
    prices: pd.DataFrame,
    shares: dict[str, float],
    dividends: pd.DataFrame,
    macro: pd.DataFrame,
    date: pd.Timestamp,
    n: int,
) -> list[str]:
    """Regime switching: Risk-off when T10Y2Y <= 0."""
    risk_on = True
    if macro is not None and not macro.empty and "T10Y2Y" in macro.columns:
        macro_slice = macro.loc[:date, "T10Y2Y"].dropna()
        if not macro_slice.empty:
            t10y2y = macro_slice.iloc[-1]
            if t10y2y <= 0:
                risk_on = False

    if risk_on:
        p1 = select_top_n_by_momentum(prices, date, 5)
        p2 = select_top_n_by_market_cap(prices, shares, date, 5)
    else:
        p1 = select_top_n_by_low_volatility(prices, date, 5)
        p2 = select_top_n_by_high_dividend(prices, dividends, date, 5)

    combined = []
    seen = set()
    for t in p1 + p2:
        if t not in seen:
            combined.append(t)
            seen.add(t)

    return combined[:n]


def select_ult_vix(
    prices: pd.DataFrame,
    shares: dict[str, float],
    dividends: pd.DataFrame,
    vix_prices: pd.Series,
    date: pd.Timestamp,
    n: int,
) -> list[str]:
    """Regime switching: Risk-off when VIX > 20."""
    risk_on = True
    if vix_prices is not None and not vix_prices.empty:
        vix_slice = vix_prices.loc[:date].dropna()
        if not vix_slice.empty:
            vix_val = vix_slice.iloc[-1]
            if vix_val > 20:
                risk_on = False

    if risk_on:
        p1 = select_top_n_by_momentum(prices, date, 5)
        p2 = select_top_n_by_market_cap(prices, shares, date, 5)
    else:
        p1 = select_top_n_by_low_volatility(prices, date, 5)
        p2 = select_top_n_by_high_dividend(prices, dividends, date, 5)

    combined = []
    seen = set()
    for t in p1 + p2:
        if t not in seen:
            combined.append(t)
            seen.add(t)

    return combined[:n]


def select_ult_200sma(
    prices: pd.DataFrame,
    shares: dict[str, float],
    dividends: pd.DataFrame,
    benchmark_prices: pd.Series,
    date: pd.Timestamp,
    n: int,
) -> list[str]:
    """Regime switching: Risk-off when benchmark price < 200-day SMA."""
    risk_on = True
    if benchmark_prices is not None and not benchmark_prices.empty:
        benchmark_slice = benchmark_prices.loc[:date].dropna()
        if len(benchmark_slice) >= 200:
            sma_200 = benchmark_slice.tail(200).mean()
            latest_price = benchmark_slice.iloc[-1]
            if latest_price < sma_200:
                risk_on = False

    if risk_on:
        p1 = select_top_n_by_momentum(prices, date, 5)
        p2 = select_top_n_by_market_cap(prices, shares, date, 5)
    else:
        p1 = select_top_n_by_low_volatility(prices, date, 5)
        p2 = select_top_n_by_high_dividend(prices, dividends, date, 5)

    combined = []
    seen = set()
    for t in p1 + p2:
        if t not in seen:
            combined.append(t)
            seen.add(t)

    return combined[:n]


def select_ult_riskkpi(
    prices: pd.DataFrame,
    shares: dict[str, float],
    dividends: pd.DataFrame,
    risk_kpi_scores: pd.Series,
    date: pd.Timestamp,
    n: int,
) -> list[str]:
    """Regime switching: Risk-off when Consolidated Risk Score >= 50."""
    risk_on = True
    if risk_kpi_scores is not None and not risk_kpi_scores.empty:
        score_slice = risk_kpi_scores.loc[:date].dropna()
        if not score_slice.empty:
            latest_score = score_slice.iloc[-1]
            if latest_score >= 50.0:
                risk_on = False

    if risk_on:
        p1 = select_top_n_by_momentum(prices, date, 5)
        p2 = select_top_n_by_market_cap(prices, shares, date, 5)
    else:
        p1 = select_top_n_by_low_volatility(prices, date, 5)
        p2 = select_top_n_by_high_dividend(prices, dividends, date, 5)

    combined = []
    seen = set()
    for t in p1 + p2:
        if t not in seen:
            combined.append(t)
            seen.add(t)

    return combined[:n]


def compute_equal_weights(tickers: list[str]) -> dict[str, float]:
    """Assign equal weights to all tickers."""
    if not tickers:
        return {}
    w = 1.0 / len(tickers)
    return {t: w for t in tickers}


def select_ult_hybrid_weights(
    prices: pd.DataFrame,
    shares: dict[str, float],
    dividends: pd.DataFrame,
    benchmark_prices: pd.Series,
    risk_kpi_scores: pd.Series,
    date: pd.Timestamp,
) -> dict[str, float]:
    """
    Hybrid quantitative portfolio strategy:
    - 100% Defensive if S&P 500 < 200 SMA (Emergency brake)
    - Else, allocation determined by Consolidated Risk Score:
        - Score < 40: 100% Growth
        - Score 40-60: 50% Growth / 50% Defensive
        - Score > 60: 100% Defensive
    """
    # 1. Determine technical trend (200 SMA)
    below_sma = False
    if benchmark_prices is not None and not benchmark_prices.empty:
        benchmark_slice = benchmark_prices.loc[:date].dropna()
        if len(benchmark_slice) >= 200:
            sma_200 = benchmark_slice.tail(200).mean()
            latest_price = benchmark_slice.iloc[-1]
            if latest_price < sma_200:
                below_sma = True

    # 2. Get Consolidated Risk Score
    score = 0.0
    if risk_kpi_scores is not None and not risk_kpi_scores.empty:
        score_slice = risk_kpi_scores.loc[:date].dropna()
        if not score_slice.empty:
            score = score_slice.iloc[-1]

    # 3. Determine defensive weight percentage
    if below_sma:
        defensive_pct = 1.0
    else:
        if score < 40.0:
            defensive_pct = 0.0
        elif score <= 60.0:
            defensive_pct = 0.5
        else:
            defensive_pct = 1.0

    # 4. Get Growth and Defensive assets
    p_mom = select_top_n_by_momentum(prices, date, 5)
    p_mc = select_top_n_by_market_cap(prices, shares, date, 5)
    growth_tickers = []
    seen_g = set()
    for t in p_mom + p_mc:
        if t not in seen_g:
            growth_tickers.append(t)
            seen_g.add(t)

    p_vol = select_top_n_by_low_volatility(prices, date, 5)
    p_div = select_top_n_by_high_dividend(prices, dividends, date, 5)
    defensive_tickers = []
    seen_d = set()
    for t in p_vol + p_div:
        if t not in seen_d:
            defensive_tickers.append(t)
            seen_d.add(t)

    # 5. Build weights dictionary
    weights = {}
    growth_weight_pct = 1.0 - defensive_pct

    if growth_weight_pct > 0 and growth_tickers:
        g_w = growth_weight_pct / len(growth_tickers)
        for t in growth_tickers:
            weights[t] = weights.get(t, 0.0) + g_w

    if defensive_pct > 0 and defensive_tickers:
        d_w = defensive_pct / len(defensive_tickers)
        for t in defensive_tickers:
            weights[t] = weights.get(t, 0.0) + d_w

    return weights


# ---------------------------------------------------------------------------
# Portfolio simulation
# ---------------------------------------------------------------------------

def simulate_portfolio(
    prices: pd.DataFrame,
    shares: dict[str, float],
    rebalance_dates: list[pd.Timestamp],
    selection_rule: str,
    n: int,
    weighting: str,
    starting_value: float = 10000.0,
    dividends: pd.DataFrame = None,
    macro: pd.DataFrame = None,
    vix_prices: pd.Series = None,
    benchmark_prices: pd.Series = None,
    risk_kpi_scores: pd.Series = None,
) -> tuple[pd.Series, list[dict]]:
    """
    Simulate a portfolio with monthly rebalancing.

    Returns:
        - portfolio_values: pd.Series of daily portfolio values
        - holdings_log: list of dicts with rebalance date and holdings
    """
    # Get daily returns
    daily_returns = prices.pct_change().fillna(0)

    # Initialize
    portfolio_values = pd.Series(index=prices.index, dtype=float)
    holdings_log = []
    current_value = starting_value
    current_weights = {}
    current_tickers = []

    for i, date in enumerate(prices.index):
        # Check if it's a rebalance date
        if date in rebalance_dates:
            # Select stocks and compute weights
            if selection_rule == "ult_hybrid":
                new_weights = select_ult_hybrid_weights(
                    prices, shares, dividends, benchmark_prices, risk_kpi_scores, date
                )
                if not new_weights:
                    logger.warning(f"No weights calculated on {date}, keeping previous holdings")
                else:
                    current_weights = new_weights
                    current_tickers = list(current_weights.keys())
            else:
                if selection_rule == "top_n_by_market_cap":
                    new_tickers = select_top_n_by_market_cap(prices, shares, date, n)
                elif selection_rule == "ult_yield":
                    new_tickers = select_ult_yield(prices, shares, dividends, macro, date, n)
                elif selection_rule == "ult_vix":
                    new_tickers = select_ult_vix(prices, shares, dividends, vix_prices, date, n)
                elif selection_rule == "ult_200sma":
                    new_tickers = select_ult_200sma(prices, shares, dividends, benchmark_prices, date, n)
                elif selection_rule == "ult_riskkpi":
                    new_tickers = select_ult_riskkpi(prices, shares, dividends, risk_kpi_scores, date, n)
                else:
                    raise ValueError(f"Unknown selection rule: {selection_rule}")

                if not new_tickers:
                    logger.warning(f"No tickers selected on {date}, keeping previous holdings")
                else:
                    current_tickers = new_tickers
                    if weighting == "equal":
                        current_weights = compute_equal_weights(current_tickers)
                    else:
                        raise ValueError(f"Unknown weighting: {weighting}")

            if current_tickers:
                holdings_log.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "holdings": [
                        {"ticker": t, "weight": round(current_weights[t], 4)}
                        for t in current_tickers
                    ],
                })

            # Reset weight tracking after rebalance
            # Weights apply from this date forward
            weight_values = {t: current_value * current_weights.get(t, 0) for t in current_tickers}

        if not current_tickers:
            portfolio_values.iloc[i] = current_value
            continue

        if date in rebalance_dates:
            # On rebalance day, value stays the same (we just redistributed)
            portfolio_values.iloc[i] = current_value
        else:
            # Apply daily returns weighted by position sizes
            day_return = 0.0
            total_weight = 0.0
            for ticker in current_tickers:
                if ticker in daily_returns.columns:
                    ret = daily_returns.loc[date, ticker]
                    if pd.notna(ret):
                        w = current_weights.get(ticker, 0)
                        day_return += w * ret
                        total_weight += w

            if total_weight > 0:
                day_return = day_return / total_weight * total_weight  # already weighted
            current_value = current_value * (1 + day_return)
            portfolio_values.iloc[i] = current_value

    return portfolio_values, holdings_log


def simulate_benchmark(prices: pd.Series, starting_value: float = 10000.0) -> pd.Series:
    """Simulate buy-and-hold for a benchmark ETF."""
    daily_returns = prices.pct_change().fillna(0)
    values = starting_value * (1 + daily_returns).cumprod()
    values.iloc[0] = starting_value
    return values


# ---------------------------------------------------------------------------
# Performance metrics
# ---------------------------------------------------------------------------

def compute_metrics(values: pd.Series) -> dict:
    """Compute key performance metrics from a portfolio value series."""
    values = values.dropna()
    if len(values) < 2:
        return {
            "total_return_pct": 0,
            "annualized_return_pct": 0,
            "max_drawdown_pct": 0,
            "volatility_pct": 0,
            "sharpe_ratio": 0,
        }

    total_return = (values.iloc[-1] / values.iloc[0]) - 1
    n_days = (values.index[-1] - values.index[0]).days
    n_years = n_days / 365.25
    annualized_return = (1 + total_return) ** (1 / max(n_years, 0.01)) - 1

    # Daily returns
    daily_returns = values.pct_change().dropna()
    volatility = daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)

    # Sharpe ratio
    excess_return = annualized_return - RISK_FREE_RATE
    sharpe = excess_return / volatility if volatility > 0 else 0

    # Max drawdown
    cummax = values.cummax()
    drawdown = (values - cummax) / cummax
    max_drawdown = drawdown.min()

    return {
        "total_return_pct": round(total_return * 100, 2),
        "annualized_return_pct": round(annualized_return * 100, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "volatility_pct": round(volatility * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
    }


def compute_drawdown_series(values: pd.Series) -> pd.Series:
    """Compute drawdown percentage series."""
    cummax = values.cummax()
    drawdown = (values - cummax) / cummax * 100
    return drawdown


def compute_monthly_returns(values: pd.Series) -> pd.DataFrame:
    """
    Compute monthly returns formatted as year × month table.
    Returns DataFrame with year as index and month (1-12) as columns.
    """
    monthly = values.resample("ME").last()
    monthly_returns = monthly.pct_change().dropna() * 100

    result = []
    for date, ret in monthly_returns.items():
        result.append({"year": date.year, "month": date.month, "return": round(ret, 2)})

    return result


def load_risk_kpi_scores() -> pd.Series:
    """Load Consolidated Risk Scores from cached risk_kpi.json."""
    path = Path(__file__).parent / "dashboard" / "risk_kpi.json"
    if not path.exists():
        logger.warning(f"risk_kpi.json not found at {path}, cannot run Ult-RiskKPI portfolio simulation")
        return pd.Series(dtype=float)
    try:
        with open(path) as f:
            data = json.load(f)
        dates = pd.to_datetime(data["dates"])
        scores = pd.Series(data["composite"], index=dates)
        return scores
    except Exception as e:
        logger.error(f"Failed to parse risk_kpi.json: {e}")
        return pd.Series(dtype=float)


# ---------------------------------------------------------------------------
# Main backtest runner
# ---------------------------------------------------------------------------

def run_backtest(config_path: str, start_date: str, end_date: str) -> dict:
    """
    Run the full backtest pipeline.

    Args:
        config_path: path to YAML config file
        start_date: backtest start date (YYYY-MM-DD)
        end_date: backtest end date (YYYY-MM-DD)

    Returns:
        dict with all results for the dashboard
    """
    # Load config
    with open(config_path) as f:
        config = yaml.safe_load(f)

    etf_configs = config["etfs"]
    benchmark_configs = config["benchmarks"]

    results = {
        "meta": {
            "start_date": start_date,
            "end_date": end_date,
            "generated_at": datetime.now().isoformat(),
            "starting_value": 10000,
        },
        "etfs": [],
        "benchmarks": [],
    }

    # Collect all tickers we need
    all_universe_tickers = {}
    for etf_cfg in etf_configs:
        universe_name = etf_cfg["universe"]
        if universe_name not in all_universe_tickers:
            tickers = get_universe(universe_name)
            all_universe_tickers[universe_name] = tickers
            logger.info(f"Universe '{universe_name}': {len(tickers)} tickers")
            
    results["ticker_names"] = get_all_ticker_names()

    benchmark_tickers = [b["ticker"] for b in benchmark_configs]

    # Fetch all price data (including ^VIX)
    all_tickers = list(set(
        sum(all_universe_tickers.values(), []) + benchmark_tickers + ["^VIX"]
    ))
    logger.info(f"Total unique tickers to download: {len(all_tickers)}")

    # Extend start date by 400 days to have data for trailing indicators (Momentum, Low Vol, etc.)
    fetch_start = (pd.Timestamp(start_date) - timedelta(days=400)).strftime("%Y-%m-%d")
    prices, dividends = fetch_prices_and_dividends(all_tickers, fetch_start, end_date)
    logger.info(f"Price data: {len(prices)} trading days, {len(prices.columns)} tickers")

    # Fetch shares outstanding for market cap ranking
    universe_tickers_flat = list(set(sum(all_universe_tickers.values(), [])))
    available_tickers = [t for t in universe_tickers_flat if t in prices.columns]
    shares = fetch_shares_outstanding(available_tickers)

    # Fetch FRED macro indicators
    macro = fetch_macro_data(fetch_start, end_date)

    # Load cached Risk KPI scores
    risk_kpi_scores = load_risk_kpi_scores()

    # Extract VIX and SPY benchmarks if available
    vix_prices = prices["^VIX"] if "^VIX" in prices.columns else None
    spy_prices = prices["SPY"] if "SPY" in prices.columns else None

    # Rebalance dates will be determined per ETF based on its frequency

    # Run each hypothetical ETF
    for etf_cfg in etf_configs:
        name = etf_cfg["name"]
        universe_name = etf_cfg["universe"]
        logger.info(f"\n{'='*60}")
        logger.info(f"Simulating: {name}")
        logger.info(f"{'='*60}")

        universe_tickers = all_universe_tickers[universe_name]
        # Filter prices to this universe
        available = [t for t in universe_tickers if t in prices.columns]
        universe_prices = prices[available]

        freq = etf_cfg.get("rebalance_frequency", "monthly")
        # Rebalance dates only within actual backtest range
        all_rebalance_dates = get_rebalance_dates(prices.index, freq)
        rebalance_dates = [d for d in all_rebalance_dates if pd.Timestamp(start_date) <= d <= pd.Timestamp(end_date)]
        logger.info(f"Rebalance dates ({freq}): {len(rebalance_dates)}")

        portfolio_values, holdings_log = simulate_portfolio(
            prices=universe_prices,
            shares=shares,
            rebalance_dates=rebalance_dates,
            selection_rule=etf_cfg["selection_rule"],
            n=etf_cfg["n"],
            weighting=etf_cfg["weighting"],
            dividends=dividends[available] if dividends is not None else None,
            macro=macro,
            vix_prices=vix_prices,
            benchmark_prices=spy_prices,
            risk_kpi_scores=risk_kpi_scores,
        )

        # Trim to actual backtest range
        portfolio_values = portfolio_values.loc[start_date:end_date].dropna()
        metrics = compute_metrics(portfolio_values)
        drawdown = compute_drawdown_series(portfolio_values)
        monthly_returns = compute_monthly_returns(portfolio_values)

        # Downsample timeseries for JSON (daily is too much data)
        ts_dates = portfolio_values.index.strftime("%Y-%m-%d").tolist()
        ts_values = portfolio_values.round(2).tolist()

        dd_values = drawdown.round(2).tolist()

        results["etfs"].append({
            "name": name,
            "description": etf_cfg["description"],
            "universe": universe_name,
            "n": etf_cfg["n"],
            "weighting": etf_cfg["weighting"],
            "metrics": metrics,
            "timeseries": {"dates": ts_dates, "values": ts_values},
            "drawdown": {"dates": ts_dates, "values": dd_values},
            "monthly_returns": monthly_returns,
            "holdings_log": holdings_log,
        })

        logger.info(f"  Total Return: {metrics['total_return_pct']}%")
        logger.info(f"  Annualized: {metrics['annualized_return_pct']}%")
        logger.info(f"  Max Drawdown: {metrics['max_drawdown_pct']}%")
        logger.info(f"  Sharpe: {metrics['sharpe_ratio']}")

    # Run benchmarks
    for bench_cfg in benchmark_configs:
        ticker = bench_cfg["ticker"]
        name = bench_cfg["name"]
        logger.info(f"\nBenchmark: {name} ({ticker})")

        if ticker not in prices.columns:
            logger.warning(f"  No data for benchmark {ticker}, skipping")
            continue

        bench_values = simulate_benchmark(prices[ticker])
        # Trim to actual backtest range
        bench_values = bench_values.loc[start_date:end_date].dropna()
        metrics = compute_metrics(bench_values)
        drawdown = compute_drawdown_series(bench_values)
        monthly_returns = compute_monthly_returns(bench_values)

        ts_dates = bench_values.index.strftime("%Y-%m-%d").tolist()
        ts_values = bench_values.round(2).tolist()
        dd_values = drawdown.round(2).tolist()

        results["benchmarks"].append({
            "name": name,
            "ticker": ticker,
            "metrics": metrics,
            "timeseries": {"dates": ts_dates, "values": ts_values},
            "drawdown": {"dates": ts_dates, "values": dd_values},
            "monthly_returns": monthly_returns,
        })

        logger.info(f"  Total Return: {metrics['total_return_pct']}%")
        logger.info(f"  Annualized: {metrics['annualized_return_pct']}%")

    return results
