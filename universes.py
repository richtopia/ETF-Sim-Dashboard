"""
Universe definitions for ETF backtesting.
Provides constituent ticker lists for each investment universe.
"""

import pandas as pd
import requests
import logging

logger = logging.getLogger(__name__)


def get_sp500_tickers() -> list[str]:
    """
    Fetch current S&P 500 constituent tickers from Wikipedia.
    Falls back to a hardcoded list of the largest companies if scraping fails.
    """
    try:
        import requests
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        html = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).text
        tables = pd.read_html(html)
        df = tables[0]
        tickers = df["Symbol"].tolist()
        # Clean tickers: replace '.' with '-' for Yahoo Finance compatibility
        tickers = [t.replace(".", "-") for t in tickers]
        
        # Save a global map for names
        global _SP500_NAMES_CACHE
        _SP500_NAMES_CACHE = {t.replace(".", "-"): n for t, n in zip(df["Symbol"], df["Security"])}
        
        logger.info(f"Fetched {len(tickers)} S&P 500 tickers from Wikipedia")
        return tickers
    except Exception as e:
        logger.warning(f"Failed to scrape S&P 500 from Wikipedia: {e}. Using fallback list.")
        return _SP500_FALLBACK


def get_efa_tickers() -> list[str]:
    """
    Curated list of the ~50 largest holdings in the iShares MSCI EAFE ETF (EFA).
    Uses Yahoo Finance ticker symbols for international stocks.
    """
    return _EFA_CONSTITUENTS


def get_eem_tickers() -> list[str]:
    """
    Curated list of the ~30 largest holdings in the iShares MSCI Emerging Markets ETF (EEM).
    Uses Yahoo Finance ticker symbols for international stocks.
    Note: Some tickers use US-listed ADRs where available for better data quality.
    """
    return _EEM_CONSTITUENTS


def get_universe(universe_name: str) -> list[str]:
    """Get ticker list for a named universe."""
    universes = {
        "sp500": get_sp500_tickers,
        "efa": get_efa_tickers,
        "eem": get_eem_tickers,
    }
    if universe_name not in universes:
        raise ValueError(f"Unknown universe: {universe_name}. Available: {list(universes.keys())}")
    return universes[universe_name]()


_SP500_NAMES_CACHE = {}

def get_all_ticker_names() -> dict[str, str]:
    """
    Returns a unified dictionary mapping every known ticker to its company name.
    """
    names = {}
    names.update(_SP500_FALLBACK_NAMES)
    names.update(_SP500_NAMES_CACHE)
    
    import re
    # Extract names from comments in this file
    with open(__file__, 'r', encoding='utf-8') as f:
        text = f.read()
    
    matches = re.finditer(r'"([A-Z0-9\.\-]+)",\s*#\s*(.+)', text)
    for m in matches:
        names[m.group(1)] = m.group(2).strip()
        
    names['SPY'] = 'SPDR S&P 500 ETF Trust'
    names['EFA'] = 'iShares MSCI EAFE ETF'
    names['EEM'] = 'iShares MSCI Emerging Markets ETF'
    names['VT'] = 'Vanguard Total World Stock ETF'
    names['GOOG'] = 'Alphabet Inc. (Class C)'
    names['BRK-B'] = 'Berkshire Hathaway Inc.'
    
    return names


# ---------------------------------------------------------------------------
# Curated constituent lists
# ---------------------------------------------------------------------------

# Top ~50 EFA holdings with Yahoo Finance tickers
_EFA_CONSTITUENTS = [
    # Netherlands
    "ASML",          # ASML Holding (US-listed ADR)
    # Switzerland
    "ROG.SW",        # Roche Holding
    "NOVN.SW",       # Novartis
    "NESN.SW",       # Nestlé
    "UBSG.SW",       # UBS Group
    "ABBN.SW",       # ABB
    "ZURN.SW",       # Zurich Insurance
    # UK
    "AZN.L",         # AstraZeneca
    "SHEL.L",        # Shell
    "HSBA.L",        # HSBC Holdings
    "ULVR.L",        # Unilever
    "RIO.L",         # Rio Tinto
    "BP.L",          # BP
    "GSK.L",         # GSK
    "LSEG.L",        # London Stock Exchange Group
    "REL.L",         # RELX
    "DGE.L",         # Diageo
    "BA.L",          # BAE Systems
    # Germany
    "SAP",           # SAP SE (US-listed ADR)
    "SIE.DE",        # Siemens
    "ALV.DE",        # Allianz
    "MBG.DE",        # Mercedes-Benz
    "DTE.DE",        # Deutsche Telekom
    "MUV2.DE",       # Munich Re
    "BAS.DE",        # BASF
    "BMW.DE",        # BMW
    # France
    "MC.PA",         # LVMH
    "TTE.PA",        # TotalEnergies
    "SAN.PA",        # Sanofi
    "AI.PA",         # L'Air Liquide
    "SU.PA",         # Schneider Electric
    "BNP.PA",        # BNP Paribas
    "OR.PA",         # L'Oréal
    "CS.PA",         # AXA
    "RMS.PA",        # Hermès
    # Denmark
    "NOVO-B.CO",     # Novo Nordisk
    "MAERSK-B.CO",   # Maersk
    # Japan
    "7203.T",        # Toyota Motor
    "6758.T",        # Sony Group
    "8306.T",        # Mitsubishi UFJ Financial
    "6861.T",        # Keyence
    "6501.T",        # Hitachi
    "9984.T",        # SoftBank Group
    "8035.T",        # Tokyo Electron
    "6902.T",        # Denso
    # Australia
    "BHP.AX",        # BHP Group
    "CBA.AX",        # Commonwealth Bank
    "CSL.AX",        # CSL Limited
    # Spain
    "SAN.MC",        # Banco Santander
    # Italy
    "ENEL.MI",       # Enel
]

# Top ~30 EEM holdings with Yahoo Finance tickers
# Prefer US-listed ADRs where available for data reliability
_EEM_CONSTITUENTS = [
    # Taiwan
    "TSM",           # Taiwan Semiconductor (ADR)
    "2317.TW",       # Hon Hai Precision (Foxconn)
    "2308.TW",       # Delta Electronics
    "2454.TW",       # MediaTek
    "2382.TW",       # Quanta Computer
    # South Korea
    "005930.KS",     # Samsung Electronics
    "000660.KS",     # SK Hynix
    "373220.KS",     # LG Energy Solution
    "035420.KS",     # NAVER
    # China / Hong Kong
    "BABA",          # Alibaba (ADR)
    "TCEHY",         # Tencent (OTC ADR)
    "PDD",           # PDD Holdings (ADR)
    "JD",            # JD.com (ADR)
    "BIDU",          # Baidu (ADR)
    "NIO",           # NIO (ADR)
    "0939.HK",       # China Construction Bank
    "1398.HK",       # ICBC
    "3690.HK",       # Meituan
    # India
    "RELIANCE.NS",   # Reliance Industries
    "HDFCBANK.NS",   # HDFC Bank
    "INFY",          # Infosys (ADR)
    "TCS.NS",        # Tata Consultancy Services
    "ICICIBANK.NS",  # ICICI Bank
    # Brazil
    "VALE",          # Vale (ADR)
    "PBR",           # Petrobras (ADR)
    "ITUB",          # Itaú Unibanco (ADR)
    # Saudi Arabia
    "2222.SR",       # Saudi Aramco
    # South Africa
    "NPN.JO",        # Naspers
    # Mexico
    "AMX",           # América Móvil (ADR)
    # Thailand
    "PTT.BK",        # PTT Public Company
]

# Fallback S&P 500 top ~30 by market cap (in case Wikipedia scraping fails)
_SP500_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "AVGO", "TSLA",
    "BRK-B", "LLY", "WMT", "JPM", "V", "UNH", "MA", "XOM",
    "COST", "HD", "PG", "JNJ", "NFLX", "ABBV", "CRM", "BAC",
    "CVX", "KO", "MRK", "AMD", "PEP", "TMO",
]

_SP500_FALLBACK_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corp.",
    "NVDA": "NVIDIA Corp.",
    "AMZN": "Amazon.com Inc.",
    "GOOGL": "Alphabet Inc. (Class A)",
    "GOOG": "Alphabet Inc. (Class C)",
    "META": "Meta Platforms Inc.",
    "AVGO": "Broadcom Inc.",
    "TSLA": "Tesla Inc.",
    "BRK-B": "Berkshire Hathaway Inc.",
    "LLY": "Eli Lilly and Co.",
    "WMT": "Walmart Inc.",
    "JPM": "JPMorgan Chase & Co.",
    "V": "Visa Inc.",
    "UNH": "UnitedHealth Group Inc.",
    "MA": "Mastercard Inc.",
    "XOM": "Exxon Mobil Corp.",
    "COST": "Costco Wholesale Corp.",
    "HD": "The Home Depot Inc.",
    "PG": "Procter & Gamble Co.",
    "JNJ": "Johnson & Johnson",
    "NFLX": "Netflix Inc.",
    "ABBV": "AbbVie Inc.",
    "CRM": "Salesforce Inc.",
    "BAC": "Bank of America Corp.",
    "CVX": "Chevron Corp.",
    "KO": "The Coca-Cola Co.",
    "MRK": "Merck & Co. Inc.",
    "AMD": "Advanced Micro Devices Inc.",
    "PEP": "PepsiCo Inc.",
    "TMO": "Thermo Fisher Scientific Inc."
}
