"""Simulations : stratégie Fibonacci sur BTC + placement de la liquidité en attente + poche séparée (bot, or, Nasdaq…).

Hypothèses (identiques aux simulations faites dans la conversation) :
- Fibonacci BTC : achats 50/30/20 % du cash à −50/−61,8/−78,6 % sous l'ATH, ventes 30/30/20/20 % de la position
  au retour de l'ATH puis aux extensions 1,272/1,618/2,618, exécution à l'ouverture du lendemain, frais 0,1 %.
  La stratégie tourne depuis 2015 ; à la date de départ, le portefeuille est remis à l'échelle du capital choisi
  (on reprend donc la stratégie « en cours », avec sa répartition BTC / liquidité du moment).
- La liquidité en attente est placée chaque jour dans le support choisi ; un achat Fibonacci revend ce qu'il faut.
- Staking : rendement annuel appliqué chaque jour aux BTC détenus.
- Poche séparée : capital à part, placé dans le support choisi. Si « injection » est activée, à chaque palier d'achat
  Fibonacci touché, les gains de la poche au-dessus de son capital initial achètent du BTC.
"""
import os
import numpy as np
import pandas as pd
import core

H = os.path.dirname(os.path.abspath(__file__))
FEE = 0.001
# Rendements annuels du bot multi-actifs BTC/ETH/SOL (FINDINGS du projet BotCrypto, 26/09/2026)
BOT_YEARS = {2021: 2.5, 2022: 32.0, 2023: 106.8, 2024: 59.4, 2025: 14.1, 2026: 9.8}
BOT_START = "2021-04-10"
# Taux directeur américain moyen (coût du levier) et volatilité annuelle du Nasdaq-100, par année
FF = {2015: .1, 2016: .4, 2017: 1.0, 2018: 1.8, 2019: 2.2, 2020: .4, 2021: .1, 2022: 1.7, 2023: 5.0, 2024: 5.1, 2025: 4.2, 2026: 3.7}
VOL = {2015: .17, 2016: .15, 2017: .11, 2018: .24, 2019: .17, 2020: .36, 2021: .20, 2022: .35, 2023: .21, 2024: .20, 2025: .25, 2026: .20}

PLACEMENTS = {
    "cash": "Cash (0 %)",
    "stable": "Stablecoins / monétaire",
    "gold": "Or",
    "qqq": "Nasdaq-100",
    "qqq2": "Nasdaq-100 ×2",
    "gold_qqq": "½ or + ½ Nasdaq",
    "gold_stable": "½ or + ½ stablecoins",
    "qqq_stable": "½ Nasdaq + ½ stablecoins",
}
POCKETS = {"bot": "Bot BTC/ETH/SOL (rendements annuels)", **PLACEMENTS}


def _read(name):
    s = pd.read_csv(f"{H}/data/{name}.csv", index_col=0, parse_dates=True).iloc[:, 0].dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def load_markets():
    btc = core.rd("btc")
    idx = pd.date_range("2015-01-01", btc.index[-1])
    btc = btc.reindex(idx).ffill()
    gold = _read("gold").reindex(idx).ffill().bfill()
    qqq = _read("qqq").reindex(idx).ffill().bfill()
    return btc, gold, qqq


def factors(idx, gold, qqq, stable_rate=4.0, bot_years=None):
    """Facteur de croissance quotidien de chaque support (1,0 = ne bouge pas)."""
    one = pd.Series(1.0, index=idx)
    stable = pd.Series((1 + stable_rate / 100) ** (1 / 365), index=idx)
    g = (gold / gold.shift(1)).fillna(1.0) * (1 - 0.0025) ** (1 / 365)  # frais d'ETC / de conservation ~0,25 %/an
    r = (qqq / qqq.shift(1) - 1).fillna(0.0)
    q = (1 + r) * (1 + 0.005) ** (1 / 365)  # dividendes réinvestis ~0,5 %/an
    cost = pd.Series([(0.0095 + FF.get(d.year, 3.7) / 100 + VOL.get(d.year, 0.22) ** 2) / 365 for d in idx], index=idx)
    q2 = (1 + 2 * r) * np.exp(-cost)  # ETF x2 à levier quotidien : frais, financement, érosion de volatilité
    F = {"cash": one, "stable": stable, "gold": g, "qqq": q, "qqq2": q2,
         "gold_qqq": (g + q) / 2, "gold_stable": (g + stable) / 2, "qqq_stable": (q + stable) / 2}
    by = bot_years if bot_years is not None else BOT_YEARS
    bot = one.copy()
    for y, pct in by.items():
        a = max(pd.Timestamp(f"{y}-01-01"), pd.Timestamp(BOT_START))
        b = pd.Timestamp(f"{y}-12-31")
        m = (idx >= a) & (idx <= b)
        if m.sum() and pct is not None and not pd.isna(pct):
            bot[m] = (1 + pct / 100) ** (1 / m.sum())
    F["bot"] = bot
    return F


def run(btc, F, start, capital=14000.0, pocket_amt=0.0, liq="cash", pocket="bot", inject=True, stake=2.0):
    """Renvoie (série quotidienne, injections, ordres Fibonacci) à partir de `start`."""
    S0 = pd.Timestamp(start)
    C = btc.values
    ix = btc.index
    fib_cap = capital - pocket_amt
    cash, q = 10000.0, 0.0
    A = float(core.rd("btc").loc[:ix[0] - pd.Timedelta(days=1)].max())
    bf = [False] * 3
    bud = None
    sell = None
    pend = []
    bot = pocket_amt
    on = False
    rows, inj, orders = [], [], []
    LF, PF = F[liq], F[pocket]
    stk = (1 + stake / 100) ** (1 / 365)
    for i in range(1, len(C)):
        d = ix[i]
        o = C[i - 1]
        if not on and d >= S0:
            k = fib_cap / (cash + q * o) if (cash + q * o) > 0 else 0
            cash *= k
            q *= k
            on = True
            if bud is not None:
                bud *= k
            if sell and sell["Q0"]:
                sell["Q0"] *= k
            pend = [(a, x * k, w) for a, x, w in pend]
        for side, x, why in pend:
            if side == "B":
                amt = min(cash, x)
                if amt > 1:
                    q += amt * (1 - FEE) / o
                    cash -= amt
                    if on:
                        orders.append((d, "Achat", o, amt, why))
            elif side == "I":
                q += x * (1 - FEE) / o
                orders.append((d, "Injection poche", o, x, why))
            else:
                qq = min(q, x)
                if qq > 0:
                    cash += qq * o * (1 - FEE)
                    q -= qq
                    if on:
                        orders.append((d, "Vente", o, qq * o, why))
        pend = []
        if on:
            q *= stk
            cash *= LF.iloc[i]
            bot *= PF.iloc[i]
        c = C[i]
        fired = False
        if c > A:
            A = c
            bf = [False] * 3
            bud = None
        for j, (rr, f) in enumerate(core.BUY):
            if not bf[j] and c <= A * (1 - rr / 100):
                if bud is None:
                    bud = cash
                bf[j] = True
                pend.append(("B", bud * f, f"palier −{rr} %"))
                fired = True
                if sell is None or sell["A"] != A or sell["st"]:
                    sell = {"A": A, "B": c, "Q0": None, "fl": [False] * 4, "st": False}
        if sell:
            if not sell["st"]:
                sell["B"] = min(sell["B"], c)
            for j, (x, f) in enumerate(core.EXT):
                lv = sell["B"] + x * (sell["A"] - sell["B"])
                if not sell["fl"][j] and c >= lv and q > 0:
                    if not sell["st"]:
                        sell["st"] = True
                        sell["Q0"] = q
                    sell["fl"][j] = True
                    pend.append(("S", sell["Q0"] * f, "retour ATH" if x == 1 else f"extension {x}"))
        if on and inject and fired and bot > pocket_amt + 1:
            g = bot - pocket_amt
            bot = pocket_amt
            pend.append(("I", g, "gains de la poche"))
            inj.append((d, g))
        if on:
            rows.append((d, cash + q * c + bot, q, cash, bot, c))
    E = pd.DataFrame(rows, columns=["date", "total", "btc", "liquidite", "poche", "prix"]).set_index("date")
    E["buy_hold"] = capital * (1 - FEE) * E["prix"] / btc.loc[S0:].iloc[0]
    return E, inj, orders


def max_dd(s):
    return float((s / s.cummax() - 1).min() * 100)
