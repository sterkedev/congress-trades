"""Who is who: party, state and committee seats for current members of Congress.

Source: the open congress-legislators dataset on GitHub
(github.com/unitedstates/congress-legislators), maintained by volunteers and
updated when committee assignments change.
"""

import yaml

from common import http, norm_name

RAW = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main/"
PARTY = {"Democrat": "D", "Republican": "R", "Independent": "I"}


class Members:
    def __init__(self):
        self.people = {}          # bioguide -> info dict
        self.by_seat = {}         # (state, district) -> bioguide, House only
        self.senators = []        # bioguide list

    @classmethod
    def load(cls, s):
        m = cls()
        loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
        legislators = yaml.load(http(s, "GET", RAW + "legislators-current.yaml").text, Loader=loader)
        committees = yaml.load(http(s, "GET", RAW + "committees-current.yaml").text, Loader=loader)
        membership = yaml.load(http(s, "GET", RAW + "committee-membership-current.yaml").text, Loader=loader)

        names = {}
        for c in committees:
            names[c["thomas_id"]] = c["name"]
            for sub in c.get("subcommittees", []) or []:
                names[c["thomas_id"] + sub["thomas_id"]] = f"{c['name']}: {sub['name']}"

        for p in legislators:
            term = p["terms"][-1]
            bid = p["id"]["bioguide"]
            n = p["name"]
            info = {
                "bioguide_id": bid,
                "name": n.get("official_full") or f"{n.get('first', '')} {n.get('last', '')}".strip(),
                "first": n.get("first", ""), "last": n.get("last", ""), "nickname": n.get("nickname", ""),
                "party": PARTY.get(term.get("party"), term.get("party")),
                "state": term.get("state"),
                "district": term.get("district"),
                "chamber": "Senate" if term["type"] == "sen" else "House",
                "committees": [], "subcommittees": [], "leadership_roles": [],
            }
            m.people[bid] = info
            if term["type"] == "rep":
                m.by_seat[(term.get("state"), int(term.get("district") or 0))] = bid
            else:
                m.senators.append(bid)

        for code, seats in membership.items():
            label = names.get(code, code)
            is_sub = code not in {c["thomas_id"] for c in committees}
            for seat in seats or []:
                info = m.people.get(seat.get("bioguide"))
                if not info:
                    continue
                (info["subcommittees"] if is_sub else info["committees"]).append(label)
                if seat.get("title"):
                    info["leadership_roles"].append(f"{seat['title']}, {label}")
        return m

    # -- matching ------------------------------------------------------------

    def _name_ok(self, info, first, last):
        full = norm_name(f"{info['first']} {info['last']} {info['name']}")
        lw = norm_name(last).split()
        if not lw or not all(w in full.split() for w in lw):
            return False
        if not first:
            return True
        f = norm_name(first).split()
        firsts = {norm_name(info["first"]), norm_name(info.get("nickname", ""))} | set(full.split())
        return bool(f) and (f[0] in firsts or any(x.startswith(f[0][:3]) for x in firsts if x))

    def match_house(self, first, last, state_dst):
        state = (state_dst or "")[:2].upper()
        digits = "".join(ch for ch in (state_dst or "")[2:] if ch.isdigit())
        if digits:
            bid = self.by_seat.get((state, int(digits)))
            if bid and self._name_ok(self.people[bid], "", last):
                return self.people[bid]
        same_state = [p for p in self.people.values() if p["chamber"] == "House" and p["state"] == state]
        return self._pick(same_state, first, last)

    def match_senate(self, first, last):
        return self._pick([self.people[b] for b in self.senators], first, last)

    def _pick(self, pool, first, last):
        """Unique last-name match wins; if several share the last name, use the first name."""
        by_last = [p for p in pool if self._name_ok(p, "", last)]
        if len(by_last) == 1:
            return by_last[0]
        by_both = [p for p in by_last if self._name_ok(p, first, last)]
        return by_both[0] if len(by_both) == 1 else None
