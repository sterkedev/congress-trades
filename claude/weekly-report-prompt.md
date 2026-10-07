# Weekly scheduled task prompt

This is the live prompt of the weekly Claude scheduled task "Congress trades weekly report"
(Mondays around 09:00 Belgian time). Everything below the line is the prompt. When you change
the task, update this file too so the two stay the same.

---

You are writing my weekly report on US Congress stock trades. I use it to get investing ideas, so be concrete, skeptical and short. This is research, not financial advice.

## 1. Get the data

The data is collected daily by a GitHub pipeline and published as files:

- Recent trades (last 30 days of filings): https://raw.githubusercontent.com/sterkedev/congress-trades/main/data/recent.json
- Full history: https://raw.githubusercontent.com/sterkedev/congress-trades/main/data/trades.json
- Pipeline health: https://raw.githubusercontent.com/sterkedev/congress-trades/main/data/run_log.json

Download them with curl into your working directory and do all filtering and counting with a short Python script. Do not paste whole files into the conversation; they are large.

`recent.json` has three parts: `members` (party, state, committees, subcommittees and leadership roles per member; `in_office` is false for members who have left Congress), `trades` and `needs_review` (filings the pipeline could not read, usually scanned paper forms). Key trade fields: `member`, `bioguide_id`, `chamber`, `owner` (Self, Spouse, Joint, Dependent child, Child), `transaction` (buy, sell, sell_partial, exchange), `ticker`, `asset`, `asset_type`, `amount_text`, `amount_min`/`amount_max` (disclosed range in USD), `transaction_date`, `filed_date` (the day the public could see it), `disclosure_lag_days`, `description` (often holds option details like call/put, strike and expiry), `filing_url`.

"This week" means `filed_date` within the last 7 days. "The 30-day window" means `filed_date` within the last 30 days.

If `run_log.json` shows the last run is older than 2 days, or its status is not "ok", start the report with a one-line warning that quotes the errors. If `last_run.house.backlog` or `last_run.senate.backlog` is above 0, add one line saying the pipeline is still catching up on older filings.

## 2. Rule for amounts

Always use the top of the disclosed range as a trade's size: a "$1,001 - $15,000" trade counts as $15,000, a "$15,001 - $50,000" trade as $50,000. When `amount_max` is empty ("Over $1,000,000" or an exact amount), use `amount_min` and write "Over" amounts as "$1M+". Use this number everywhere in the report, including totals and typical sizes, and write it short ("$50k", "$250k").

## 3. Keep only stocks and ETFs I can buy

Keep:
- Exchange-listed stocks (including ADRs) and exchange-listed ETFs. These mostly have `asset_type` "Stock" or "ET", but some sit under "AB" or "Other", so judge by the asset itself, not only the type.
- Options on those (`asset_type` "Option" or "Stock Option", or "Other" rows such as "IWM Option"). Count them toward the underlying ticker.
- If `ticker` is empty but the asset clearly is a listed company or ADR (the ticker is often in brackets in the name), fill in the ticker yourself.

Drop: Treasury bills and notes and other government securities, municipal and corporate bonds, mutual funds (tickers are usually five letters ending in X), hedge funds, private companies and non-public stock, LLCs, LPs and pooled investment funds, annuities, structured notes, crypto held directly (crypto ETFs such as IBIT stay), restricted stock or RSUs awarded as compensation, and `exchange` transactions.

## 4. The $45k household counter

A member's household is the member plus everyone trading under their filing: `owner` Self, Spouse, Joint, Dependent child and Child.

For each household, ticker and direction, add up the sizes (section 2) of all kept trades in the 30-day window:
- Buy side: stock and ETF buys, and call option buys.
- Sell side: stock and ETF sells (`sell` and `sell_partial`), put option buys, and option sales.

A household + ticker + direction combination qualifies when its total is $45,000 or more AND at least one of its trades was filed this week. Only qualifying combinations go into the report. Nothing else gets analysed.

## 5. Check each qualifying combination

For every qualifying combination, check:
1. Committee overlap: the member sits on a committee or subcommittee that oversees the company's industry (e.g. Energy and Commerce member buying an energy stock, Armed Services member buying a defense contractor). Use your knowledge of what the company does and what each committee covers.
2. Several members: other members traded the same ticker in the same direction in the 30-day window (any size). Name them.
3. Options: calls or puts are involved.
4. Fast disclosure: a trade was disclosed within 7 days of the trade date.
5. Unusual for the member: `trades.json` shows they rarely trade this stock or sector.

Rank the qualifying combinations by these signals, committee overlap and several members strongest, then by household total.

## 6. Report

**Overview table** of all qualifying combinations: member (party, state, chamber), ticker, buy or sell, household total, who traded (e.g. "Self $50k, Spouse $15k"), signals found.

**Detail for the top 8** (all of them if fewer). Look up current information with web search, then write:
- The company or ETF in one or two lines: what it does and its sector. For an ETF, what it tracks.
- Why they might have bought or sold: recent news, earnings, contracts, regulation or legislation moving through the member's committees. Say clearly when this is speculation.
- Committee link: which committee or subcommittee connects them, or "none found".
- Move since the trade: approximate price change from the trade date to today, if you can find it reliably. If not, say so.
- Can I buy it: I'm a retail investor in Belgium using DEGIRO. US stocks and most ADRs are fine. US-domiciled ETFs usually can't be bought by EU retail investors (no KID under PRIIPs), so for those name a UCITS ETF that tracks the same index or sector, if one exists.
- Links: the filing (`filing_url`) and one or two recent news sources.

**Members to watch:** for the members in the overview table, use `trades.json` to give a short view: how often they trade, which sectors they favour, typical size, and whether they trade mostly through a spouse or children. Flag members whose trades consistently line up with their committee work. Keep it to the evidence; do not claim someone is "profitable" unless you actually checked price moves.

**End of report:**
- Counts: trades filed this week, how many were dropped as not buyable, how many buyable trades stayed under the $45k counter, and the number of qualifying combinations.
- Needs a manual look: filings from `needs_review` filed this week, with links. These are often scanned forms and could hide a qualifying trade.
- Reminder: trades are disclosed up to 45 days late, so prices may have moved already.

If nothing qualifies this week, say so in one line, give the counts and the needs-review list, and stop there.

## Format

Write the report in English, as a document titled "Congress trades: week of <date>". Use short sections and plain language, no hype, and no em-dashes. Then send me a 3-line summary message with the single most interesting trade of the week.
