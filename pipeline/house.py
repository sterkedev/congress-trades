"""House of Representatives: Periodic Transaction Reports (PTRs) from the House Clerk.

How the House publishes trades:
  * A yearly ZIP (e.g. 2026FD.zip) holds an XML index of every disclosure filed
    that year. FilingType "P" means a Periodic Transaction Report.
  * Each PTR is a PDF at /public_disc/ptr-pdfs/<year>/<DocID>.pdf
  * Electronically filed PDFs contain text we can read. Paper filings are
    scanned images; those go to needs_review instead.
"""

import io
import re
import zipfile
import xml.etree.ElementTree as ET

from common import TransientError, http, parse_amount, parse_us_date

BASE = "https://disclosures-clerk.house.gov/public_disc"

TX_TYPES = {"P": "buy", "S": "sell", "S (partial)": "sell_partial", "E": "exchange"}
OWNERS = {"SP": "Spouse", "JT": "Joint", "DC": "Dependent child", "": "Self"}
ASSET_TYPES = {
    "ST": "Stock", "OP": "Option", "GS": "Government security", "MF": "Mutual fund",
    "EF": "ETF", "CS": "Corporate bond", "CT": "Crypto", "OT": "Other",
    "RE": "Real estate", "PS": "Stock (not public)", "HN": "Hedge fund", "OI": "Other investment",
}


# ---------------------------------------------------------------------------
# Index of filings
# ---------------------------------------------------------------------------

def _tag(el):
    return el.tag.rsplit("}", 1)[-1]


def _child(el, name):
    for c in el:
        if _tag(c) == name:
            return (c.text or "").strip()
    return ""


def list_filings(s, years):
    """Return PTR filings from the yearly XML indexes."""
    filings, errors = [], []
    for year in years:
        try:
            r = http(s, "GET", f"{BASE}/financial-pdfs/{year}FD.zip")
            z = zipfile.ZipFile(io.BytesIO(r.content))
            xml_name = next(n for n in z.namelist() if n.lower().endswith(".xml"))
            root = ET.fromstring(z.read(xml_name))
        except Exception as e:  # noqa: BLE001 - one bad year should not stop the rest
            errors.append(f"House index {year}: {type(e).__name__}: {e}")
            continue
        for el in root.iter():
            if _tag(el) != "Member" or _child(el, "FilingType").upper() != "P":
                continue
            doc_id = _child(el, "DocID")
            if not doc_id:
                continue
            filings.append({
                "doc_id": doc_id,
                "year": _child(el, "Year") or str(year),
                "first": _child(el, "First"),
                "last": _child(el, "Last"),
                "state_dst": _child(el, "StateDst"),
                "filed": parse_us_date(_child(el, "FilingDate")),
            })
    return filings, errors


def filing_url(f):
    return f"{BASE}/ptr-pdfs/{f['year']}/{f['doc_id']}.pdf"


def download(s, f) -> bytes:
    r = http(s, "GET", filing_url(f))
    if not r.content.startswith(b"%PDF"):
        raise TransientError(f"{filing_url(f)} did not return a PDF")
    return r.content


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_texts(pdf_bytes):
    """Yield the text of the PDF as read by pypdf, then by pdfplumber as a fallback."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        yield "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:  # noqa: BLE001
        pass
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            yield "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:  # noqa: BLE001
        pass


def has_text(text):
    return len(re.sub(r"\s", "", text or "")) > 80


# ---------------------------------------------------------------------------
# PTR text parser
# ---------------------------------------------------------------------------

STOP_RE = re.compile(
    r"^(P T R|F I|T|I P O|Yes No|Type|Date|Date Notification|Notification|Amount|Amount Cap\.?|"
    r"Cap\.|Gains >|\$200\?|C\s+S|ID Owner Asset.*|Clerk of the House.*|Name:.*|Status:.*|"
    r"State/District:.*|Filing ID.*|\* For the complete list.*|.*I CERTIFY.*|my knowledge and belief.*|"
    r"Digitally Signed:.*|Periodic Transaction Report.*)$",
    re.I,
)
LABEL_RE = re.compile(r"^(F S|S O|L|C|D)\s*:")
DESC_RE = re.compile(r"^D\s*:\s*")
TAG_RE = re.compile(r"\[(?P<atype>[A-Z]{2})\]")
CORE_RE = re.compile(
    r"(?:^|(?<=\s))(?P<tx>S \(partial\)|P|S|E)\s+"
    r"(?P<tdate>\d{1,2}/\d{1,2}/\d{4})\s+(?P<ndate>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<amt>(?:Spouse/DC\s+)?Over\s+\$[\d,]+|\$[\d,]+(?:\s*-\s*(?:\$[\d,]+)?)?)"
)
AMT_CONT_RE = re.compile(r"^\$[\d,]+$")
OWNER_RE = re.compile(r"^(SP|JT|DC)(?:\s+|$)")
TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,9})\)")


def _clean_lines(text):
    out = []
    for raw in (text or "").replace("\x00", "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            out.append(line)
    return out


def _classify(lines):
    """Label each line: stop (page furniture), label (F S:, S O:...), desc (D: and its wrap), text."""
    kinds = []
    open_desc, wraps = False, 0
    for line in lines:
        if STOP_RE.match(line):
            kind = "stop"
        elif DESC_RE.match(line):
            kind = "desc"
        elif LABEL_RE.match(line):
            kind = "label"
        elif (open_desc and wraps < 2 and not TAG_RE.search(line)
              and not CORE_RE.search(line) and not OWNER_RE.match(line)):
            kind = "desc"  # a description that wrapped onto the next line
        else:
            kind = "text"
        if kind == "desc":
            wraps = wraps + 1 if (open_desc and not DESC_RE.match(line)) else 0
            open_desc = not line.endswith(".")
        elif kind != "stop":
            open_desc, wraps = False, 0
        kinds.append(kind)
    return kinds


def _make_asset(fragments, atype):
    frags = fragments[-4:]
    for i in range(len(frags) - 1, -1, -1):
        if OWNER_RE.match(frags[i]):
            frags = frags[i:]
            break
    text = " ".join(frags).strip()
    owner = ""
    m = OWNER_RE.match(text)
    if m:
        owner = m.group(1)
        text = text[m.end():]
    tickers = TICKER_RE.findall(text)
    ticker = tickers[-1] if tickers else None
    name = TICKER_RE.sub("", text) if ticker else text
    name = re.sub(r"\s+", " ", name).strip(" -")
    return {"owner": OWNERS.get(owner, owner), "ticker": ticker, "asset": name,
            "asset_type": ASSET_TYPES.get(atype, atype)}


def parse_ptr_text(text):
    """Turn the text of one House PTR into transaction rows.

    Returns (rows, problems). Works whether the PDF text comes out row by row
    or with the transaction details on the first asset line.
    """
    lines = _clean_lines(text)
    kinds = _classify(lines)
    assets, cores, descs = [], [], {}
    buffer = []

    for line, kind in zip(lines, kinds):
        if kind in ("stop", "label"):
            buffer = []
            continue
        if kind == "desc":
            buffer = []
            if cores:
                idx = len(cores) - 1
                piece = DESC_RE.sub("", line)
                descs[idx] = (descs.get(idx, "") + " " + piece).strip()
            continue

        events = sorted(
            [(m.start(), "tag", m) for m in TAG_RE.finditer(line)]
            + [(m.start(), "core", m) for m in CORE_RE.finditer(line)],
            key=lambda e: e[0],
        )
        cursor = 0
        for start, ev, m in events:
            chunk = line[cursor:start].strip()
            if chunk:
                if cores and cores[-1]["open"] and AMT_CONT_RE.match(chunk):
                    cores[-1]["amt"] += " " + chunk
                    cores[-1]["open"] = False
                else:
                    buffer.append(chunk)
            if ev == "tag":
                assets.append(_make_asset(buffer, m.group("atype")))
                buffer = []
            else:
                amt = m.group("amt").strip()
                cores.append({"tx": m.group("tx"), "tdate": m.group("tdate"),
                              "ndate": m.group("ndate"), "amt": amt,
                              "open": amt.endswith("-")})
            cursor = m.end()
        tail = line[cursor:].strip()
        if tail:
            if cores and cores[-1]["open"] and AMT_CONT_RE.match(tail):
                cores[-1]["amt"] += " " + tail
                cores[-1]["open"] = False
            elif len(tail) > 1:
                buffer.append(tail)

    problems = []
    if len(assets) != len(cores):
        problems.append(f"found {len(assets)} assets but {len(cores)} transactions")

    rows = []
    for i, (a, c) in enumerate(zip(assets, cores)):
        lo, hi = parse_amount(c["amt"])
        rows.append({
            **a,
            "transaction": TX_TYPES.get(c["tx"], c["tx"]),
            "transaction_date": parse_us_date(c["tdate"]),
            "notification_date": parse_us_date(c["ndate"]),
            "amount_text": c["amt"],
            "amount_min": lo,
            "amount_max": hi,
            "description": descs.get(i),
        })
    return rows, problems


def parse_pdf(pdf_bytes):
    """Return (rows, problems, text_sample). Tries each text extractor until one parses."""
    best = ([], ["no readable text (probably a scanned paper filing)"], "")
    for text in extract_texts(pdf_bytes):
        if not has_text(text):
            continue
        rows, problems = parse_ptr_text(text)
        if rows and not problems:
            return rows, problems, ""
        if len(rows) > len(best[0]) or not best[2]:
            best = (rows, problems or ["no transactions recognised"], text[:1500])
    return best
