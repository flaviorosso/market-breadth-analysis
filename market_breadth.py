"""
Global Market Breadth Dashboard
================================

Um único script que:
  1. baixa os preços (yfinance) de vários mercados de ações, de ETFs de países e de cripto;
  2. calcula o breadth de tendência (% acima da MA) e de momentum (% RSI sobrecomprado/sobrevendido);
  3. calcula limites relativos (percentis do próprio histórico) e um estudo de eventos simples;
  4. gera o dashboard interativo (docs/index.html), um gráfico-resumo (docs/summary.png)
     e um histórico (docs/history.csv);
  5. envia tudo por e-mail (SMTP).

Uso:
    python market_breadth.py                # roda tudo e envia o e-mail
    python market_breadth.py --no-email     # só gera os arquivos
    python market_breadth.py --save-eml     # gera e salva o e-mail em docs/last_email.eml (teste)

Variáveis de ambiente para o e-mail (no GitHub: Settings > Secrets and variables > Actions):
    SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASS, EMAIL_TO (vírgulas p/ vários), EMAIL_FROM (opcional),
    DASHBOARD_URL (opcional, link do GitHub Pages)
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import smtplib
import sys
from email.message import EmailMessage
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

# =====================================================================
# 1. PARÂMETROS (ajuste fino aqui)
# =====================================================================
MA_DAYS = 17            # média curta do breadth (parâmetro de ajuste do projeto original)
RSI_DAYS = 14
RSI_OB, RSI_OS = 65, 35  # limites de sobrecompra / sobrevenda por ativo
FIXED_TOP, FIXED_BOTTOM = 90, 10   # limites clássicos do breadth
PCT_LOW, PCT_HIGH = 0.05, 0.95     # limites relativos: percentis do histórico de cada mercado
HISTORY = "5y"          # histórico baixado (para percentis e estudo de eventos)
PLOT_DAYS = 504         # ~2 anos de pregões nos gráficos
STALE_DAYS = 10         # ticker sem cotação há mais de N dias = considerado "morto"
FWD_HORIZONS = [5, 20, 60]  # dias à frente no estudo de eventos

OUT_DIR = Path(__file__).resolve().parent / "docs"
UA = {"User-Agent": "Mozilla/5.0 (market-breadth research script)"}

# ---------------------------------------------------------------------
# Listas fixas (usadas quando não há fonte automática, ou como reserva)
# Tickers que deixaram de existir aparecem no relatório como "sem dados".
# ---------------------------------------------------------------------
IBOV = [  # sem ETFs (BOVA11/SMAL11 removidos)
    "ABEV3", "ALOS3", "ALPA4", "AZZA3", "ASAI3", "AURE3", "B3SA3", "BBAS3", "BBDC3", "BBDC4",
    "BBSE3", "BEEF3", "BHIA3", "BPAC11", "BRAP4", "BRFS3", "BRKM5", "CASH3", "CBAV3", "MOTV3",
    "CMIG4", "CMIN3", "COGN3", "CPFE3", "CPLE6", "CSAN3", "CSMG3", "CSNA3", "CVCB3", "CYRE3",
    "DIRR3", "DXCO3", "ECOR3", "EGIE3", "ELET3", "ELET6", "EMBR3", "ENEV3", "ENGI11", "EQTL3",
    "EZTC3", "FLRY3", "GGBR4", "GMAT3", "GOAU4", "HAPV3", "HYPE3", "IGTI11", "IRBR3", "ITSA4",
    "ITUB4", "KLBN11", "LREN3", "LWSA3", "MDIA3", "MGLU3", "MOVI3", "MRFG3", "MRVE3", "MULT3",
    "PCAR3", "PETR3", "PETR4", "PETZ3", "PRIO3", "PSSA3", "RADL3", "RAIL3", "RAIZ4", "RDOR3",
    "RECV3", "RENT3", "BRAV3", "SANB11", "SBSP3", "SIMH3", "SLCE3", "SMTO3", "STBP3", "SUZB3",
    "TAEE11", "TIMS3", "TOTS3", "ISAE4", "UGPA3", "USIM5", "VALE3", "VAMO3", "VBBR3", "VIVA3",
    "VIVT3", "WEGE3", "YDUQ3", "MBRF3", "AXIA3", "AXIA6",
]
IBOV = [t + ".SA" for t in IBOV]

HSI = [
    "0001.HK", "0002.HK", "0003.HK", "0005.HK", "0006.HK", "0011.HK", "0012.HK", "0016.HK",
    "0017.HK", "0019.HK", "0027.HK", "0066.HK", "0101.HK", "0175.HK", "0241.HK", "0267.HK",
    "0285.HK", "0288.HK", "0291.HK", "0316.HK", "0322.HK", "0386.HK", "0388.HK", "0669.HK",
    "0688.HK", "0700.HK", "0762.HK", "0823.HK", "0836.HK", "0857.HK", "0868.HK", "0881.HK",
    "0883.HK", "0939.HK", "0941.HK", "0960.HK", "0968.HK", "0981.HK", "0992.HK", "1024.HK",
    "1038.HK", "1044.HK", "1088.HK", "1093.HK", "1099.HK", "1109.HK", "1113.HK", "1177.HK",
    "1211.HK", "1299.HK", "1378.HK", "1398.HK", "1810.HK", "1876.HK", "1928.HK", "1929.HK",
    "2015.HK", "2020.HK", "2269.HK", "2313.HK", "2318.HK", "2319.HK", "2331.HK", "2382.HK",
    "2388.HK", "2628.HK", "2688.HK", "2899.HK", "3690.HK", "3968.HK", "3988.HK", "6618.HK",
    "6690.HK", "9618.HK", "9633.HK", "9888.HK", "9988.HK", "9999.HK",
]

CHINA_A = [  # grandes ações A (amostra do CSI 300) — sem ETFs americanos
    "600519.SS", "601318.SS", "600036.SS", "300750.SZ", "000858.SZ", "601166.SS", "600900.SS",
    "601398.SS", "600030.SS", "000333.SZ", "002594.SZ", "600276.SS", "601012.SS", "000651.SZ",
    "600887.SS", "601899.SS", "600309.SS", "601888.SS", "000001.SZ", "600000.SS", "600028.SS",
    "601668.SS", "601857.SS", "601988.SS", "601939.SS", "601288.SS", "601328.SS", "600050.SS",
    "601088.SS", "600104.SS", "002415.SZ", "300059.SZ", "601628.SS", "600048.SS", "601601.SS",
    "000725.SZ", "601919.SS", "600585.SS", "002475.SZ", "300760.SZ", "688981.SS", "601138.SS",
]

NIKKEI = [  # 40 maiores do Japão
    "7203.T", "6758.T", "8306.T", "6861.T", "9984.T", "6501.T", "8035.T", "9983.T", "4063.T",
    "8316.T", "9432.T", "6098.T", "8058.T", "8001.T", "7974.T", "4568.T", "6902.T", "7267.T",
    "8766.T", "4502.T", "6367.T", "8031.T", "6981.T", "7741.T", "9433.T", "6273.T", "6594.T",
    "4519.T", "8411.T", "6954.T", "7011.T", "6702.T", "6503.T", "4661.T", "2914.T", "8053.T",
    "6146.T", "6857.T", "4543.T", "6301.T",
]

EUROSTOXX50 = [
    "ASML.AS", "MC.PA", "SAP.DE", "SIE.DE", "TTE.PA", "SAN.PA", "ALV.DE", "OR.PA", "SU.PA",
    "AIR.PA", "DTE.DE", "IBE.MC", "SAN.MC", "BNP.PA", "CS.PA", "RMS.PA", "ITX.MC", "ENEL.MI",
    "ISP.MI", "UCG.MI", "MUV2.DE", "EL.PA", "SAF.PA", "DG.PA", "BAS.DE", "BAYN.DE", "BMW.DE",
    "MBG.DE", "VOW3.DE", "ADS.DE", "IFX.DE", "DB1.DE", "DHL.DE", "RACE.MI", "ENI.MI",
    "STLAM.MI", "BBVA.MC", "INGA.AS", "PRX.AS", "AD.AS", "ABI.BR", "KER.PA", "AI.PA", "BN.PA",
    "RI.PA", "NDA-FI.HE", "NOKIA.HE", "WKL.AS", "RHM.DE", "SGO.PA",
]

DAX_FALLBACK = [
    "ADS.DE", "AIR.DE", "ALV.DE", "BAS.DE", "BAYN.DE", "BEI.DE", "BMW.DE", "BNR.DE", "CBK.DE",
    "CON.DE", "DB1.DE", "DBK.DE", "DHL.DE", "DTE.DE", "DTG.DE", "ENR.DE", "EOAN.DE", "FRE.DE",
    "G1A.DE", "G24.DE", "HEI.DE", "HEN3.DE", "HNR1.DE", "IFX.DE", "MBG.DE", "MRK.DE", "MTX.DE",
    "MUV2.DE", "PAH3.DE", "QIA.DE", "RHM.DE", "RWE.DE", "SAP.DE", "SHL.DE", "SIE.DE", "SY1.DE",
    "VNA.DE", "VOW3.DE", "ZAL.DE", "FME.DE",
]

FTSE_FALLBACK = [
    "AZN.L", "SHEL.L", "HSBA.L", "ULVR.L", "BP.L", "RIO.L", "GSK.L", "REL.L", "BATS.L", "LSEG.L",
    "DGE.L", "RR.L", "NG.L", "BA.L", "CPG.L", "GLEN.L", "LLOY.L", "BARC.L", "AAL.L", "PRU.L",
    "TSCO.L", "EXPN.L", "HLN.L", "VOD.L", "NWG.L", "IMB.L", "SSE.L", "AHT.L", "III.L", "STAN.L",
    "LGEN.L", "ABF.L", "BT-A.L", "AV.L", "IHG.L", "SGE.L", "ANTO.L", "WPP.L", "CNA.L", "SMIN.L",
]

NIFTY_FALLBACK = [t + ".NS" for t in [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "BHARTIARTL", "ITC", "LT", "SBIN",
    "AXISBANK", "KOTAKBANK", "HINDUNILVR", "BAJFINANCE", "M&M", "MARUTI", "SUNPHARMA", "HCLTECH",
    "TITAN", "NTPC", "ULTRACEMCO", "POWERGRID", "ASIANPAINT", "TATASTEEL", "ONGC", "COALINDIA",
    "BAJAJFINSV", "NESTLEIND", "ADANIENT", "ADANIPORTS", "JSWSTEEL", "WIPRO", "TECHM", "GRASIM",
    "HINDALCO", "CIPLA", "DRREDDY", "SBILIFE", "HDFCLIFE", "EICHERMOT", "BAJAJ-AUTO",
    "HEROMOTOCO", "APOLLOHOSP", "BEL", "TRENT", "SHRIRAMFIN", "INDUSINDBK", "BRITANNIA", "TATACONSUM",
]]

SP500_FALLBACK = [  # só se a Wikipedia falhar E não houver cache
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK-B", "LLY", "AVGO", "TSLA",
    "JPM", "UNH", "XOM", "V", "PG", "JNJ", "MA", "COST", "HD", "ABBV", "WMT", "MRK", "NFLX",
    "BAC", "KO", "CVX", "CRM", "ADBE", "PEP", "TMO", "ORCL", "LIN", "AMD", "ACN", "WFC", "MCD",
    "CSCO", "ABT", "GE", "DHR", "QCOM", "PM", "AMGN", "INTU", "TXN", "IBM", "PFE", "VZ", "DIS",
    "NOW", "AMAT", "CAT", "GS", "NEE", "ISRG", "CMCSA", "SPGI", "RTX", "UNP", "AXP", "T", "LOW",
    "HON", "VRTX", "TJX", "MS", "UBER", "COP", "PGR", "BKNG", "INTC", "BLK", "C", "ETN", "PLD",
    "LMT", "SYK", "MU", "BSX", "ADI", "LRCX", "MDT", "ADP", "AMT", "BA", "PANW", "KLAC", "BMY",
]

COUNTRY_ETFS = {
    "SPY": "EUA", "EWC": "Canadá", "EWW": "México", "EWZ": "Brasil", "ECH": "Chile",
    "EPU": "Peru", "GXG": "Colômbia", "ARGT": "Argentina", "EWU": "Reino Unido",
    "EWG": "Alemanha", "EWQ": "França", "EWI": "Itália", "EWP": "Espanha", "EWN": "Holanda",
    "EWL": "Suíça", "EWD": "Suécia", "EWK": "Bélgica", "EWO": "Áustria", "EDEN": "Dinamarca",
    "NORW": "Noruega", "EFNL": "Finlândia", "EIRL": "Irlanda", "EPOL": "Polônia",
    "TUR": "Turquia", "EIS": "Israel", "KSA": "Arábia Saudita", "QAT": "Catar", "UAE": "Emirados",
    "EZA": "África do Sul", "EWJ": "Japão", "EWY": "Coreia", "EWT": "Taiwan", "MCHI": "China",
    "EWH": "Hong Kong", "INDA": "Índia", "EWS": "Singapura", "EWM": "Malásia",
    "THD": "Tailândia", "EIDO": "Indonésia", "EPHE": "Filipinas", "VNM": "Vietnã",
    "EWA": "Austrália", "ENZL": "Nova Zelândia",
}

CRYPTO = [  # top cripto sem stablecoins (alguns tickers do Yahoo têm sufixo numérico)
    "BTC-USD", "ETH-USD", "XRP-USD", "BNB-USD", "SOL-USD", "DOGE-USD", "TRX-USD", "ADA-USD",
    "LINK-USD", "AVAX-USD", "XLM-USD", "BCH-USD", "HBAR-USD", "LTC-USD", "DOT-USD",
    "SUI20947-USD", "TON11419-USD", "UNI7083-USD", "NEAR-USD", "AAVE-USD", "ETC-USD",
    "ATOM-USD", "FIL-USD",
]

# weight = peso aproximado no MSCI ACWI, usado no "breadth global" ponderado (edite à vontade).
# source: "static" usa a lista; "wiki_*" busca a composição atual na Wikipedia (com cache).
MARKETS = [
    dict(key="SP500", name="S&P 500 (EUA)", index="^GSPC", source="wiki_sp500", fallback=SP500_FALLBACK, weight=0.64),
    dict(key="STOXX50", name="Euro Stoxx 50", index="^STOXX50E", source="static", tickers=EUROSTOXX50, weight=0.06),
    dict(key="DAX", name="DAX (Alemanha)", index="^GDAXI", source="wiki_dax", fallback=DAX_FALLBACK, weight=0.02),
    dict(key="FTSE", name="FTSE 100 (Reino Unido)", index="^FTSE", source="wiki_ftse100", fallback=FTSE_FALLBACK, weight=0.03),
    dict(key="NIKKEI", name="Japão (top 40)", index="^N225", source="static", tickers=NIKKEI, weight=0.05),
    dict(key="NIFTY", name="Nifty 50 (Índia)", index="^NSEI", source="wiki_nifty50", fallback=NIFTY_FALLBACK, weight=0.02),
    dict(key="HSI", name="Hang Seng (Hong Kong)", index="^HSI", source="static", tickers=HSI, weight=0.015),
    dict(key="CHINA", name="China A (CSI 300, amostra)", index="000300.SS", source="static", tickers=CHINA_A, weight=0.015),
    dict(key="IBOV", name="Ibovespa (Brasil)", index="^BVSP", source="static", tickers=IBOV, weight=0.005),
]
EXTRA = [  # não entram no breadth global de ações
    dict(key="COUNTRIES", name="Países (ETFs MSCI, em USD)", index="ACWI", source="static", tickers=list(COUNTRY_ETFS), weight=0),
    dict(key="CRYPTO", name="Cripto (top 23, dias úteis)", index="BTC-USD", source="static", tickers=CRYPTO, weight=0, crypto=True),
]

# Paleta (validada para daltonismo — referência do projeto de dataviz)
C_BLUE, C_ORANGE, C_AQUA, C_VIOLET, C_RED = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#e34948"
C_MUTED, C_GRID, C_TEXT = "#8a8985", "#e6e5e1", "#0b0b0b"


# =====================================================================
# 2. COLETA DE DADOS
# =====================================================================
def _read_wiki_tables(url: str) -> list[pd.DataFrame]:
    import requests
    html = requests.get(url, headers=UA, timeout=30).text
    return pd.read_html(StringIO(html))


def _find_col(tables, names, min_rows):
    for t in tables:
        cols = {str(c).strip().lower(): c for c in t.columns}
        for n in names:
            if n in cols and len(t) >= min_rows:
                return t[cols[n]].astype(str).str.strip().tolist()
    raise ValueError("tabela não encontrada")


def fetch_constituents(m: dict) -> list[str]:
    """Composição atual do índice. Ordem: Wikipedia -> cache local -> lista reserva."""
    if m["source"] == "static":
        return m["tickers"]
    cache = OUT_DIR / "constituents" / f"{m['key']}.txt"
    try:
        if m["source"] == "wiki_sp500":
            raw = _find_col(_read_wiki_tables("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"), ["symbol"], 400)
            tick = [s.replace(".", "-") for s in raw]
        elif m["source"] == "wiki_dax":
            raw = _find_col(_read_wiki_tables("https://en.wikipedia.org/wiki/DAX"), ["ticker", "symbol"], 30)
            tick = [s if "." in s else s + ".DE" for s in raw]
        elif m["source"] == "wiki_ftse100":
            raw = _find_col(_read_wiki_tables("https://en.wikipedia.org/wiki/FTSE_100_Index"), ["ticker", "epic"], 90)
            tick = [s.rstrip(".").replace(".", "-") + ".L" for s in raw]
        elif m["source"] == "wiki_nifty50":
            raw = _find_col(_read_wiki_tables("https://en.wikipedia.org/wiki/NIFTY_50"), ["symbol"], 45)
            tick = [s + ".NS" for s in raw]
        else:
            raise ValueError(m["source"])
        tick = sorted(set(t for t in tick if t and t.lower() != "nan"))
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("\n".join(tick))
        print(f"  {m['key']}: {len(tick)} componentes (Wikipedia)")
        return tick
    except Exception as e:  # noqa: BLE001
        if cache.exists():
            print(f"  {m['key']}: Wikipedia falhou ({e}); usando cache")
            return cache.read_text().split()
        print(f"  {m['key']}: Wikipedia falhou ({e}); usando lista reserva")
        return m["fallback"]


def download_closes(tickers: list[str]) -> pd.DataFrame:
    """Fechamentos ajustados por dividendos e desdobramentos."""
    import yfinance as yf
    df = yf.download(tickers, period=HISTORY, auto_adjust=True, progress=False, threads=True)
    if df is None or df.empty:
        return pd.DataFrame()
    close = df["Close"] if "Close" in df else df
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.sort_index()


def split_dead(close: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Remove tickers sem dados ou sem cotação recente (deslistados, renomeados)."""
    if close.empty:
        return close, []
    last_date = close.index.max()
    last_valid = close.apply(lambda s: s.last_valid_index())
    dead = [c for c, d in last_valid.items() if d is None or (last_date - d).days > STALE_DAYS]
    return close.drop(columns=dead), sorted(dead)


# =====================================================================
# 3. INDICADORES
# =====================================================================
def rsi_wilder(s: pd.Series, n: int = RSI_DAYS) -> pd.Series:
    """RSI com suavização de Wilder (o mesmo das plataformas de gráfico)."""
    s = s.dropna()
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.where(loss != 0, 100.0)


def pct_true(cond: pd.DataFrame, valid: pd.DataFrame, min_count: int) -> pd.Series:
    """% de ativos que atendem à condição, contando SÓ os ativos com dado válido no dia."""
    n = valid.sum(axis=1)
    out = (cond & valid).sum(axis=1) / n * 100
    return out.where(n >= min_count)


def event_study(breadth: pd.Series, index: pd.Series, lo: float, hi: float) -> pd.DataFrame:
    """Retorno médio do índice N dias depois que o breadth CRUZA os extremos."""
    if index is None or index.dropna().empty:
        return pd.DataFrame()
    idx = index.reindex(breadth.index).ffill()
    rows = []
    signals = {
        f"Breadth cruza abaixo de {lo:.0f}% (p{PCT_LOW*100:.0f})": (breadth < lo) & (breadth.shift() >= lo),
        f"Breadth cruza acima de {hi:.0f}% (p{PCT_HIGH*100:.0f})": (breadth > hi) & (breadth.shift() <= hi),
        "Qualquer dia (referência)": breadth.notna(),
    }
    for label, sig in signals.items():
        row = {"Sinal": label, "Eventos": int(sig.sum())}
        for h in FWD_HORIZONS:
            fwd = (idx.shift(-h) / idx - 1) * 100
            r = fwd[sig].dropna()
            row[f"{h}d média %"] = r.mean() if len(r) else np.nan
            row[f"{h}d % positivos"] = (r > 0).mean() * 100 if len(r) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def analyze(m: dict) -> dict | None:
    print(f"\n== {m['name']}")
    tickers = fetch_constituents(m)
    close = download_closes(tickers)
    close, dead = split_dead(close)
    if close.shape[1] < 5:
        print("  dados insuficientes — mercado ignorado")
        return None
    if m.get("crypto"):  # cripto negocia 24/7: usa só dias úteis p/ a MA ter o mesmo sentido das ações
        close = close[close.index.dayofweek < 5]
    index_close = download_closes([m["index"]])
    index = index_close.iloc[:, 0].dropna() if not index_close.empty else pd.Series(dtype=float)
    if m.get("crypto"):
        index = index[index.index.dayofweek < 5]

    # alinha ao calendário dominante do mercado (dias em que >= metade dos ativos negociou)
    close = close[close.notna().sum(axis=1) >= close.shape[1] * 0.5]
    min_count = max(5, int(close.shape[1] * 0.5))

    ma = close.rolling(MA_DAYS, min_periods=MA_DAYS).mean()
    breadth = pct_true(close > ma, close.notna() & ma.notna(), min_count)

    rsi = pd.DataFrame({c: rsi_wilder(close[c]) for c in close}).reindex(close.index)
    rsi_ok = rsi.notna()
    ob = pct_true(rsi > RSI_OB, rsi_ok, min_count)
    os_ = pct_true(rsi < RSI_OS, rsi_ok, min_count)

    b = breadth.dropna()
    lo, hi = b.quantile(PCT_LOW), b.quantile(PCT_HIGH)
    last = b.iloc[-1]
    if last >= FIXED_TOP or last >= hi:
        status = "Euforia: possível topo"
    elif last <= FIXED_BOTTOM or last <= lo:
        status = "Pânico: possível fundo"
    else:
        status = "Neutro"

    res = dict(
        key=m["key"], name=m["name"], weight=m["weight"], index_symbol=m["index"],
        index=index, index_ma200=index.rolling(200).mean(), breadth=breadth, ob=ob, os=os_,
        lo=lo, hi=hi, status=status, dead=dead, n_assets=close.shape[1],
        last_date=b.index[-1], events=event_study(breadth, index, lo, hi),
    )
    if m.get("crypto") and {"BTC-USD", "ETH-USD"} <= set(close.columns):
        res["eth_btc"] = (close["ETH-USD"] / close["BTC-USD"]).dropna()
        res["btc_dist"] = ((close["BTC-USD"] / close["BTC-USD"].rolling(200).mean() - 1) * 100).dropna()
    print(f"  {close.shape[1]} ativos | breadth {last:.1f}% | {status} | sem dados: {len(dead)}")
    return res


def global_breadth(results: list[dict]) -> pd.Series:
    """Breadth mundial: média dos mercados de ações ponderada pelo peso no ACWI."""
    eq = [r for r in results if r["weight"] > 0]
    df = pd.concat({r["key"]: r["breadth"] for r in eq}, axis=1).sort_index().ffill(limit=3)
    w = pd.Series({r["key"]: r["weight"] for r in eq})
    avail = df.notna()
    return (df.fillna(0) * w).sum(axis=1) / (avail * w).sum(axis=1).replace(0, np.nan)


def summary_table(results: list[dict]) -> pd.DataFrame:
    rows = []
    for r in results:
        last_idx = r["index"].iloc[-1] if len(r["index"]) else np.nan
        rows.append({
            "Mercado": r["name"],
            "Data": r["last_date"].strftime("%Y-%m-%d"),
            "Índice": last_idx,
            f"% acima MA{MA_DAYS}": r["breadth"].dropna().iloc[-1],
            "Faixa normal (p5–p95)": f"{r['lo']:.0f}–{r['hi']:.0f}%",
            f"% RSI>{RSI_OB}": r["ob"].dropna().iloc[-1],
            f"% RSI<{RSI_OS}": r["os"].dropna().iloc[-1],
            "Sinal": r["status"],
            "Ativos": r["n_assets"],
        })
    return pd.DataFrame(rows)


# =====================================================================
# 4. SAÍDAS: dashboard HTML, PNG resumo, histórico CSV
# =====================================================================
def market_figure(r: dict):
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go

    cut = r["breadth"].dropna().index[-PLOT_DAYS:][0]
    sl = lambda s: s[s.index >= cut]  # noqa: E731
    extra = "eth_btc" in r
    rows = 4 if extra else 3
    titles = [f"{r['name']} — índice {r['index_symbol']} e MA200",
              f"% de ativos acima da MA{MA_DAYS}",
              f"% de ativos com RSI{RSI_DAYS} > {RSI_OB} (sobrecompra) e < {RSI_OS} (sobrevenda)"]
    if extra:
        titles.append("Razão ETH/BTC (apetite a risco dentro de cripto)")
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.06, subplot_titles=titles)

    if len(r["index"]):
        fig.add_scatter(x=sl(r["index"]).index, y=sl(r["index"]), name="Índice", line=dict(color=C_BLUE, width=2), row=1, col=1)
        fig.add_scatter(x=sl(r["index_ma200"]).index, y=sl(r["index_ma200"]), name="MA200",
                        line=dict(color=C_ORANGE, width=2, dash="dash"), row=1, col=1)
    fig.add_scatter(x=sl(r["breadth"]).index, y=sl(r["breadth"]), name=f"% > MA{MA_DAYS}",
                    line=dict(color=C_AQUA, width=2), row=2, col=1)
    for y, txt, dash in [(FIXED_TOP, f"{FIXED_TOP}% fixo", "dot"), (FIXED_BOTTOM, f"{FIXED_BOTTOM}% fixo", "dot"),
                         (r["hi"], f"p95 {r['hi']:.0f}%", "dash"), (r["lo"], f"p5 {r['lo']:.0f}%", "dash")]:
        fig.add_hline(y=y, line=dict(color=C_MUTED, width=1, dash=dash), annotation_text=txt,
                      annotation_font_color=C_MUTED, annotation_position="right", row=2, col=1)
    fig.add_scatter(x=sl(r["ob"]).index, y=sl(r["ob"]), name="Sobrecompra", line=dict(color=C_VIOLET, width=2), row=3, col=1)
    fig.add_scatter(x=sl(r["os"]).index, y=sl(r["os"]), name="Sobrevenda", line=dict(color=C_ORANGE, width=2), row=3, col=1)
    if extra:
        fig.add_scatter(x=sl(r["eth_btc"]).index, y=sl(r["eth_btc"]), name="ETH/BTC", line=dict(color=C_BLUE, width=2), row=4, col=1)
    fig.update_yaxes(range=[0, 100], ticksuffix="%", row=2, col=1)
    fig.update_yaxes(range=[0, 100], ticksuffix="%", row=3, col=1)
    fig.update_layout(height=260 * rows, template="plotly_white", hovermode="x unified",
                      margin=dict(l=50, r=90, t=50, b=30), legend=dict(orientation="h", y=1.04, x=0),
                      font=dict(family="system-ui, sans-serif", color=C_TEXT))
    fig.update_xaxes(gridcolor=C_GRID)
    fig.update_yaxes(gridcolor=C_GRID)
    return fig


def overview_figure(results, gb):
    from plotly.subplots import make_subplots
    order = sorted(results, key=lambda r: r["breadth"].dropna().iloc[-1])
    names = [r["name"] for r in order]
    vals = [r["breadth"].dropna().iloc[-1] for r in order]
    fig = make_subplots(rows=1, cols=2, column_widths=[0.45, 0.55], horizontal_spacing=0.18,
                        subplot_titles=[f"% acima da MA{MA_DAYS} hoje (traço = faixa normal p5–p95)",
                                        "Breadth global ponderado (ações, último ano)"])
    fig.add_bar(y=names, x=vals, orientation="h", marker_color=C_AQUA, name=f"% > MA{MA_DAYS}",
                text=[f"{v:.0f}%" for v in vals], textposition="outside", row=1, col=1)
    fig.add_scatter(y=names, x=[r["lo"] for r in order], mode="markers", name="p5",
                    marker=dict(symbol="line-ns-open", size=16, color=C_MUTED, line=dict(width=2)), row=1, col=1)
    fig.add_scatter(y=names, x=[r["hi"] for r in order], mode="markers", name="p95",
                    marker=dict(symbol="line-ns-open", size=16, color=C_TEXT, line=dict(width=2)), row=1, col=1)
    g = gb.dropna().iloc[-252:]
    fig.add_scatter(x=g.index, y=g, name="Global", line=dict(color=C_BLUE, width=2), row=1, col=2)
    fig.update_xaxes(range=[0, 110], ticksuffix="%", row=1, col=1)
    fig.update_yaxes(range=[0, 100], ticksuffix="%", row=1, col=2)
    fig.update_layout(height=max(380, 34 * len(names) + 120), template="plotly_white", showlegend=False,
                      margin=dict(l=10, r=20, t=50, b=30), font=dict(family="system-ui, sans-serif", color=C_TEXT))
    return fig


def build_png(results, gb, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    order = sorted(results, key=lambda r: r["breadth"].dropna().iloc[-1])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 0.42 * len(order) + 2.6), gridspec_kw=dict(width_ratios=[1.1, 1]))
    y = np.arange(len(order))
    vals = [r["breadth"].dropna().iloc[-1] for r in order]
    a1.set_axisbelow(True)
    a1.barh(y, vals, color=C_AQUA, height=0.55)
    for i, r in enumerate(order):  # faixa normal desenhada logo abaixo da barra
        yy = i - 0.38
        a1.plot([r["lo"], r["hi"]], [yy, yy], color=C_MUTED, lw=1.2)
        a1.plot([r["lo"], r["hi"]], [yy, yy], "|", color=C_MUTED, ms=7, mew=1.5)
        a1.text(103, i, f"{vals[i]:.0f}%", va="center", ha="left", fontsize=9, color=C_TEXT, fontweight="bold")
    a1.set_yticks(y, [r["name"] for r in order], fontsize=9)
    a1.set_xlim(0, 112)
    a1.set_xticks([0, 20, 40, 60, 80, 100])
    a1.set_ylim(-0.8, len(order) - 0.4)
    a1.set_title(f"% de ativos acima da MA{MA_DAYS}  (linha cinza = faixa normal p5–p95)", fontsize=10, loc="left")
    g = gb.dropna().iloc[-252:]
    a2.plot(g.index, g.values, color=C_BLUE, lw=2)
    a2.axhline(FIXED_TOP, color=C_MUTED, ls=":", lw=1)
    a2.axhline(FIXED_BOTTOM, color=C_MUTED, ls=":", lw=1)
    a2.set_ylim(0, 100)
    a2.set_title(f"Breadth global ponderado — hoje {g.iloc[-1]:.0f}%", fontsize=10, loc="left")
    for ax in (a1, a2):
        ax.grid(axis="x" if ax is a1 else "y", color=C_GRID)
        ax.spines[["top", "right"]].set_visible(False)
    plt.setp(a2.get_xticklabels(), rotation=30, ha="right")
    fig.suptitle(f"Global Market Breadth — {dt.date.today():%d/%m/%Y}", fontsize=13, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fmt_table(df: pd.DataFrame) -> str:
    return df.to_html(index=False, border=0, classes="tbl", na_rep="–",
                      float_format=lambda v: f"{v:,.2f}")


def build_html(results, gb, summary: pd.DataFrame, path: Path):
    ov = overview_figure(results, gb).to_html(full_html=False, include_plotlyjs="cdn")
    sections = []
    for r in results:
        fig = market_figure(r).to_html(full_html=False, include_plotlyjs=False)
        ev = fmt_table(r["events"].round(2)) if not r["events"].empty else "<p>Sem índice para o estudo.</p>"
        dead = ", ".join(r["dead"]) if r["dead"] else "nenhum"
        sections.append(f"""
<section id="{r['key']}">
  <h2>{r['name']} <span class="pill">{r['status']}</span></h2>
  {fig}
  <details><summary>Estudo de eventos: o que o índice fez depois dos extremos (histórico de {HISTORY})</summary>{ev}</details>
  <p class="muted">Tickers sem dados/deslistados (fora do cálculo): {dead}</p>
</section>""")
    nav = " · ".join(f'<a href="#{r["key"]}">{r["name"]}</a>' for r in results)
    g_last = gb.dropna().iloc[-1]
    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Global Market Breadth</title>
<style>
 body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#fcfcfb;color:{C_TEXT}}}
 main{{max-width:1200px;margin:auto;padding:24px}}
 h1{{margin:0 0 4px}} h2{{margin-top:40px;border-top:1px solid {C_GRID};padding-top:24px}}
 .muted{{color:#52514e;font-size:13px}} a{{color:{C_BLUE}}}
 .hero{{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0}}
 .card{{background:#fff;border:1px solid {C_GRID};border-radius:10px;padding:14px 18px;min-width:180px}}
 .card b{{font-size:28px;display:block}}
 .tbl{{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}}
 .tbl th,.tbl td{{padding:6px 8px;border-bottom:1px solid {C_GRID};text-align:right}}
 .tbl th:first-child,.tbl td:first-child{{text-align:left}}
 .pill{{font-size:13px;font-weight:500;background:#f0efec;border-radius:20px;padding:3px 10px;vertical-align:middle}}
 details{{margin:8px 0}} summary{{cursor:pointer;color:{C_BLUE}}}
</style></head><body><main>
<h1>Global Market Breadth</h1>
<p class="muted">Atualizado em {dt.datetime.now(dt.timezone.utc):%d/%m/%Y %H:%M} UTC · MA{MA_DAYS} · RSI{RSI_DAYS} (Wilder) ·
preços ajustados · só ativos com dado válido entram no cálculo</p>
<div class="hero">
 <div class="card"><span class="muted">Breadth global (ações, ponderado ACWI)</span><b>{g_last:.0f}%</b></div>
 <div class="card"><span class="muted">Mercados em euforia</span><b>{sum(r['status'].startswith('Euforia') for r in results)}</b></div>
 <div class="card"><span class="muted">Mercados em pânico</span><b>{sum(r['status'].startswith('Pânico') for r in results)}</b></div>
</div>
{ov}
<h2>Resumo</h2>
{fmt_table(summary)}
<p class="muted">Ir para: {nav}</p>
{''.join(sections)}
<p class="muted" style="margin-top:40px">Ferramenta de estudo, não é recomendação de investimento.
Faixa normal = percentis 5 e 95 do breadth do próprio mercado nos últimos {HISTORY}.</p>
</main></body></html>"""
    path.write_text(html, encoding="utf-8")


def append_history(summary: pd.DataFrame, gb: pd.Series, path: Path):
    today = summary[["Data", "Mercado", f"% acima MA{MA_DAYS}", f"% RSI>{RSI_OB}", f"% RSI<{RSI_OS}", "Sinal"]].copy()
    g = pd.DataFrame([{"Data": gb.dropna().index[-1].strftime("%Y-%m-%d"), "Mercado": "GLOBAL (ponderado)",
                       f"% acima MA{MA_DAYS}": gb.dropna().iloc[-1]}])
    new = pd.concat([today, g], ignore_index=True)
    if path.exists():
        new = pd.concat([pd.read_csv(path), new], ignore_index=True)
    new.drop_duplicates(subset=["Data", "Mercado"], keep="last").round(2).to_csv(path, index=False)


# =====================================================================
# 5. E-MAIL
# =====================================================================
def build_email(summary: pd.DataFrame, gb: pd.Series, png: Path, html_file: Path) -> EmailMessage:
    url = os.getenv("DASHBOARD_URL", "")
    link = f'<p><a href="{url}">Abrir o dashboard interativo</a></p>' if url else \
        "<p>O dashboard interativo vai anexado (index.html).</p>"
    alerts = summary[summary["Sinal"] != "Neutro"]
    alert_txt = "".join(f"<li><b>{r['Mercado']}</b>: {r['Sinal']} ({r[f'% acima MA{MA_DAYS}']:.0f}% acima da MA)</li>"
                        for _, r in alerts.iterrows()) or "<li>Nenhum mercado em extremo hoje.</li>"
    cols = ["Mercado", "Data", f"% acima MA{MA_DAYS}", "Faixa normal (p5–p95)", f"% RSI>{RSI_OB}", f"% RSI<{RSI_OS}", "Sinal"]
    table = summary[cols].to_html(index=False, border=0, float_format=lambda v: f"{v:.0f}%")
    table = table.replace("<table", '<table style="border-collapse:collapse;font-size:13px" cellpadding="6"')
    msg = EmailMessage()
    msg["Subject"] = f"Market Breadth {dt.date.today():%d/%m} — global {gb.dropna().iloc[-1]:.0f}%"
    msg["From"] = os.getenv("EMAIL_FROM") or os.getenv("SMTP_USER", "market-breadth@localhost")
    msg["To"] = os.getenv("EMAIL_TO", "")
    msg.set_content("Seu leitor de e-mail não mostra HTML. Abra o anexo index.html.")
    msg.add_alternative(f"""<html><body style="font-family:system-ui,sans-serif;color:#0b0b0b">
<h2 style="margin:0">Global Market Breadth — {dt.date.today():%d/%m/%Y}</h2>
<p>Breadth global ponderado: <b>{gb.dropna().iloc[-1]:.0f}%</b></p>
<ul>{alert_txt}</ul>
<img src="cid:summary" style="max-width:100%">
{table}
{link}
<p style="color:#8a8985;font-size:12px">Ferramenta de estudo, não é recomendação de investimento.</p>
</body></html>""", subtype="html")
    msg.get_payload()[1].add_related(png.read_bytes(), "image", "png", cid="<summary>")
    msg.add_attachment(html_file.read_bytes(), maintype="text", subtype="html", filename="index.html")
    return msg


def send_email(msg: EmailMessage):
    host, user, pwd = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASS")
    if not (host and user and pwd and msg["To"]):
        print("E-mail não enviado: faltam SMTP_HOST/SMTP_USER/SMTP_PASS/EMAIL_TO")
        return
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=60) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)
    print(f"E-mail enviado para {msg['To']}")


# =====================================================================
# 6. EXECUÇÃO
# =====================================================================
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--save-eml", action="store_true")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = [r for r in (analyze(m) for m in MARKETS + EXTRA) if r]
    if not results:
        sys.exit("Nenhum dado baixado.")
    gb = global_breadth(results)
    summary = summary_table(results)
    print("\n", summary.round(2).to_string(index=False))

    png, html_file = OUT_DIR / "summary.png", OUT_DIR / "index.html"
    build_png(results, gb, png)
    build_html(results, gb, summary, html_file)
    append_history(summary, gb, OUT_DIR / "history.csv")
    summary.round(2).to_csv(OUT_DIR / "latest.csv", index=False)

    msg = build_email(summary, gb, png, html_file)
    if args.save_eml:
        (OUT_DIR / "last_email.eml").write_bytes(bytes(msg))
    if not args.no_email:
        send_email(msg)


if __name__ == "__main__":
    main()
