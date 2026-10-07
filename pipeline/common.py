"""Shared settings and helpers for the congress trades pipeline."""

import datetime as dt
import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Settings you might want to change
# ---------------------------------------------------------------------------

# How far back the very first runs go. Older filings are ignored.
BACKFILL_SINCE = dt.date(2025, 1, 1)

# Max filings processed per run, per chamber. Newest filings go first, so the
# backlog from BACKFILL_SINCE fills in over the first few daily runs.
MAX_HOUSE_FILINGS_PER_RUN = 400
MAX_SENATE_FILINGS_PER_RUN = 250

# recent.json holds trades disclosed in this many days (what the weekly
# Claude task reads).
RECENT_WINDOW_DAYS = 30

# Pause between requests to the government sites, in seconds.
REQUEST_DELAY = 0.4

# Give up on a filing that keeps failing to download after this many runs.
MAX_ATTEMPTS = 5

# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)


class TransientError(Exception):
    """Download failed in a way that is worth retrying on a later run."""


def today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def http(s: requests.Session, method: str, url: str, tries: int = 3, **kw) -> requests.Response:
    """GET/POST with a polite delay and a few retries."""
    kw.setdefault("timeout", 60)
    last = None
    for attempt in range(tries):
        time.sleep(REQUEST_DELAY * (attempt + 1))
        try:
            r = s.request(method, url, **kw)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code in (403, 404):
                break
        except requests.RequestException as e:
            last = f"{type(e).__name__}: {e}"
    raise TransientError(f"{method} {url} failed: {last}")


def load_json(name: str, default):
    p = DATA / name
    if not p.exists():
        return default
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(name: str, obj) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / name).open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def parse_us_date(text):
    """'1/23/2024' or '01/14/2024' -> '2024-01-23'. Returns None if unparseable."""
    if not text:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if not m:
        return None
    month, day, year = (int(x) for x in m.groups())
    try:
        return dt.date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_amount(text):
    """'$1,001 - $15,000' -> (1001, 15000). 'Over $50,000,000' -> (50000001, None)."""
    if not text:
        return None, None
    nums = [int(n.replace(",", "")) for n in re.findall(r"\$\s*([\d,]+)", text)]
    if not nums:
        return None, None
    if re.search(r"\bover\b", text, re.I):
        return nums[0] + 1, None
    if len(nums) == 1:
        return nums[0], None
    return nums[0], nums[1]


def days_between(a, b):
    try:
        return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days
    except (TypeError, ValueError):
        return None


def norm_name(text: str) -> str:
    """Lowercase, strip accents and punctuation, drop suffixes like Jr."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z\s-]", " ", text).replace("-", " ")
    words = [w for w in text.split() if w not in {"jr", "sr", "ii", "iii", "iv", "hon", "dr", "mr", "mrs", "ms"}]
    return " ".join(words)


def make_id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]
