"""Alertes e-mail du Plan Fibonacci.
1. Met à jour les cours (data_update), 2. recalcule (core),
3. compare avec l'état précédent (alerts_state.json), 4. envoie un e-mail s'il y a du nouveau.

Variables d'environnement :
  SMTP_HOST (défaut smtp.gmail.com), SMTP_PORT (défaut 465), SMTP_USER, SMTP_PASSWORD, MAIL_TO
  ALERT_NEAR_PCT (défaut 5) : prévenir quand le prix est à moins de X % d'un niveau non encore touché
  DRY_RUN=1 : affiche l'e-mail au lieu de l'envoyer
"""
import json, os, smtplib, ssl, datetime as dt
from email.message import EmailMessage
import core, data_update

H = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(H, "alerts_state.json")
NEAR = float(os.environ.get("ALERT_NEAR_PCT") or "5")
APP_URL = os.environ.get("APP_URL", "")


def fnum(v):
    v = float(v); d = 0 if v >= 1000 else 1 if v >= 100 else 2 if v >= 1 else 4
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",") + " $"


def lvl_name(kind, v):
    if kind == "buy":
        return f"palier d'achat −{str(v).replace('.', ',')} %"
    return "retour à l'ATH" if v == 1 else f"extension de vente ×{str(v).replace('.', ',')}"


def snapshot(D):
    c, g = D["cur"], D["gold"]
    return {"athD": c["athD"], "ath": c["ath"], "price": c["price"], "date": D["dates"][-1],
            "buy": {str(b["r"]): b["hit"] for b in c["buy"]},
            "ext": {str(e["x"]): (c["price"] >= e["p"]) for e in c["ext"]},
            "near": {}, "gb": g["sbNow"], "gs": g["ssNow"]}


def diff(k, D, old):
    """Renvoie la liste des événements (niveau, texte) entre l'ancien état et le nouveau."""
    c, g = D["cur"], D["gold"]
    new = snapshot(D)
    ev = []
    if old is None:
        return ev, new
    if new["athD"] != old["athD"]:
        ev.append(("info", f"Nouvel ATH le {new['athD']} à {fnum(c['ath'])} : un nouveau cycle Fibonacci commence, les paliers sont recalculés."))
        new["near"] = {}
        return ev, new
    new["near"] = dict(old.get("near", {}))
    for b in c["buy"]:
        key = str(b["r"])
        if b["hit"] and not old["buy"].get(key):
            ev.append(("achat", f"Zone d'achat touchée : {lvl_name('buy', b['r'])} à {fnum(b['p'])} (clôture {fnum(c['price'])})."))
        elif not b["hit"] and b["p"] < c["price"] and (c["price"] / b["p"] - 1) * 100 <= NEAR and not new["near"].get("b" + key):
            ev.append(("proche", f"Proche d'une zone d'achat : {lvl_name('buy', b['r'])} à {fnum(b['p'])}, prix actuel {fnum(c['price'])}."))
            new["near"]["b" + key] = True
    for e in c["ext"]:
        key = str(e["x"])
        if c["price"] >= e["p"] and not old["ext"].get(key):
            ev.append(("vente", f"Zone de vente touchée : {lvl_name('ext', e['x'])} à {fnum(e['p'])} (clôture {fnum(c['price'])})."))
        elif c["price"] < e["p"] and (1 - c["price"] / e["p"]) * 100 <= NEAR and not new["near"].get("e" + key):
            ev.append(("proche", f"Proche d'une zone de vente : {lvl_name('ext', e['x'])} à {fnum(e['p'])}, prix actuel {fnum(c['price'])}."))
            new["near"]["e" + key] = True
    if g["sbNow"] and not old.get("gb"):
        ev.append(("or", f"★ ENTRÉE EN OR : signal d'opportunité exceptionnelle allumé (score {g['score']}/100)."))
    if g["ssNow"] and not old.get("gs"):
        ev.append(("or", f"☆ SORTIE EN OR : zone de vente exceptionnelle allumée (score {g['score']}/100)."))
    return ev, new


COL = {"achat": "#11875f", "vente": "#c8452f", "or": "#b07d09", "proche": "#5d6878", "info": "#3a6fd8"}


def build_mail(events, out):
    gold = any(t == "or" for _, evs in events for t, _ in evs)
    kinds = {t for _, evs in events for t, _ in evs}
    tag = "★ Point d'or" if gold else "Zone touchée" if kinds & {"achat", "vente"} else "Info"
    subj = f"[Plan Fibo] {tag} : " + ", ".join(k for k, _ in events)
    txt, html = [], ["<div style='font-family:Arial,sans-serif;font-size:15px;color:#18202b'>"]
    for k, evs in events:
        c = out[k]["cur"]
        txt.append(f"{k} — {fnum(c['price'])} ({out[k]['dates'][-1]})")
        html.append(f"<h3 style='margin:18px 0 6px'>{k} · {fnum(c['price'])}</h3><ul style='margin:0;padding-left:18px'>")
        for t, m in evs:
            txt.append("  - " + m)
            html.append(f"<li style='color:{COL[t]};margin:4px 0'>{m}</li>")
        nb = next((b for b in c["buy"] if not b["hit"] and b["p"] < c["price"]), None)
        ns = next((e for e in c["ext"] if e["p"] > c["price"]), None)
        extra = f"Prochain achat : {fnum(nb['p']) if nb else '–'} · prochaine vente : {fnum(ns['p']) if ns else '–'}"
        txt.append("  " + extra)
        html.append(f"</ul><p style='color:#5d6878;margin:6px 0'>{extra}</p>")
    if APP_URL:
        txt.append("\n" + APP_URL)
        html.append(f"<p><a href='{APP_URL}'>Ouvrir le Plan Fibonacci</a></p>")
    foot = "Alerte automatique, clôtures journalières. Ce n'est pas un conseil d'investissement."
    txt.append("\n" + foot)
    html.append(f"<p style='color:#98a3b3;font-size:12px'>{foot}</p></div>")
    return subj, "\n".join(txt), "".join(html)


def send(subj, txt, html):
    if os.environ.get("DRY_RUN") == "1" or not os.environ.get("SMTP_USER"):
        print("=== E-MAIL (non envoyé) ===\n" + subj + "\n" + txt)
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subj, os.environ["SMTP_USER"], os.environ["MAIL_TO"]
    msg.set_content(txt)
    msg.add_alternative(html, subtype="html")
    host, port = os.environ.get("SMTP_HOST") or "smtp.gmail.com", int(os.environ.get("SMTP_PORT") or "465")
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as s:
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"]); s.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"]); s.send_message(msg)
    print("E-mail envoyé :", subj)


def main():
    for r in data_update.update_all():
        print(r)
    out = core.compute(core.load())
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    first = not state
    events, newstate = [], {}
    for k in core.ASSETS:
        ev, ns = diff(k, out[k], state.get(k))
        newstate[k] = ns
        if ev:
            events.append((k, ev))
    if first:
        lines = []
        for k in core.ASSETS:
            c = out[k]["cur"]
            nb = next((b for b in c["buy"] if not b["hit"] and b["p"] < c["price"]), None)
            ns = next((e for e in c["ext"] if e["p"] > c["price"]), None)
            lines.append(("info", f"Suivi activé. Prix {fnum(c['price'])} · prochain achat {fnum(nb['p']) if nb else '–'} · prochaine vente {fnum(ns['p']) if ns else '–'}"))
        subj, txt, html = build_mail([(k, [l]) for k, l in zip(core.ASSETS, lines)], out)
        send("[Plan Fibo] Alertes activées", txt, html)
    elif events:
        send(*build_mail(events, out))
    else:
        print("Rien de nouveau.")
    json.dump(newstate, open(STATE, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
