"""Daily run: collect new congressional trade filings and update the files in data/.

Output files (all in data/):
  trades.json        every trade collected so far (newest disclosures first)
  trades.csv         the same, for opening in Excel
  recent.json        trades disclosed in the last RECENT_WINDOW_DAYS days (read by Claude)
  needs_review.json  filings that could not be read automatically (scanned paper filings etc.)
  run_log.json       health of the last runs, so problems are visible
  state.json         bookkeeping: which filings are already processed
"""

import csv
import datetime as dt
import sys
import traceback

import house
import senate
from common import (BACKFILL_SINCE, DATA, MAX_ATTEMPTS, MAX_HOUSE_FILINGS_PER_RUN,
                    MAX_SENATE_FILINGS_PER_RUN, RECENT_WINDOW_DAYS, TransientError,
                    days_between, load_json, make_id, new_session, save_json, today)
from members import Members

CSV_FIELDS = [
    "filed_date", "transaction_date", "chamber", "member", "party", "state", "district",
    "owner", "transaction", "ticker", "asset", "asset_type", "amount_min", "amount_max",
    "amount_text", "disclosure_lag_days", "description", "committees", "subcommittees",
    "leadership_roles", "filing_url", "first_seen", "id",
]
MEMBER_FIELDS = ("bioguide_id", "chamber", "party", "state", "district",
                 "committees", "subcommittees", "leadership_roles")


def build_trade(chamber, filing_key, i, row, who, filed, url, run_day):
    return {
        "id": make_id(chamber, filing_key, i),
        "chamber": chamber,
        "member": who.get("name"),
        "bioguide_id": who.get("bioguide_id"),
        "party": who.get("party"),
        "state": who.get("state"),
        "district": who.get("district"),
        "committees": who.get("committees", []),
        "subcommittees": who.get("subcommittees", []),
        "leadership_roles": who.get("leadership_roles", []),
        **row,
        "filed_date": filed,
        "disclosure_lag_days": days_between(row.get("transaction_date"), filed),
        "filing_id": filing_key,
        "filing_url": url,
        "first_seen": run_day,
    }


def who_from_match(match, fallback_name, state=None, district=None):
    if match:
        return match
    return {"name": fallback_name, "state": state, "district": district}


def review_item(chamber, member, filed, url, reason, run_day, text_sample=""):
    item = {"chamber": chamber, "member": member, "filed_date": filed, "filing_url": url,
            "reason": reason, "first_seen": run_day}
    if text_sample:
        item["text_sample"] = text_sample
    return item


def run_house(s, members, state, run_day, log):
    years = range(BACKFILL_SINCE.year, dt.date.fromisoformat(run_day).year + 1)
    filings, errors = house.list_filings(s, years)
    log["errors"] += errors
    done = set(state["house_done"])
    attempts = state.setdefault("house_attempts", {})
    todo = [f for f in filings if f["doc_id"] not in done
            and (f["filed"] or "9999") >= BACKFILL_SINCE.isoformat()]
    todo.sort(key=lambda f: f["filed"] or "", reverse=True)
    log["house"]["backlog"] = max(0, len(todo) - MAX_HOUSE_FILINGS_PER_RUN)

    trades, review = [], []
    for f in todo[:MAX_HOUSE_FILINGS_PER_RUN]:
        url = house.filing_url(f)
        raw_name = f"{f['first']} {f['last']}".strip()
        try:
            pdf = house.download(s, f)
        except TransientError as e:
            n = attempts.get(f["doc_id"], 0) + 1
            attempts[f["doc_id"]] = n
            if n >= MAX_ATTEMPTS:
                review.append(review_item("House", raw_name, f["filed"], url, f"download kept failing: {e}", run_day))
                state["house_done"].append(f["doc_id"])
            log["house"]["download_failures"] += 1
            continue
        attempts.pop(f["doc_id"], None)
        rows, problems, sample = house.parse_pdf(pdf)
        match = members.match_house(f["first"], f["last"], f["state_dst"]) if members else None
        who = who_from_match(match, raw_name, f["state_dst"][:2] or None, f["state_dst"][2:] or None)
        for i, row in enumerate(rows):
            trades.append(build_trade("House", f["doc_id"], i, row, who, f["filed"], url, run_day))
        if problems:
            review.append(review_item("House", who["name"], f["filed"], url, "; ".join(problems), run_day, sample))
        state["house_done"].append(f["doc_id"])
        log["house"]["filings"] += 1
        log["house"]["trades"] += len(rows)
    return trades, review


def run_senate(s, members, state, run_day, log):
    sess = senate.SenateSession(s)
    filings = sess.list_filings(BACKFILL_SINCE)
    done = set(state["senate_done"])
    attempts = state.setdefault("senate_attempts", {})
    todo = [f for f in filings if f["report_id"] not in done]
    todo.sort(key=lambda f: f["filed"] or "", reverse=True)
    log["senate"]["backlog"] = max(0, len(todo) - MAX_SENATE_FILINGS_PER_RUN)

    trades, review = [], []
    for f in todo[:MAX_SENATE_FILINGS_PER_RUN]:
        raw_name = f"{f['first']} {f['last']}".strip()
        match = members.match_senate(f["first"], f["last"]) if members else None
        who = who_from_match(match, raw_name)
        if f["paper"]:
            review.append(review_item("Senate", who["name"], f["filed"], f["url"],
                                      "paper filing (scanned image), read it on the linked page", run_day))
            state["senate_done"].append(f["report_id"])
            log["senate"]["filings"] += 1
            continue
        try:
            html = sess.fetch_report(f)
        except TransientError as e:
            n = attempts.get(f["report_id"], 0) + 1
            attempts[f["report_id"]] = n
            if n >= MAX_ATTEMPTS:
                review.append(review_item("Senate", who["name"], f["filed"], f["url"], f"download kept failing: {e}", run_day))
                state["senate_done"].append(f["report_id"])
            log["senate"]["download_failures"] += 1
            continue
        attempts.pop(f["report_id"], None)
        rows, problems = senate.parse_report_html(html)
        for i, row in enumerate(rows):
            trades.append(build_trade("Senate", f["report_id"], i, row, who, f["filed"], f["url"], run_day))
        if problems:
            review.append(review_item("Senate", who["name"], f["filed"], f["url"], "; ".join(problems), run_day))
        state["senate_done"].append(f["report_id"])
        log["senate"]["filings"] += 1
        log["senate"]["trades"] += len(rows)
    return trades, review


def write_outputs(all_trades, review, run_day):
    all_trades.sort(key=lambda t: (t.get("filed_date") or "", t.get("transaction_date") or ""), reverse=True)
    save_json("trades.json", all_trades)

    with (DATA / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for t in all_trades:
            row = dict(t)
            for k in ("committees", "subcommittees", "leadership_roles"):
                row[k] = "; ".join(t.get(k) or [])
            w.writerow(row)

    cutoff = (dt.date.fromisoformat(run_day) - dt.timedelta(days=RECENT_WINDOW_DAYS)).isoformat()
    review_cutoff = (dt.date.fromisoformat(run_day) - dt.timedelta(days=365)).isoformat()
    review = [r for r in review if (r.get("filed_date") or r["first_seen"]) >= review_cutoff]
    save_json("needs_review.json", review)

    # recent.json stays small: committee info is listed once per member, not per trade.
    recent, people = [], {}
    for t in all_trades:
        if (t.get("filed_date") or "") < cutoff:
            continue
        people.setdefault(t["member"], {k: t.get(k) for k in MEMBER_FIELDS})
        recent.append({k: v for k, v in t.items() if k not in MEMBER_FIELDS or k == "chamber"})
    save_json("recent.json", {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "window_days": RECENT_WINDOW_DAYS,
        "note": ("Trades whose filing became public in the window (filed_date). "
                 "Member party, state and committee seats are in 'members', keyed by trade.member."),
        "members": people,
        "trades": recent,
        "needs_review": [r for r in review if (r.get("filed_date") or r["first_seen"]) >= cutoff],
    })


def main():
    run_day = today().isoformat()
    s = new_session()
    state = load_json("state.json", {"house_done": [], "senate_done": []})
    all_trades = load_json("trades.json", [])
    review = load_json("needs_review.json", [])
    known = {t["id"] for t in all_trades}
    log = {"run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "errors": [],
           "house": {"filings": 0, "trades": 0, "download_failures": 0, "backlog": None},
           "senate": {"filings": 0, "trades": 0, "download_failures": 0, "backlog": None}}

    try:
        members = Members.load(s)
    except Exception as e:  # noqa: BLE001
        members = None
        log["errors"].append(f"committee data unavailable this run: {type(e).__name__}: {e}")

    ok = 0
    for name, fn in (("House", run_house), ("Senate", run_senate)):
        try:
            trades, new_review = fn(s, members, state, run_day, log)
            all_trades += [t for t in trades if t["id"] not in known]
            known |= {t["id"] for t in trades}
            review += new_review
            ok += 1
        except Exception as e:  # noqa: BLE001
            log["errors"].append(f"{name} failed: {type(e).__name__}: {e}")
            traceback.print_exc()

    # Refresh committee info on recent trades (assignments change over time).
    # Older trades keep the committee seats as they were when collected.
    if members:
        by_id = members.people
        cutoff = (today() - dt.timedelta(days=RECENT_WINDOW_DAYS)).isoformat()
        for t in all_trades:
            if (t.get("filed_date") or "") < cutoff:
                continue
            info = by_id.get(t.get("bioguide_id"))
            if info:
                for k in ("committees", "subcommittees", "leadership_roles", "party"):
                    t[k] = info[k]

    write_outputs(all_trades, review, run_day)
    save_json("state.json", state)

    log["status"] = "ok" if ok == 2 and not log["errors"] else ("partial" if ok else "failed")
    history = load_json("run_log.json", {}).get("history", [])
    history = ([{k: log[k] for k in ("run_at", "status")} | {
        "house_trades": log["house"]["trades"], "senate_trades": log["senate"]["trades"],
        "errors": len(log["errors"])}] + history)[:30]
    save_json("run_log.json", {"last_run": log, "history": history})

    print(f"Status {log['status']}: House {log['house']}, Senate {log['senate']}")
    for e in log["errors"]:
        print("ERROR:", e)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
