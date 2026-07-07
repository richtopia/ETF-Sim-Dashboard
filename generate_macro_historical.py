import pandas as pd
import numpy as np
import yfinance as yf
import requests
import io
import json
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("generate_macro_historical")

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def fetch_fred_csv(series_id: str) -> pd.Series:
    """Fetch daily or monthly series from FRED CSV endpoint with caching."""
    cache_file = CACHE_DIR / f"{series_id}.csv"
    if cache_file.exists():
        logger.info(f"Loading cached FRED series {series_id}")
        df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
        return df[series_id]

    logger.info(f"Downloading FRED series {series_id}...")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text), index_col=0, parse_dates=True)
        # Clean data (replace '.' with NaN)
        df[series_id] = pd.to_numeric(df[series_id].replace(".", np.nan), errors="coerce")
        df = df.dropna()
        df.to_csv(cache_file)
        return df[series_id]
    except Exception as e:
        logger.error(f"Failed to fetch FRED series {series_id}: {e}")
        return pd.Series(dtype=float)


def fetch_gold_historical() -> pd.Series:
    """Fetch monthly gold prices from raw GitHub datasets source with caching."""
    cache_file = CACHE_DIR / "gold_historical.csv"
    if cache_file.exists():
        logger.info("Loading cached gold_historical.csv")
        df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
        return df["Price"]
        
    logger.info("Downloading historical monthly gold prices from GitHub...")
    url = "https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(response.text)
        df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
        return df["Price"]
    except Exception as e:
        logger.error(f"Failed to fetch gold prices from GitHub: {e}")
        return pd.Series(dtype=float)


def get_yf_series(ticker: str, start: str, end: str) -> pd.Series:
    """Fetch a clean 1D Close price Series for a ticker."""
    logger.info(f"Downloading {ticker} close prices...")
    data = yf.download(ticker, start=start, end=end, progress=False)
    if data.empty:
        return pd.Series(dtype=float)
        
    if "Close" in data.columns:
        res = data["Close"]
        if isinstance(res, pd.DataFrame):
            res = res.iloc[:, 0]
        return res
    elif isinstance(data.columns, pd.MultiIndex):
        # Handle MultiIndex
        for col in data.columns:
            if col[0] == "Close":
                res = data[col]
                if isinstance(res, pd.DataFrame):
                    res = res.iloc[:, 0]
                return res
    # Fallback to the first column
    res = data.iloc[:, 0]
    return res


def main():
    start_date = "1954-07-01"
    end_date = datetime.today().strftime("%Y-%m-%d")

    logger.info(f"Generating historical backtest from {start_date} to {end_date}...")

    # 1. Fetch FRED macro variables
    dff = fetch_fred_csv("DFF")                 # Daily Fed Funds Rate (starts 1954)
    dtb3 = fetch_fred_csv("DTB3")               # Daily 3-Month T-Bill Yield (starts 1954)
    dgs10 = fetch_fred_csv("DGS10")             # Daily 10-Year Treasury Yield (starts 1962)
    unrate = fetch_fred_csv("UNRATE")           # Monthly Unemployment Rate (starts 1948)

    # 2. Fetch Gold Historical series
    gold_monthly = fetch_gold_historical()

    # 3. Download Equity Indices
    sp500 = get_yf_series("^GSPC", start_date, end_date)
    nasdaq = get_yf_series("^IXIC", "1971-02-05", end_date)
    dow = get_yf_series("^DJI", "1985-01-29", end_date)

    # Align to a common daily index (business days)
    all_dates = pd.date_range(start=start_date, end=end_date, freq="B")
    
    # Reindex series
    sp500 = sp500.reindex(all_dates).ffill()
    nasdaq = nasdaq.reindex(all_dates).ffill()
    dow = dow.reindex(all_dates).ffill()
    
    dff = dff.reindex(all_dates).ffill()
    dtb3 = dtb3.reindex(all_dates).ffill()
    dgs10 = dgs10.reindex(all_dates).ffill()
    gold_monthly = gold_monthly.reindex(all_dates).ffill().bfill()

    # 4. Build Gold Spot Index (fixed at $35/oz before 1968-12-30)
    logger.info("Building Gold return index...")
    gold_prices = gold_monthly.copy()
    gold_prices.loc[gold_prices.index < "1968-12-30"] = 35.0
    gold_returns = gold_prices.pct_change().fillna(0)
    gold_index = 100 * (1 + gold_returns).cumprod()

    # 5. Build U.S. Treasury Bond Return Index
    logger.info("Building Treasury Bond return index...")
    treasury_returns = pd.Series(0.0, index=all_dates)
    
    for i in range(1, len(all_dates)):
        prev_date = all_dates[i - 1]
        date = all_dates[i]
        
        y_10_prev = dgs10.loc[prev_date]
        y_10 = dgs10.loc[date]
        y_3_prev = dtb3.loc[prev_date]
        
        # If 10-Year yield is available, use a duration-approximated bond return model (10-Yr Treasury Bond)
        if pd.notna(y_10) and pd.notna(y_10_prev):
            duration = 7.0
            y_prev_val = y_10_prev / 100.0
            y_val = y_10 / 100.0
            ret = -duration * (y_val - y_prev_val) + (y_prev_val / 252.0)
        # Else, fall back to T-Bill daily interest rate
        elif pd.notna(y_3_prev):
            ret = (y_3_prev / 100.0) / 252.0
        # Else, fall back to Fed Funds Rate
        else:
            y_fed = dff.loc[prev_date]
            ret = ((y_fed if pd.notna(y_fed) else 2.0) / 100.0) / 252.0
            
        treasury_returns.iloc[i] = ret

    treasury_index = 100 * (1 + treasury_returns).cumprod()

    # 6. Build Dynamic Equal-Weighted Equity Index
    logger.info("Building Dynamic Equity Index...")
    equity_returns = pd.Series(0.0, index=all_dates)
    
    sp500_ret = sp500.pct_change().fillna(0)
    nasdaq_ret = nasdaq.pct_change().fillna(0)
    dow_ret = dow.pct_change().fillna(0)
    
    for i in range(1, len(all_dates)):
        date = all_dates[i]
        rets = []
        
        # Add S&P 500
        rets.append(sp500_ret.loc[date])
        
        # Add Nasdaq if it exists (Feb 1971 onwards)
        if date >= pd.Timestamp("1971-02-08"):
            rets.append(nasdaq_ret.loc[date])
            
        # Add Dow Jones if it exists (Jan 1985 onwards)
        if date >= pd.Timestamp("1985-02-01"):
            rets.append(dow_ret.loc[date])
            
        equity_returns.iloc[i] = np.mean(rets)
        
    equity_index = 100 * (1 + equity_returns).cumprod()

    # 7. Calculate Sahm Rule (using monthly UNRATE)
    logger.info("Computing Sahm Rule series...")
    sahm_series = pd.Series(0.0, index=all_dates)
    unrate_monthly = unrate.resample("MS").first().ffill()
    
    # Calculate 3-month moving average of UNRATE
    unrate_ma = unrate_monthly.rolling(3).mean()
    # Calculate 12-month low of that moving average
    unrate_min = unrate_ma.rolling(12).min()
    sahm_monthly = unrate_ma - unrate_min
    
    # Align monthly Sahm to daily series
    for i, date in enumerate(all_dates):
        slice_s = sahm_monthly.loc[:date]
        if not slice_s.empty:
            sahm_series.iloc[i] = slice_s.iloc[-1]

    # 8. Compute indicators for backtest
    logger.info("Computing macro signal states...")
    
    # Fed Funds 12M Change
    dff_monthly = dff.resample("ME").last().ffill()
    dff_12m_change = dff_monthly.diff(12)
    
    # S&P 500 200 SMA
    sp500_sma200 = sp500.rolling(200).mean()
    
    # 9. Simulate Switching Portfolios
    portfolio_value_sma_gold = 100.0
    portfolio_value_sma_treas = 100.0
    portfolio_value_macro_gold = 100.0
    portfolio_value_macro_treas = 100.0
    
    port_sma_gold_series = [100.0]
    port_sma_treas_series = [100.0]
    port_macro_gold_series = [100.0]
    port_macro_treas_series = [100.0]
    
    macro_score_series = [0.0]
    unemp_state_series = [0.0]
    fed_state_series = [0.0]
    sma_state_series = [0.0]
    
    # Skip first day
    for i in range(1, len(all_dates)):
        date = all_dates[i]
        prev_date = all_dates[i - 1]
        
        # Calculate daily asset returns
        ret_eq = equity_returns.iloc[i]
        ret_gold = gold_returns.iloc[i]
        ret_treas = treasury_returns.iloc[i]
        
        # Determine 200 SMA state (based on previous day to avoid look-ahead)
        sp = float(sp500.loc[prev_date])
        sma = float(sp500_sma200.loc[prev_date]) if pd.notna(sp500_sma200.loc[prev_date]) else np.nan
        below_sma = False
        if pd.notna(sp) and pd.notna(sma):
            below_sma = sp < sma
            
        # Determine Unemployment State (Sahm Rule >= 0.50%)
        sahm = float(sahm_series.loc[prev_date])
        unemp_recession = sahm >= 0.50
        
        # Determine Fed Funds Rate State (12M Change >= 1.00% hike)
        fed_change = 0.0
        fed_slice = dff_12m_change.loc[:prev_date]
        if not fed_slice.empty:
            fed_change = float(fed_slice.iloc[-1])
        fed_hiking = fed_change >= 1.00
        
        # Compute Macro Score (3-Factor)
        score = 0.0
        if below_sma:
            score += 30.0
        if unemp_recession:
            score += 35.0
        if fed_hiking:
            score += 35.0
            
        # Record indicator states (as 0 or 100 for UI scaling)
        sma_state_series.append(100.0 if below_sma else 0.0)
        unemp_state_series.append(100.0 if unemp_recession else 0.0)
        fed_state_series.append(100.0 if fed_hiking else 0.0)
        macro_score_series.append(score)
        
        # Simulate Portfolios (monthly rebalancing constraint)
        is_rebalance = (date.month != prev_date.month) or (i == 1)
        
        if is_rebalance:
            w_eq_sma = 0.0 if below_sma else 1.0
            w_safe_sma = 1.0 - w_eq_sma
            
            w_eq_macro = 0.0 if score >= 50.0 else 1.0
            w_safe_macro = 1.0 - w_eq_macro
            
        # Accumulate returns
        portfolio_value_sma_gold *= (1 + (w_eq_sma * ret_eq + w_safe_sma * ret_gold))
        portfolio_value_sma_treas *= (1 + (w_eq_sma * ret_eq + w_safe_sma * ret_treas))
        portfolio_value_macro_gold *= (1 + (w_eq_macro * ret_eq + w_safe_macro * ret_gold))
        portfolio_value_macro_treas *= (1 + (w_eq_macro * ret_eq + w_safe_macro * ret_treas))
        
        port_sma_gold_series.append(portfolio_value_sma_gold)
        port_sma_treas_series.append(portfolio_value_sma_treas)
        port_macro_gold_series.append(portfolio_value_macro_gold)
        port_macro_treas_series.append(portfolio_value_macro_treas)

    # 9. Format output payload
    logger.info("Writing historical backtest payload...")
    dates_str = [d.strftime("%Y-%m-%d") for d in all_dates]
    
    payload = {
        "dates": dates_str,
        "assets": {
            "equity": equity_index.tolist(),
            "gold": gold_index.tolist(),
            "treasury": treasury_index.tolist()
        },
        "portfolios": {
            "sma_gold": port_sma_gold_series,
            "sma_treas": port_sma_treas_series,
            "macro_gold": port_macro_gold_series,
            "macro_treas": port_macro_treas_series
        },
        "indicators": {
            "macro_score": macro_score_series,
            "sma_state": sma_state_series,
            "unemp_state": unemp_state_series,
            "fed_state": fed_state_series
        }
    }
    
    output_file = Path(__file__).parent / "dashboard" / "macro_historical.json"
    with open(output_file, "w") as f:
        json.dump(payload, f)
        
    logger.info(f"Compilation complete! File size: {output_file.stat().st_size / 1024.0:.2f} KB")


if __name__ == "__main__":
    main()
