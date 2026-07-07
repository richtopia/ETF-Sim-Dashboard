"""
data_loader.py — Downloads and caches S&P 500 constituent and price data.

Data Sources:
  - S&P 500 constituents (1996–present): fja05680/sp500 on GitHub
  - Historical adjusted close prices: Yahoo Finance via yfinance
  - Shares outstanding (current snapshot): yfinance Ticker.info
  - Benchmark (^GSPC): Yahoo Finance via yfinance
"""

import os
import io
import time
import logging
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pandas as pd
import numpy as np
import yfinance as yf
import pandas_datareader.data as web

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PRICES_DIR = os.path.join(DATA_DIR, "prices")
CONSTITUENTS_CSV = os.path.join(DATA_DIR, "sp500_constituents.csv")
SHARES_CSV = os.path.join(DATA_DIR, "shares_outstanding.csv")
BENCHMARK_PARQUET = os.path.join(DATA_DIR, "benchmark.parquet")
DIVIDENDS_PARQUET = os.path.join(DATA_DIR, "dividends.parquet")
MACRO_PARQUET = os.path.join(DATA_DIR, "macro.parquet")

# GitHub raw URL for the fja05680/sp500 historical components file
CONSTITUENTS_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes(01-17-2026).csv"
)
# Fallback: try the generic name
CONSTITUENTS_URL_FALLBACK = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes.csv"
)


def ensure_dirs():
    """Create data directories if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PRICES_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Constituents
# ---------------------------------------------------------------------------

def download_constituents(refresh: bool = False) -> pd.DataFrame:
    """
    Download the S&P 500 historical constituents CSV from GitHub.

    Returns a DataFrame with columns: ['date', 'tickers']
    where 'tickers' is a comma-separated string of ticker symbols.
    """
    ensure_dirs()

    if os.path.exists(CONSTITUENTS_CSV) and not refresh:
        logger.info("Loading cached constituents from %s", CONSTITUENTS_CSV)
        df = pd.read_csv(CONSTITUENTS_CSV, parse_dates=["date"])
        return df

    logger.info("Downloading S&P 500 constituents from GitHub...")
    resp = requests.get(CONSTITUENTS_URL, timeout=30)
    if resp.status_code != 200:
        logger.warning("Primary URL failed (%s), trying fallback...", resp.status_code)
        resp = requests.get(CONSTITUENTS_URL_FALLBACK, timeout=30)
        resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))

    # Normalise column names
    df.columns = [c.strip().lower() for c in df.columns]
    if "date" not in df.columns:
        # The file sometimes uses the first column as the date index
        df = df.reset_index()
        df.columns = ["date"] + list(df.columns[1:])

    # The CSV typically has 'date' and 'tickers' columns.
    # Ensure the tickers column exists — it might be named differently.
    ticker_col = [c for c in df.columns if c != "date"][0]
    df = df.rename(columns={ticker_col: "tickers"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    df.to_csv(CONSTITUENTS_CSV, index=False)
    logger.info("Saved constituents to %s (%d rows)", CONSTITUENTS_CSV, len(df))
    return df


def get_all_tickers(constituents_df: pd.DataFrame) -> list[str]:
    """
    Extract the deduplicated set of all tickers that ever appeared
    in the S&P 500 constituent lists.
    """
    all_tickers = set()
    for tickers_str in constituents_df["tickers"].dropna():
        for t in str(tickers_str).split(","):
            t = t.strip()
            if t:
                all_tickers.add(t)
    return sorted(all_tickers)


def get_tickers_in_range(
    constituents_df: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> list[str]:
    """
    Extract tickers that appear in constituent lists within the given
    date range. This avoids downloading data for tickers that are only
    relevant outside our backtest window.
    """
    s = pd.Timestamp(start_date)
    e = pd.Timestamp(end_date)

    # Include one year before start_date so momentum has lookback data
    lookback_start = s - pd.Timedelta(days=400)

    mask = (constituents_df["date"] >= lookback_start) & (constituents_df["date"] <= e)
    relevant = constituents_df.loc[mask]

    tickers = set()
    for tickers_str in relevant["tickers"].dropna():
        for t in str(tickers_str).split(","):
            t = t.strip()
            if t:
                tickers.add(t)

    logger.info(
        "Found %d unique tickers in date range %s to %s",
        len(tickers), lookback_start.date(), e.date(),
    )
    return sorted(tickers)


def get_constituents_on_date(
    constituents_df: pd.DataFrame, target_date: pd.Timestamp
) -> list[str]:
    """
    Return the list of S&P 500 tickers for the given date.
    Uses the most recent constituent snapshot on or before target_date.
    """
    mask = constituents_df["date"] <= target_date
    if not mask.any():
        return []
    row = constituents_df.loc[mask].iloc[-1]
    tickers = [t.strip() for t in str(row["tickers"]).split(",") if t.strip()]
    return tickers


# ---------------------------------------------------------------------------
# Price Data
# ---------------------------------------------------------------------------

def download_prices(
    tickers: list[str],
    start_date: str = "1995-01-01",
    end_date: str | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """
    Download adjusted close prices for all given tickers via yfinance.
    Caches as a single parquet file.  Returns a DataFrame indexed by date
    with tickers as columns.
    """
    ensure_dirs()
    prices_file = os.path.join(PRICES_DIR, "all_adj_close.parquet")

    if os.path.exists(prices_file) and not refresh:
        logger.info("Loading cached prices from %s", prices_file)
        return pd.read_parquet(prices_file)

    if end_date is None:
        end_date = dt.date.today().isoformat()

    # Use a lookback period for momentum calculation
    price_start = (pd.Timestamp(start_date) - pd.Timedelta(days=400)).strftime("%Y-%m-%d")

    logger.info(
        "Downloading price data for %d tickers from %s to %s ...",
        len(tickers), price_start, end_date,
    )

    # Download in batches to avoid yfinance timeouts
    batch_size = 100
    all_frames = []
    failed_tickers = []

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        batch_str = " ".join(batch)
        batch_num = i // batch_size + 1
        total_batches = (len(tickers) + batch_size - 1) // batch_size
        logger.info(
            "  Batch %d/%d  (%d tickers)",
            batch_num, total_batches, len(batch),
        )
        try:
            data = yf.download(
                batch_str,
                start=price_start,
                end=end_date,
                auto_adjust=True,
                progress=False,
                threads=True,
                timeout=30,
            )
            if data.empty:
                failed_tickers.extend(batch)
                continue

            # yfinance returns MultiIndex columns (Price, Ticker) for multiple tickers
            if isinstance(data.columns, pd.MultiIndex):
                close = data["Close"]
            else:
                # Single ticker case
                close = data[["Close"]].rename(columns={"Close": batch[0]})

            all_frames.append(close)
        except Exception as e:
            logger.warning("Failed to download batch %d: %s", batch_num, e)
            failed_tickers.extend(batch)

        time.sleep(0.25)  # Be polite to Yahoo

    if not all_frames:
        raise RuntimeError("Failed to download any price data!")

    prices = pd.concat(all_frames, axis=1)
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index()

    # Drop columns that are entirely NaN
    prices = prices.dropna(axis=1, how="all")

    # --- Data quality filter ---
    # Detect and remove tickers with corrupted price data.
    # When a ticker is recycled (old company delisted, new company reuses
    # the same symbol), yfinance sometimes returns a spliced series that
    # jumps from e.g. $15 to $22,900 overnight.  No real S&P 500 stock
    # has a >500% single-day return, so we use that as a filter.
    daily_returns = prices.pct_change(fill_method=None)
    max_abs_return = daily_returns.abs().max()
    bad_tickers = max_abs_return[max_abs_return > 5.0].index.tolist()  # >500%

    if bad_tickers:
        logger.warning(
            "Removing %d tickers with corrupted price data (>500%% daily move): %s",
            len(bad_tickers),
            ", ".join(bad_tickers[:20]) + ("..." if len(bad_tickers) > 20 else ""),
        )
        prices = prices.drop(columns=bad_tickers)

    if failed_tickers:
        logger.warning(
            "%d tickers failed to download: %s",
            len(failed_tickers),
            ", ".join(failed_tickers[:20]) + ("..." if len(failed_tickers) > 20 else ""),
        )

    prices.to_parquet(prices_file)
    logger.info("Saved prices to %s  (%d tickers, %d days)", prices_file, prices.shape[1], prices.shape[0])
    return prices


# ---------------------------------------------------------------------------
# Shares Outstanding (for market-cap estimation)
# ---------------------------------------------------------------------------

def _fetch_shares_for_ticker(ticker: str) -> tuple[str, float]:
    """Fetch shares outstanding for a single ticker. Returns (ticker, shares)."""
    try:
        info = yf.Ticker(ticker).fast_info
        so = getattr(info, "shares", None)
        if so is None or so == 0:
            mc = getattr(info, "market_cap", None)
            lp = getattr(info, "last_price", None)
            if mc and lp and lp > 0:
                so = mc / lp
            else:
                so = np.nan
        return (ticker, so)
    except Exception:
        return (ticker, np.nan)


def download_shares_outstanding(
    tickers: list[str], refresh: bool = False
) -> pd.Series:
    """
    Fetch current shares outstanding for each ticker from yfinance.
    Uses threading for speed.  Returns a Series indexed by ticker symbol.
    """
    ensure_dirs()

    if os.path.exists(SHARES_CSV) and not refresh:
        logger.info("Loading cached shares outstanding from %s", SHARES_CSV)
        s = pd.read_csv(SHARES_CSV, index_col=0)
        return s.iloc[:, 0]

    logger.info("Fetching shares outstanding for %d tickers (threaded)...", len(tickers))
    shares = {}
    completed = 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(_fetch_shares_for_ticker, t): t
            for t in tickers
        }
        for future in as_completed(futures):
            ticker, so = future.result()
            shares[ticker] = so
            completed += 1
            if completed % 100 == 0:
                logger.info("  %d / %d tickers processed", completed, len(tickers))

    series = pd.Series(shares, name="shares_outstanding")
    series.to_csv(SHARES_CSV, header=True)
    logger.info("Saved shares outstanding to %s", SHARES_CSV)
    return series


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def download_benchmark(
    start_date: str = "1995-01-01",
    end_date: str | None = None,
    refresh: bool = False,
) -> pd.Series:
    """
    Download S&P 500 index (^GSPC) adjusted close as the benchmark.
    """
    ensure_dirs()

    if os.path.exists(BENCHMARK_PARQUET) and not refresh:
        logger.info("Loading cached benchmark from %s", BENCHMARK_PARQUET)
        return pd.read_parquet(BENCHMARK_PARQUET).squeeze()

    if end_date is None:
        end_date = dt.date.today().isoformat()

    logger.info("Downloading S&P 500 benchmark (^GSPC)...")
    data = yf.download("^GSPC", start=start_date, end=end_date, auto_adjust=True, progress=False)
    bench = data["Close"].squeeze()
    bench.name = "SP500"
    bench.to_frame().to_parquet(BENCHMARK_PARQUET)
    logger.info("Saved benchmark to %s", BENCHMARK_PARQUET)
    return bench


# ---------------------------------------------------------------------------
# Macro (FRED) Data
# ---------------------------------------------------------------------------

def download_fred_data(start_date: str = "1996-01-01", end_date: str | None = None, refresh: bool = False) -> pd.DataFrame:
    """Download macroeconomic datasets from FRED."""
    ensure_dirs()
    if os.path.exists(MACRO_PARQUET) and not refresh:
        logger.info("Loading cached macro data from %s", MACRO_PARQUET)
        return pd.read_parquet(MACRO_PARQUET)
    
    if end_date is None:
        end_date = dt.date.today().isoformat()
        
    logger.info("Downloading FRED macro data...")
    # T10Y2Y: 10-Year Treasury Constant Maturity Minus 2-Year Treasury Constant Maturity
    df = web.DataReader(['T10Y2Y'], 'fred', start_date, end_date)
    # Forward fill weekends/holidays so daily checks work
    df = df.ffill()
    df.to_parquet(MACRO_PARQUET)
    logger.info("Saved macro data to %s", MACRO_PARQUET)
    return df


# ---------------------------------------------------------------------------
# Dividends
# ---------------------------------------------------------------------------

def _fetch_dividends_for_ticker(ticker: str) -> tuple[str, pd.Series]:
    try:
        t = yf.Ticker(ticker)
        div = t.dividends
        if div is not None and not div.empty:
            # Normalize dates to avoid time-of-day mismatch
            div.index = pd.to_datetime(div.index, utc=True).tz_localize(None).normalize()
            div.name = ticker
            
            # Ensure dividends are float (sometimes yfinance returns str like "0.01 USD")
            if div.dtype == object:
                div = pd.to_numeric(div.astype(str).str.extract(r'([+\-]?\d+(?:\.\d+)?)', expand=False), errors='coerce')
                div = div.dropna()
                
            return ticker, div
    except Exception as e:
        logger.debug("Failed to get dividends for %s: %s", ticker, e)
    return ticker, pd.Series(dtype=float)

def download_dividends(tickers: list[str], refresh: bool = False) -> pd.DataFrame:
    ensure_dirs()
    if os.path.exists(DIVIDENDS_PARQUET) and not refresh:
        logger.info("Loading cached dividends from %s", DIVIDENDS_PARQUET)
        return pd.read_parquet(DIVIDENDS_PARQUET)
        
    logger.info("Fetching dividend history for %d tickers (threaded)...", len(tickers))
    div_series = []
    completed = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_dividends_for_ticker, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, div = future.result()
            if not div.empty:
                div_series.append(div.to_frame(name=ticker))
            completed += 1
            if completed % 100 == 0:
                logger.info("  %d / %d dividend histories processed", completed, len(tickers))
                
    if not div_series:
        logger.warning("No dividend data found for any tickers!")
        df = pd.DataFrame()
    else:
        df = pd.concat(div_series, axis=1)
        # Group by index in case of duplicate dates
        df = df.groupby(df.index).sum()
        
    df.to_parquet(DIVIDENDS_PARQUET)
    logger.info("Saved dividends data to %s", DIVIDENDS_PARQUET)
    return df


# ---------------------------------------------------------------------------
# Convenience: load everything
# ---------------------------------------------------------------------------

def load_all_data(
    start_date: str = "1996-01-01",
    end_date: str | None = None,
    refresh: bool = False,
) -> dict:
    """
    Download / load all required datasets and return as a dict.

    Returns:
        {
            "constituents": pd.DataFrame,
            "prices": pd.DataFrame,
            "shares_outstanding": pd.Series,
            "benchmark": pd.Series,
        }
    """
    constituents = download_constituents(refresh=refresh)

    # Only download tickers relevant to our date range (much faster)
    if end_date is None:
        end_date = dt.date.today().isoformat()
    relevant_tickers = get_tickers_in_range(constituents, start_date, end_date)

    prices = download_prices(relevant_tickers, start_date=start_date, end_date=end_date, refresh=refresh)

    # Only fetch shares and dividends for tickers that have price data (skip delisted)
    tickers_with_prices = list(prices.columns)
    shares = download_shares_outstanding(tickers_with_prices, refresh=refresh)
    benchmark = download_benchmark(start_date=start_date, end_date=end_date, refresh=refresh)
    
    macro = download_fred_data(start_date=start_date, end_date=end_date, refresh=refresh)
    dividends = download_dividends(tickers_with_prices, refresh=refresh)

    return {
        "constituents": constituents,
        "prices": prices,
        "shares_outstanding": shares,
        "benchmark": benchmark,
        "macro": macro,
        "dividends": dividends,
    }
