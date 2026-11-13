#!/usr/bin/env python3
"""Runs once: checks many news sources, sends a phone alert (ntfy) ONLY for strong,
market-moving headlines about Crypto / Gold / Oil."""
import html, json, os, re, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

TOPIC = os.environ.get("NTFY_TOPIC", "")
SEEN_FILE = "seen.json"
MAX_AGE_HOURS = 2          # ignore stories older than this
MIN_LEVEL = 3              # only alert at impact 3/5 or higher (use 2 to see more, 4 for fewer)
OFFICIAL = {"FederalReserve"}   # official sources get +1 impact


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

# Each entry: (phrase, impact weight 2-5, is_macro). A phrase ending in * matches any ending.
# is_macro=1 -> counts on its own (e.g. "rate cut"). is_macro=0 -> only counts when the
# headline also mentions that market (e.g. "hack" must come with bitcoin/crypto/coin...).
STRONG = {
 "Crypto": {
  "p": [("etf approved", 5, 0), ("etf approval", 4, 0), ("approves bitcoin etf", 5, 1),
        ("bitcoin reserve", 4, 1), ("rate cut", 5, 1), ("cuts rates", 5, 1),
        ("all-time high", 3, 0), ("record high", 3, 0), ("surge*", 2, 0), ("rally", 2, 0),
        ("rallies", 2, 0), ("adoption", 2, 0), ("partnership", 2, 0), ("inflow*", 2, 0)],
  "n": [("hack*", 4, 0), ("exploit", 4, 0), ("stolen", 4, 0), ("bans", 4, 0), ("banned", 3, 0),
        ("sues", 3, 0), ("lawsuit", 3, 0), ("sec charges", 3, 0), ("bankrupt*", 5, 0),
        ("insolven*", 5, 0), ("delist*", 3, 0), ("collapse*", 5, 0), ("plunge*", 4, 0),
        ("crash*", 4, 0), ("liquidations", 3, 0), ("rate hike", 5, 1), ("raises rates", 5, 1),
        ("outflow*", 2, 0), ("selloff", 2, 0), ("sell-off", 2, 0), ("fraud", 2, 0)]},
 "Gold": {
  "p": [("rate cut", 5, 1), ("cuts rates", 5, 1), ("invasion", 4, 1), ("missile*", 4, 1),
        ("airstrike*", 4, 1), ("escalat*", 3, 1), ("safe haven", 3, 1), ("banking crisis", 4, 1),
        ("debt default", 4, 1), ("sovereign default", 4, 1), ("all-time high", 4, 0),
        ("record high", 4, 0), ("central bank buying", 4, 0), ("gold rall*", 2, 1),
        ("gold surge*", 2, 1), ("gold jump*", 2, 1)],
  "n": [("rate hike", 5, 1), ("raises rates", 5, 1), ("hawkish", 3, 1), ("dollar surges", 3, 1),
        ("yields surge", 3, 1), ("ceasefire", 3, 1), ("peace deal", 3, 1),
        ("peace agreement", 3, 1), ("plunge*", 4, 0), ("slump*", 3, 0), ("gold fall*", 2, 1),
        ("gold drop*", 2, 1), ("gold slide*", 2, 1)]},
 "Oil": {
  "p": [("opec+ cut", 5, 1), ("opec cut", 5, 1), ("strait of hormuz", 5, 1),
        ("refinery attack", 4, 1), ("pipeline attack", 4, 1), ("invasion", 4, 1),
        ("production cut", 4, 0), ("cuts output", 4, 0), ("supply disruption", 4, 0),
        ("embargo", 4, 0), ("escalat*", 3, 0), ("spike*", 3, 0), ("oil rall*", 2, 1),
        ("oil surge*", 2, 1), ("oil jump*", 2, 1)],
  "n": [("raises output", 4, 0), ("increase output", 4, 0), ("glut", 4, 0), ("plunge*", 4, 0),
        ("slump*", 3, 0), ("recession fears", 3, 0), ("inventory build", 3, 0),
        ("ceasefire", 3, 1), ("peace deal", 3, 1), ("oil fall*", 2, 1), ("oil drop*", 2, 1),
        ("oil slide*", 2, 1)]},
}
CTX = {
 "Crypto": r"\b(bitcoin|btc|crypto\w*|ethereum|eth|coin|coins|coinbase|token\w*|blockchain|binance|solana|xrp|stablecoin\w*|defi|altcoin\w*)\b",
 "Gold": r"\b(gold|bullion|xau\w*|precious metals?)\b",
 "Oil": r"\b(oil|crude|brent|wti|opec\+?|barrel\w*|petroleum|refiner\w*|pipeline\w*|hormuz|iran|saudi|gulf|middle east)\b",
}


def hit(title, entries, ctx_ok):
    t = title.lower()
    found = []
    for w, wt, macro in entries:
        if not macro and not ctx_ok:
            continue
        pat = r"\b" + re.escape(w.rstrip("*")) + (r"\w*" if w.endswith("*") else r"\b")
        if re.search(pat, t):
            found.append((w.rstrip("*"), wt))
    return found


def strong_signal(title, inst, source=""):
    """Returns (direction, impact 1-5, trigger). direction 0 = nothing relevant."""
    ctx_ok = bool(re.search(CTX[inst], title.lower()))
    p = hit(title, STRONG[inst]["p"], ctx_ok)
    n = hit(title, STRONG[inst]["n"], ctx_ok)
    if p and n:                      # mixed meaning -> too unclear, skip
        return 0, 0, ""
    hits = p or n
    if not hits:
        return 0, 0, ""
    lvl = max(w for _, w in hits)
    if len(hits) >= 2:               # several triggers in one headline
        lvl += 1
    if source in OFFICIAL:
        lvl += 1
    lvl = min(5, lvl)
    return (1 if p else -1), lvl, max(hits, key=lambda h: h[1])[0]


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


def send_telegram(title, body, link=""):
    """Posts the same alert to a Telegram chat/group (needs the two secrets)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    lines = body.split("\n")
    text = "<b>" + html.escape(title) + "</b>\n\n" + html.escape(lines[0])
    text += "\n" + html.escape("\n".join(lines[1:]))
    if link.startswith("http"):
        text += '\n<a href="' + html.escape(link, quote=True) + '">Read the story</a>'
    text += "\n<i>Not financial advice.</i>"
    data = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/sendMessage", data=data,
        headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)


LABELS = {1: "MINOR", 2: "NORMAL", 3: "MODERATE", 4: "STRONG", 5: "MAJOR"}


def notify(headline, signals, source, link="", pub=""):
    """signals = {"Crypto": (direction, impact, trigger), ...}. One alert per direction."""
    for d in (-1, 1):
        picked = [(i, lv, kw) for i, (sg, lv, kw) in signals.items() if sg == d]
        if not picked:
            continue
        top = max(lv for _, lv, _ in picked)
        top_kw = max(picked, key=lambda x: x[1])[2]
        square = "\U0001F7E9" if d > 0 else "\U0001F7E5"
        bar = square * top + "\u2B1C" * (5 - top)
        word = "POSITIVE" if d > 0 else "NEGATIVE"
        names = ", ".join(i for i, _, _ in picked)
        title = f"{bar} {LABELS[top]} {word}: {names}"
        detail = ", ".join(f"{i} {lv}/5" for i, lv, _ in picked)
        reason = WHY.get(top_kw, "this kind of news often moves prices")
        ago = minutes_ago(pub)
        when = f" - {ago} min ago" if ago is not None and ago < 180 else ""
        body = "\n".join([
            headline,
            f"Impact {top}/5 - Likely {'UP' if d > 0 else 'DOWN'}: {detail}",
            f"Why: {reason}.",
            f"Source: {source}{when}",
        ])
        print(title, "|", headline)
        if TOPIC:
            try:
                msg = {"topic": TOPIC, "title": title, "message": body, "priority": top}
                if link.startswith("http"):
                    msg["click"] = link
                req = urllib.request.Request(
                    "https://ntfy.sh/", data=json.dumps(msg).encode("utf-8"),
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10)
            except Exception as e:
                print("ntfy error", e)
        try:
            send_telegram(title, body, link)
        except Exception as e:
            print("telegram error", e)


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
                sg, lvl, why = strong_signal(title, inst, name)
                if sg != 0 and lvl >= MIN_LEVEL:
                    signals[inst] = (sg, lvl, why)
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
