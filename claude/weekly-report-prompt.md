# Weekly scheduled task prompt

Paste everything below the line into the prompt of a weekly Claude scheduled task
(suggested: Monday morning). Replace `<GITHUB-USERNAME>` with your GitHub username first.

---

You are writing my weekly report on US Congress stock trades. I use it to get investing
ideas, so be concrete, skeptical and short. This is research, not financial advice.

## 1. Get the data

The data is collected daily by a GitHub pipeline and published as files:

- Recent trades: https://raw.githubusercontent.com/<GITHUB-USERNAME>/congress-trades/main/data/recent.json
- Full history: https://raw.githubusercontent.com/<GITHUB-USERNAME>/congress-trades/main/data/trades.json
- Pipeline health: https://raw.githubusercontent.com/<GITHUB-USERNAME>/congress-trades/main/data/run_log.json

Download them with a shell command (curl) into your working directory and analyse them with
a short Python script. Do not paste whole files into the conversation; they are large.

`recent.json` has three parts: `members` (party, state, committees, subcommittees and
leadership roles per member; `in_office` is false for members who have left Congress), `trades` and `needs_review` (filings the pipeline could not
read, usually scanned paper forms). Key trade fields: `member`, `chamber`, `owner`
(Self/Spouse/Joint/Dependent child), `transaction` (buy, sell, sell_partial, exchange),
`ticker`, `asset`, `asset_type`, `amount_min`/`amount_max` (disclosed range in USD; `amount_max` is empty for "Over" amounts),
`transaction_date`, `filed_date` (the day the public could see it), `disclosure_lag_days`,
`description` (often holds option details like strike and expiry), `filing_url`.

"This week" means `filed_date` within the last 7 days.

If `run_log.json` shows the last run is older than 2 days, or its status is not "ok",
start the report with a one-line warning that quotes the errors.

## 2. Pick what matters

From this week's trades, select the notable ones. Rank by these signals, strongest first:

1. **Committee overlap:** the member sits on a committee or subcommittee that oversees the
   company's industry (e.g. Energy and Commerce member buying an energy stock, Armed
   Services member buying a defense contractor). Use your knowledge of what each company
   does and what each committee covers.
2. **Size:** purchases of individual stocks or options with `amount_min` of $50,001 or more.
3. **Clusters:** the same ticker bought by two or more members in the last 30 days
   (check `trades.json` for the 30-day window).
4. **Options and conviction:** call options, or a member buying something they rarely trade.
5. **Fast disclosure:** buys disclosed within 7 days of the trade (fresher signal).

Mostly ignore: Treasury bills and notes, broad index funds and ETFs, mutual funds, and sales
that look like routine rebalancing. Mention them only as a count.

## 3. For each notable trade (max 8)

Look up current information with web search, then write:

- **Who and what:** member (party, state, chamber), buy or sell, ticker and company,
  amount range, owner, trade date and disclosure date.
- **The company in one or two lines:** what it does and its sector.
- **Why they might have bought or sold:** recent news, earnings, contracts, regulation or
  legislation moving through the member's committees. Say clearly when this is speculation.
- **Committee link:** which committee or subcommittee connects them, or "none found".
- **Move since the trade:** approximate price change from the trade date to today, if you
  can find it reliably. If not, say so.
- **Links:** the filing (`filing_url`) and one or two recent news sources.

## 4. Members to watch

Using `trades.json` (all history), give a short view on the members who appeared this week:
how often they trade, which sectors they favour, typical size, and whether they trade
mostly through a spouse. Flag members whose trades consistently line up with their
committee work. Keep it to the evidence; do not claim someone is "profitable" unless you
actually checked price moves.

## 5. End of report

- **Count of the rest:** total trades this week, buys vs sells, how many routine ones you skipped.
- **Needs a manual look:** filings from `needs_review` filed this week, with links.
- **Reminder:** trades are disclosed up to 45 days late, so prices may have moved already.

## Format

Write the report in English, as a document titled "Congress trades: week of <date>".
Use short sections and plain language, no hype. Then send me a 3-line summary message with
the single most interesting trade of the week.
