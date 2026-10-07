"""Senate: Periodic Transaction Reports from the Senate eFD site (efdsearch.senate.gov).

How the Senate publishes trades:
  * The search site asks you to accept a usage agreement first (a form post).
  * The results list comes from a JSON endpoint behind the search page.
  * Electronic PTRs are HTML pages with a table of trades (easy to read).
    Paper PTRs are scanned images; those go to needs_review instead.
"""

import re

from bs4 import BeautifulSoup

from common import TransientError, http, parse_amount, parse_us_date

BASE = "https://efdsearch.senate.gov"
HOME = BASE + "/search/home/"
SEARCH = BASE + "/search/"
DATA = BASE + "/search/report/data/"
PTR_REPORT_TYPE = "[11]"

TX_TYPES = {
    "purchase": "buy", "sale (full)": "sell", "sale (partial)": "sell_partial",
    "sale": "sell", "exchange": "exchange",
}


class SenateSession:
    def __init__(self, s):
        self.s = s
        self.token = None

    def open(self):
        r = http(self.s, "GET", HOME)
        soup = BeautifulSoup(r.text, "html.parser")
        field = soup.find("input", {"name": "csrfmiddlewaretoken"})
        if field is None:
            raise TransientError("Senate agreement page has no csrf token (site layout changed?)")
        http(self.s, "POST", HOME, data={
            "csrfmiddlewaretoken": field["value"], "prohibition_agreement": "1",
        }, headers={"Referer": HOME})
        self.token = self.s.cookies.get("csrftoken") or self.s.cookies.get("csrf") or field["value"]

    def list_filings(self, since_date):
        """All PTRs submitted on or after since_date (a datetime.date)."""
        if not self.token:
            self.open()
        filings, start = [], 0
        while True:
            r = http(self.s, "POST", DATA, data={
                "start": str(start), "length": "100", "report_types": PTR_REPORT_TYPE,
                "filer_types": "[]", "submitted_start_date": since_date.strftime("%m/%d/%Y 00:00:00"),
                "submitted_end_date": "", "candidate_state": "", "senator_state": "",
                "office_id": "", "first_name": "", "last_name": "",
                "csrfmiddlewaretoken": self.token,
            }, headers={"Referer": SEARCH, "X-CSRFToken": self.token,
                        "X-Requested-With": "XMLHttpRequest"})
            try:
                payload = r.json()
            except ValueError as e:
                raise TransientError("Senate search did not return JSON (agreement not accepted?)") from e
            rows = payload.get("data") or []
            for row in rows:
                if len(row) < 5:
                    continue
                first, last, office, link_html, received = row[:5]
                m = re.search(r'href="([^"]+)"', link_html or "")
                if not m:
                    continue
                href = m.group(1)
                rid = href.rstrip("/").rsplit("/", 1)[-1]
                filings.append({
                    "report_id": rid,
                    "url": href if href.startswith("http") else BASE + href,
                    "paper": "/paper/" in href,
                    "first": BeautifulSoup(first or "", "html.parser").get_text(" ", strip=True),
                    "last": BeautifulSoup(last or "", "html.parser").get_text(" ", strip=True),
                    "office": BeautifulSoup(office or "", "html.parser").get_text(" ", strip=True),
                    "filed": parse_us_date(received),
                })
            start += len(rows)
            total = int(payload.get("recordsFiltered") or payload.get("recordsTotal") or 0)
            if not rows or start >= total:
                break
        return filings

    def fetch_report(self, f):
        r = http(self.s, "GET", f["url"], headers={"Referer": SEARCH})
        if "prohibition_agreement" in r.text or "agreement_form" in r.text:
            self.open()  # session expired, accept the agreement again
            r = http(self.s, "GET", f["url"], headers={"Referer": SEARCH})
        return r.text


def parse_report_html(html):
    """Return (rows, problems) from an electronic Senate PTR page."""
    soup = BeautifulSoup(html, "html.parser")
    table = None
    for t in soup.find_all("table"):
        heads = [th.get_text(" ", strip=True).lower() for th in t.find_all("th")]
        if any("transaction date" in h for h in heads):
            table = t
            break
    if table is None:
        return [], ["no transaction table found"]

    heads = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]

    def col(*names):
        for i, h in enumerate(heads):
            if any(n in h for n in names):
                return i
        return None

    idx = {
        "tdate": col("transaction date"), "owner": col("owner"), "ticker": col("ticker"),
        "asset": col("asset name"), "atype": col("asset type"), "type": col("type"),
        "amount": col("amount"), "comment": col("comment"),
    }
    # "type" also matches "asset type"; make sure it points at the transaction type column
    for i, h in enumerate(heads):
        if h == "type":
            idx["type"] = i

    rows = []
    body = table.find("tbody") or table
    for tr in body.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 5:
            continue

        def get(key):
            i = idx.get(key)
            return cells[i] if i is not None and i < len(cells) else ""

        ticker = get("ticker")
        ticker = None if ticker in ("", "--", "N/A") else ticker.split()[0]
        tx_raw = get("type")
        lo, hi = parse_amount(get("amount"))
        comment = get("comment")
        rows.append({
            "owner": get("owner") or "Self",
            "ticker": ticker,
            "asset": get("asset"),
            "asset_type": get("atype"),
            "transaction": TX_TYPES.get(tx_raw.lower(), tx_raw.lower() or None),
            "transaction_date": parse_us_date(get("tdate")),
            "notification_date": None,
            "amount_text": get("amount"),
            "amount_min": lo,
            "amount_max": hi,
            "description": None if comment in ("", "--") else comment,
        })
    if not rows:
        return [], ["transaction table was empty"]
    return rows, []
