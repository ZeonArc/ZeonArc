#!/usr/bin/env python3
"""Render the dynamic sections of README.md.

Sections are delimited by HTML comment markers, e.g.:

    <!--TRACKER:START-->  ...  <!--TRACKER:END-->

Sections rendered:
  FOCUS     - progress bars from data/tracker.json
  ACTIVITY  - latest public GitHub events for the profile owner
  REPOS     - most recently pushed public repositories
  UPDATED   - UTC timestamp of the last run

Standard library only. Set GITHUB_TOKEN to raise the API rate limit.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
DATA = ROOT / "data" / "tracker.json"
USER = os.environ.get("GITHUB_USER", "ZeonArc")
BAR_WIDTH = 10


def api(path):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "profile-tracker"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def esc(text):
    return re.sub(r"([|\[\]<>`*_])", r"\\\1", str(text)).replace("\n", " ")


def ago(iso):
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    secs = int((datetime.now(timezone.utc) - then).total_seconds())
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{secs // size}{unit} ago"
    return "just now"


def render_focus():
    items = json.loads(DATA.read_text(encoding="utf-8"))["focus"]
    rows = ["| Focus area | Status | Progress |", "|---|---|---|"]
    for it in items:
        pct = max(0, min(100, int(it["progress"])))
        filled = round(pct / 100 * BAR_WIDTH)
        bar = "█" * filled + "░" * (BAR_WIDTH - filled)
        rows.append(f"| {esc(it['name'])} | {esc(it['status'])} | `{bar}` {pct}% |")
    return "\n".join(rows)


def describe(ev):
    repo = ev["repo"]["name"]
    link = f"[{repo}](https://github.com/{repo})"
    p = ev["payload"]
    t = ev["type"]
    if t == "PushEvent":
        n = p.get("size") or len(p.get("commits", [])) or 1
        return f"⬆️ Pushed {n} commit{'s' if n != 1 else ''} to {link}"
    if t == "PullRequestEvent":
        return f"🔀 {p['action'].capitalize()} pull request in {link}"
    if t == "IssuesEvent":
        return f"🐛 {p['action'].capitalize()} an issue in {link}"
    if t == "CreateEvent":
        return f"✨ Created {p.get('ref_type', 'repository')} in {link}"
    if t == "ReleaseEvent":
        return f"🚀 Published a release in {link}"
    if t == "WatchEvent":
        return f"⭐ Starred {link}"
    if t == "ForkEvent":
        return f"🍴 Forked {link}"
    return None


def render_activity(limit=5):
    lines = []
    for ev in api(f"/users/{USER}/events/public?per_page=50"):
        text = describe(ev)
        if text:
            lines.append(f"- {text} — <sub>{ago(ev['created_at'])}</sub>")
        if len(lines) == limit:
            break
    return "\n".join(lines) or "_No recent public activity._"


def render_repos(limit=5):
    repos = api(f"/users/{USER}/repos?sort=pushed&per_page=30&type=owner")
    repos = [r for r in repos if not r["fork"] and r["name"].lower() != USER.lower()][:limit]
    if not repos:
        return "_No public repositories yet._"
    rows = ["| Repository | Language | ⭐ | Last push |", "|---|---|---|---|"]
    for r in repos:
        rows.append(
            f"| [{esc(r['name'])}]({r['html_url']}) | {esc(r['language'] or '—')} "
            f"| {r['stargazers_count']} | {ago(r['pushed_at'])} |"
        )
    return "\n".join(rows)


def replace(text, key, body):
    pattern = re.compile(rf"(<!--{key}:START-->)(.*?)(<!--{key}:END-->)", re.S)
    if not pattern.search(text):
        print(f"warning: marker {key} not found", file=sys.stderr)
        return text
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(3)}", text)


def safe(fn, fallback):
    try:
        return fn()
    except Exception as exc:  # network/API failures must not wipe a section
        print(f"warning: {fn.__name__} failed: {exc}", file=sys.stderr)
        return fallback


def main():
    text = README.read_text(encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = replace(text, "FOCUS", render_focus())
    for key, fn in (("ACTIVITY", render_activity), ("REPOS", render_repos)):
        body = safe(fn, None)
        if body is not None:
            text = replace(text, key, body)
    text = replace(text, "UPDATED", f"<sub>Last updated: {stamp}</sub>")
    README.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
