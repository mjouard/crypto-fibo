"""Calculs : cycles Fibonacci, stratégie Fibonacci, radar BTC et points d'or."""
import pandas as pd,numpy as np,json,bisect,os
H=os.path.dirname(os.path.abspath(__file__))
def load(H=H):
    return {a:rd(a.lower(),H) for a in ASSETS+["BNB"]}
def rd(a,H=H):
    s=pd.read_csv(f"{H}/data/{a}.csv",index_col=0,parse_dates=True).iloc[:,0].dropna()
    s=s[~s.index.duplicated(keep="last")].sort_index()
    s=s.asfreq("D").ffill()  # comble d'éventuels jours manquants
    return s
ASSETS=["BTC","ETH","SOL","LINK","AAVE","TAO"];REFS_ALL=["BTC","ETH","BNB","SOL","LINK","AAVE"]
START={"BTC":"2015-01-01","ETH":"2016-06-01","SOL":"2021-01-01","LINK":"2018-01-01","AAVE":"2020-10-10","TAO":"2024-10-08"}
BUY=[(50,.5),(61.8,.3),(78.6,.2)];EXT=[(1.0,.3),(1.272,.3),(1.618,.2),(2.618,.2)]
# ---------- radar BTC (on-chain + prix, percentile 4 ans)
def btc_radar(price,H=H):
    cm=pd.read_csv(f"{H}/data/btc_onchain.csv",index_col=0,parse_dates=True)
    idx=price.index;tail=idx[idx>cm.index[-1]]
    rc=cm.CapMrktCurUSD/cm.CapMVRVCur;drift=(rc.iloc[-1]/rc.iloc[-91])**(1/90)
    rc=pd.concat([rc,pd.Series([rc.iloc[-1]*drift**(k+1) for k in range(len(tail))],index=tail)]).reindex(idx)
    sup=pd.concat([cm.SplyCur,pd.Series([cm.SplyCur.iloc[-1]+450*(k+1) for k in range(len(tail))],index=tail)]).reindex(idx)
    iss=pd.concat([cm.IssTotNtv,pd.Series(450.0,index=tail)]).reindex(idx)*price
    M=pd.DataFrame({"price":price}).loc["2011-06-01":];p=M.price
    M["mvrv"]=p*sup/rc;M["puell"]=iss/iss.rolling(365,min_periods=200).mean()
    M["mayer"]=p/p.rolling(200).mean();M["wma200"]=p/p.rolling(1400,min_periods=700).mean();M["ath"]=p/p.cummax();M["ret90"]=p/p.shift(90)-1
    rp=lambda s:s.rolling(1460,min_periods=365).apply(lambda a:(a[:-1]<a[-1]).mean(),raw=True)
    Pp=pd.DataFrame({f:rp(M[f]) for f in ["mvrv","puell","mayer","wma200","ath","ret90"]})
    return Pp.mean(axis=1)*100
# ---------- score altcoins (mesures ajustées volatilité, comparées aux autres cryptos)
FE=["mayer","dd","r90","y1"]
def feats(p):
    lp=np.log(p);vol=lp.diff().rolling(365,min_periods=180).std()*np.sqrt(365);F=pd.DataFrame(index=p.index)
    F["mayer"]=(lp-np.log(p.rolling(200).mean()))/vol;F["dd"]=(lp-np.log(p.cummax()))/vol
    F["r90"]=(lp-lp.shift(90))/vol;F["y1"]=(lp-np.log(p.rolling(365,min_periods=300).mean()))/vol;return F
def pooled(target,P):
    refs=[x for x in REFS_ALL if x!=target];Fs={k:feats(P[k]) for k in refs+[target]};T=Fs[target];out=pd.DataFrame(index=T.index)
    for f in FE:
        ref=pd.concat([Fs[k][f] for k in refs]).dropna().sort_index();rdx=ref.index.values;rv=ref.values;hist=[];j=0;res=[]
        for d,vv in T[f].items():
            while j<len(rdx) and rdx[j]<=np.datetime64(d):bisect.insort(hist,rv[j]);j+=1
            res.append(np.nan if np.isnan(vv) or len(hist)<500 else bisect.bisect_left(hist,vv)/len(hist))
        out[f]=res
    sc=out.mean(axis=1)*100;sc[out.notna().sum(axis=1)<3]=np.nan;return sc
# ---------- Fibonacci
def cycles(s):
    v=s.values;ix=s.index;n=len(v);out=[];ath=v[0];ia=0;j=1
    while j<n:
        if v[j]>ath:ath=v[j];ia=j;j+=1;continue
        k=j
        while k<n and v[k]<=ath:k+=1
        seg=v[ia:k];ib=ia+int(seg.argmin());dd=seg.min()/ath-1
        if dd<=-0.5:
            c={"top":str(ix[ia].date()),"topP":float(ath),"bot":str(ix[ib].date()),"botP":float(seg.min()),"dd":round(dd*100,1),"done":k<n,"regain":str(ix[k].date()) if k<n else None,"buy":[],"ext":[]}
            for r,_ in BUY:
                lv=ath*(1-r/100);hit=next((str(ix[t].date()) for t in range(ia,k) if v[t]<=lv),None);c["buy"].append({"r":r,"p":lv,"hit":hit})
            for x,_ in EXT:
                lv=seg.min()+x*(ath-seg.min());hit=next((str(ix[t].date()) for t in range(ib,n) if v[t]>=lv),None);c["ext"].append({"x":x,"p":lv,"hit":hit})
            out.append(c)
        if k>=n:break
        ath=v[k];ia=k;j=k+1
    return out
def fib_bt(s,start,cap=10000,fee=.001):
    C=s.values;ix=s.index;si=ix.get_loc(pd.Timestamp(start))
    cash,q=cap,0.;A=C[0];bf=[False]*3;bud=None;sell=None;pend=[];tr=[];eq=[]
    for i in range(1,len(C)):
        o=C[i-1]
        for side,x,why in pend:
            if side=="B":
                amt=min(cash,x)
                if amt>1:q+=amt*(1-fee)/o;cash-=amt;tr.append(("Achat",i,o,amt,why))
            else:
                qq=min(q,x)
                if qq>0:cash+=qq*o*(1-fee);q-=qq;tr.append(("Vente",i,o,qq*o,why))
        pend=[]
        if i==si:
            V=cash+q*o;kf=cap/V;cash*=kf;q*=kf;bud=bud*kf if bud else bud
            if sell and sell["Q0"]:sell["Q0"]*=kf
            tr=[t for t in tr if t[1]>=si]
            if q>0:tr.append(("Position reprise",i,o,q*o,"état hérité du cycle en cours"))
        c=C[i]
        if c>A:A=c;bf=[False]*3;bud=None
        for kk,(r,f) in enumerate(BUY):
            if not bf[kk] and c<=A*(1-r/100):
                if bud is None:bud=cash
                bf[kk]=True;pend.append(("B",bud*f,f"−{r} % depuis l'ATH".replace(".",",")))
                if sell is None or sell["A"]!=A or sell["st"]:sell={"A":A,"B":c,"Q0":None,"fl":[False]*4,"st":False}
        if sell:
            if not sell["st"]:sell["B"]=min(sell["B"],c)
            for kk,(x,f) in enumerate(EXT):
                lv=sell["B"]+x*(sell["A"]-sell["B"])
                if not sell["fl"][kk] and c>=lv and q>0:
                    if not sell["st"]:sell["st"]=True;sell["Q0"]=q
                    sell["fl"][kk]=True;pend.append(("S",sell["Q0"]*f,"retour à l'ATH" if x==1 else f"extension {x}".replace(".",",")))
        if i>=si:eq.append(cash+q*c)
    e=np.array(eq);bh=cap*(1-fee)/C[si]*C[si:];mdd=lambda a:round(((a/np.maximum.accumulate(a))-1).min()*100,1)
    return {"final":round(e[-1]),"dd":mdd(e),"bh":round(bh[-1]),"bhdd":mdd(bh),"cash":round(cash),"coin":round(q*C[-1]),
            "trades":[{"t":t[0],"d":str(ix[t[1]].date()),"p":round(float(t[2]),4),"v":round(t[3]),"why":t[4]} for t in tr]}
def eps(m,p):
    d=m.index[m.values];out=[]
    for x in d:
        if out and (x-out[-1][1]).days<=30:out[-1][1]=x
        else:out.append([x,x])
    f365=p.shift(-365)/p-1
    return [{"a":str(a.date()),"b":str(b.date()),"pmin":float(p.loc[a:b].min()),"pmax":float(p.loc[a:b].max()),"dmin":str(p.loc[a:b].idxmin().date()),"dmax":str(p.loc[a:b].idxmax().date()),
             "days":int(m.loc[a:b].sum()),"pa":float(p.loc[a]),"f365":None if np.isnan(f365.loc[a]) else round(float(f365.loc[a])*100)} for a,b in out]
def compute(P):
    OUT={}
    for k in ASSETS:
        s=P[k];st=START[k];disp=s.loc[st:]
        cyc=[c for c in cycles(s) if c["top"]>=st or not c["done"] or (c["regain"] and c["regain"]>=st)]
        A=float(s.max());ia=s.idxmax();low=float(s.loc[ia:].min());dl=s.loc[ia:].idxmin();now=float(s.iloc[-1])
        cur={"ath":A,"athD":str(ia.date()),"low":low,"lowD":str(dl.date()),"price":now,"dd":round((1-now/A)*100,1),
             "buy":[{"r":r,"p":A*(1-r/100),"hit":next((str(d.date()) for d,v in s.loc[ia:].items() if v<=A*(1-r/100)),None)} for r,_ in BUY],
             "ext":[{"x":x,"p":low+x*(A-low)} for x,_ in EXT]}
        if k=="BTC":
            sc=btc_radar(s);sb=sc<=10;ss=sc>=90;rule=("Score radar ≤ 10","Score radar ≥ 90")
        else:
            sc=pooled(k,P);dd2=(1-s/s.rolling(730,min_periods=1).max())*100
            sb=(sc<=15)&(dd2>=70);ss=sc>=85;rule=("Score ≤ 15 et au moins 70 % sous le plus haut des 2 dernières années","Score ≥ 85")
        sb=sb.reindex(disp.index).fillna(False).astype(bool);ss=ss.reindex(disp.index).fillna(False).astype(bool);scd=sc.reindex(disp.index)
        OUT[k]={"dates":[str(x.date()) for x in disp.index],"price":[float(f"{x:.6g}") for x in disp.values],"cycles":cyc,"cur":cur,"fib":fib_bt(s,st),
                "gold":{"buy":eps(sb,disp),"sell":eps(ss,disp),"rule":rule,"score":None if np.isnan(scd.iloc[-1]) else round(float(scd.iloc[-1])),"sbNow":bool(sb.iloc[-1]),"ssNow":bool(ss.iloc[-1])},
                "start":st,"first":str(s.index[0].date())}
        #print(k,OUT[k]["dates"][-1],round(now,4),"score",OUT[k]["gold"]["score"],"gold now",OUT[k]["gold"]["sbNow"],OUT[k]["gold"]["ssNow"])
    
    return OUT
