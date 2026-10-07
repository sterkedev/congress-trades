"""Quick checks for the parsers, using text from real filings.

Run with:  python -m pytest pipeline/test_parsers.py   (only needed when changing a parser)
"""

from house import parse_ptr_text
from senate import parse_report_html

# Real House PTR text (Filing ID 20026590), as a PDF reader returns it, including a page break.
PELOSI = """P T R
Clerk of the House of Representatives • Legislative Resource Center • B81 Cannon Building • Washington, DC 20515
F I
Name: Hon. Nancy Pelosi
Status: Member
State/District: CA11
T
ID Owner Asset Transaction
Type
Date Notification
Date
Amount Cap.
Gains >
$200?
SP Alphabet Inc. - Class A Common
Stock (GOOGL) [OP]
P 01/14/2025 01/14/2025 $250,001 -
$500,000
F S: New
D: Purchased 50 call options with a strike price of $150 and an expiration date of 1/16/26.
SP Apple Inc. - Common Stock (AAPL)
[ST]
S (partial) 12/31/2024 12/31/2024 $5,000,001 -
$25,000,000
F S: New
D: Sold 31,600 shares.
SP NVIDIA Corporation - Common
Stock (NVDA) [ST]
P 12/20/2024 12/20/2024 $500,001 -
$1,000,000
F S: New
D: Exercised 500 call options purchased 11/22/23 (50,000 shares) at a strike price of $12 with an expiration date
of 12/20/24.
SP NVIDIA Corporation - Common
Stock (NVDA) [OP]
P 01/14/2025 01/14/2025 $250,001 -
$500,000
F S: New
Filing ID #20026590
ID Owner Asset Transaction
Type
Date Notification
Date
Amount Cap.
Gains >
$200?
D: Purchased 50 call options with a strike price of $80 and an expiration date of 1/16/26.
Microsoft Corporation - Common
Stock (MSFT) [ST]
E 01/02/2025 01/03/2025 $1,001 - $15,000
F S: New
"""

# Real House PTR text (Filing ID 20029120): asset and transaction on one line.
PETERS = """P T R
Name: Hon. Scott H. Peters
State/District: CA50
ID Owner Asset Transaction
Type
Date Notification
Date
Amount Cap.
Gains >
$200?
SP U.S Treasury Bills [GS] S (partial) 03/27/2025 03/31/2025 $500,001 -
$1,000,000
F S: New
SP U.S Treasury Bills [GS] P 03/31/2025 03/31/2025 $500,001 -
$1,000,000
F S: New
* For the complete list of asset type abbreviations, please visit https://fd.house.gov/reference/asset-type-codes.aspx.
I P O
Yes No
C S
Digitally Signed: Hon. Scott H. Peters , 04/18/2025
Filing ID #20029120
"""

# Same kind of row, but read in the other order some PDF readers use
# (transaction details on the first asset line).
REORDERED = """ID Owner Asset Transaction
SP Alphabet Inc. - Class A Common P 01/14/2025 01/14/2025 $250,001 -
Stock (GOOGL) [OP] $500,000
F S: New
D: Purchased 50 call options.
JT Vistra Corp. Common Stock (VST) S 02/03/2025 02/04/2025 Over $50,000,000
[ST]
"""


def test_pelosi_layout():
    rows, problems = parse_ptr_text(PELOSI)
    assert problems == []
    assert [r["ticker"] for r in rows] == ["GOOGL", "AAPL", "NVDA", "NVDA", "MSFT"]
    assert [r["transaction"] for r in rows] == ["buy", "sell_partial", "buy", "buy", "exchange"]
    assert rows[0]["asset_type"] == "Option" and rows[1]["asset_type"] == "Stock"
    assert rows[0]["owner"] == "Spouse" and rows[4]["owner"] == "Self"
    assert (rows[1]["amount_min"], rows[1]["amount_max"]) == (5000001, 25000000)
    assert (rows[4]["amount_min"], rows[4]["amount_max"]) == (1001, 15000)
    assert rows[1]["transaction_date"] == "2024-12-31"
    assert rows[2]["description"].endswith("of 12/20/24.")
    assert "strike price of $80" in rows[3]["description"]
    assert rows[4]["asset"] == "Microsoft Corporation - Common Stock"
    assert rows[0]["asset"] == "Alphabet Inc. - Class A Common Stock"


def test_peters_single_line():
    rows, problems = parse_ptr_text(PETERS)
    assert problems == []
    assert len(rows) == 2
    assert rows[0]["transaction"] == "sell_partial" and rows[1]["transaction"] == "buy"
    assert rows[0]["ticker"] is None and rows[0]["asset"] == "U.S Treasury Bills"
    assert rows[0]["amount_max"] == 1000000


def test_reordered_layout():
    rows, problems = parse_ptr_text(REORDERED)
    assert problems == []
    assert [r["ticker"] for r in rows] == ["GOOGL", "VST"]
    assert rows[0]["amount_max"] == 500000
    assert rows[1]["owner"] == "Joint" and rows[1]["amount_min"] == 50000001
    assert rows[0]["description"] == "Purchased 50 call options."


SENATE_HTML = """<html><body><table class="table table-striped">
<thead><tr><th>#</th><th>Transaction Date</th><th>Owner</th><th>Ticker</th><th>Asset Name</th>
<th>Asset Type</th><th>Type</th><th>Amount</th><th>Comment</th></tr></thead>
<tbody>
<tr><td>1</td><td>09/12/2026</td><td>Spouse</td><td><a href="https://finance.yahoo.com/quote/XOM">XOM</a></td>
<td>Exxon Mobil Corporation</td><td>Stock</td><td>Purchase</td><td>$15,001 - $50,000</td><td>--</td></tr>
<tr><td>2</td><td>09/15/2026</td><td>Self</td><td>--</td><td>US Treasury Note</td><td>Other Securities</td>
<td>Sale (Partial)</td><td>$1,001 - $15,000</td><td>Matured</td></tr>
</tbody></table></body></html>"""


def test_senate_table():
    rows, problems = parse_report_html(SENATE_HTML)
    assert problems == []
    assert rows[0]["ticker"] == "XOM" and rows[0]["transaction"] == "buy"
    assert rows[0]["asset_type"] == "Stock" and rows[0]["owner"] == "Spouse"
    assert rows[1]["ticker"] is None and rows[1]["transaction"] == "sell_partial"
    assert rows[1]["description"] == "Matured" and rows[0]["description"] is None
    assert (rows[0]["amount_min"], rows[0]["amount_max"]) == (15001, 50000)
