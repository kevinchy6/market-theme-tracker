"""Shared configuration: ETF lists for the tab views and ticker tape."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data_cache")
DATA_DIR = os.path.join(ROOT, "site", "data")
TICKER_DIR = os.path.join(DATA_DIR, "tickers")

HISTORY_PERIOD = "2y"  # daily bars downloaded per ticker

# ---- Ticker tape (top strip) ----
TAPE = [
    "SPY", "QQQ", "IWM", "DIA", "NVDA", "AAPL", "MSFT", "TSLA", "META",
    "AMD", "GOOGL", "AMZN", "XLE", "XLF", "XLK", "GLD", "TLT", "BTC-USD",
]

# ---- S&P sector SPDRs + industry ETFs (cap-weighted) ----
SP_SECTORS = {
    "XLK": "Technology", "XLF": "Financials", "XLV": "Health Care",
    "XLY": "Consumer Discretionary", "XLP": "Consumer Staples", "XLE": "Energy",
    "XLI": "Industrials", "XLB": "Materials", "XLU": "Utilities",
    "XLRE": "Real Estate", "XLC": "Communication Services",
    # sub-sector / industry ETFs
    "SMH": "Semiconductors (SMH)", "IGV": "Software (IGV)", "XBI": "Biotech (XBI)",
    "KRE": "Regional Banks (KRE)", "XOP": "Oil & Gas E&P (XOP)", "OIH": "Oil Services (OIH)",
    "ITA": "Aerospace & Defense (ITA)", "XHB": "Homebuilders (XHB)", "XRT": "Retail (XRT)",
    "JETS": "Airlines (JETS)", "TAN": "Solar (TAN)", "URA": "Uranium (URA)",
    "GDX": "Gold Miners (GDX)", "COPX": "Copper Miners (COPX)", "ARKK": "Innovation (ARKK)",
    "BOTZ": "Robotics & AI (BOTZ)", "IPO": "Recent IPOs (IPO)", "BITQ": "Crypto Equities (BITQ)",
}

# ---- Equal-weight sector ETFs (Invesco) ----
EQWT = {
    "RSP": "S&P 500 Equal Weight", "RSPT": "Technology EW", "RSPF": "Financials EW",
    "RSPH": "Health Care EW", "RSPD": "Consumer Discretionary EW", "RSPS": "Consumer Staples EW",
    "RSPG": "Energy EW", "RSPN": "Industrials EW", "RSPM": "Materials EW",
    "RSPU": "Utilities EW", "RSPR": "Real Estate EW", "RSPC": "Communication Svcs EW",
    "QQQE": "Nasdaq-100 EW", "EQAL": "Russell 1000 EW",
}

# ---- Country ETFs (iShares MSCI mostly) ----
COUNTRY = {
    "SPY": "United States", "EWJ": "Japan", "MCHI": "China", "EWZ": "Brazil",
    "EWG": "Germany", "EWU": "United Kingdom", "EWQ": "France", "EWI": "Italy",
    "EWP": "Spain", "EWL": "Switzerland", "EWN": "Netherlands", "EWD": "Sweden",
    "EWA": "Australia", "EWC": "Canada", "EWW": "Mexico", "EWY": "South Korea",
    "EWT": "Taiwan", "INDA": "India", "EWS": "Singapore", "EWH": "Hong Kong",
    "EWM": "Malaysia", "THD": "Thailand", "EIDO": "Indonesia", "EPHE": "Philippines",
    "EPOL": "Poland", "TUR": "Turkey", "EZA": "South Africa", "EWO": "Austria",
    "EDEN": "Denmark", "ENOR": "Norway", "EIS": "Israel", "ARGT": "Argentina",
    "ECH": "Chile", "GXG": "Colombia", "EPU": "Peru", "GREK": "Greece",
    "KSA": "Saudi Arabia", "UAE": "UAE", "QAT": "Qatar", "VNM": "Vietnam",
    "EGPT": "Egypt", "NGE": "Nigeria", "PAK": "Pakistan", "EWK": "Belgium",
    "NZAC": "New Zealand", "EFNL": "Finland", "EIRL": "Ireland", "EWJV": "Japan Value",
}

# ---- Broad market / macro snapshot ETFs ----
SNAPSHOT = {
    "SPY": "S&P 500", "QQQ": "Nasdaq 100", "IWM": "Russell 2000", "DIA": "Dow 30",
    "RSP": "S&P Equal Weight", "MDY": "S&P MidCap 400", "IJR": "S&P SmallCap 600",
    "EFA": "Developed ex-US", "EEM": "Emerging Markets", "GLD": "Gold", "SLV": "Silver",
    "USO": "Oil (USO)", "UNG": "Nat Gas (UNG)", "TLT": "20+yr Treasuries", "IEF": "7-10yr Treasuries",
    "HYG": "High Yield", "LQD": "IG Credit", "UUP": "US Dollar", "FXE": "Euro",
    "FXY": "Yen", "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "VIXY": "VIX Futures",
}

# COT futures markets to chart (CFTC legacy futures-only codes)
COT_MARKETS = {
    "13874A": "S&P 500 E-Mini",
    "209742": "Nasdaq 100 E-Mini",
    "239742": "Russell 2000 E-Mini",
    "124603": "Dow Jones $5 Mini",
    "088691": "Gold",
    "084691": "Silver",
    "067651": "Crude Oil WTI",
    "023651": "Natural Gas",
    "098662": "US Dollar Index",
    "099741": "Euro FX",
    "097741": "Japanese Yen",
    "020601": "US Treasury Bonds",
    "043602": "10-Year Notes",
    "133741": "Bitcoin",
    "002602": "Corn",
    "005602": "Soybeans",
    "001602": "Wheat SRW",
    "085692": "Copper",
}

ALL_ETFS = sorted(
    set(list(SP_SECTORS) + list(EQWT) + list(COUNTRY) + list(SNAPSHOT) + TAPE)
)
