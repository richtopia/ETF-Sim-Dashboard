# ETF Simulator & Macro-Financial Risk Dashboard

An interactive quantitative simulation platform and macroeconomic scoreboard. The project simulates concentrated, monthly-rebalanced ETF portfolios against global benchmarks and integrates a multi-factor **Consolidated Risk Score** to dynamically switch between Growth and Defensive equity regimes.

---

## 🚀 Quick Start

### 1. Installation
Install the required dependencies (pandas, numpy, yfinance, pyyaml, requests):
```bash
pip install -r requirements.txt
```

### 2. Update Data Pipelines
Always run the data pipelines in this order to compile the latest historical datasets:
```bash
# Step 1: Download FRED/YFinance data and compile the Macro Risk Scorecard
python generate_risk_kpi.py

# Step 2: Simulate all ETF strategies (reading from etf_definitions.yaml and caching prices)
python run_backtest.py
```
*Note: Both pipelines dynamically query Yahoo Finance and FRED up to **today's date** (the current system date) on execution.*

### 3. Launch Dashboard
Start a local web server to view the interface (highly recommended over opening raw HTML to avoid CORS fetch issues):
```bash
python -m http.server 8000
```
Open your browser and navigate to:
* **ETF Simulator:** [http://localhost:8000/dashboard/index.html](http://localhost:8000/dashboard/index.html)
* **Risk Scoreboard:** [http://localhost:8000/dashboard/risk_kpi.html](http://localhost:8000/dashboard/risk_kpi.html)
* **Strategy Definitions:** [http://localhost:8000/dashboard/definitions.html](http://localhost:8000/dashboard/definitions.html)

---

## 📁 Repository Structure

```
├── backtest_engine.py      # Core simulation math (portfolio accounting, selection logic, caching)
├── run_backtest.py         # CLI entry point to execute backtest simulations
├── generate_risk_kpi.py    # Fetches FRED/YFinance macro variables and outputs the Risk Scorecard
├── etf_definitions.yaml    # Config file defining selection criteria and universes for simulated ETFs
├── universes.py            # Static lists of universe constituents (S&P 500, MSCI EAFE, MSCI EM)
├── requirements.txt        # Package requirements
├── cache/                  # Cached stock prices and dividends (created automatically on run)
└── dashboard/              # Dynamic frontend files
    ├── index.html          # ETF Backtesting Simulator UI
    ├── app.js              # Controller handling simulator plots, metrics tables, and rebalance logs
    ├── risk_kpi.html       # Macro Risk Scoreboard UI
    ├── risk_app.js         # Controller handling risk charts, date pickers, and NBER recessions
    ├── risk_styles.css     # Glassmorphism dark-theme layout css
    ├── definitions.html    # Strategy definitions glossary UI
    ├── results.json        # Output dataset from run_backtest.py (contains timeseries & holdings logs)
    └── risk_kpi.json       # Output dataset from generate_risk_kpi.py (contains normalized scores)
```

---

## 🛠️ Work Completed (2026 Upgrades)

### 1. Regime-Switching "Ultimate" Strategies
* Replaced the original, single *Ultimate Strategy* with five distinct variants defined in `etf_definitions.yaml`:
  1. **`Ult-Yield`:** Switches defensive when the 10Y-2Y Treasury curve inverts ($T10Y2Y \le 0$).
  2. **`Ult-VIX`:** Switches defensive when the VIX index exceeds $20$.
  3. **`Ult-200SMA`:** Switches defensive when the S&P 500 index price falls below its 200-day Simple Moving Average.
  4. **`Ult-RiskKPI`:** Switches defensive when the multi-factor Consolidated Risk Score $\ge 50$.
  5. **`Ult-Hybrid`:** Dynamically scales exposure (100% Growth, 50/50 Balanced, 100% Defensive) based on the Consolidated Risk Score and enforces a 200-day SMA emergency brake (100% Defensive if S&P 500 is in a bear market).
* Enforced **Risk-On** parameters: Top 5 Momentum + Top 5 Market Cap stocks.
* Enforced **Risk-Off** (Defensive) parameters: Top 5 Low Volatility + Top 5 High Dividend Yield stocks.

### 2. Macro-Financial Risk Scoreboard
* Programmed `generate_risk_kpi.py` to fetch daily leading economic variables from FRED and Yahoo Finance:
  * **Sahm Rule Real-time recession indicator** (FRED: `SAHMREALTIME`, Weight: 15%)
  * **MOVE Index bond volatility** (Yahoo: `^MOVE`, Weight: 20%)
  * **Trend Momentum** (S&P 500 Index `^GSPC` vs. its 200-day SMA, Weight: 20%)
  * **Yield Curve Inversion** (FRED: `T10Y2Y`, Weight: 15%)
  * **Fed Funds Rate 12M Change** (FRED: `DFF`, Weight: 20%)
  * **Oil Price Shock** (FRED: `DCOILWTICO` positive-only increases, Weight: 10%)
* Created a dedicated dashboard to plot these series with NBER recession bands, dynamic monthly scaling, and an overlay of the actual S&P 500 Index on a secondary right-hand Y-axis.
* Added a dynamic metadata status bar showing the latest scores for each component as of the last trading day.

---

## 📊 Backtest Performance Summary (2004 – July 2026)

| Strategy | Total Return | Ann. Return | Max Drawdown | Sharpe Ratio | Primary Driver |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`Ult-RiskKPI`** | **8,494.3%** | **21.88%** | -49.0% | 0.81 | Strongest absolute returns by combining macro signals. |
| **`Ult-200SMA`** | 7,705.2% | 21.36% | -40.2% | 0.82 | Robust price trend protection during rate hikes. |
| **`Ult-Hybrid`** | 7,542.7% | 21.25% | **-40.2%** | **0.83** | **Top risk-adjuster:** Lowest volatility, high compounding. |
| **`Ult-Yield`** | 7,151.2% | 20.96% | -51.3% | 0.79 | Dragged down by 2022-24 yield curve false positives. |
| **`Ult-VIX`** | 5,998.6% | 20.04% | **-38.4%** | 0.81 | Fastest downside reaction; best drawdown control. |
| *S&P 500 (SPY)* | 910.9% | 10.82% | -55.2% | 0.38 | Passive benchmark buy-and-hold. |

---

## 🤖 Handoff Guide for Future Users and AI Agents

### 1. Adding a New ETF Strategy
To define a new ETF:
1. Open `etf_definitions.yaml`.
2. Append a new block under `etfs:`:
   ```yaml
     - name: "Ult-Custom"
       description: "Your description..."
       universe: "sp500" # Choose sp500, efa, or eem
       selection_rule: "ult_custom"
       n: 10
       weighting: "equal"
       rebalance_frequency: "monthly"
   ```
3. Open `backtest_engine.py`, scroll to `simulate_portfolio` (around line 550), and map your new `selection_rule` value:
   ```python
   elif selection_rule == "ult_custom":
       # Write a select_ult_custom helper function and assign new_tickers
       new_tickers = select_ult_custom(prices, shares, date, n)
   ```
4. If you want custom weights (like the `Ult-Hybrid` scaled allocation), return a dictionary mapping `ticker: weight` directly and assign it to `current_weights`.
5. Run `python run_backtest.py` to regenerate results. Open the simulator dashboard; the new ETF will automatically render in the checkboxes list and metrics table.

### 2. Modifying Risk Weights
To change the weight configuration of the Consolidated Risk Score:
1. Open `generate_risk_kpi.py`, locate the **Compute Consolidated Risk Score** section (around line 125).
2. Adjust the decimal coefficients. Ensure they sum to exactly `1.0`:
   ```python
   df["Composite"] = (
       0.15 * df["I_Sahm"] +
       0.20 * df["I_MOVE"] + ...
   )
   ```
3. Update the text labels in the static HTML sidebar inside `dashboard/risk_kpi.html` (around line 85) to reflect the new weights on the UI.
4. Run `python generate_risk_kpi.py` to recompile.

### 3. API Guidelines
* **yfinance downloads:** Yahoo Finance is queried directly. Standard tickers like `^MOVE` (MOVE Index), `^GSPC` (S&P 500 Index), and individual company tickers are supported. To avoid MultiIndex header issues when downloading multiple tickers, retrieve columns individually or download single tickers as series.
* **FRED downloads:** Downloads are handled directly via FRED CSV endpoints using pandas. If you add indicators, query them via `https://fred.stlouisfed.org/graph/fredgraph.csv?id=YOUR_FRED_ID`.

### 4. Code Consistency
* **Preserve comment structure:** Keep the existing docstrings and `# ---` section separators intact.
* **JS Downsampling:** Daily backtest timeseries are too large for browser JSON memory. Ensure the python scripts downsample/format outputs cleanly, and `downsampleTimeseries` remains active in both JS files (`app.js` and `risk_app.js`) to prevent browser chart lag.
