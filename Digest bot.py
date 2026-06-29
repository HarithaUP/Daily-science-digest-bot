#!/usr/bin/env python3
"""
Daily Science Digest Bot
-------------------------
Pulls:
  - "On this day" science history facts (Wikipedia REST API)
  - One fresh NASA APOD item
  - One fresh arXiv paper
Sends the digest via Email (Gmail SMTP) and Telegram.

All APIs used are free / keyless (or free-tier keyless DEMO_KEY for NASA).
"""

import os
import sys
import smtplib
import requests
import datetime
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---------- CONFIG ----------
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
TO_EMAIL = os.environ.get("TO_EMAIL", GMAIL_USER)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

NASA_API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")

MAX_HISTORY_FACTS = 5  # how many "on this day" facts to include

# Keywords used to filter Wikipedia's "on this day" events for science relevance.
SCIENCE_KEYWORDS = [
    "physic", "astronom", "space", "nasa", "satellite", "telescope", "rocket",
    "nuclear", "atom", "chemist", "biolog", "math", "scientist", "discover",
    "invent", "engineer", "darwin", "einstein", "newton", "evolution", "genome",
    "dna", "vaccine", "spacecraft", "orbit", "planet", "particle", "physicist",
    "chemistry", "physics", "science", "laboratory", "experiment", "theory",
    "quantum", "gravity", "radiation", "element", "species", "fossil",
]


# ---------- DATA FETCHERS ----------

def fetch_on_this_day():
    """Fetch today's events/births/deaths from Wikipedia and filter for science relevance."""
    today = datetime.date.today()
    mm, dd = f"{today.month:02d}", f"{today.day:02d}"
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/all/{mm}/{dd}"

    try:
        resp = requests.get(url, headers={"User-Agent": "science-digest-bot/1.0"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[warn] Wikipedia fetch failed: {e}", file=sys.stderr)
        return []

    candidates = []
    for category in ("events", "births", "deaths"):
        for item in data.get(category, []):
            text = item.get("text", "")
            year = item.get("year")
            lower = text.lower()
            if any(kw in lower for kw in SCIENCE_KEYWORDS):
                candidates.append({
                    "year": year,
                    "text": text,
                    "category": category,
                })

    # Prefer events with a wider spread of years; just take first N for now
    candidates = candidates[:MAX_HISTORY_FACTS]
    return candidates


def fetch_apod():
    """Fetch today's NASA Astronomy Picture of the Day."""
    url = "https://api.nasa.gov/planetary/apod"
    try:
        resp = requests.get(url, params={"api_key": NASA_API_KEY}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return {
            "title": data.get("title"),
            "explanation": data.get("explanation"),
            "url": data.get("url"),
            "date": data.get("date"),
        }
    except Exception as e:
        print(f"[warn] NASA APOD fetch failed: {e}", file=sys.stderr)
        return None


def fetch_arxiv_paper(category="physics"):
    """Fetch the most recently submitted paper in a given arXiv category."""
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"cat:{category}.*" if "." not in category else f"cat:{category}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": 1,
    }
    # arXiv categories like astro-ph, physics, cond-mat don't all take wildcard the same way;
    # fall back to a safe known category if needed.
    try:
        resp = requests.get(url, params={
            "search_query": "cat:astro-ph",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": 1,
        }, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
        summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
        link = entry.find("atom:id", ns).text.strip()
        return {"title": title, "summary": summary[:400] + "...", "link": link}
    except Exception as e:
        print(f"[warn] arXiv fetch failed: {e}", file=sys.stderr)
        return None


# ---------- DIGEST BUILDER ----------

def build_digest():
    today_str = datetime.date.today().strftime("%B %d, %Y")
    history_facts = fetch_on_this_day()
    apod = fetch_apod()
    paper = fetch_arxiv_paper()

    lines = [f"🔭 SCIENCE DIGEST — {today_str}", ""]

    lines.append("📜 ON THIS DAY IN SCIENCE")
    if history_facts:
        for f in history_facts:
            lines.append(f"  • {f['year']}: {f['text']}")
    else:
        lines.append("  (no strong science matches found today)")
    lines.append("")

    if apod:
        lines.append("🌌 NASA PICTURE OF THE DAY")
        lines.append(f"  {apod['title']}")
        short_expl = (apod["explanation"][:280] + "...") if apod["explanation"] else ""
        lines.append(f"  {short_expl}")
        lines.append(f"  {apod['url']}")
        lines.append("")

    if paper:
        lines.append("🧪 FRESH FROM ARXIV (astro-ph)")
        lines.append(f"  {paper['title']}")
        lines.append(f"  {paper['summary']}")
        lines.append(f"  {paper['link']}")
        lines.append("")

    return "\n".join(lines)


# ---------- SENDERS ----------

def send_email(body_text):
    if not (GMAIL_USER and GMAIL_APP_PASSWORD and TO_EMAIL):
        print("[skip] Email not configured, skipping.")
        return
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    msg["Subject"] = f"Science Digest — {datetime.date.today().strftime('%b %d, %Y')}"
    msg.attach(MIMEText(body_text, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
    print("[ok] Email sent.")


def send_telegram(body_text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("[skip] Telegram not configured, skipping.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Telegram messages cap at 4096 chars; trim if needed
    text = body_text[:4000]
    resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    if resp.ok:
        print("[ok] Telegram sent.")
    else:
        print(f"[warn] Telegram send failed: {resp.text}", file=sys.stderr)


# ---------- MAIN ----------

if __name__ == "__main__":
    digest = build_digest()
    print(digest)
    print("\n--- sending ---\n")
    send_email(digest)
    send_telegram(digest)
