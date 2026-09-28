"""Met à jour data/<actif>.csv avec les clôtures journalières récentes.
Sources publiques, sans clé : Binance (paires USDT), puis Kraken (paires USD) en secours.
Seuls les jours terminés (avant aujourd'hui en UTC) sont ajoutés."""
import os,time,datetime as dt
import pandas as pd,requests
H=os.path.dirname(os.path.abspath(__file__))
BINANCE={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","link":"LINKUSDT","aave":"AAVEUSDT","tao":"TAOUSDT","bnb":"BNBUSDT"}
KRAKEN={"btc":"XBTUSD","eth":"ETHUSD","sol":"SOLUSD","link":"LINKUSD","aave":"AAVEUSD","tao":"TAOUSD","bnb":"BNBUSD"}
HOSTS=["https://api.binance.com","https://data-api.binance.vision"]
def _today():return pd.Timestamp(dt.datetime.now(dt.timezone.utc).date())
def _binance(sym,start):
    out={};t0=int(start.timestamp()*1000)
    for host in HOSTS:
        try:
            out={};t=t0
            while True:
                r=requests.get(f"{host}/api/v3/klines",params={"symbol":sym,"interval":"1d","startTime":t,"limit":1000},timeout=15);r.raise_for_status();rows=r.json()
                if not rows:break
                for k in rows:out[pd.Timestamp(int(k[0]),unit="ms")]=float(k[4])
                if len(rows)<1000:break
                t=int(rows[-1][0])+86400000
            return out,host.split("//")[1]
        except Exception as e:
            last=e
    raise last
def _kraken(pair,start):
    out={};since=int(start.timestamp())
    for _ in range(10):
        r=requests.get("https://api.kraken.com/0/public/OHLC",params={"pair":pair,"interval":1440,"since":since},timeout=15);r.raise_for_status();j=r.json()
        if j.get("error"):raise RuntimeError(j["error"])
        rows=next(v for k,v in j["result"].items() if k!="last")
        for k in rows:out[pd.Timestamp(int(k[0]),unit="s")]=float(k[4])
        if len(rows)<700:break
        since=int(j["result"]["last"])
    return out,"kraken"
def update_asset(a):
    path=f"{H}/data/{a}.csv";s=pd.read_csv(path,index_col=0,parse_dates=True).iloc[:,0]
    last=s.index[-1];today=_today()
    if last>=today-pd.Timedelta(days=1):return {"actif":a.upper(),"ajout":0,"dernier":str(last.date()),"source":"déjà à jour"}
    start=last+pd.Timedelta(days=1)
    try:new,src=_binance(BINANCE[a],start)
    except Exception:
        new,src=_kraken(KRAKEN[a],start)
    new={d:c for d,c in new.items() if last<d<today}
    if new:
        s=pd.concat([s,pd.Series(new)]).sort_index();s=s[~s.index.duplicated(keep="last")]
        s.rename("close").rename_axis("date").to_csv(path,float_format="%.6g")
    return {"actif":a.upper(),"ajout":len(new),"dernier":str(s.index[-1].date()),"source":src}
def update_all():
    res=[]
    for a in BINANCE:
        try:res.append(update_asset(a))
        except Exception as e:res.append({"actif":a.upper(),"ajout":0,"dernier":None,"source":f"échec : {type(e).__name__}"})
    return res
if __name__=="__main__":
    for r in update_all():print(r)
