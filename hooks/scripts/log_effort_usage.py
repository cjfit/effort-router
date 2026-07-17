#!/usr/bin/env python3
"""Stop hook for effort-router: log per-turn tier + token usage.

Reads the hook payload from stdin (session_id, transcript_path), re-derives
every turn of this session from the transcript, and rewrites this session's
usage file. Rewriting the whole session each time makes the hook idempotent —
no dedupe state needed. The Stop hook fires after every completed turn, so
the file stays current throughout the session. Stdlib only.

Turns are grouped by the transcript's promptId: every event carries the id of
the user prompt that started its turn, so skill-launch plumbing (isMeta user
messages injected mid-turn) doesn't split a routed turn's tokens off into a
phantom unrouted turn.

Output: ~/.claude/effort-router/usage/<session_id>.jsonl
  line 1 (session meta):
    {"meta": true, "session_id": "...", "summary": "<one line>"}
  then one record per turn:
    {"ts": ..., "tier": "low|medium|high|xhigh|max|null", "output_tokens": N,
     "assistant_messages": N, "model": "..."}
"""
import json
import os
import re
import sys

SUMMARY_MAX = 100


def one_line(text, limit=SUMMARY_MAX):
    text = re.sub(r"\s+", " ", text).strip()
    return text[: limit - 1] + "…" if len(text) > limit else text


def prompt_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text")
    return ""


def parse_transcript(transcript_path):
    """Return (turn records in order, one-line session summary)."""
    turns = {}  # promptId -> record, insertion-ordered
    summary = None
    first_prompt = None
    last_pid = None
    for line in open(transcript_path, encoding="utf-8"):
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "summary" and ev.get("summary"):
            summary = one_line(ev["summary"])  # session title, when present
            continue
        if ev.get("isSidechain"):
            continue  # subagent traffic has its own budget; don't attribute it
        pid = ev.get("promptId") or last_pid
        if pid is None:
            continue
        last_pid = pid
        turn = turns.setdefault(pid, {"ts": None, "tier": None,
                                      "output_tokens": 0,
                                      "assistant_messages": 0, "model": None})
        if turn["ts"] is None:
            turn["ts"] = ev.get("timestamp")
        msg = ev.get("message") or {}
        content = msg.get("content")
        if ev.get("type") == "user":
            if first_prompt is None and not ev.get("isMeta"):
                text = prompt_text(content)
                # skip injected tags (command output, system reminders)
                if text.strip() and not text.lstrip().startswith("<"):
                    first_prompt = one_line(text)
        elif ev.get("type") == "assistant":
            turn["assistant_messages"] += 1
            turn["model"] = msg.get("model") or turn["model"]
            usage = msg.get("usage") or {}
            turn["output_tokens"] += usage.get("output_tokens") or 0
            if turn["tier"] is None:
                for b in content if isinstance(content, list) else []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" \
                            and b.get("name") == "Skill":
                        skill = (b.get("input") or {}).get("skill", "")
                        if "effort-" in skill:
                            turn["tier"] = skill.split("effort-")[-1]
    # local commands (/context etc.) create turns with no assistant work
    records = [t for t in turns.values() if t["assistant_messages"]]
    return records, summary or first_prompt


def main():
    try:
        payload = json.load(sys.stdin)
        transcript = payload.get("transcript_path")
        session_id = payload.get("session_id")
        if not transcript or not session_id or not os.path.isfile(transcript):
            return
        out_dir = os.path.expanduser("~/.claude/effort-router/usage")
        os.makedirs(out_dir, exist_ok=True)
        records, summary = parse_transcript(transcript)
        tmp = os.path.join(out_dir, f"{session_id}.jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"meta": True, "session_id": session_id,
                                "summary": summary}) + "\n")
            for r in records:
                f.write(json.dumps(r) + "\n")
        os.replace(tmp, os.path.join(out_dir, f"{session_id}.jsonl"))
    except Exception:
        # A logging hook must never break the session it observes.
        pass


if __name__ == "__main__":
    main()
