#!/usr/bin/env python3
"""הורדת קבצי מחירים ומבצעים (PriceFull + PromoFull) לסניף אחד בכל רשת.

שימוש:  python fetch_prices.py [תיקיית_יעד]
ברירת מחדל: ./prices_YYYY-MM-DD
דורש רק את הספרייה requests  (pip install requests).
בסוף נכתב manifest.json עם מה שירד, ממה, ומה נכשל.
"""
import json, os, re, sys, time, datetime, html
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}

# מהגיליון: רשת, סוג שרת, שם משתמש, מספר סניף (ראש העין / הוד השרון / כפר סבא)
CHAINS = [
    {"key": "hazi_hinam", "name": "חצי חינם", "chain_id": "7290700100008", "store": "206", "kind": "hazi"},
    {"key": "rami_levy",  "name": "רמי לוי",  "chain_id": "7290058140886", "store": "017", "kind": "cerberus", "user": "RamiLevi"},
    {"key": "victory",    "name": "ויקטורי",  "chain_id": "7290696200003", "store": "026", "kind": "laib"},
    {"key": "osher_ad",   "name": "אושר עד",  "chain_id": "7290103152017", "store": "031", "kind": "cerberus", "user": "osherad"},
    {"key": "yohananof",  "name": "יוחננוף",  "chain_id": "7290803800003", "store": "024", "kind": "cerberus", "user": "yohananof"},
]
TYPES = ("PriceFull", "PromoFull")


def stamp(fname):
    """תאריך-שעה מתוך שם הקובץ, למיון: ...-20261023-125424.gz -> 20261023125424"""
    m = re.search(r"-(\d{8})-?(\d{4,6})", fname)
    return (m.group(1) + m.group(2).ljust(6, "0")) if m else "0"


def matches(fname, t, c):
    """PriceFull<chain>-[subchain-]<store>-<date>... ; לא Price/Promo חלקיים"""
    base = os.path.basename(fname)
    # מספר הסניף יכול להופיע כ-024 או 24 או 0024
    pat = rf"^{t}{c['chain_id']}-(?:\d{{3}}-)?0*{int(c['store'])}-\d"
    return re.match(pat, base) is not None


def pick_latest(names, c):
    out = {}
    for t in TYPES:
        cand = sorted({n for n in names if matches(n, t, c)}, key=lambda n: stamp(os.path.basename(n)))
        if cand:
            out[t] = cand[-1]
    return out


def download(sess, url, dest):
    r = sess.get(url, headers=UA, timeout=180, stream=True)
    r.raise_for_status()
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(1 << 16):
            f.write(chunk)
    os.replace(tmp, dest)
    return os.path.getsize(dest)


# ---------- Cerberus: url.publishedprices.co.il (רמי לוי, אושר עד, יוחננוף) ----------
CERB = "https://url.publishedprices.co.il"

def csrf_of(text):
    m = re.search(r'name="csrftoken"\s+content="([^"]+)"', text) or re.search(r'csrftoken["\']?\s*[:=]\s*["\']([^"\']+)', text)
    return m.group(1) if m else ""

def cerberus(c, sess):
    r = sess.get(CERB + "/login", headers=UA, timeout=60)
    tok = csrf_of(r.text)
    r = sess.post(CERB + "/login/user", headers=UA, timeout=60,
                  data={"r": "", "username": c["user"], "password": c.get("password", ""), "Submit": "Sign in", "csrftoken": tok})
    if "/login" in r.url and "logout" not in r.text.lower():
        raise RuntimeError("ההתחברות נכשלה (שם משתמש " + c["user"] + ")")
    tok = csrf_of(r.text) or csrf_of(sess.get(CERB + "/file", headers=UA, timeout=60).text) or tok
    names = []
    for t in TYPES:
        q = f"{t}{c['chain_id']}"
        r = sess.post(CERB + "/file/json/dir", headers=UA, timeout=120, data={
            "sEcho": 1, "iColumns": 5, "sColumns": ",,,,", "iDisplayStart": 0, "iDisplayLength": 100000,
            "mDataProp_0": "fname", "mDataProp_1": "typeLabel", "mDataProp_2": "size", "mDataProp_3": "ftime", "mDataProp_4": "",
            "sSearch": q, "bRegex": "false", "iSortingCols": 0, "cd": "/", "csrftoken": tok})
        r.raise_for_status()
        names += [row.get("fname") or row.get("name") for row in r.json().get("aaData", [])]
    latest = pick_latest([n for n in names if n], c)
    return {t: CERB + "/file/d/" + n for t, n in latest.items()}


# ---------- חצי חינם: shop.hazi-hinam.co.il/Prices  (t=1 מחירים, t=2 מבצעים, d=תאריך, p=עמוד; נבדק 23.10.2026) ----------
def hazi(c, sess):
    base = "https://shop.hazi-hinam.co.il/Prices"
    rx = re.compile(r'href="([^"]+?\.gz)"', re.I)
    out = {}
    for t, code in (("PriceFull", "1"), ("PromoFull", "2")):
        for d in ("", (datetime.date.today() - datetime.timedelta(days=1)).isoformat()):   # היום, ואם עוד לא פורסם - אתמול
            links = set()
            for p in range(1, 40):
                r = sess.get(base, params={"p": p, "s": "", "f": "", "t": code, "d": d}, headers=UA, timeout=60)
                r.raise_for_status()
                found = {html.unescape(h) for h in rx.findall(r.text)}
                if not found:
                    break
                links |= found
                if t in pick_latest(links, c):
                    break
            got = pick_latest(links, c).get(t)
            if got:
                out[t] = got
                break
    return out


# ---------- ויקטורי: laibcatalog.co.il  (JSON: /webapi/api/getfiles?edi=<chain>; נבדק 23.10.2026) ----------
def laib(c, sess):
    api = "https://laibcatalog.co.il/webapi"
    r = sess.get(f"{api}/api/getfiles", params={"edi": c["chain_id"]}, headers=UA, timeout=60)
    r.raise_for_status()
    names = [f["fileName"] for f in r.json() if int(f.get("branchNumber") or 0) == int(c["store"])]
    return {t: f"{api}/{c['chain_id']}/{n}" for t, n in pick_latest(names, c).items()}


KINDS = {"cerberus": cerberus, "hazi": hazi, "laib": laib}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "prices_" + datetime.date.today().isoformat()
    os.makedirs(out, exist_ok=True)
    manifest = {"run": datetime.datetime.now().isoformat(timespec="seconds"), "chains": {}}
    for c in CHAINS:
        rec = {"name": c["name"], "store": c["store"], "files": {}, "error": None}
        try:
            sess = requests.Session()
            urls = KINDS[c["kind"]](c, sess)
            for t in TYPES:
                if t not in urls:
                    raise RuntimeError(f"לא נמצא קובץ {t} לסניף {c['store']}")
            for t, u in urls.items():
                fname = os.path.basename(u.split("?")[0])
                if not fname.endswith(".gz"):
                    fname += ".gz"
                dest = os.path.join(out, f"{c['key']}_{fname}")
                size = download(sess, u, dest)
                with open(dest, "rb") as fh:
                    magic = fh.read(2)
                if size < 1000 or magic != b"\x1f\x8b":
                    raise RuntimeError(f"הקובץ {fname} לא תקין ({size} בתים, לא gzip)")
                rec["files"][t] = {"path": os.path.abspath(dest), "source": fname, "date": stamp(fname)[:8], "bytes": size}
            print(f"✓ {c['name']}: " + ", ".join(v["source"] for v in rec["files"].values()))
        except Exception as e:  # רשת אחת שנכשלה לא עוצרת את השאר
            rec["error"] = f"{type(e).__name__}: {e}"
            print(f"✗ {c['name']}: {rec['error']}")
        manifest["chains"][c["key"]] = rec
        time.sleep(2)
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    bad = [r["name"] for r in manifest["chains"].values() if r["error"]]
    print("תיקייה:", os.path.abspath(out), "| נכשלו:", ", ".join(bad) if bad else "אף רשת")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
