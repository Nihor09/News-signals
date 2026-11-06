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
    "Mining-Gold": "https://www.mining.com/feed/",
    "FXStreet": "https://www.fxstreet.com/rss",
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
EMOJI = {1: "\U0001F7E2 POSITIVE", -1: "\U0001F534 NEGATIVE"}


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
        out.append((it.findtext("title", "").strip(), it.findtext("pubDate", "")))
    return out


def too_old(pub):
    try:
        d = parsedate_to_datetime(pub)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).total_seconds() > MAX_AGE_HOURS * 3600
    except Exception:
        return False


def notify(title, lines):
    print(title, lines)
    if not TOPIC:
        return
    req = urllib.request.Request(
        "https://ntfy.sh/" + TOPIC,
        data=(title + "\n" + "\n".join(lines)).encode("utf-8"),
        headers={"Title": "STRONG news signal", "Priority": "high"})
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
        for title, pub in items:
            if not title or title in seen:
                continue
            seen.add(title)
            order.append(title)
            if quiet or too_old(pub):
                continue
            lines = []
            for inst in STRONG:
                s, why = strong_signal(title, inst)
                if s != 0:
                    lines.append(f"{inst}: {EMOJI[s]} ({why})")
            if lines:
                lines.append("via " + name)
                try:
                    notify(title, lines)
                except Exception as e:
                    print("notify error", e)
        seeded.add(name)
    with open(SEEN_FILE, "w") as f:
        json.dump({"seen": order[-3000:], "seeded": sorted(seeded)}, f)


if __name__ == "__main__":
    main()
