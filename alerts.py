#!/usr/bin/env python3
"""Runs once: checks news, sends phone alerts (ntfy) for new Crypto/Gold/Oil signals."""
import json, os, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

TOPIC = os.environ.get("NTFY_TOPIC", "")
SEEN_FILE = "seen.json"
FEEDS = {
    "Crypto": "bitcoin OR crypto OR ethereum when:1h",
    "Gold": "gold price OR XAUUSD when:1h",
    "Oil": "crude oil OR OPEC OR Brent when:1h",
    "Macro": "Federal Reserve OR inflation OR Middle East OR sanctions when:1h",
}
K = {
 "Crypto": {
  "p": ["etf approv", "approves", "adoption", "rate cut", "cuts rates", "institutional",
        "inflow", "rally", "surge", "record high", "halving", "partnership", "reserve",
        "upgrade", "dovish"],
  "n": ["ban", "hack", "exploit", "crackdown", "lawsuit", "sues", "rate hike",
        "raises rates", "outflow", "crash", "plunge", "liquidat", "bankrupt", "delist",
        "hawkish", "fraud"]},
 "Gold": {
  "p": ["rate cut", "cuts rates", "war", "conflict", "tension", "geopolit", "safe haven",
        "weaker dollar", "dollar falls", "dollar weakens", "recession", "central bank buy",
        "turmoil", "sanction", "inflation rises", "dovish", "attack"],
  "n": ["rate hike", "raises rates", "stronger dollar", "dollar rises", "dollar strengthens",
        "yields rise", "ceasefire", "peace", "risk-on", "hawkish", "strong jobs"]},
 "Oil": {
  "p": ["opec cut", "production cut", "cuts output", "supply disruption", "sanction", "war",
        "middle east", "attack", "inventory draw", "stockpiles fall", "stocks fall",
        "demand rises", "stimulus", "hurricane", "pipeline", "outage", "tension"],
  "n": ["raises output", "increase output", "production hike", "inventory build",
        "stockpiles rise", "stocks rise", "recession", "weak demand", "demand falls",
        "ceasefire", "peace", "glut", "oversupply", "slowdown"]},
}
MARK = {1: "GREEN (positive)", -1: "RED (negative)", 0: "BLUE (neutral)"}


def score(title, inst):
    t = title.lower()
    s = sum(w in t for w in K[inst]["p"]) - sum(w in t for w in K[inst]["n"])
    return 1 if s > 0 else -1 if s < 0 else 0


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
        headers={"Title": "News signal"})
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
            sig = {i: score(title, i) for i in K}
            lines = [f"{i}: {MARK[s]}" for i, s in sig.items() if s != 0]
            if lines and not first_run:
                try:
                    notify(title, lines)
                except Exception as e:
                    print("notify error", e)
    with open(SEEN_FILE, "w") as f:
        json.dump(new_seen[-600:], f)


main()
