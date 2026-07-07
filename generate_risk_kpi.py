import os
import io
import json
import logging
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DASHBOARD_DIR = Path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard")
OUTPUT_PATH = os.path.join(DASHBOARD_DIR, "risk_kpi.json")

def download_fred(series_id):
    logger.info(f"Downloading {series_id} from FRED...")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=45)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text), index_col=0, parse_dates=True)
            df = df.replace(".", np.nan)
            df = df.astype(float)
            return df
        except Exception as e:
            if attempt == 2:
                raise e
            logger.warning(f"Attempt {attempt+1} failed for {series_id}, retrying in 2s: {e}")
            import time
            time.sleep(2)

def main():
    start_date = "2003-01-01"  # Fetch from 2003 to calculate 12-month changes for 2004
    end_date = datetime.now().strftime("%Y-%m-%d")

    # 1. Download FRED Series
    try:
        t10y2y = download_fred("T10Y2Y")
        sahm = download_fred("SAHMREALTIME")
        dff = download_fred("DFF")
        wti = download_fred("DCOILWTICO")
        
        # Download Trade Weighted USD Index Data
        dtwexbgs = download_fred("DTWEXBGS")       # Active Broad Index (starts 2006)
        dtwexm = download_fred("DTWEXM")           # Discontinued Major Currencies Index (starts 1973)
    except Exception as e:
        logger.error(f"Error downloading from FRED: {e}")
        return

    # 2. Download ^MOVE and SPY from Yahoo Finance
    logger.info("Downloading ^MOVE and SPY from Yahoo Finance...")
    try:
        move_df = yf.download("^MOVE", start=start_date, end=end_date, progress=False)
        if move_df.empty:
            raise RuntimeError("Downloaded empty MOVE DataFrame")
        if isinstance(move_df.columns, pd.MultiIndex):
            move = move_df["Close"].squeeze()
        else:
            move = move_df["Close"]
        move = move.to_frame(name="MOVE")

        spy_df = yf.download("^GSPC", start=start_date, end=end_date, progress=False)
        if spy_df.empty:
            raise RuntimeError("Downloaded empty S&P 500 Index DataFrame")
        if isinstance(spy_df.columns, pd.MultiIndex):
            spy = spy_df["Close"].squeeze()
        else:
            spy = spy_df["Close"]
        spy = spy.to_frame(name="SPY")
    except Exception as e:
        logger.error(f"Error downloading MOVE/SPY: {e}")
        return

    # 3. Align all series onto a daily index
    logger.info("Aligning data indices...")
    idx = pd.date_range(start=start_date, end=end_date, freq="D")
    
    # Forward fill daily rates/indexes to cover weekends/gaps
    t10y2y = t10y2y.reindex(idx).ffill().bfill()
    sahm = sahm.reindex(idx).ffill().bfill() # Sahm is monthly, ffill makes it daily step
    dff = dff.reindex(idx).ffill().bfill()
    wti = wti.reindex(idx).ffill().bfill()
    move = move.reindex(idx).ffill().bfill()
    spy = spy.reindex(idx).ffill().bfill()
    
    # Stitch Trade Weighted USD Index back to 2003
    dtwexbgs = dtwexbgs.reindex(idx)
    dtwexm = dtwexm.reindex(idx)
    
    # Scale DTWEXM to match DTWEXBGS at first overlapping point in 2006
    common_dates = dtwexbgs.dropna().index.intersection(dtwexm.dropna().index)
    if not common_dates.empty:
        align_date = common_dates[0]
        scale_factor = dtwexbgs.loc[align_date]["DTWEXBGS"] / dtwexm.loc[align_date]["DTWEXM"]
        dtwexm_scaled = dtwexm * scale_factor
    else:
        dtwexm_scaled = dtwexm * 1.18
        
    usd_stitched = pd.DataFrame(index=idx, columns=["USD"])
    for date in idx:
        if date >= pd.Timestamp("2006-01-02"):
            val = dtwexbgs.loc[date]["DTWEXBGS"]
            if pd.isna(val):
                val = dtwexbgs.loc[:date].ffill().iloc[-1]["DTWEXBGS"] if not dtwexbgs.loc[:date].dropna().empty else 100.0
            usd_stitched.loc[date, "USD"] = val
        else:
            val = dtwexm_scaled.loc[date]["DTWEXM"]
            if pd.isna(val):
                val = dtwexm_scaled.loc[:date].ffill().iloc[-1]["DTWEXM"] if not dtwexm_scaled.loc[:date].dropna().empty else 100.0
            usd_stitched.loc[date, "USD"] = val
            
    usd_stitched = usd_stitched.ffill().bfill()

    # Create merged DataFrame
    df = pd.DataFrame(index=idx)
    df["T10Y2Y"] = t10y2y["T10Y2Y"]
    df["SAHM"] = sahm["SAHMREALTIME"]
    df["DFF"] = dff["DFF"]
    df["WTI"] = wti["DCOILWTICO"]
    df["MOVE"] = move["MOVE"]
    df["SPY"] = spy["SPY"]
    df["USD"] = usd_stitched["USD"].astype(float)

    # 4. Calculate 12-month changes and 200 SMA
    logger.info("Computing sub-component metrics...")
    df["SPY_200SMA"] = df["SPY"].rolling(window=200).mean()
    df["USD_200SMA"] = df["USD"].rolling(window=200).mean()
    
    # Fed Funds 12m change (in percentage points)
    df["DFF_12m_change"] = df["DFF"] - df["DFF"].shift(365)
    
    # WTI 12m percentage change
    df["WTI_12m_pct"] = (df["WTI"] - df["WTI"].shift(365)) / df["WTI"].shift(365) * 100

    # Drop the lookback period (2003)
    df = df.loc["2004-01-01":end_date].copy()

    # Fill any remaining NaNs
    df = df.ffill().bfill()

    # 5. Normalize Components to 0-100
    # Yield Curve Inversion
    df["I_Yield"] = df["T10Y2Y"].apply(lambda val: min(abs(val) * 100.0, 100.0) if val < 0 else 0.0)
    
    # Sahm Rule
    df["I_Sahm"] = df["SAHM"].apply(lambda val: min(max((val / 0.50) * 100.0, 0.0), 100.0))
    
    # MOVE Index
    df["I_MOVE"] = df["MOVE"].apply(lambda val: min(max(((val - 60.0) / 60.0) * 100.0, 0.0), 100.0))
    
    # Fed Funds Target Rate Change
    df["I_Fed"] = df["DFF_12m_change"].apply(lambda val: min(max((val / 2.5) * 100.0, 0.0), 100.0))
    
    # Oil Shock (WTI change positive value only, shifted by 15% threshold, scaled by 35%)
    df["I_Oil"] = df["WTI_12m_pct"].apply(lambda val: min(max(((val - 15.0) / 35.0) * 100.0, 0.0), 100.0))

    # Trend Momentum (Price vs 200 SMA, 100% risk if index drops 10% or more below SMA)
    df["I_Trend"] = (df["SPY_200SMA"] - df["SPY"]) / (df["SPY_200SMA"] * 0.10) * 100.0
    df["I_Trend"] = df["I_Trend"].clip(lower=0.0, upper=100.0)

    # US Dollar Index Trend (0% risk if at/below 200 SMA, scaling to 100% risk if 8% or more above 200 SMA)
    df["I_USD"] = (df["USD"] - df["USD_200SMA"]) / (df["USD_200SMA"] * 0.08) * 100.0
    df["I_USD"] = df["I_USD"].clip(lower=0.0, upper=100.0)

    # 6. Compute Consolidated Risk Score
    # Sahm (15%), MOVE (15%), Trend (20%), Yield Curve (15%), Fed Funds (15%), Oil (10%), USD (10%)
    df["Composite"] = (
        0.15 * df["I_Sahm"] +
        0.15 * df["I_MOVE"] +
        0.20 * df["I_Trend"] +
        0.15 * df["I_Yield"] +
        0.15 * df["I_Fed"] +
        0.10 * df["I_Oil"] +
        0.10 * df["I_USD"]
    )

    # 7. Format output for JSON
    logger.info("Formatting JSON output...")
    # Round all values to 2 decimal places to save file size
    df = df.round(2)
    
    dates = df.index.strftime("%Y-%m-%d").tolist()
    
    output_data = {
        "dates": dates,
        "composite": df["Composite"].tolist(),
        "components": {
            "yield": df["I_Yield"].tolist(),
            "sahm": df["I_Sahm"].tolist(),
            "move": df["I_MOVE"].tolist(),
            "fed": df["I_Fed"].tolist(),
            "oil": df["I_Oil"].tolist(),
            "trend": df["I_Trend"].tolist(),
            "usd": df["I_USD"].tolist()
        },
        "raw": {
            "t10y2y": df["T10Y2Y"].tolist(),
            "sahm_value": df["SAHM"].tolist(),
            "move_value": df["MOVE"].tolist(),
            "dff": df["DFF"].tolist(),
            "wti": df["WTI"].tolist(),
            "spy": df["SPY"].tolist(),
            "usd_value": df["USD"].tolist()
        }
    }

    # Ensure output dir exists
    os.makedirs(DASHBOARD_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.info(f"Successfully generated Risk KPI data at {OUTPUT_PATH}")
    logger.info(f"File size: {os.path.getsize(OUTPUT_PATH) / 1024:.1f} KB")

if __name__ == "__main__":
    main()
