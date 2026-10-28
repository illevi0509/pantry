"""Build the app's data files (catalog.json, deals.json, prices.json, index_history.json) from the chains' PriceFull/PromoFull files.
Usage: python tools/build_data.py tools/config.json      (paths inside the config are relative to the config file)
Chain order (index in prices.json arrays) is CHAINS below and must match the "files" entries."""
import gzip,sys,re,json,collections,datetime,os
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import xml.etree.ElementTree as ET
from build import CATS,cat,num,UNIT
def load(f):
    raw=gzip.open(f).read()
    try: t=raw.decode("utf-8-sig")
    except UnicodeDecodeError: t=raw.decode("utf-16")
    return ET.fromstring(t)
CHAINS=["חצי חינם","רמי לוי","ויקטורי","אושר עד","יוחננוף"]
# (chain index, PriceFull path, PromoFull path or None)
cfg=json.load(open(sys.argv[1]))
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root: the app reads the JSON files from there
_base=os.path.dirname(os.path.abspath(sys.argv[1]))
cfg["files"]=[[ci,os.path.join(_base,pf),os.path.join(_base,pr) if pr else None] for ci,pf,pr in cfg["files"]]
cfg.setdefault("catalog_out",os.path.join(ROOT,"catalog.json")); cfg.setdefault("deals_out",os.path.join(ROOT,"deals.json"))
today=datetime.date.today().isoformat()
items={}; regular=collections.defaultdict(dict); src=[]
for ci,pf,_ in cfg["files"]:
    r=load(pf); n=0
    for it in r.iter("Item"):
        g=lambda k:re.sub(r"\s+"," ",(it.findtext(k) or "")).strip()
        code=g("ItemCode")
        if not re.fullmatch(r"\d{7,14}",code): continue
        key=code.lstrip("0")
        if ci>=0:
            try: regular[key][ci]=float(g("ItemPrice"))
            except ValueError: pass
        if key in items: continue
        name=g("ItemName") or g("ManufactureItemDescription")
        if not name: continue
        q=num(g("Quantity")); u=UNIT.get(g("UnitQty"))
        if g("bIsWeighted")!="1" and q and u and not re.search(r"\d",name) and not (u=="יח'" and q=="1"):
            name=f"{name} {q} {u}"
        items[key]=[name,cat(name)]; n+=1
    src.append(f"{CHAINS[ci] if ci>=0 else 'קטלוג נוסף'} ({n} חדשים)")
print("catalog",len(items),src)
deals=collections.defaultdict(dict); stat=collections.Counter()
for ci,_,promo in cfg["files"]:
    if not promo: continue
    r=load(promo)
    for p in r.iter("Promotion"):
        g=lambda k:(p.findtext(k) or "").strip()
        end=g("PromotionEndDateTime")[:10]; start=g("PromotionStartDateTime")[:10]
        if not end or end<today: stat["expired"]+=1; continue
        if start and start>today: stat["future"]+=1; continue
        # ClubID may be "0" or "0 - כלל הלקוחות" (Yohananof): the leading number decides
        cl=g("ClubID")
        m0=re.match(r"\s*(\d+)",cl); club=bool(m0 and int(m0.group(1))!=0)
        mpa=0.0
        for x in p.iter("MinPurchaseAmount"):
            try: mpa=max(mpa,float(x.text or 0))
            except ValueError: pass
        cond=1 if (mpa>0 or re.search(r"מעל\s*\d+|קופון",g("PromotionDescription"))) else 0
        for it in p.iter("PromotionItem"):
            gi=lambda k:(it.findtext(k) or "").strip()
            if gi("bIsWeighted")=="1": stat["weighted"]+=1; continue
            key=gi("ItemCode").lstrip("0")
            try: mq=float(gi("MinQty") or 1); tot=float(gi("DiscountedPrice"))
            except ValueError: stat["noprice"]+=1; continue
            if 0<mq<1: mq=1.0
            if mq<1 or mq!=int(mq) or tot<=0: stat["badqty"]+=1; continue
            mq=int(mq); unit=tot/mq
            reg=regular.get(key,{}).get(ci)
            if reg is not None and unit>=reg-0.01: stat["nosaving"]+=1; continue
            prev=deals[key].get(ci)
            if prev and prev[1]/prev[0]<=unit: continue
            deals[key][ci]=[mq,round(tot,2),round(reg*mq,2) if reg else None,end,1 if club else 0,cond]
            stat["ok"]+=1
print(stat.most_common()); print("deal items",len(deals))
out={k:{str(c):v for c,v in d.items()} for k,d in deals.items()}
json.dump({"v":2,"source":" · ".join(src),"cats":CATS,"items":items},open(cfg["catalog_out"],"w",encoding="utf-8"),ensure_ascii=False,separators=(",",":"))
json.dump({"v":1,"built":cfg.get("data_date",today),"chains":CHAINS,"note":cfg.get("note",""),"deals":out},open(cfg["deals_out"],"w",encoding="utf-8"),ensure_ascii=False,separators=(",",":"))
# regular shelf prices per chain, for basket comparison: {barcode: [p0,p1,p2,p3]} (null = not sold there)
pr={}
for k,d in regular.items():
    if k not in items: continue
    row=[round(d[c],2) if c in d else None for c in range(len(CHAINS))]
    if any(v is not None for v in row): pr[k]=row
json.dump({"v":1,"built":cfg.get("data_date",today),"chains":CHAINS,"prices":pr},open(cfg.get("prices_out",os.path.join(ROOT,"prices.json")),"w",encoding="utf-8"),separators=(",",":"))
print("prices",len(pr))

# ---- chain price index: every product sold in ALL chains, regular shelf prices; one snapshot per data date ----
import statistics, os.path
full=[(k,v) for k,v in pr.items() if all(x is not None for x in v)]
sums=[round(sum(v[c] for k,v in full),2) for c in range(len(CHAINS))]
cheapest=[0]*len(CHAINS)
ratios=[[] for _ in CHAINS]
for k,v in full:
    m=min(v)
    for c in range(len(CHAINS)):
        if v[c]==m: cheapest[c]+=1
        ratios[c].append(v[c]/m-1)
snap={"date":cfg.get("data_date",today),"items":len(full),"sum":sums,"cheapest":cheapest,
      "avgAbove":[round(statistics.mean(r)*100,1) for r in ratios]}
hp=cfg.get("history_out",os.path.join(ROOT,"index_history.json"))
hist={"chains":CHAINS,"snapshots":[]}
if os.path.exists(hp):
    try: hist=json.load(open(hp,encoding="utf-8"))
    except Exception: pass
hist["snapshots"]=[s for s in hist["snapshots"] if s["date"]!=snap["date"]]+[snap]
hist["snapshots"].sort(key=lambda s:s["date"])
json.dump(hist,open(hp,"w",encoding="utf-8"),ensure_ascii=False,separators=(",",":"))
print("index",snap)
