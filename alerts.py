#!/usr/bin/env python3
"""Runs once: checks many news sources, sends a phone alert (ntfy) ONLY for strong,
market-moving headlines about Crypto / Gold / Oil."""
import json, os, re, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

TOPIC = os.environ.get("NTFY_TOPIC", "")
SEEN_FILE = "seen.json"
MAX_AGE_HOURS = 3          # ignore stories older than this


def gnews(q):
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})


# If a source stops working, just delete its line or replace the address.
SOURCES = {
    "Google-Crypto": gnews("bitcoin OR crypto OR ethereum when:1h"),
    "Google-Gold": gnews("gold price OR XAUUSD when:1h"),
    "Google-Oil": gnews("crude oil OR OPEC OR Brent when:1h"),
    "Google-Macro": gnews("Federal Reserve OR inflation OR Middle East OR sanctions when:1h"),
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "Decrypt": "https://decrypt.co/feed",
    "TheBlock": "https://www.theblock.co/rss.xml",
    "OilPrice": "https://oilprice.com/rss/main",
    "Google-GoldSites": gnews("site:kitco.com OR site:fxstreet.com OR site:mining.com when:3h"),
    "FederalReserve": "https://www.federalreserve.gov/feeds/press_all.xml",
}

# Strong events only. A word ending in * matches any ending (escalat* = escalates).
STRONG = {
 "Crypto": {
  "p": ["etf approved", "etf approval", "approves bitcoin etf", "bitcoin reserve",
        "rate cut", "cuts rates", "all-time high", "record high"],
  "n": ["hack*", "exploit", "stolen", "bans", "banned", "sues", "lawsuit", "bankrupt*",
        "insolven*", "delist*", "collapse*", "plunge*", "crash*", "liquidations",
        "rate hike", "raises rates"]},
 "Gold": {
  "p": ["rate cut", "cuts rates", "escalat*", "invasion", "missile*", "airstrike*",
        "safe haven", "all-time high", "record high", "central bank buying",
        "banking crisis", "default"],
  "n": ["rate hike", "raises rates", "ceasefire", "peace deal", "peace agreement",
        "hawkish", "dollar surges", "yields surge", "plunge*", "slump*"]},
 "Oil": {
  "p": ["opec+ cut", "opec cut", "production cut", "cuts output", "supply disruption",
        "strait of hormuz", "refinery attack", "pipeline attack", "embargo",
        "escalat*", "invasion", "spike*"],
  "n": ["raises output", "increase output", "ceasefire", "peace deal",
        "recession fears", "glut", "plunge*", "slump*", "inventory build"]},
}


def hit(title, words):
    t = title.lower()
    found = []
    for w in words:
        pat = r"\b" + re.escape(w.rstrip("*")) + (r"\w*" if w.endswith("*") else r"\b")
        if re.search(pat, t):
            found.append(w.rstrip("*"))
    return found


def strong_signal(title, inst):
    p = hit(title, STRONG[inst]["p"])
    n = hit(title, STRONG[inst]["n"])
    if p and n:
        return 0, ""
    if p:
        return 1, p[0]
    if n:
        return -1, n[0]
    return 0, ""


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    out = []
    for it in root.iter("item"):
        out.append((it.findtext("title", "").strip(), it.findtext("pubDate", ""),
                    it.findtext("link", "").strip()))
    return out


def too_old(pub):
    try:
        d = parsedate_to_datetime(pub)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).total_seconds() > MAX_AGE_HOURS * 3600
    except Exception:
        return False


WHY = {
 "etf approved": "a big new door opens for buyers", "etf approval": "a big new door opens for buyers",
 "approves bitcoin etf": "a big new door opens for buyers",
 "bitcoin reserve": "governments buying adds demand",
 "rate cut": "cheaper money usually lifts prices", "cuts rates": "cheaper money usually lifts prices",
 "all-time high": "strong momentum, buyers in control", "record high": "strong momentum, buyers in control",
 "hack": "hacks and thefts scare buyers", "exploit": "hacks and thefts scare buyers",
 "stolen": "hacks and thefts scare buyers", "bans": "bans cut demand", "banned": "bans cut demand",
 "sues": "legal trouble hurts confidence", "lawsuit": "legal trouble hurts confidence",
 "bankrupt": "a failing company shakes the market", "insolven": "a failing company shakes the market",
 "delist": "the coin loses places to trade", "collapse": "a collapse spreads fear",
 "plunge": "a sharp drop is already under way", "crash": "a sharp drop is already under way",
 "slump": "prices are sliding", "liquidations": "forced selling pushes prices down",
 "rate hike": "costlier money usually pulls prices down", "raises rates": "costlier money usually pulls prices down",
 "escalat": "war fear sends money to safe assets and puts oil supply at risk",
 "invasion": "war fear sends money to safe assets and puts oil supply at risk",
 "missile": "war fear sends money to safe assets and puts oil supply at risk",
 "airstrike": "war fear sends money to safe assets and puts oil supply at risk",
 "safe haven": "investors are running to safety", "central bank buying": "big buyers are adding demand",
 "banking crisis": "fear sends money into gold", "default": "debt fear sends money into gold",
 "ceasefire": "less war fear, so less demand for safe assets and less oil risk",
 "peace deal": "less war fear, so less demand for safe assets and less oil risk",
 "peace agreement": "less war fear, so less demand for safe assets and less oil risk",
 "hawkish": "central bank sounds tough on rates", "dollar surges": "a stronger dollar weighs on gold",
 "yields surge": "higher yields make gold less attractive",
 "opec+ cut": "less oil supplied, prices tend to rise", "opec cut": "less oil supplied, prices tend to rise",
 "production cut": "less oil supplied, prices tend to rise", "cuts output": "less oil supplied, prices tend to rise",
 "supply disruption": "oil supply is at risk", "strait of hormuz": "a key oil route is at risk",
 "refinery attack": "oil supply is at risk", "pipeline attack": "oil supply is at risk",
 "embargo": "oil supply is at risk", "spike": "price is jumping",
 "raises output": "more oil supplied, prices tend to fall", "increase output": "more oil supplied, prices tend to fall",
 "recession fears": "less oil demand expected", "glut": "too much oil on the market",
 "inventory build": "oil is piling up in storage",
}


def minutes_ago(pub):
    try:
        d = parsedate_to_datetime(pub)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        m = int((datetime.now(timezone.utc) - d).total_seconds() // 60)
        return None if m < 0 else m
    except Exception:
        return None


def notify(headline, signals, source, link="", pub=""):
    """signals = {"Crypto": (1, "rate cut"), ...}. Sends one alert per direction."""
    names = {1: "Positive", -1: "Negative"}
    icon = {1: "\U0001F7E2", -1: "\U0001F534"}
    for d in (-1, 1):
        picked = [(i, why) for i, (s, why) in signals.items() if s == d]
        if not picked:
            continue
        title = f"{icon[d]} Strong {names[d]} news for " + " & ".join(i for i, _ in picked)
        names_txt = " & ".join(i for i, _ in picked)
        reason = WHY.get(picked[0][1], "this kind of news often moves prices")
        ago = minutes_ago(pub)
        when = f" - {ago} min ago" if ago is not None and ago < 180 else ""
        body = "\n".join([
            headline,
            f"{icon[d]} Likely {'UP' if d > 0 else 'DOWN'}: {names_txt}",
            f"Why: {reason}.",
            f"Source: {source}{when}",
        ])
        print(title, "|", headline)
        if not TOPIC:
            continue
        msg = {"topic": TOPIC, "title": title, "message": body, "priority": 4}
        if link.startswith("http"):
            msg["click"] = link
        req = urllib.request.Request(
            "https://ntfy.sh/", data=json.dumps(msg).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)


def load():
    if not os.path.exists(SEEN_FILE):
        return None
    with open(SEEN_FILE) as f:
        d = json.load(f)
    if isinstance(d, list):                       # older format
        return {"seen": d, "seeded": ["Google-Crypto", "Google-Gold", "Google-Oil", "Google-Macro"]}
    return d


def main():
    state = load()
    brand_new = state is None
    if brand_new:
        state = {"seen": [], "seeded": []}
    seen = set(state["seen"])
    order = list(state["seen"])
    seeded = set(state["seeded"])
    for name, url in SOURCES.items():
        try:
            items = fetch(url)
        except Exception as e:
            print("source failed:", name, e)
            continue
        quiet = name not in seeded          # first look at a source: record, don't alert
        for title, pub, link in items:
            if not title or title in seen:
                continue
            seen.add(title)
            order.append(title)
            if quiet or too_old(pub):
                continue
            signals = {}
            for inst in STRONG:
                sg, why = strong_signal(title, inst)
                if sg != 0:
                    signals[inst] = (sg, why)
            if signals:
                try:
                    notify(title, signals, name, link, pub)
                except Exception as e:
                    print("notify error", e)
        seeded.add(name)
    with open(SEEN_FILE, "w") as f:
        json.dump({"seen": order[-3000:], "seeded": sorted(seeded)}, f)


if __name__ == "__main__":
    main()
