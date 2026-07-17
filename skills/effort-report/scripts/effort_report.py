#!/usr/bin/env python3
"""Effort-router savings report.

Reads ~/.claude/effort-router/usage/*.jsonl (written per turn by the Stop
hook) and leads with what the router is worth: tokens saved by downshifting,
then likely misroutes — turns routed low that ballooned (probably flailed
without enough reasoning) and turns routed high/xhigh/max that were tiny
(paid heavy reasoning for trivial work). Breakdown tables follow as context.
Stdlib only.
"""
import glob
import json
import os
from collections import defaultdict

TIER_ORDER = ["low", "medium", "high", "xhigh", "max", "unrouted"]
NEXT_TIER_UP = {"low": "medium", "medium": "high"}
# absolute fallbacks when the reference tier has no data yet
UNDER_ABS = {"low": 5000, "medium": 20000}   # bigger than this looks underrouted
OVER_ABS = 1500                              # high+ tiers smaller than this look overrouted
SUMMARY_WIDTH = 52


def load_sessions():
    """Return [(session_id, summary, [turn records])] per usage file."""
    sessions = []
    for path in sorted(glob.glob(
            os.path.expanduser("~/.claude/effort-router/usage/*.jsonl"))):
        session_id = os.path.basename(path).removesuffix(".jsonl")
        summary = None
        records = []
        for line in open(path, encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("meta"):
                summary = r.get("summary")
            else:
                records.append(r)
        sessions.append((session_id, summary, records))
    return sessions


def tier_of(r):
    return r.get("tier") or "unrouted"


def tokens_of(r):
    return r.get("output_tokens") or 0


def tier_counts(records):
    counts = defaultdict(int)
    for r in records:
        counts[tier_of(r)] += 1
    return ", ".join(f"{t}={counts[t]}" for t in TIER_ORDER if counts.get(t))


def print_flagged(flagged):
    print(f"  {'date':10} {'tier':7} {'tokens':>8}  session")
    for r in flagged:
        day = (r.get("ts") or "?")[:10]
        text = (r.get("_summary") or "(no summary)")[:SUMMARY_WIDTH]
        print(f"  {day:10} {tier_of(r):7} {tokens_of(r):>8}  {text}")


def main():
    sessions = load_sessions()
    records = []
    for _, summary, recs in sessions:
        for r in recs:
            r["_summary"] = summary
            records.append(r)
    if not records:
        print("No usage data yet. Records appear after turns complete in "
              "sessions with effort-router installed (Stop hook writes "
              "~/.claude/effort-router/usage/).")
        return

    by_tier = defaultdict(lambda: {"turns": 0, "tokens": 0})
    for r in records:
        by_tier[tier_of(r)]["turns"] += 1
        by_tier[tier_of(r)]["tokens"] += tokens_of(r)
    means = {t: d["tokens"] / d["turns"]
             for t, d in by_tier.items() if d["turns"]}

    print("== savings from downshifting ==")
    low = by_tier.get("low")
    med = by_tier.get("medium")
    if low and med:
        saved = low["turns"] * (means["medium"] - means["low"])
        print(f"  {saved:,.0f} output tokens saved across {low['turns']} "
              f"low-routed turns")
        print("  (low turns x (mean medium turn - mean low turn); "
              "counterfactual and rough — tiers see different task mixes)")
    else:
        print("  not enough data: needs at least one low-routed and one "
              "medium-routed turn to compare")

    # underrouted: a low/medium turn that ran far past its tier's norm —
    # it likely flailed for lack of reasoning, wasting the whole turn
    underrouted = []
    for r in records:
        tier = tier_of(r)
        if tier not in NEXT_TIER_UP:
            continue
        ref = means.get(NEXT_TIER_UP[tier])
        limit = ref if ref is not None else UNDER_ABS[tier]
        if tokens_of(r) > limit:
            underrouted.append(r)

    # overrouted: a high/xhigh/max turn so small the work was trivial —
    # its output (incl. thinking) tokens were mostly unnecessary
    overrouted = [r for r in records
                  if tier_of(r) in ("high", "xhigh", "max")
                  and tokens_of(r) <= OVER_ABS]

    print("\n== likely misroutes (heuristic — inspect before concluding) ==")
    if underrouted:
        wasted = sum(tokens_of(r) for r in underrouted)
        print(f"underrouted — ran big at low effort, turn may be wasted "
              f"({len(underrouted)} turns, {wasted:,} tokens at risk):")
        print_flagged(sorted(underrouted, key=tokens_of, reverse=True))
    else:
        print("underrouted: none — no low/medium turn outgrew the tier above")
    if overrouted:
        base = means.get("low") or means.get("medium") or 0
        excess = sum(max(tokens_of(r) - base, 0) for r in overrouted)
        print(f"overrouted — trivial work at high/xhigh/max "
              f"({len(overrouted)} turns, ~{excess:,.0f} tokens recoverable):")
        print_flagged(sorted(overrouted, key=tokens_of))
    else:
        print("overrouted: none — no high/xhigh/max turn looked trivially small")

    print("\n== context ==")
    print(f"{'tier':10} {'turns':>6} {'output tokens':>14} {'mean/turn':>10}")
    for tier in TIER_ORDER:
        if tier not in by_tier:
            continue
        d = by_tier[tier]
        print(f"{tier:10} {d['turns']:>6} {d['tokens']:>14} "
              f"{d['tokens'] / d['turns']:>10.0f}")

    by_day = defaultdict(list)
    for r in records:
        ts = r.get("ts") or ""
        if len(ts) >= 10:
            by_day[ts[:10]].append(r)
    print("\nby day:")
    for day in sorted(by_day):
        recs = by_day[day]
        tokens = sum(tokens_of(r) for r in recs)
        print(f"  {day:10} {len(recs):>4} turns {tokens:>12} tok  "
              f"{tier_counts(recs)}")

    by_model = defaultdict(lambda: {"turns": 0, "tokens": 0})
    for r in records:
        model = r.get("model") or "unknown"
        by_model[model]["turns"] += 1
        by_model[model]["tokens"] += tokens_of(r)
    print("\nby model:")
    for model in sorted(by_model):
        d = by_model[model]
        print(f"  {model:32} {d['turns']:>4} turns {d['tokens']:>12} tok")

    print("\nby session:")
    for _, summary, recs in sessions:
        if not recs:
            continue
        tokens = sum(tokens_of(r) for r in recs)
        first_ts = next((r["ts"][:10] for r in recs
                         if len(r.get("ts") or "") >= 10), "?")
        text = (summary or "(no summary)")[:SUMMARY_WIDTH]
        print(f"  {first_ts:10} {len(recs):>4} turns {tokens:>12} tok  {text}")
        print(f"  {'':43}[{tier_counts(recs)}]")


if __name__ == "__main__":
    main()
