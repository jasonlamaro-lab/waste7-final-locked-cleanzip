"""
Market constituent lists — 15–20 top-weight heavyweights per index.
Weights are approximate free-float market-cap weights (normalised to top holdings).
Weights are expressed as decimals and sum to < 1.0 (only top holdings included).
The engine normalises across whichever constituents have live data each cycle.

% comments = approximate real-world index weight for tracking.
"""

MARKET_DEFINITIONS = {
    # ── Americas ──────────────────────────────────────────────────────────────

    "nasdaq100": {
        "constituents": {
            "MSFT":  {"weight": 0.085, "sector": "tech"},         # 8.5%
            "AAPL":  {"weight": 0.082, "sector": "tech"},         # 8.2%
            "NVDA":  {"weight": 0.079, "sector": "semiconductors"},# 7.9%
            "AMZN":  {"weight": 0.055, "sector": "consumer"},     # 5.5%
            "META":  {"weight": 0.048, "sector": "tech"},         # 4.8%
            "GOOGL": {"weight": 0.044, "sector": "tech"},         # 4.4%
            "GOOG":  {"weight": 0.040, "sector": "tech"},         # 4.0%
            "TSLA":  {"weight": 0.033, "sector": "auto"},         # 3.3%
            "AVGO":  {"weight": 0.032, "sector": "semiconductors"},# 3.2%
            "COST":  {"weight": 0.026, "sector": "retail"},       # 2.6%
            "NFLX":  {"weight": 0.022, "sector": "media"},        # 2.2%
            "AMD":   {"weight": 0.021, "sector": "semiconductors"},# 2.1%
            "ADBE":  {"weight": 0.018, "sector": "tech"},         # 1.8%
            "QCOM":  {"weight": 0.016, "sector": "semiconductors"},# 1.6%
            "INTC":  {"weight": 0.012, "sector": "semiconductors"},# 1.2%
            "CSCO":  {"weight": 0.012, "sector": "tech"},         # 1.2%
            "INTU":  {"weight": 0.011, "sector": "tech"},         # 1.1%
            "TXN":   {"weight": 0.010, "sector": "semiconductors"},# 1.0%
            "AMGN":  {"weight": 0.009, "sector": "health"},       # 0.9%
            "SBUX":  {"weight": 0.009, "sector": "consumer"},     # 0.9%
        }
    },

    "sp500": {
        "constituents": {
            "MSFT":  {"weight": 0.072, "sector": "tech"},         # 7.2%
            "AAPL":  {"weight": 0.068, "sector": "tech"},         # 6.8%
            "NVDA":  {"weight": 0.060, "sector": "semiconductors"},# 6.0%
            "AMZN":  {"weight": 0.038, "sector": "consumer"},     # 3.8%
            "META":  {"weight": 0.028, "sector": "tech"},         # 2.8%
            "GOOGL": {"weight": 0.026, "sector": "tech"},         # 2.6%
            "BRK-B": {"weight": 0.020, "sector": "finance"},      # 2.0%
            "TSLA":  {"weight": 0.018, "sector": "auto"},         # 1.8%
            "JPM":   {"weight": 0.016, "sector": "finance"},      # 1.6%
            "UNH":   {"weight": 0.014, "sector": "health"},       # 1.4%
            "V":     {"weight": 0.013, "sector": "finance"},      # 1.3%
            "XOM":   {"weight": 0.012, "sector": "energy"},       # 1.2%
            "MA":    {"weight": 0.012, "sector": "finance"},      # 1.2%
            "AVGO":  {"weight": 0.011, "sector": "semiconductors"},# 1.1%
            "PG":    {"weight": 0.010, "sector": "consumer"},     # 1.0%
            "JNJ":   {"weight": 0.010, "sector": "health"},       # 1.0%
            "HD":    {"weight": 0.009, "sector": "retail"},       # 0.9%
            "COST":  {"weight": 0.009, "sector": "retail"},       # 0.9%
            "WMT":   {"weight": 0.008, "sector": "retail"},       # 0.8%
            "BAC":   {"weight": 0.008, "sector": "finance"},      # 0.8%
        }
    },

    "dowjones": {
        "constituents": {
            "UNH":   {"weight": 0.100, "sector": "health"},       # 10.0%
            "GS":    {"weight": 0.080, "sector": "finance"},      # 8.0%
            "MSFT":  {"weight": 0.070, "sector": "tech"},         # 7.0%
            "HD":    {"weight": 0.065, "sector": "retail"},       # 6.5%
            "CAT":   {"weight": 0.062, "sector": "industrials"},  # 6.2%
            "AMGN":  {"weight": 0.055, "sector": "health"},       # 5.5%
            "MCD":   {"weight": 0.052, "sector": "consumer"},     # 5.2%
            "V":     {"weight": 0.050, "sector": "finance"},      # 5.0%
            "HON":   {"weight": 0.048, "sector": "industrials"},  # 4.8%
            "SHW":   {"weight": 0.045, "sector": "materials"},    # 4.5%
            "TRV":   {"weight": 0.042, "sector": "finance"},      # 4.2%
            "IBM":   {"weight": 0.040, "sector": "tech"},         # 4.0%
            "JPM":   {"weight": 0.038, "sector": "finance"},      # 3.8%
            "BA":    {"weight": 0.035, "sector": "industrials"},  # 3.5%
            "AAPL":  {"weight": 0.032, "sector": "tech"},         # 3.2%
            "AXP":   {"weight": 0.030, "sector": "finance"},      # 3.0%
            "MMM":   {"weight": 0.028, "sector": "industrials"},  # 2.8%
            "CVX":   {"weight": 0.026, "sector": "energy"},       # 2.6%
            "WMT":   {"weight": 0.024, "sector": "retail"},       # 2.4%
            "PG":    {"weight": 0.022, "sector": "consumer"},     # 2.2%
        }
    },

    "tsx": {
        "constituents": {
            "RY":    {"weight": 0.115, "sector": "finance"},      # 11.5%
            "TD":    {"weight": 0.095, "sector": "finance"},      # 9.5%
            "ENB":   {"weight": 0.075, "sector": "energy"},       # 7.5%
            "CNR":   {"weight": 0.060, "sector": "industrials"},  # 6.0%
            "BMO":   {"weight": 0.058, "sector": "finance"},      # 5.8%
            "BNS":   {"weight": 0.052, "sector": "finance"},      # 5.2%
            "CM":    {"weight": 0.042, "sector": "finance"},      # 4.2%
            "CNQ":   {"weight": 0.038, "sector": "energy"},       # 3.8%
            "MFC":   {"weight": 0.032, "sector": "finance"},      # 3.2%
            "SU":    {"weight": 0.030, "sector": "energy"},       # 3.0%
            "CP":    {"weight": 0.028, "sector": "industrials"},  # 2.8%
            "TRP":   {"weight": 0.025, "sector": "energy"},       # 2.5%
            "GIB":   {"weight": 0.022, "sector": "tech"},         # 2.2%
            "MG":    {"weight": 0.018, "sector": "auto"},         # 1.8%
            "ABX":   {"weight": 0.016, "sector": "materials"},    # 1.6%
        }
    },

    "bovespa": {
        "constituents": {
            "VALE":  {"weight": 0.130, "sector": "materials"},    # 13.0%
            "PBR":   {"weight": 0.110, "sector": "energy"},       # 11.0%
            "ITUB":  {"weight": 0.090, "sector": "finance"},      # 9.0%
            "BBD":   {"weight": 0.075, "sector": "finance"},      # 7.5%
            "ABEV":  {"weight": 0.045, "sector": "consumer"},     # 4.5%
            "BRAP":  {"weight": 0.035, "sector": "materials"},    # 3.5%
            "GGBR":  {"weight": 0.030, "sector": "materials"},    # 3.0%
            "RENT3.SA": {"weight": 0.025, "sector": "consumer"},  # 2.5%
            "WEGE3.SA": {"weight": 0.022, "sector": "industrials"},# 2.2%
            "JBSS3.SA": {"weight": 0.018, "sector": "consumer"},  # 1.8%
        }
    },

    # ── Europe ────────────────────────────────────────────────────────────────

    "ftse100": {
        "constituents": {
            "SHEL":  {"weight": 0.095, "sector": "energy"},       # 9.5%
            "AZN":   {"weight": 0.088, "sector": "health"},       # 8.8%
            "HSBC":  {"weight": 0.068, "sector": "finance"},      # 6.8%
            "UL":    {"weight": 0.058, "sector": "consumer"},     # 5.8%
            "BP":    {"weight": 0.050, "sector": "energy"},       # 5.0%
            "RIO":   {"weight": 0.042, "sector": "materials"},    # 4.2%
            "GSK":   {"weight": 0.038, "sector": "health"},       # 3.8%
            "BATS":  {"weight": 0.032, "sector": "consumer"},     # 3.2%
            "LLOY":  {"weight": 0.028, "sector": "finance"},      # 2.8%
            "PRU":   {"weight": 0.025, "sector": "finance"},      # 2.5%
            "DGE":   {"weight": 0.022, "sector": "consumer"},     # 2.2%
            "BARC":  {"weight": 0.020, "sector": "finance"},      # 2.0%
            "REL":   {"weight": 0.018, "sector": "media"},        # 1.8%
            "NG":    {"weight": 0.016, "sector": "utilities"},    # 1.6%
            "VOD":   {"weight": 0.014, "sector": "telecom"},      # 1.4%
        }
    },

    "dax40": {
        "constituents": {
            "SAP":   {"weight": 0.120, "sector": "tech"},         # 12.0%
            "SIE":   {"weight": 0.082, "sector": "industrials"},  # 8.2%
            "ALV":   {"weight": 0.075, "sector": "finance"},      # 7.5%
            "MUV2":  {"weight": 0.058, "sector": "finance"},      # 5.8%
            "DTE":   {"weight": 0.052, "sector": "telecom"},      # 5.2%
            "MBG":   {"weight": 0.048, "sector": "auto"},         # 4.8%
            "BMW":   {"weight": 0.042, "sector": "auto"},         # 4.2%
            "RWE":   {"weight": 0.038, "sector": "utilities"},    # 3.8%
            "BAS":   {"weight": 0.035, "sector": "materials"},    # 3.5%
            "BAYN":  {"weight": 0.032, "sector": "health"},       # 3.2%
            "VOW3":  {"weight": 0.028, "sector": "auto"},         # 2.8%
            "DBK":   {"weight": 0.025, "sector": "finance"},      # 2.5%
            "HEN3":  {"weight": 0.022, "sector": "consumer"},     # 2.2%
            "ADS":   {"weight": 0.020, "sector": "consumer"},     # 2.0%
            "IFX":   {"weight": 0.018, "sector": "semiconductors"},# 1.8%
        }
    },

    "cac40": {
        "constituents": {
            "MC.PA":  {"weight": 0.115, "sector": "luxury"},      # 11.5%
            "TTE":    {"weight": 0.082, "sector": "energy"},      # 8.2%
            "SAN.PA": {"weight": 0.062, "sector": "health"},      # 6.2%
            "AI.PA":  {"weight": 0.058, "sector": "industrials"}, # 5.8%
            "BNP.PA": {"weight": 0.052, "sector": "finance"},     # 5.2%
            "ACA.PA": {"weight": 0.042, "sector": "finance"},     # 4.2%
            "SU.PA":  {"weight": 0.038, "sector": "energy"},      # 3.8%
            "OR.PA":  {"weight": 0.036, "sector": "consumer"},    # 3.6%
            "CS.PA":  {"weight": 0.032, "sector": "finance"},     # 3.2%
            "DG.PA":  {"weight": 0.028, "sector": "utilities"},   # 2.8%
            "KER.PA": {"weight": 0.025, "sector": "luxury"},      # 2.5%
            "RI.PA":  {"weight": 0.022, "sector": "consumer"},    # 2.2%
            "VIE.PA": {"weight": 0.018, "sector": "utilities"},   # 1.8%
            "WLN.PA": {"weight": 0.015, "sector": "retail"},      # 1.5%
            "EN.PA":  {"weight": 0.014, "sector": "industrials"}, # 1.4%
        }
    },

    "eurostoxx50": {
        "constituents": {
            "SAP":    {"weight": 0.072, "sector": "tech"},        # 7.2%
            "MC.PA":  {"weight": 0.068, "sector": "luxury"},      # 6.8%
            "ASML":   {"weight": 0.065, "sector": "semiconductors"},# 6.5%
            "SIE":    {"weight": 0.050, "sector": "industrials"}, # 5.0%
            "TTE":    {"weight": 0.045, "sector": "energy"},      # 4.5%
            "ALV":    {"weight": 0.042, "sector": "finance"},     # 4.2%
            "SAN.PA": {"weight": 0.038, "sector": "health"},      # 3.8%
            "BNP.PA": {"weight": 0.036, "sector": "finance"},     # 3.6%
            "AI.PA":  {"weight": 0.032, "sector": "industrials"}, # 3.2%
            "MUV2":   {"weight": 0.028, "sector": "finance"},     # 2.8%
            "OR.PA":  {"weight": 0.025, "sector": "consumer"},    # 2.5%
            "IFX":    {"weight": 0.022, "sector": "semiconductors"},# 2.2%
            "DTE":    {"weight": 0.020, "sector": "telecom"},     # 2.0%
            "ABI.BR": {"weight": 0.018, "sector": "consumer"},    # 1.8%
            "ENEL":   {"weight": 0.016, "sector": "utilities"},   # 1.6%
        }
    },

    "aex": {
        "constituents": {
            "ASML":   {"weight": 0.210, "sector": "semiconductors"},# 21.0%
            "SHEL":   {"weight": 0.120, "sector": "energy"},      # 12.0%
            "UL":     {"weight": 0.085, "sector": "consumer"},    # 8.5%
            "ING":    {"weight": 0.065, "sector": "finance"},     # 6.5%
            "PHIA":   {"weight": 0.055, "sector": "health"},      # 5.5%
            "AD.AS":  {"weight": 0.045, "sector": "retail"},      # 4.5%
            "NN.AS":  {"weight": 0.038, "sector": "finance"},     # 3.8%
            "AKZA.AS":{"weight": 0.032, "sector": "materials"},   # 3.2%
            "WKL.AS": {"weight": 0.028, "sector": "industrials"}, # 2.8%
            "HEIA.AS":{"weight": 0.025, "sector": "consumer"},    # 2.5%
        }
    },

    "ibex35": {
        "constituents": {
            "SAN":    {"weight": 0.155, "sector": "finance"},     # 15.5%
            "IBE":    {"weight": 0.098, "sector": "utilities"},   # 9.8%
            "ITX":    {"weight": 0.090, "sector": "retail"},      # 9.0%
            "TEF":    {"weight": 0.072, "sector": "telecom"},     # 7.2%
            "BBVA":   {"weight": 0.068, "sector": "finance"},     # 6.8%
            "REP":    {"weight": 0.052, "sector": "energy"},      # 5.2%
            "ACS.MC": {"weight": 0.038, "sector": "industrials"}, # 3.8%
            "FER.MC": {"weight": 0.032, "sector": "industrials"}, # 3.2%
            "ELE.MC": {"weight": 0.028, "sector": "utilities"},   # 2.8%
            "MAP.MC": {"weight": 0.022, "sector": "finance"},     # 2.2%
        }
    },

    "mib": {
        "constituents": {
            "ENEL.MI": {"weight": 0.120, "sector": "utilities"},   # 12.0%
            "ISP.MI":  {"weight": 0.098, "sector": "finance"},     # 9.8%
            "ENI.MI":  {"weight": 0.085, "sector": "energy"},      # 8.5%
            "UCG.MI":  {"weight": 0.075, "sector": "finance"},     # 7.5%
            "STM.MI":  {"weight": 0.062, "sector": "semiconductors"},# 6.2%
            "TIT.MI":  {"weight": 0.042, "sector": "telecom"},     # 4.2%
            "RACE.MI": {"weight": 0.038, "sector": "auto"},        # 3.8%
            "LDO.MI":  {"weight": 0.032, "sector": "industrials"}, # 3.2%
            "G.MI":    {"weight": 0.028, "sector": "finance"},     # 2.8%
            "MB.MI":   {"weight": 0.022, "sector": "finance"},     # 2.2%
        }
    },

    "omxs30": {
        "constituents": {
            "VOLV-B.ST": {"weight": 0.105, "sector": "industrials"},# 10.5%
            "ASSA-B.ST": {"weight": 0.088, "sector": "industrials"},# 8.8%
            "AZN":       {"weight": 0.075, "sector": "health"},    # 7.5%
            "SEB-A.ST":  {"weight": 0.065, "sector": "finance"},   # 6.5%
            "SWED-A.ST": {"weight": 0.058, "sector": "finance"},   # 5.8%
            "HM-B.ST":   {"weight": 0.052, "sector": "retail"},    # 5.2%
            "ATCO-A.ST": {"weight": 0.045, "sector": "industrials"},# 4.5%
            "SAND.ST":   {"weight": 0.038, "sector": "industrials"},# 3.8%
            "NDA-SE.ST": {"weight": 0.035, "sector": "finance"},   # 3.5%
            "ERIC-B.ST": {"weight": 0.030, "sector": "tech"},      # 3.0%
        }
    },

    "smi": {
        "constituents": {
            "NESN.SW": {"weight": 0.185, "sector": "consumer"},   # 18.5%
            "ROG.SW":  {"weight": 0.152, "sector": "health"},     # 15.2%
            "NOVN.SW": {"weight": 0.140, "sector": "health"},     # 14.0%
            "UBS":     {"weight": 0.062, "sector": "finance"},    # 6.2%
            "ABBN.SW": {"weight": 0.055, "sector": "industrials"},# 5.5%
            "ZURN.SW": {"weight": 0.048, "sector": "finance"},    # 4.8%
            "SIKA.SW": {"weight": 0.042, "sector": "materials"},  # 4.2%
            "LONN.SW": {"weight": 0.038, "sector": "industrials"},# 3.8%
            "GEBN.SW": {"weight": 0.032, "sector": "finance"},    # 3.2%
            "CSGN.SW": {"weight": 0.025, "sector": "finance"},    # 2.5%
        }
    },

    # ── Asia-Pacific ──────────────────────────────────────────────────────────

    "nikkei225": {
        "constituents": {
            "TM":    {"weight": 0.082, "sector": "auto"},         # 8.2%
            "SONY":  {"weight": 0.065, "sector": "tech"},         # 6.5%
            "MUFG":  {"weight": 0.055, "sector": "finance"},      # 5.5%
            "SFT":   {"weight": 0.048, "sector": "tech"},         # 4.8% (SoftBank)
            "FAST":  {"weight": 0.042, "sector": "retail"},       # 4.2% (Fast Retailing)
            "TKY":   {"weight": 0.038, "sector": "industrials"},  # 3.8% (Keyence)
            "SMC":   {"weight": 0.035, "sector": "industrials"},  # 3.5%
            "FANUY": {"weight": 0.028, "sector": "industrials"},  # 2.8% (Fanuc)
            "NMR":   {"weight": 0.022, "sector": "finance"},      # 2.2%
            "HTHIY": {"weight": 0.018, "sector": "tech"},         # 1.8% (Hitachi)
        }
    },

    "hangseng": {
        "constituents": {
            "BABA":   {"weight": 0.095, "sector": "tech"},        # 9.5%
            "TCEHY":  {"weight": 0.088, "sector": "tech"},        # 8.8%
            "HSBC":   {"weight": 0.065, "sector": "finance"},     # 6.5%
            "9988.HK":{"weight": 0.055, "sector": "tech"},        # 5.5%
            "0700.HK":{"weight": 0.052, "sector": "tech"},        # 5.2% (Tencent HK)
            "1398.HK":{"weight": 0.042, "sector": "finance"},     # 4.2% (ICBC)
            "3988.HK":{"weight": 0.038, "sector": "finance"},     # 3.8% (BOC)
            "941.HK": {"weight": 0.035, "sector": "telecom"},     # 3.5% (China Mobile)
            "2318.HK":{"weight": 0.028, "sector": "finance"},     # 2.8% (Ping An)
            "388.HK": {"weight": 0.022, "sector": "finance"},     # 2.2% (HKEX)
        }
    },

    "csi300": {
        "constituents": {
            "BABA":    {"weight": 0.075, "sector": "tech"},       # 7.5%
            "PDD":     {"weight": 0.058, "sector": "consumer"},   # 5.8%
            "JD":      {"weight": 0.045, "sector": "consumer"},   # 4.5%
            "BIDU":    {"weight": 0.038, "sector": "tech"},       # 3.8%
            "NIO":     {"weight": 0.032, "sector": "auto"},       # 3.2%
            "XPEV":    {"weight": 0.025, "sector": "auto"},       # 2.5%
            "LI":      {"weight": 0.022, "sector": "auto"},       # 2.2%
            "601318.SS":{"weight": 0.040, "sector": "finance"},   # 4.0% (Ping An)
            "600519.SS":{"weight": 0.038, "sector": "consumer"},  # 3.8% (Kweichow Moutai)
            "000858.SZ":{"weight": 0.022, "sector": "consumer"},  # 2.2% (Wuliangye)
        }
    },

    "kospi": {
        "constituents": {
            "005930.KS": {"weight": 0.205, "sector": "semiconductors"},# 20.5% Samsung
            "000660.KS": {"weight": 0.062, "sector": "semiconductors"},# 6.2% SK Hynix
            "373220.KS": {"weight": 0.038, "sector": "auto"},          # 3.8% LG Energy
            "005380.KS": {"weight": 0.035, "sector": "auto"},          # 3.5% Hyundai
            "035420.KS": {"weight": 0.030, "sector": "tech"},          # 3.0% Naver
            "051910.KS": {"weight": 0.028, "sector": "materials"},     # 2.8% LG Chem
            "035720.KS": {"weight": 0.025, "sector": "tech"},          # 2.5% Kakao
            "005490.KS": {"weight": 0.022, "sector": "materials"},     # 2.2% POSCO
            "055550.KS": {"weight": 0.018, "sector": "finance"},       # 1.8% Shinhan
            "105560.KS": {"weight": 0.016, "sector": "finance"},       # 1.6% KB Financial
        }
    },

    "sensex": {
        "constituents": {
            "RELIANCE.NS": {"weight": 0.118, "sector": "energy"},  # 11.8%
            "TCS.NS":      {"weight": 0.060, "sector": "tech"},    # 6.0%
            "HDFCBANK.NS": {"weight": 0.055, "sector": "finance"}, # 5.5%
            "INFY":        {"weight": 0.048, "sector": "tech"},    # 4.8%
            "HDB":         {"weight": 0.042, "sector": "finance"}, # 4.2%
            "ICICIBANK.NS":{"weight": 0.038, "sector": "finance"}, # 3.8%
            "HINDUNILVR.NS":{"weight":0.032, "sector": "consumer"},# 3.2%
            "KOTAKBANK.NS":{"weight": 0.028, "sector": "finance"}, # 2.8%
            "ITC.NS":      {"weight": 0.025, "sector": "consumer"},# 2.5%
            "AXISBANK.NS": {"weight": 0.022, "sector": "finance"}, # 2.2%
        }
    },

    "twse": {
        "constituents": {
            "TSM":     {"weight": 0.300, "sector": "semiconductors"},# 30.0%
            "2330.TW": {"weight": 0.105, "sector": "semiconductors"},# 10.5% (TSMC local)
            "2317.TW": {"weight": 0.048, "sector": "tech"},          # 4.8% Hon Hai
            "2454.TW": {"weight": 0.038, "sector": "semiconductors"},# 3.8% MediaTek
            "2308.TW": {"weight": 0.032, "sector": "tech"},          # 3.2% Delta
            "2881.TW": {"weight": 0.025, "sector": "finance"},       # 2.5% Fubon
            "2412.TW": {"weight": 0.022, "sector": "telecom"},       # 2.2% Chunghwa
            "3008.TW": {"weight": 0.018, "sector": "tech"},          # 1.8% LARGAN
            "2882.TW": {"weight": 0.016, "sector": "finance"},       # 1.6% Cathay
            "1301.TW": {"weight": 0.014, "sector": "materials"},     # 1.4% Formosa
        }
    },

    "set": {
        "constituents": {
            "PTT.BK":  {"weight": 0.118, "sector": "energy"},     # 11.8%
            "AOT.BK":  {"weight": 0.082, "sector": "industrials"},# 8.2%
            "SCC.BK":  {"weight": 0.062, "sector": "materials"},  # 6.2%
            "CPALL.BK":{"weight": 0.052, "sector": "retail"},     # 5.2%
            "KBANK.BK":{"weight": 0.045, "sector": "finance"},    # 4.5%
            "PTTEP.BK":{"weight": 0.038, "sector": "energy"},     # 3.8%
            "BBL.BK":  {"weight": 0.032, "sector": "finance"},    # 3.2%
            "GULF.BK": {"weight": 0.028, "sector": "utilities"},  # 2.8%
            "TRUE.BK": {"weight": 0.022, "sector": "telecom"},    # 2.2%
            "BH.BK":   {"weight": 0.018, "sector": "health"},     # 1.8%
        }
    },

    "asx200": {
        "constituents": {
            "BHP":   {"weight": 0.102, "sector": "materials"},    # 10.2%
            "CBA":   {"weight": 0.098, "sector": "finance"},      # 9.8%
            "CSL":   {"weight": 0.068, "sector": "health"},       # 6.8%
            "NAB":   {"weight": 0.052, "sector": "finance"},      # 5.2%
            "WBC":   {"weight": 0.048, "sector": "finance"},      # 4.8%
            "ANZ":   {"weight": 0.043, "sector": "finance"},      # 4.3%
            "WES":   {"weight": 0.038, "sector": "retail"},       # 3.8%
            "MQG":   {"weight": 0.035, "sector": "finance"},      # 3.5%
            "GMG":   {"weight": 0.021, "sector": "property"},     # 2.1%
            "WOW":   {"weight": 0.020, "sector": "retail"},       # 2.0%
            "FMG":   {"weight": 0.019, "sector": "materials"},    # 1.9%
            "RIO":   {"weight": 0.018, "sector": "materials"},    # 1.8%
            "XRO":   {"weight": 0.014, "sector": "tech"},         # 1.4%
            "TLS":   {"weight": 0.012, "sector": "telecom"},      # 1.2%
            "ALL":   {"weight": 0.010, "sector": "consumer"},     # 1.0%
        }
    },

    "nzx50": {
        "constituents": {
            "FPH.NZ":  {"weight": 0.148, "sector": "health"},     # 14.8%
            "ATM.NZ":  {"weight": 0.102, "sector": "retail"},     # 10.2%
            "SPK.NZ":  {"weight": 0.082, "sector": "telecom"},    # 8.2%
            "MCY.NZ":  {"weight": 0.065, "sector": "utilities"},  # 6.5%
            "CEN.NZ":  {"weight": 0.058, "sector": "utilities"},  # 5.8%
            "MEL.NZ":  {"weight": 0.052, "sector": "utilities"},  # 5.2%
            "SKC.NZ":  {"weight": 0.042, "sector": "consumer"},   # 4.2%
            "POT.NZ":  {"weight": 0.035, "sector": "finance"},    # 3.5%
            "PCT.NZ":  {"weight": 0.028, "sector": "property"},   # 2.8%
            "AIR.NZ":  {"weight": 0.022, "sector": "industrials"},# 2.2%
        }
    },

    # ── Middle East & Africa ──────────────────────────────────────────────────

    "tadawul": {
        "constituents": {
            "2222.SR": {"weight": 0.195, "sector": "energy"},     # 19.5% Saudi Aramco
            "1180.SR": {"weight": 0.082, "sector": "finance"},    # 8.2%  Al Rajhi
            "2010.SR": {"weight": 0.062, "sector": "materials"},  # 6.2%  SABIC
            "1120.SR": {"weight": 0.048, "sector": "finance"},    # 4.8%  Al Rajhi Bank
            "2380.SR": {"weight": 0.038, "sector": "telecom"},    # 3.8%  STC
            "4010.SR": {"weight": 0.032, "sector": "finance"},    # 3.2%  NCB
            "2030.SR": {"weight": 0.025, "sector": "energy"},     # 2.5%  SABIC petrochem
            "1050.SR": {"weight": 0.020, "sector": "finance"},    # 2.0%  Riyad Bank
            "2350.SR": {"weight": 0.016, "sector": "telecom"},    # 1.6%  Mobily
            "4030.SR": {"weight": 0.014, "sector": "finance"},    # 1.4%  Alinma Bank
        }
    },

    "jse": {
        "constituents": {
            "NPN.JO": {"weight": 0.148, "sector": "tech"},        # 14.8% Naspers
            "BHP":    {"weight": 0.098, "sector": "materials"},   # 9.8%
            "SOL.JO": {"weight": 0.062, "sector": "energy"},      # 6.2%  Sasol
            "AGL.JO": {"weight": 0.055, "sector": "materials"},   # 5.5%  Anglo American
            "GFI":    {"weight": 0.042, "sector": "materials"},   # 4.2%  Gold Fields
            "FSR.JO": {"weight": 0.038, "sector": "finance"},     # 3.8%  Firstrand
            "SBK.JO": {"weight": 0.035, "sector": "finance"},     # 3.5%  Standard Bank
            "MTN.JO": {"weight": 0.030, "sector": "telecom"},     # 3.0%  MTN Group
            "SLM.JO": {"weight": 0.025, "sector": "finance"},     # 2.5%  Sanlam
            "NED.JO": {"weight": 0.020, "sector": "finance"},     # 2.0%  Nedbank
        }
    },
}
