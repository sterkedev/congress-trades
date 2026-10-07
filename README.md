# Congress trades tracker

Collects the stock trades that US House and Senate members disclose, every day, straight
from the official government sites. It adds each member's party, state and committee seats,
and saves everything as files in this repository. A weekly Claude scheduled task reads those
files and writes the report.

Nothing runs on your own computer. GitHub runs the collection for free in its cloud.

```
House Clerk (PDF filings) ─┐
                           ├─> GitHub Actions, daily ──> data/ files in this repo ──> weekly Claude task ──> report
Senate eFD (web filings) ──┘           │
                                       └─ adds committees from the congress-legislators dataset
```

## One-time setup (about 15 minutes, all in the browser)

**1. Create the repository**

1. Sign in at github.com (create a free account if you don't have one).
2. Top right: **+** > **New repository**.
3. Name: `congress-trades`. Visibility: **Public** (see "Why public" below).
4. Leave "Add a README" unticked. Click **Create repository**.

**2. Upload the files**

1. Unzip `congress-trades.zip` on your computer (right-click > Extract All).
2. On the new, empty repository page, click the link **uploading an existing file**.
3. Open the extracted `congress-trades` folder, select everything inside it
   (`.github`, `claude`, `data`, `pipeline`, `README.md`) and drag it onto the browser page.
4. Click **Commit changes**.
5. Check that the repository now shows a `.github` folder. If it does not (some browsers
   skip folders starting with a dot): click **Add file** > **Create new file**, type the name
   `.github/workflows/update-trades.yml`, paste in the contents of that file from the zip,
   and click **Commit changes**.

**3. Start the first run**

1. Open the **Actions** tab. If GitHub asks, click the button to enable workflows.
2. Click **Update congress trades** in the left list, then **Run workflow** > **Run workflow**.
3. Wait for the green check mark (the first run can take 10 to 20 minutes).
4. Open the `data` folder in the repository. You should see `recent.json`, `trades.json`,
   `trades.csv`, `needs_review.json` and `run_log.json`.

From now on it runs by itself every morning at 08:17 Belgian summer time (07:17 in winter).

**Backfill:** the first runs collect everything since 1 January 2025, newest first, a few
hundred filings per run. Recent weeks are complete after the first run; the full history
fills in over roughly the first ten days. Clicking **Run workflow** a few extra times on
day one speeds that up.

**4. Set up the weekly Claude task**

Done: the weekly Claude scheduled task "Congress trades weekly report" runs on Mondays.
Its prompt is kept in `claude/weekly-report-prompt.md`.

## What's in `data/`

| File | What it is |
|---|---|
| `recent.json` | Trades disclosed in the last 30 days, plus member committee info. This is what Claude reads. |
| `trades.json` | Every trade collected so far. |
| `trades.csv` | The same, opens in Excel. |
| `needs_review.json` | Filings that could not be read automatically (mostly scanned paper forms), with links. |
| `run_log.json` | Health of the last 30 runs: status, counts and errors. |
| `state.json` | Bookkeeping of which filings are done. Leave it alone. |

## Settings

The top of `pipeline/common.py` holds the settings: how far back to collect
(`BACKFILL_SINCE`), how many filings per run, and the 30-day window for `recent.json`.
You can edit them in the browser (open the file, click the pencil icon, commit).

## Why public

Public repositories get unlimited free GitHub Actions minutes, and Claude can read the files
without a login. The data is public record anyway. If you prefer private, it still fits in
GitHub's free monthly minutes, but the weekly Claude task then needs access to your GitHub
account to read the files.

## If something breaks

- **Red cross in the Actions tab:** click the failed run, then the step with the red cross,
  and copy the error text. Paste it to Claude and ask for a fix.
- **"Permission denied" when saving data:** Settings > Actions > General > Workflow permissions >
  choose **Read and write permissions** > Save.
- **GitHub emails that the workflow was disabled:** GitHub pauses scheduled workflows in
  public repositories after 60 days without activity. Open the Actions tab and re-enable it.
- **Many entries in `needs_review.json` with a `text_sample`:** a filing format changed and
  the reader needs an update. Send Claude a few of those entries.

## Rules of use

These are public records under the STOCK Act. The House and Senate sites restrict using the
information for commercial purposes or fundraising. Personal research is fine; don't resell
the data or turn it into a paid product.

## Known limits

- Only electronic filings are read automatically. Paper filings are listed in
  `needs_review.json` with a link.
- Amounts are ranges, as disclosed (for example $1,001 to $15,000).
- Amended filings show up as new filings, so an amendment can duplicate trades.
- No price performance yet. That's the natural next step (a member track-record score).
