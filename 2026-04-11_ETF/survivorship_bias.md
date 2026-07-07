# Survivorship Bias in This Backtest

## What Is Survivorship Bias?

Survivorship bias occurs when a study or backtest only considers entities (stocks, funds, companies) that currently exist or have "survived" to the present, ignoring those that have failed, been delisted, or been acquired over the period being studied.

In stock market backtesting, this means our historical data set may be missing companies that were once major S&P 500 constituents but no longer trade under their original tickers. These missing companies disproportionately include **spectacular failures** — bankruptcies, fraud-related collapses, and crisis casualties — which means our backtest systematically **overstates historical returns** by excluding the worst possible outcomes.

## How This Affects Our Backtest

This backtest is affected by survivorship bias in two specific ways:

### 1. Constituent Data Limitation (starts 1996, not 1960s)

Our S&P 500 constituent data comes from a community-maintained GitHub dataset ([fja05680/sp500](https://github.com/fja05680/sp500)) which only covers **1996 to present**. The S&P 500 was established in 1957, and its predecessor (the S&P 90) dates to 1926. We are missing approximately 40 years of history that would have included major market events:

- The **1960s–70s Nifty Fifty** collapse — many "must-own" stocks fell 70–90%
- The **1973–74 bear market** — S&P 500 fell ~48%
- The **1987 Black Monday crash** — single-day drop of 22.6%
- Numerous **industry-specific collapses** (airlines, steel, rail companies that once dominated the index)

### 2. Missing Price Data for Delisted Stocks

Yahoo Finance (via `yfinance`) generally does **not** maintain historical price data for companies that have been delisted, acquired, or gone bankrupt. When our backtest encounters a ticker that yfinance cannot find, it simply skips that stock. This creates a selection bias in two ways:

- **We never "buy" stocks that would have been index constituents but whose data is missing.** If those stocks later went to zero, our backtest is spared those losses.
- **We may keep holding a stock whose price data disappears mid-backtest**, using entry price as a fallback — which is likely *more generous* than reality (where the stock went to $0 or a fire-sale acquisition price).

---

## Notable Missing Companies

The following table lists major S&P 500 companies that were likely among the **top 10 by market capitalisation or momentum** at some point during 1996–2024, but whose data is missing or incomplete in our free dataset. These are exactly the stocks whose inclusion would have produced the worst outcomes in our backtest.

### Companies Lost to Bankruptcy / Failure

| Company | Ticker | Approx. S&P 500 Period | Event | Impact on Top-10 Strategies |
|---------|--------|----------------------|-------|---------------------------|
| **Enron** | ENE | 1990s–Dec 2001 | Fraud/Bankruptcy | Was ~#7 by market cap before collapse. Would have appeared in **market cap top 10**. Stock went from ~$90 to $0. |
| **WorldCom / MCI** | WCOM / MCIT | 1990s–Jul 2002 | Fraud/Bankruptcy | Major telecom, top 20 by market cap. Potential **momentum** pick during 1998–99 bubble. Stock went from ~$64 to $0. |
| **Lehman Brothers** | LEH | 1990s–Sep 2008 | Bankruptcy (financial crisis) | Major financial institution. Would have been in portfolios during 2005–07 if using market cap. Stock went from ~$86 to $0. |
| **Bear Stearns** | BSC | 1990s–Mar 2008 | Forced sale to JPMorgan at $10/share | Investment bank, potential **momentum** pick in mid-2000s. |
| **Washington Mutual** | WM | 2000s–Sep 2008 | Largest bank failure in US history | $307B in assets seized by FDIC. Stock went from ~$45 to $0. |
| **Countrywide Financial** | CFC | 2000s–Jul 2008 | Acquired by BofA during mortgage crisis | Stock fell from ~$45 to ~$5 before acquisition. |
| **AIG** | AIG | 1980s–present | Near-failure, massive government bailout | Stock fell from ~$72 to ~$1. AIG still trades but under completely restructured form. |

### Companies Lost to Mergers & Acquisitions

These companies were absorbed and their historical price data is often incomplete or unavailable:

| Company | Original Ticker | Acquired By | Year | Relevance |
|---------|----------------|-------------|------|-----------|
| **Compaq Computer** | CPQ | Hewlett-Packard | 2002 | Top 10 market cap in late 1990s |
| **Lucent Technologies** | LU | Alcatel | 2006 | Spun off from AT&T, was massive; stock fell ~98% from peak |
| **Nortel Networks** | NT | Bankruptcy | 2009 | Major telecom equipment maker, once worth $250B+ |
| **General Motors (old)** | GM | Bankruptcy/IPO | 2009 | Was consistently top 10 by market cap for decades; old GM went bankrupt |
| **Wachovia** | WB | Wells Fargo | 2008 | 4th largest US bank before crisis |
| **Merrill Lynch** | MER | Bank of America | 2009 | Iconic Wall Street firm |
| **Time Warner (original)** | TWX | AT&T (later spun off) | 2018 | Mega-cap media company |
| **Ameriquest / Household International** | HI | HSBC | 2003 | Large consumer finance company |
| **McDonnell Douglas** | MD | Boeing | 1997 | Major defense/aerospace |
| **Digital Equipment Corp** | DEC | Compaq | 1998 | Once 2nd largest computer company |

### Companies with Ticker/Name Changes

These companies changed tickers, creating potential gaps in our data:

| Old Name / Ticker | New Name / Ticker | Year | Notes |
|-------------------|-------------------|------|-------|
| Philip Morris (MO) | Altria (MO) + Philip Morris International (PM) | 2008 | Split into two companies |
| Andersen Consulting | Accenture (ACN) | 2001 | Name change + IPO |
| Exxon + Mobil | ExxonMobil (XOM) | 1999 | Merger |
| Travelers Group + Citicorp | Citigroup (C) | 1998 | Merger |
| SBC Communications | AT&T (T) | 2005 | SBC acquired AT&T, took its name |
| Google (GOOG) | Alphabet (GOOGL/GOOG) | 2015 | Corporate restructuring |
| Facebook (FB) | Meta Platforms (META) | 2022 | Rebrand |

---

## Impact by Strategy

### Market Capitalisation Strategy

The market cap strategy is **moderately affected** by survivorship bias. Large companies tend to be more stable than small ones, but several of the most catastrophic failures in market history involved top-10 market-cap companies:

- **Enron** would have been in the top 10 before its bankruptcy
- **General Electric (GE)** was consistently #1–3 by market cap from 1996–2005, then declined ~80%. GE data is available but the stock was later restructured.
- **General Motors** was a perennial top-10 member that went bankrupt in 2009
- The **dot-com bubble** (2000–2002) destroyed several top-10 tech stocks

**Estimated bias**: Our market cap strategy returns are likely **overstated by 1–3% annually** due to missing failures.

### Momentum Strategy

The momentum strategy is **significantly more affected** by survivorship bias. Momentum strategies, by definition, buy stocks that have recently risen the most. These stocks include:

- **Bubble stocks** that rose rapidly then crashed (Enron, WorldCom, Nortel, Lucent)
- **Leveraged financials** that soared during credit expansions then collapsed (Lehman, Bear Stearns, WaMu)
- **High-flying growth stocks** that ultimately failed

Momentum is known to suffer from **"momentum crashes"** — sharp, sudden reversals where previously winning stocks collapse simultaneously. Missing these events from our data makes momentum appear safer than it actually is.

**Estimated bias**: Our momentum strategy returns are likely **overstated by 2–5% annually**, and our maximum drawdown is likely **understated by 10–20 percentage points**.

---

## Mitigation Recommendations

To reduce survivorship bias in future research, consider:

1. **CRSP/Compustat via WRDS** (~free with university affiliation): Complete delisting-adjusted returns for all US stocks back to 1926. The gold standard for academic research.

2. **Norgate Data** (~$400/year): Provides delisting-adjusted data including historical S&P 500 constituents. Designed specifically for backtesting.

3. **EODHD** (~$80/year): Includes some delisted stock data and historical index constituents.

4. **Adjust returns for known failures**: Even without full data, you can manually add known bankruptcy events (e.g., simulate Enron going to $0 in Dec 2001) to stress-test results.

5. **Use the backtest results directionally, not precisely**: The relative ranking of strategies may still be valid even if absolute return levels are overstated.

---

## Summary

> **This backtest should be interpreted as an upper bound on historical performance.** The true returns of these strategies would have been lower, and the drawdowns deeper, than what our free-data backtest shows. The momentum strategy is more severely affected than the market cap strategy.
