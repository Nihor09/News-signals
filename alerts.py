#!/usr/bin/env python3
"""Runs once: sends a phone alert ONLY for strong, market-moving headlines (ntfy)."""
import json, os, re, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

TOPIC = os.environ.get("NTFY_TOPIC", "")
SEEN_FILE = "seen.json"
FEEDS = {
    "Crypto": "bitcoin OR crypto OR ethereum when:1h",
    "Gold": "gold price OR XAUUSD when:1h",
    "Oil": "crude oil OR OPEC OR Brent when:1h",
    "Macro": "Federal Reserve OR inflation OR Middle East OR sanctions when:1h",
}
# Strong events only. A word ending in * matches any ending (escalat* = escalates, escalation).
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
    if p and n:          # mixed meaning -> skip, too unclear
        return 0, ""
    if p:
        return 1, p[0]
    if n:
        return -1, n[0]
    return 0, ""


def fetch(query):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    return [it.findtext("title", "").strip() for it in root.iter("item")]


def notify(title, lines):
    print(title, lines)
    if not TOPIC:
        return
    req = urllib.request.Request(
        "https://ntfy.sh/" + TOPIC,
        data=(title + "\n" + "\n".join(lines)).encode("utf-8"),
        headers={"Title": "STRONG news signal", "Priority": "high"})
    urllib.request.urlopen(req, timeout=10)


def main():
    first_run = not os.path.exists(SEEN_FILE)
    seen = set()
    if not first_run:
        with open(SEEN_FILE) as f:
            seen = set(json.load(f))
    new_seen = list(seen)
    for topic, query in FEEDS.items():
        try:
            titles = fetch(query)
        except Exception as e:
            print("fetch error", topic, e)
            continue
        for title in titles:
            if not title or title in seen:
                continue
            seen.add(title)
            new_seen.append(title)
            lines = []
            for inst in STRONG:
                s, why = strong_signal(title, inst)
                if s != 0:
                    lines.append(f"{inst}: {EMOJI[s]} ({why})")
            if lines and not first_run:
                try:
                    notify(title, lines)
                except Exception as e:
                    print("notify error", e)
    with open(SEEN_FILE, "w") as f:
        json.dump(new_seen[-600:], f)


main()
