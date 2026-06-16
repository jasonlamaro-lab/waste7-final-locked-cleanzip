"""
Deep constituent universes for each equity market. The monthly refresh picks
the TOP holdings by market cap whose cumulative weight >= PIVOT_THRESHOLD.
Ordered by exchange open time (earliest first).
"""

PIVOT_THRESHOLD = 0.80

UNIVERSE = {
    "asx200": {
        "opens_utc_hour": 23,
        "tickers": [
            "BHP.AX","CBA.AX","CSL.AX","WBC.AX","NAB.AX","ANZ.AX","WES.AX","MQG.AX",
            "WDS.AX","RIO.AX","TLS.AX","GMG.AX","TCL.AX","WOW.AX","FMG.AX","ALL.AX",
            "STO.AX","REA.AX","COL.AX","QBE.AX","XRO.AX","IAG.AX","RMD.AX","SUN.AX",
            "JHX.AX","ASX.AX","SCG.AX","MPL.AX","ORG.AX","EDV.AX"
        ],
        "sectors": {
            "BHP.AX":"materials","CBA.AX":"finance","CSL.AX":"health","WBC.AX":"finance",
            "NAB.AX":"finance","ANZ.AX":"finance","WES.AX":"retail","MQG.AX":"finance",
            "WDS.AX":"energy","RIO.AX":"materials","TLS.AX":"telecom","GMG.AX":"reit",
            "TCL.AX":"infra","WOW.AX":"retail","FMG.AX":"materials","ALL.AX":"gaming",
            "STO.AX":"energy","REA.AX":"tech","COL.AX":"retail","QBE.AX":"finance",
            "XRO.AX":"tech","IAG.AX":"finance","RMD.AX":"health","SUN.AX":"finance",
            "JHX.AX":"materials","ASX.AX":"finance","SCG.AX":"reit","MPL.AX":"health",
            "ORG.AX":"energy","EDV.AX":"retail"
        }
    },
    "nzx50": {
        "opens_utc_hour": 22,
        "tickers": [
            "FPH.NZ","ATM.NZ","SPK.NZ","AIA.NZ","MEL.NZ","CEN.NZ","EBO.NZ","MFT.NZ",
            "FBU.NZ","MCY.NZ","RYM.NZ","IFT.NZ","CNU.NZ","GNE.NZ","CHI.NZ"
        ],
        "sectors": {
            "FPH.NZ":"health","ATM.NZ":"retail","SPK.NZ":"telecom","AIA.NZ":"infra",
            "MEL.NZ":"utilities","CEN.NZ":"utilities","EBO.NZ":"health","MFT.NZ":"logistics",
            "FBU.NZ":"materials","MCY.NZ":"utilities","RYM.NZ":"health","IFT.NZ":"infra",
            "CNU.NZ":"telecom","GNE.NZ":"utilities","CHI.NZ":"utilities"
        }
    },
    "nikkei225": {
        "opens_utc_hour": 0,
        "tickers": [
            "7203.T","6758.T","8306.T","9432.T","8316.T","6861.T","8411.T","9984.T",
            "6954.T","6594.T","7267.T","4063.T","8035.T","6098.T","6902.T","6971.T",
            "4502.T","9433.T","6273.T","7974.T","6367.T","4661.T","8001.T","8802.T"
        ],
        "sectors": {
            "7203.T":"auto","6758.T":"tech","8306.T":"finance","9432.T":"telecom",
            "8316.T":"finance","6861.T":"tech","8411.T":"finance","9984.T":"tech",
            "6954.T":"industrials","6594.T":"industrials","7267.T":"auto","4063.T":"materials",
            "8035.T":"industrials","6098.T":"services","6902.T":"auto","6971.T":"tech",
            "4502.T":"health","9433.T":"telecom","6273.T":"industrials","7974.T":"gaming",
            "6367.T":"industrials","4661.T":"services","8001.T":"trading","8802.T":"reit"
        }
    },
    "kospi": {
        "opens_utc_hour": 0,
        "tickers": [
            "005930.KS","000660.KS","207940.KS","005380.KS","035420.KS","005490.KS",
            "035720.KS","051910.KS","028260.KS","105560.KS","055550.KS","086790.KS",
            "012330.KS","006400.KS","066570.KS","003550.KS","032830.KS","017670.KS"
        ],
        "sectors": {
            "005930.KS":"tech","000660.KS":"tech","207940.KS":"health","005380.KS":"auto",
            "035420.KS":"tech","005490.KS":"materials","035720.KS":"tech","051910.KS":"chemicals",
            "028260.KS":"trading","105560.KS":"finance","055550.KS":"finance","086790.KS":"finance",
            "012330.KS":"auto","006400.KS":"tech","066570.KS":"tech","003550.KS":"trading",
            "032830.KS":"finance","017670.KS":"telecom"
        }
    },
    "hangseng": {
        "opens_utc_hour": 1,
        "tickers": [
            "0700.HK","9988.HK","0939.HK","3690.HK","2318.HK","1398.HK","0005.HK","0941.HK",
            "0883.HK","0386.HK","0857.HK","1288.HK","0002.HK","0003.HK","2388.HK","1299.HK",
            "0388.HK","1109.HK","2331.HK","1093.HK"
        ],
        "sectors": {
            "0700.HK":"tech","9988.HK":"tech","0939.HK":"finance","3690.HK":"tech",
            "2318.HK":"finance","1398.HK":"finance","0005.HK":"finance","0941.HK":"telecom",
            "0883.HK":"energy","0386.HK":"energy","0857.HK":"energy","1288.HK":"finance",
            "0002.HK":"utilities","0003.HK":"utilities","2388.HK":"finance","1299.HK":"finance",
            "0388.HK":"finance","1109.HK":"reit","2331.HK":"retail","1093.HK":"health"
        }
    },
    "csi300": {
        "opens_utc_hour": 1,
        "tickers": [
            "600519.SS","601398.SS","601318.SS","600036.SS","601288.SS","601988.SS",
            "600276.SS","600030.SS","601166.SS","000858.SZ","000333.SZ","300750.SZ",
            "600900.SS","601628.SS","601668.SS"
        ],
        "sectors": {
            "600519.SS":"consumer","601398.SS":"finance","601318.SS":"finance",
            "600036.SS":"finance","601288.SS":"finance","601988.SS":"finance",
            "600276.SS":"health","600030.SS":"finance","601166.SS":"finance",
            "000858.SZ":"consumer","000333.SZ":"industrials","300750.SZ":"tech",
            "600900.SS":"utilities","601628.SS":"finance","601668.SS":"construction"
        }
    },
    "twse": {
        "opens_utc_hour": 1,
        "tickers": [
            "2330.TW","2454.TW","2317.TW","2303.TW","2412.TW","2881.TW","1301.TW","2308.TW",
            "2882.TW","1303.TW","2886.TW","2891.TW","3711.TW","2002.TW","3008.TW"
        ],
        "sectors": {
            "2330.TW":"tech","2454.TW":"tech","2317.TW":"tech","2303.TW":"tech",
            "2412.TW":"telecom","2881.TW":"finance","1301.TW":"chemicals","2308.TW":"tech",
            "2882.TW":"finance","1303.TW":"chemicals","2886.TW":"finance","2891.TW":"finance",
            "3711.TW":"tech","2002.TW":"materials","3008.TW":"tech"
        }
    },
    "set": {
        "opens_utc_hour": 3,
        "tickers": [
            "PTT.BK","AOT.BK","SCC.BK","CPALL.BK","ADVANC.BK","KBANK.BK","SCB.BK",
            "BBL.BK","GULF.BK","BDMS.BK","DELTA.BK","PTTEP.BK","MINT.BK","BH.BK"
        ],
        "sectors": {
            "PTT.BK":"energy","AOT.BK":"infra","SCC.BK":"materials","CPALL.BK":"retail",
            "ADVANC.BK":"telecom","KBANK.BK":"finance","SCB.BK":"finance","BBL.BK":"finance",
            "GULF.BK":"utilities","BDMS.BK":"health","DELTA.BK":"tech","PTTEP.BK":"energy",
            "MINT.BK":"services","BH.BK":"health"
        }
    },
    "sensex": {
        "opens_utc_hour": 3,
        "tickers": [
            "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS","HINDUNILVR.NS",
            "SBIN.NS","BHARTIARTL.NS","ITC.NS","KOTAKBANK.NS","LT.NS","BAJFINANCE.NS",
            "AXISBANK.NS","ASIANPAINT.NS","MARUTI.NS","SUNPHARMA.NS","TITAN.NS","WIPRO.NS"
        ],
        "sectors": {
            "RELIANCE.NS":"energy","TCS.NS":"tech","HDFCBANK.NS":"finance","INFY.NS":"tech",
            "ICICIBANK.NS":"finance","HINDUNILVR.NS":"consumer","SBIN.NS":"finance",
            "BHARTIARTL.NS":"telecom","ITC.NS":"consumer","KOTAKBANK.NS":"finance",
            "LT.NS":"construction","BAJFINANCE.NS":"finance","AXISBANK.NS":"finance",
            "ASIANPAINT.NS":"chemicals","MARUTI.NS":"auto","SUNPHARMA.NS":"health",
            "TITAN.NS":"retail","WIPRO.NS":"tech"
        }
    },
    "tadawul": {
        "opens_utc_hour": 7,
        "tickers": [
            "2222.SR","1180.SR","2010.SR","1120.SR","1211.SR","7010.SR","2030.SR","1150.SR"
        ],
        "sectors": {
            "2222.SR":"energy","1180.SR":"finance","2010.SR":"chemicals","1120.SR":"finance",
            "1211.SR":"materials","7010.SR":"telecom","2030.SR":"chemicals","1150.SR":"finance"
        }
    },
    "jse": {
        "opens_utc_hour": 7,
        "tickers": [
            "NPN.JO","PRX.JO","BHG.JO","CFR.JO","AGL.JO","FSR.JO","SBK.JO","SOL.JO",
            "MTN.JO","ABG.JO","VOD.JO","CPI.JO","SHP.JO","NED.JO"
        ],
        "sectors": {
            "NPN.JO":"tech","PRX.JO":"tech","BHG.JO":"materials","CFR.JO":"retail",
            "AGL.JO":"materials","FSR.JO":"finance","SBK.JO":"finance","SOL.JO":"energy",
            "MTN.JO":"telecom","ABG.JO":"finance","VOD.JO":"telecom","CPI.JO":"finance",
            "SHP.JO":"retail","NED.JO":"finance"
        }
    },
    "ftse100": {
        "opens_utc_hour": 8,
        "tickers": [
            "SHEL.L","AZN.L","HSBA.L","ULVR.L","BP.L","GSK.L","RIO.L","LLOY.L","BARC.L",
            "LSEG.L","NG.L","DGE.L","REL.L","BATS.L","CPG.L","VOD.L","RKT.L","IMB.L",
            "AV.L","PRU.L","GLEN.L","STAN.L","ABDN.L","BT-A.L"
        ],
        "sectors": {
            "SHEL.L":"energy","AZN.L":"health","HSBA.L":"finance","ULVR.L":"consumer",
            "BP.L":"energy","GSK.L":"health","RIO.L":"materials","LLOY.L":"finance",
            "BARC.L":"finance","LSEG.L":"finance","NG.L":"utilities","DGE.L":"consumer",
            "REL.L":"media","BATS.L":"consumer","CPG.L":"services","VOD.L":"telecom",
            "RKT.L":"consumer","IMB.L":"consumer","AV.L":"finance","PRU.L":"finance",
            "GLEN.L":"materials","STAN.L":"finance","ABDN.L":"finance","BT-A.L":"telecom"
        }
    },
    "dax40": {
        "opens_utc_hour": 8,
        "tickers": [
            "SAP.DE","SIE.DE","ALV.DE","DTE.DE","MBG.DE","IFX.DE","AIR.DE","BMW.DE","BAS.DE",
            "MUV2.DE","BAYN.DE","DB1.DE","VOW3.DE","ADS.DE","RWE.DE","HEI.DE","ENR.DE",
            "DBK.DE","FRE.DE","DHL.DE","HEN3.DE","MRK.DE"
        ],
        "sectors": {
            "SAP.DE":"tech","SIE.DE":"industrials","ALV.DE":"finance","DTE.DE":"telecom",
            "MBG.DE":"auto","IFX.DE":"tech","AIR.DE":"aerospace","BMW.DE":"auto",
            "BAS.DE":"chemicals","MUV2.DE":"finance","BAYN.DE":"chemicals","DB1.DE":"finance",
            "VOW3.DE":"auto","ADS.DE":"retail","RWE.DE":"utilities","HEI.DE":"materials",
            "ENR.DE":"industrials","DBK.DE":"finance","FRE.DE":"health","DHL.DE":"logistics",
            "HEN3.DE":"consumer","MRK.DE":"health"
        }
    },
    "cac40": {
        "opens_utc_hour": 8,
        "tickers": [
            "MC.PA","TTE.PA","OR.PA","RMS.PA","SU.PA","AIR.PA","CDI.PA","SAN.PA","BNP.PA",
            "AI.PA","KER.PA","EL.PA","CS.PA","ACA.PA","DG.PA","STM.PA","VIV.PA","SAF.PA",
            "BN.PA","ORA.PA","VIE.PA"
        ],
        "sectors": {
            "MC.PA":"consumer","TTE.PA":"energy","OR.PA":"consumer","RMS.PA":"consumer",
            "SU.PA":"industrials","AIR.PA":"aerospace","CDI.PA":"consumer","SAN.PA":"health",
            "BNP.PA":"finance","AI.PA":"industrials","KER.PA":"consumer","EL.PA":"consumer",
            "CS.PA":"finance","ACA.PA":"finance","DG.PA":"industrials","STM.PA":"tech",
            "VIV.PA":"media","SAF.PA":"aerospace","BN.PA":"consumer","ORA.PA":"telecom",
            "VIE.PA":"utilities"
        }
    },
    "eurostoxx50": {
        "opens_utc_hour": 8,
        "tickers": [
            "ASML.AS","SAP.DE","MC.PA","LVMH.PA","TTE.PA","SIE.DE","NESN.SW",
            "NOVN.SW","ALV.DE","ADYEN.AS","AI.PA","IBE.MC","ENEL.MI","PHIA.AS","ITX.MC",
            "AD.AS","MBG.DE","BMW.DE","DTE.DE"
        ],
        "sectors": {
            "ASML.AS":"tech","SAP.DE":"tech","MC.PA":"consumer","LVMH.PA":"consumer",
            "TTE.PA":"energy","SIE.DE":"industrials","NESN.SW":"consumer",
            "NOVN.SW":"health","ALV.DE":"finance","ADYEN.AS":"tech","AI.PA":"industrials",
            "IBE.MC":"utilities","ENEL.MI":"utilities","PHIA.AS":"health","ITX.MC":"retail",
            "AD.AS":"retail","MBG.DE":"auto","BMW.DE":"auto","DTE.DE":"telecom"
        }
    },
    "aex": {
        "opens_utc_hour": 8,
        "tickers": [
            "ASML.AS","UNA.AS","ING.AS","ADYEN.AS","AD.AS","PHIA.AS","HEIA.AS",
            "WKL.AS","MT.AS","DSM.AS","AKZA.AS","REN.AS","ASM.AS"
        ],
        "sectors": {
            "ASML.AS":"tech","UNA.AS":"consumer","ING.AS":"finance","ADYEN.AS":"tech",
            "AD.AS":"retail","PHIA.AS":"health","HEIA.AS":"consumer","WKL.AS":"services",
            "MT.AS":"materials","DSM.AS":"chemicals","AKZA.AS":"chemicals","REN.AS":"services",
            "ASM.AS":"tech"
        }
    },
    "ibex35": {
        "opens_utc_hour": 8,
        "tickers": [
            "SAN.MC","IBE.MC","ITX.MC","BBVA.MC","REP.MC","TEF.MC","AMS.MC","MAP.MC",
            "FER.MC","ENG.MC","CABK.MC","AENA.MC"
        ],
        "sectors": {
            "SAN.MC":"finance","IBE.MC":"utilities","ITX.MC":"retail","BBVA.MC":"finance",
            "REP.MC":"energy","TEF.MC":"telecom","AMS.MC":"health","MAP.MC":"finance",
            "FER.MC":"construction","ENG.MC":"utilities","CABK.MC":"finance","AENA.MC":"infra"
        }
    },
    "mib": {
        "opens_utc_hour": 8,
        "tickers": [
            "ENEL.MI","ISP.MI","ENI.MI","UCG.MI","STLA.MI","STM.MI","G.MI","MONC.MI",
            "FBK.MI","RACE.MI","PST.MI","SRG.MI","TRN.MI"
        ],
        "sectors": {
            "ENEL.MI":"utilities","ISP.MI":"finance","ENI.MI":"energy","UCG.MI":"finance",
            "STLA.MI":"auto","STM.MI":"tech","G.MI":"finance","MONC.MI":"consumer",
            "FBK.MI":"finance","RACE.MI":"auto","PST.MI":"finance","SRG.MI":"utilities",
            "TRN.MI":"utilities"
        }
    },
    "smi": {
        "opens_utc_hour": 8,
        "tickers": [
            "NESN.SW","NOVN.SW","UBSG.SW","ZURN.SW","ABBN.SW","CFR.SW","GIVN.SW",
            "LONN.SW","SLHN.SW","HOLN.SW","SREN.SW","SGSN.SW"
        ],
        "sectors": {
            "NESN.SW":"consumer","NOVN.SW":"health","UBSG.SW":"finance","ZURN.SW":"finance",
            "ABBN.SW":"industrials","CFR.SW":"consumer","GIVN.SW":"chemicals","LONN.SW":"health",
            "SLHN.SW":"finance","HOLN.SW":"materials","SREN.SW":"finance","SGSN.SW":"services"
        }
    },
    "omxs30": {
        "opens_utc_hour": 8,
        "tickers": [
            "VOLV-B.ST","ASSA-B.ST","AZN.ST","SEB-A.ST","HEXA-B.ST","INVE-B.ST","ERIC-B.ST",
            "SAND.ST","EQT.ST","SCA-B.ST","ATCO-A.ST","TELIA.ST","NDA-SE.ST","SHB-A.ST"
        ],
        "sectors": {
            "VOLV-B.ST":"auto","ASSA-B.ST":"industrials","AZN.ST":"health","SEB-A.ST":"finance",
            "HEXA-B.ST":"industrials","INVE-B.ST":"finance","ERIC-B.ST":"tech",
            "SAND.ST":"industrials","EQT.ST":"finance","SCA-B.ST":"materials",
            "ATCO-A.ST":"industrials","TELIA.ST":"telecom","NDA-SE.ST":"finance","SHB-A.ST":"finance"
        }
    },
    "bovespa": {
        "opens_utc_hour": 13,
        "tickers": [
            "VALE3.SA","PETR4.SA","ITUB4.SA","BBDC4.SA","ABEV3.SA","B3SA3.SA","WEGE3.SA",
            "ELET3.SA","RENT3.SA","SUZB3.SA","BBAS3.SA","JBSS3.SA","LREN3.SA","HAPV3.SA"
        ],
        "sectors": {
            "VALE3.SA":"materials","PETR4.SA":"energy","ITUB4.SA":"finance","BBDC4.SA":"finance",
            "ABEV3.SA":"consumer","B3SA3.SA":"finance","WEGE3.SA":"industrials",
            "ELET3.SA":"utilities","RENT3.SA":"services","SUZB3.SA":"materials",
            "BBAS3.SA":"finance","JBSS3.SA":"consumer","LREN3.SA":"retail","HAPV3.SA":"health"
        }
    },
    "tsx": {
        "opens_utc_hour": 13,
        "tickers": [
            "RY.TO","TD.TO","ENB.TO","CNR.TO","BMO.TO","BNS.TO","SU.TO","CP.TO","CM.TO",
            "SHOP.TO","MFC.TO","BN.TO","ABX.TO","TRI.TO","FFH.TO","CNQ.TO","T.TO","L.TO",
            "WCN.TO","POW.TO","GIB-A.TO","ATD.TO"
        ],
        "sectors": {
            "RY.TO":"finance","TD.TO":"finance","ENB.TO":"energy","CNR.TO":"logistics",
            "BMO.TO":"finance","BNS.TO":"finance","SU.TO":"energy","CP.TO":"logistics",
            "CM.TO":"finance","SHOP.TO":"tech","MFC.TO":"finance","BN.TO":"finance",
            "ABX.TO":"materials","TRI.TO":"media","FFH.TO":"finance","CNQ.TO":"energy",
            "T.TO":"telecom","L.TO":"retail","WCN.TO":"services","POW.TO":"finance",
            "GIB-A.TO":"tech","ATD.TO":"retail"
        }
    },
    "sp500": {
        "opens_utc_hour": 14,
        "tickers": [
            "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","BRK-B","UNH","JPM",
            "V","XOM","JNJ","WMT","LLY","MA","PG","AVGO","HD","ORCL","CVX","MRK",
            "ABBV","COST","PEP","KO","ADBE","BAC","CRM","TMO","MCD","LIN","NFLX",
            "AMD","ACN","ABT","CSCO","WFC","DIS","TXN","PM","DHR","VZ","NEE","NKE",
            "CMCSA","INTC","QCOM","AMGN","T"
        ],
        "sectors": {
            "AAPL":"tech","MSFT":"tech","NVDA":"tech","AMZN":"retail","GOOGL":"tech",
            "META":"tech","TSLA":"auto","BRK-B":"finance","UNH":"health","JPM":"finance",
            "V":"finance","XOM":"energy","JNJ":"health","WMT":"retail","LLY":"health",
            "MA":"finance","PG":"consumer","AVGO":"tech","HD":"retail","ORCL":"tech",
            "CVX":"energy","MRK":"health","ABBV":"health","COST":"retail","PEP":"consumer",
            "KO":"consumer","ADBE":"tech","BAC":"finance","CRM":"tech","TMO":"health",
            "MCD":"consumer","LIN":"chemicals","NFLX":"media","AMD":"tech","ACN":"services",
            "ABT":"health","CSCO":"tech","WFC":"finance","DIS":"media","TXN":"tech",
            "PM":"consumer","DHR":"health","VZ":"telecom","NEE":"utilities","NKE":"retail",
            "CMCSA":"media","INTC":"tech","QCOM":"tech","AMGN":"health","T":"telecom"
        }
    },
    "nasdaq100": {
        "opens_utc_hour": 14,
        "tickers": [
            "AAPL","MSFT","NVDA","AMZN","GOOGL","GOOG","META","TSLA","AVGO","COST",
            "NFLX","PEP","ADBE","AMD","CSCO","TMUS","CMCSA","INTC","QCOM","AMGN",
            "TXN","HON","INTU","AMAT","BKNG","ISRG","VRTX","ADI","LRCX","REGN",
            "MU","PANW","KLAC","GILD","ADP","CDNS","SNPS","MDLZ","MRVL","CRWD"
        ],
        "sectors": {
            "AAPL":"tech","MSFT":"tech","NVDA":"tech","AMZN":"retail","GOOGL":"tech",
            "GOOG":"tech","META":"tech","TSLA":"auto","AVGO":"tech","COST":"retail",
            "NFLX":"media","PEP":"consumer","ADBE":"tech","AMD":"tech","CSCO":"tech",
            "TMUS":"telecom","CMCSA":"media","INTC":"tech","QCOM":"tech","AMGN":"health",
            "TXN":"tech","HON":"industrials","INTU":"tech","AMAT":"tech","BKNG":"services",
            "ISRG":"health","VRTX":"health","ADI":"tech","LRCX":"tech","REGN":"health",
            "MU":"tech","PANW":"tech","KLAC":"tech","GILD":"health","ADP":"services",
            "CDNS":"tech","SNPS":"tech","MDLZ":"consumer","MRVL":"tech","CRWD":"tech"
        }
    },
    "dowjones": {
        "opens_utc_hour": 14,
        "tickers": [
            "UNH","GS","MSFT","HD","CAT","AMGN","CRM","MCD","V","BA","AXP","TRV","HON",
            "JNJ","IBM","JPM","CVX","PG","AAPL","WMT","DIS","NKE","MRK","MMM","KO",
            "CSCO","VZ","INTC","DOW","WBA"
        ],
        "sectors": {
            "UNH":"health","GS":"finance","MSFT":"tech","HD":"retail","CAT":"industrials",
            "AMGN":"health","CRM":"tech","MCD":"consumer","V":"finance","BA":"aerospace",
            "AXP":"finance","TRV":"finance","HON":"industrials","JNJ":"health","IBM":"tech",
            "JPM":"finance","CVX":"energy","PG":"consumer","AAPL":"tech","WMT":"retail",
            "DIS":"media","NKE":"retail","MRK":"health","MMM":"industrials","KO":"consumer",
            "CSCO":"tech","VZ":"telecom","INTC":"tech","DOW":"chemicals","WBA":"retail"
        }
    },
}
