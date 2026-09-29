"""Plan Fibonacci crypto : zones d'achat / vente Fibonacci et points d'or.
Lancer : streamlit run app.py"""
import datetime as dt
import hmac
import math
import os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import core
import data_update
import sim

st.set_page_config(page_title="Plan Fibonacci crypto", layout="wide")

# Accès protégé si la variable d'environnement APP_PASSWORD est définie (ex. sur Railway)
_pw = os.environ.get("APP_PASSWORD")
if _pw and not st.session_state.get("auth"):
    st.title("Plan Fibonacci crypto")
    _v = st.text_input("Mot de passe", type="password")
    if _v and hmac.compare_digest(_v, _pw):
        st.session_state["auth"] = True
        st.rerun()
    elif _v:
        st.error("Mot de passe incorrect.")
    st.stop()

ASSETS = ["BTC", "ETH", "SOL", "LINK", "AAVE", "TAO"]
WARN = {
    "AAVE": "AAVE n'a jamais revu son ATH de mai 2021 (627 $) : le cycle Fibonacci de 2021 n'est pas terminé et ses objectifs de vente restent très loin.",
    "LINK": "LINK n'a jamais revu son ATH de mai 2021 (51,75 $) : le cycle de 2021 est toujours en cours.",
    "TAO": "Historique TAO disponible seulement depuis octobre 2024 : le record de mars 2024 n'est pas dans les données. Un seul cycle, résultats très fragiles.",
    "SOL": "Historique SOL disponible depuis janvier 2021.",
}
GREEN, RED, GOLD, INK = "#11875f", "#c8452f", "#d4a017", "#5d6878"


def fnum(v):
    v = float(v)
    d = 0 if v >= 1000 else 1 if v >= 100 else 2 if v >= 1 else 4
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


def fprice(v):
    return fnum(v) + " $"


def fpct(v):
    return ("+" if v > 0 else "") + f"{v:.0f} %"


def fdate(s):
    if not s:
        return "–"
    mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    d = pd.Timestamp(s)
    return f"{d.day} {mois[d.month - 1]} {d.year}"


@st.cache_data(ttl=6 * 3600, show_spinner="Récupération des derniers cours…")
def refresh_data(day: str):
    return data_update.update_all()


@st.cache_data(show_spinner="Calculs en cours…")
def compute(stamp: tuple):
    return core.compute(core.load())


# ---------- données
today = str(dt.date.today())
status = refresh_data(today)
stamp = tuple((r["actif"], str(r["dernier"])) for r in status) + (today,)
OUT = compute(stamp)

with st.sidebar:
    st.header("Données")
    last = OUT["BTC"]["dates"][-1]
    st.write(f"Clôtures journalières jusqu'au **{fdate(last)}**.")
    fails = [r for r in status if str(r["source"]).startswith("échec")]
    if fails:
        st.warning("Mise à jour impossible pour : " + ", ".join(r["actif"] for r in fails)
                   + ". Les données en cache sont utilisées. Vérifie la connexion internet.")
    st.dataframe(pd.DataFrame(status).rename(columns={"actif": "Actif", "ajout": "Jours ajoutés", "dernier": "Dernière date", "source": "Source"}),
                 hide_index=True, width="stretch")
    if st.button("Mettre à jour maintenant", width="stretch"):
        refresh_data.clear()
        compute.clear()
        st.rerun()
    st.caption("Les cours sont récupérés à l'ouverture (au plus toutes les 6 heures) depuis Binance, ou Kraken en secours. "
               "Ce n'est pas un conseil d'investissement.")

st.title("Plan Fibonacci : zones d'achat, zones de vente et points d'or")
st.caption("Achats à −50 %, −61,8 % et −78,6 % sous l'ATH ; ventes au retour de l'ATH puis aux extensions 1,272, 1,618 et 2,618 "
           "du mouvement ATH → creux. Points d'or : rares signaux du radar d'opportunités.")
age = (pd.Timestamp(today) - pd.Timestamp(last)).days
if age > 3:
    st.error(f"Les données s'arrêtent au {fdate(last)} ({age} jours) : les niveaux ci-dessous ne tiennent pas compte des derniers mouvements.")


def chart(k, D):
    dates = pd.to_datetime(D["dates"])
    price = D["price"]
    c = D["cur"]
    n = len(dates)
    future = dates[-1] + pd.Timedelta(days=max(30, int(n * 0.07)))
    idx = {d: i for i, d in enumerate(D["dates"])}
    fig = go.Figure()

    def seg(x0, x1, y, color, width=1.2, opacity=1.0, group=None, name=None, show=False):
        fig.add_trace(go.Scatter(x=[x0, x1], y=[y, y], mode="lines", line=dict(color=color, width=width, dash="dash"),
                                 opacity=opacity, hoverinfo="skip", legendgroup=group, name=name, showlegend=show))

    # cycles passés
    first_buy = first_sell = True
    for cy in D["cycles"]:
        if not cy["done"]:
            continue
        top, bot = pd.Timestamp(cy["top"]), pd.Timestamp(cy["bot"])
        nxt = next((z for z in D["cycles"] if z["top"] > cy["bot"]), None)
        end = pd.Timestamp(nxt["top"]) if nxt else dates[-1]
        for b in cy["buy"]:
            seg(top, bot, b["p"], GREEN, opacity=0.5, group="buy", name="Zones d'achat Fibonacci", show=first_buy)
            first_buy = False
        for e in cy["ext"]:
            x1 = min(end, pd.Timestamp(e["hit"])) if e["hit"] else end
            seg(bot, x1, e["p"], RED, opacity=0.45, group="sell", name="Zones de vente Fibonacci", show=first_sell)
            first_sell = False
    # cycle en cours
    for b in c["buy"]:
        seg(pd.Timestamp(c["athD"]), future, b["p"], GREEN, width=1.6, group="buy", show=first_buy)
        first_buy = False
        fig.add_annotation(x=future, y=math.log10(b["p"]), text=f"−{str(b['r']).replace('.', ',')} %  {fnum(b['p'])}", showarrow=False,
                           xanchor="left", font=dict(color=GREEN, size=11), yref="y")
    for e in c["ext"]:
        seg(pd.Timestamp(c["lowD"]), future, e["p"], RED, width=1.6, group="sell", show=first_sell)
        first_sell = False
        lab = "ATH" if e["x"] == 1 else "×" + str(e["x"]).replace(".", ",")
        fig.add_annotation(x=future, y=math.log10(e["p"]), text=f"{lab}  {fnum(e['p'])}", showarrow=False, xanchor="left",
                           font=dict(color=RED, size=11), yref="y")
    fig.add_vrect(x0=dates[-1], x1=future, fillcolor="rgba(128,128,128,0.08)", line_width=0,
                  annotation_text="à venir", annotation_position="bottom left")
    # prix
    fig.add_trace(go.Scatter(x=dates, y=price, mode="lines", line=dict(color="#2b3645", width=1.4), name=f"Prix {k}",
                             hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.4~f} $<extra></extra>"))
    # ordres de la stratégie
    tb = [t for t in D["fib"]["trades"] if t["t"] == "Achat" and t["d"] in idx]
    ts = [t for t in D["fib"]["trades"] if t["t"] == "Vente" and t["d"] in idx]
    if tb:
        fig.add_trace(go.Scatter(x=[pd.Timestamp(t["d"]) for t in tb], y=[price[idx[t["d"]]] * 0.9 for t in tb], mode="markers",
                                 marker=dict(symbol="triangle-up", size=10, color=GREEN), name="Achat stratégie",
                                 text=[t["why"] for t in tb], hovertemplate="%{x|%d/%m/%Y}<br>Achat : %{text}<extra></extra>"))
    if ts:
        fig.add_trace(go.Scatter(x=[pd.Timestamp(t["d"]) for t in ts], y=[price[idx[t["d"]]] * 1.1 for t in ts], mode="markers",
                                 marker=dict(symbol="triangle-down", size=10, color=RED), name="Vente stratégie",
                                 text=[t["why"] for t in ts], hovertemplate="%{x|%d/%m/%Y}<br>Vente : %{text}<extra></extra>"))
    gb, gs = D["gold"]["buy"], D["gold"]["sell"]
    if gb:
        fig.add_trace(go.Scatter(x=[pd.Timestamp(g["dmin"]) for g in gb], y=[g["pmin"] * 0.8 for g in gb], mode="markers",
                                 marker=dict(symbol="star", size=16, color=GOLD, line=dict(color="#8a6508", width=1)), name="Entrée en or",
                                 text=[f"{fdate(g['a'])} → {fdate(g['b'])}" for g in gb], hovertemplate="Entrée en or<br>%{text}<extra></extra>"))
    if gs:
        fig.add_trace(go.Scatter(x=[pd.Timestamp(g["dmax"]) for g in gs], y=[g["pmax"] * 1.25 for g in gs], mode="markers",
                                 marker=dict(symbol="star-open", size=16, color=GOLD, line=dict(width=2)), name="Sortie en or",
                                 text=[f"{fdate(g['a'])} → {fdate(g['b'])}" for g in gs], hovertemplate="Sortie en or<br>%{text}<extra></extra>"))
    ymin = min(min(price), c["buy"][2]["p"]) * 0.7
    ymax = max(max(price), c["ext"][3]["p"]) * 1.2
    fig.update_yaxes(type="log", range=[math.log10(ymin), math.log10(ymax)],
                     title=None, gridcolor="rgba(128,128,128,0.15)")
    fig.update_xaxes(range=[dates[0], future + pd.Timedelta(days=int(n * 0.1))], gridcolor="rgba(128,128,128,0.1)")
    fig.update_layout(height=580, margin=dict(l=10, r=10, t=10, b=10), hovermode="closest",
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0))
    return fig


def render(k):
    D = OUT[k]
    c, g, f = D["cur"], D["gold"], D["fib"]
    if k in WARN:
        st.info(WARN[k])
    hit = sum(1 for b in c["buy"] if b["hit"])
    if c["price"] >= c["ath"]:
        phase = "Au-dessus de l'ATH"
    elif hit == 0:
        phase = "En attente du 1er palier"
    elif hit < 3:
        phase = f"Accumulation : {hit}/3 paliers"
    else:
        phase = "Tous les paliers touchés"
    nb = next((b for b in c["buy"] if not b["hit"] and b["p"] < c["price"]), None)
    ns = next((e for e in c["ext"] if e["p"] > c["price"]), None)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Prix {k}", fprice(c["price"]), f"{fpct(-c['dd'])} sous l'ATH", delta_color="off")
    c2.metric("Phase Fibonacci", phase, f"creux du cycle {fprice(c['low'])}", delta_color="off")
    c3.metric("Prochain achat", fprice(nb["p"]) if nb else "–", fpct((nb["p"] / c["price"] - 1) * 100) if nb else "aucun palier restant", delta_color="off")
    c4.metric("Prochaine vente", fprice(ns["p"]) if ns else "–", fpct((ns["p"] / c["price"] - 1) * 100) if ns else None, delta_color="off")
    if g["sbNow"]:
        st.success(f"★ Entrée en or active aujourd'hui (score {g['score']}/100).")
    elif g["ssNow"]:
        st.warning(f"☆ Sortie en or active aujourd'hui (score {g['score']}/100).")
    else:
        st.caption(f"Point d'or : aucun aujourd'hui. Score du radar : {g['score'] if g['score'] is not None else '–'} / 100.")

    st.plotly_chart(chart(k, D), width="stretch")

    a, b = st.columns(2)
    with a:
        st.subheader("Prochaines zones d'achat")
        st.dataframe(pd.DataFrame([{"Palier": f"−{str(x['r']).replace('.', ',')} %", "Prix": fprice(x["p"]),
                                    "Distance": fpct((x["p"] / c["price"] - 1) * 100), "Part du cash": f"{w} %",
                                    "État": f"touché le {fdate(x['hit'])}" if x["hit"] else "en attente"}
                                   for x, w in zip(c["buy"], [50, 30, 20])]), hide_index=True, width="stretch")
        st.caption(f"Depuis l'ATH du {fdate(c['athD'])} ({fprice(c['ath'])}).")
    with b:
        st.subheader("Prochaines zones de vente")
        st.dataframe(pd.DataFrame([{"Niveau": "Retour à l'ATH" if x["x"] == 1 else f"Extension {str(x['x']).replace('.', ',')}",
                                    "Prix": fprice(x["p"]), "Distance": fpct((x["p"] / c["price"] - 1) * 100), "Part vendue": f"{w} %"}
                                   for x, w in zip(c["ext"], [30, 30, 20, 20])]), hide_index=True, width="stretch")
        st.caption(f"Mouvement ATH {fprice(c['ath'])} → creux {fprice(c['low'])} ({fdate(c['lowD'])}). Si ce creux est cassé, les extensions baissent.")

    st.subheader("Points d'or")
    st.caption(f"Entrée en or : {g['rule'][0]}. Sortie en or : {g['rule'][1]}.")
    a, b = st.columns(2)

    def gt(E, buy):
        if not E:
            return pd.DataFrame([{"Période": "Aucun signal"}])
        return pd.DataFrame([{"Période": fdate(e["a"]) + ("" if e["a"] == e["b"] else " → " + fdate(e["b"])),
                              ("Plus bas" if buy else "Plus haut"): fprice(e["pmin"] if buy else e["pmax"]),
                              "12 mois après le début": "en cours" if e["f365"] is None else fpct(e["f365"])} for e in reversed(E)])
    with a:
        st.markdown("**Entrées en or**")
        st.dataframe(gt(g["buy"], True), hide_index=True, width="stretch")
    with b:
        st.markdown("**Sorties en or**")
        st.dataframe(gt(g["sell"], False), hide_index=True, width="stretch")

    st.subheader("Cycles Fibonacci passés")
    rows = []
    for z in reversed(D["cycles"]):
        r = {"ATH": f"{fdate(z['top'])} · {fprice(z['topP'])}"}
        for x in z["buy"]:
            r[f"−{str(x['r']).replace('.', ',')} %"] = f"{fprice(x['p'])} · {fdate(x['hit']) if x['hit'] else 'non touché'}"
        r["Creux"] = f"{fdate(z['bot'])} · {fprice(z['botP'])} ({str(z['dd']).replace('.', ',')} %)" + ("" if z["done"] else " · en cours")
        for x in z["ext"]:
            lab = "Retour ATH" if x["x"] == 1 else "×" + str(x["x"]).replace(".", ",")
            r[lab] = f"{fprice(x['p'])} · {fdate(x['hit']) if x['hit'] else 'non touché'}"
        rows.append(r)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.subheader("La stratégie Fibonacci appliquée avec 10 000 $")
    st.caption(f"Départ au {fdate(D['start'])}. Achats 50/30/20 % du cash aux trois paliers, ventes 30/30/20/20 % de la position aux quatre niveaux, "
               "exécution à l'ouverture du lendemain, frais 0,1 %.")
    m1, m2, m3 = st.columns(3)
    m1.metric("Stratégie Fibonacci", fprice(f["final"]), f"pire baisse {fpct(f['dd'])}", delta_color="off")
    m2.metric("Buy & hold", fprice(f["bh"]), f"pire baisse {fpct(f['bhdd'])}", delta_color="off")
    m3.metric("Aujourd'hui", f"{fprice(f['cash'])} cash", f"{fprice(f['coin'])} en {k}", delta_color="off")
    with st.expander("Voir tous les ordres"):
        st.dataframe(pd.DataFrame([{"Ordre": t["t"], "Date": fdate(t["d"]), "Prix": fprice(t["p"]), "Montant": fprice(t["v"]), "Motif": t["why"]}
                                   for t in reversed(f["trades"])]), hide_index=True, width="stretch")


@st.cache_data(show_spinner=False)
def sim_markets(stamp: tuple):
    return sim.load_markets()


@st.cache_data(show_spinner="Simulation en cours…")
def sim_run(stamp, start, capital, pocket_amt, liq, pocket, inject, stake, stable_rate, bot_years):
    btc, gold, qqq = sim_markets(stamp)
    F = sim.factors(btc.index, gold, qqq, stable_rate, dict(bot_years))
    return sim.run(btc, F, start, capital, pocket_amt, liq, pocket, inject, stake)


def render_sim():
    st.caption("Stratégie Fibonacci sur BTC, avec la liquidité en attente placée quelque part et, en option, une poche séparée "
               "(bot de trading, or…) dont les gains sont réinjectés en BTC à chaque palier d'achat. "
               "Simulation sur le passé : ce n'est pas un conseil d'investissement.")
    btc, gold, qqq = sim_markets(stamp)
    c1, c2, c3 = st.columns(3)
    with c1:
        start = st.date_input("Date de départ", value=dt.date(2021, 4, 10), min_value=dt.date(2016, 1, 1),
                              max_value=(btc.index[-1] - pd.Timedelta(days=30)).date(), format="DD/MM/YYYY")
        capital = st.number_input("Capital total ($)", min_value=1000, value=14000, step=1000)
    with c2:
        liq = st.selectbox("Placement de la liquidité en attente", list(sim.PLACEMENTS), index=2, format_func=sim.PLACEMENTS.get)
        stake = st.number_input("Staking sur les BTC détenus (%/an)", min_value=0.0, max_value=15.0, value=2.0, step=0.5)
        stable_rate = st.number_input("Rendement stablecoins / monétaire (%/an)", min_value=0.0, max_value=20.0, value=4.0, step=0.5)
    with c3:
        pocket_amt = st.number_input("Poche séparée ($, 0 = aucune)", min_value=0, max_value=int(capital) - 500, value=4000, step=500)
        pocket = st.selectbox("Contenu de la poche", list(sim.POCKETS), index=0, format_func=sim.POCKETS.get, disabled=pocket_amt == 0)
        inject = st.checkbox("Réinjecter les gains de la poche en BTC à chaque palier d'achat", value=True, disabled=pocket_amt == 0)
    bot_years = sim.BOT_YEARS
    if pocket_amt and pocket == "bot":
        with st.expander("Rendements annuels du bot (modifiables)"):
            st.caption("Par défaut : portefeuille BTC/ETH/SOL du projet BotCrypto (FINDINGS, 26/09/2026), hors échantillon à partir d'avril 2021. "
                       "Avant, la poche reste en cash. Le rendement de chaque année est réparti uniformément sur l'année.")
            ed = st.data_editor(pd.DataFrame({"Année": list(bot_years), "Rendement (%)": list(bot_years.values())}),
                                hide_index=True, disabled=["Année"], key="bot_years")
            bot_years = {int(a): float(r) for a, r in zip(ed["Année"], ed["Rendement (%)"])}
    args = (str(start), float(capital), float(pocket_amt), liq, pocket, bool(inject), float(stake), float(stable_rate), tuple(bot_years.items()))
    E, inj, orders = sim_run(stamp, *args)
    if E.empty:
        st.warning("Pas assez de données après cette date.")
        return
    last = E.iloc[-1]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Valeur finale", fprice(last.total), f"×{str(round(last.total / capital, 2)).replace('.', ',')} le capital", delta_color="off")
    m2.metric("Buy & hold BTC", fprice(last.buy_hold), f"pire baisse {fpct(sim.max_dd(E.buy_hold))}", delta_color="off")
    m3.metric("Pire baisse de la stratégie", fpct(sim.max_dd(E.total)), None)
    m4.metric("BTC détenus", f"{last.btc:.4f}".replace(".", ","), f"+ {fprice(last.liquidite)} de liquidité" + (f", {fprice(last.poche)} en poche" if pocket_amt else ""), delta_color="off")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=E.index, y=E.btc * E.prix, stackgroup="v", name="BTC", line=dict(width=0, color="#f2a900")))
    fig.add_trace(go.Scatter(x=E.index, y=E.liquidite, stackgroup="v", name="Liquidité placée", line=dict(width=0, color="#7f9cc4")))
    if pocket_amt:
        fig.add_trace(go.Scatter(x=E.index, y=E.poche, stackgroup="v", name="Poche séparée", line=dict(width=0, color="#9b7fc4")))
    fig.add_trace(go.Scatter(x=E.index, y=E.buy_hold, name="Buy & hold BTC", line=dict(color=INK, width=1.5, dash="dot")))
    for d, g in inj:
        fig.add_annotation(x=d, y=E.total.loc[d], text=f"injection {fnum(g)} $", showarrow=True, arrowhead=2, font=dict(size=10))
    fig.update_layout(height=460, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0), yaxis=dict(title="$", gridcolor="rgba(128,128,128,0.15)"))
    st.plotly_chart(fig, width="stretch")

    st.subheader("Comparaison des placements de la liquidité")
    st.caption("Même date de départ, même capital, même poche : seul le placement de la liquidité change.")
    rows = []
    for key, lab in sim.PLACEMENTS.items():
        Ek, _, _ = sim_run(stamp, args[0], args[1], args[2], key, *args[4:])
        rows.append({"Liquidité": lab, "Valeur finale": Ek.total.iloc[-1], "BTC détenus": Ek.btc.iloc[-1],
                     "Pire baisse": sim.max_dd(Ek.total), "_sel": key == liq})
    R = pd.DataFrame(rows).sort_values("Valeur finale", ascending=False)
    R["Liquidité"] = [("▶ " if s else "") + l for l, s in zip(R["Liquidité"], R["_sel"])]
    st.dataframe(pd.DataFrame({"Liquidité": R["Liquidité"], "Valeur finale": R["Valeur finale"].map(fprice),
                               "BTC détenus": R["BTC détenus"].map(lambda v: f"{v:.4f}".replace(".", ",")),
                               "Pire baisse": R["Pire baisse"].map(fpct)}), hide_index=True, width="stretch")
    with st.expander("Ordres Fibonacci et injections sur la période"):
        st.dataframe(pd.DataFrame([{"Date": fdate(d), "Ordre": t, "Prix BTC": fprice(p), "Montant": fprice(v), "Motif": w}
                                   for d, t, p, v, w in reversed(orders)]), hide_index=True, width="stretch")
    st.caption(f"Données : BTC jusqu'au {fdate(btc.index[-1])} ; or (moyennes mensuelles interpolées, puis PAXG) et Nasdaq-100 "
               f"(QQQ mensuel interpolé, puis quotidien) mis à jour avec les autres cours. Nasdaq ×2 reconstruit à partir du Nasdaq "
               "(frais 0,95 %, coût du financement, érosion du levier quotidien). Frais : 0,1 % par ordre BTC, 0,25 %/an sur l'or, "
               "dividendes Nasdaq ~0,5 %/an. Montants en dollars, avant impôts.")


for k, tab in zip(ASSETS + ["Simulations"], st.tabs(ASSETS + ["Simulations"])):
    with tab:
        render(k) if k in ASSETS else render_sim()
