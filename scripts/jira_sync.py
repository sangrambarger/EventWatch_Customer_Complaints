#!/usr/bin/env python3
"""Fetch EAO Jira tickets compactly and diff them against the tracker.

Why this exists: pulling these tickets through a conversational tool returns ~2600
characters per ticket (self links, four avatar URLs per user, statusCategory objects,
issuetype metadata) where ~110 characters are actually useful -- roughly 24x
overhead, and 31 tickets was enough to blow a context window once. This script
requests only the fields it needs and prints one line per ticket, then narrows the
list to just the rows a human or model actually has to judge.

The division of labour this enables:
  this script   fetch, match on exact Jira Key, and report the delta
  a person/LLM  decide the ambiguous cases -- a ticket whose title names a
                different entity than the tracker row ("Dana Holding Corporation"
                vs "Dana Incorporated"), a title with no entity at all ("Event
                title change request"), or which customer a prose description is
                really about (Micron, Honeywell, GM and Liberty Blume were all
                named only in body text, never in a field)

Usage:
  python3 scripts/jira_sync.py                  # summary + unlinked tickets
  python3 scripts/jira_sync.py --describe EAO-7 EAO-9   # bodies for named tickets
  python3 scripts/jira_sync.py --all            # every ticket, one line each

Credentials (same secrets the Jira Lookup page uses), via env or .streamlit/secrets.toml:
  JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO / "customer_tracker.csv"
PROJECT = "EAO"


def load_credentials() -> tuple[str, str, str] | None:
    base = os.environ.get("JIRA_BASE_URL")
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN")
    secrets = REPO / ".streamlit" / "secrets.toml"
    if not (base and email and token) and secrets.exists():
        text = secrets.read_text()
        found = {}
        for key in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"):
            m = re.search(rf'^{key}\s*=\s*"([^"]+)"', text, re.M)
            if m:
                found[key] = m.group(1)
        base = base or found.get("JIRA_BASE_URL")
        email = email or found.get("JIRA_EMAIL")
        token = token or found.get("JIRA_API_TOKEN")
    if base and email and token:
        return base.rstrip("/"), email, token
    return None


def fetch_issues(creds: tuple[str, str, str], fields: list[str]) -> list[dict]:
    """One paged JQL call, only the requested fields."""
    base, email, token = creds
    issues: list[dict] = []
    start = 0
    while True:
        resp = requests.get(
            f"{base}/rest/api/3/search",
            params={"jql": f"project = {PROJECT} ORDER BY created ASC",
                    "fields": ",".join(fields), "maxResults": 100, "startAt": start},
            auth=(email, token), timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        issues.extend(payload.get("issues", []))
        start += len(payload.get("issues", []))
        if start >= payload.get("total", 0) or not payload.get("issues"):
            break
    return issues


def adf_to_text(node) -> str:
    """Flatten an Atlassian Document Format body to plain text."""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(n) for n in node)
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        inner = adf_to_text(node.get("content", []))
        return inner + ("\n" if node.get("type") in {"paragraph", "heading", "listItem"} else "")
    return ""


def one_line(issue: dict) -> str:
    f = issue.get("fields", {})
    status = (f.get("status") or {}).get("name", "?")
    created = (f.get("created") or "")[:10]
    summary = re.sub(r"\s+", " ", f.get("summary") or "").strip()
    return f"{issue['key']}\t{status}\t{created}\t{summary[:120]}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--all", action="store_true", help="print every ticket, not just unlinked ones")
    ap.add_argument("--describe", nargs="+", metavar="KEY",
                    help="print the body text of specific tickets (for judging customer/intent)")
    args = ap.parse_args()

    creds = load_credentials()
    if not creds:
        print("Not configured. Set JIRA_BASE_URL, JIRA_EMAIL and JIRA_API_TOKEN as environment\n"
              "variables or in .streamlit/secrets.toml. Generate the token from the Atlassian\n"
              "account that should run lookups: account settings -> Security -> API tokens.",
              file=sys.stderr)
        return 2

    if args.describe:
        wanted = {k.upper() for k in args.describe}
        for issue in fetch_issues(creds, ["summary", "description"]):
            if issue["key"].upper() not in wanted:
                continue
            body = adf_to_text(issue["fields"].get("description") or {})
            body = re.sub(r"\n{3,}", "\n\n", body).strip()
            print(f"\n=== {issue['key']}: {issue['fields'].get('summary')}\n{body}")
        return 0

    issues = fetch_issues(creds, ["summary", "status", "created"])
    by_key = {i["key"].upper(): i for i in issues}

    df = pd.read_csv(args.csv, dtype=str, keep_default_na=False)
    tracked = {k.strip().upper() for k in df.get("Jira Key", pd.Series(dtype=str)) if k.strip()}

    unlinked = [by_key[k] for k in sorted(by_key) if k not in tracked]
    stale = sorted(tracked - set(by_key))

    print(f"{PROJECT}: {len(issues)} ticket(s) in Jira, {len(tracked)} distinct key(s) in the tracker")
    if args.all:
        print("\nkey\tstatus\tcreated\tsummary")
        for k in sorted(by_key):
            print(one_line(by_key[k]))
        return 0

    if unlinked:
        print(f"\n{len(unlinked)} ticket(s) with no tracker row — each needs a customer, a classification "
              f"and a decision on whether it duplicates an existing row:")
        print("key\tstatus\tcreated\tsummary")
        for issue in unlinked:
            print(one_line(issue))
        print("\nRun with --describe KEY ... for the bodies; the customer is often only in prose.")
    else:
        print("\nEvery Jira ticket has a tracker row.")

    if stale:
        print(f"\n{len(stale)} tracker key(s) not found in {PROJECT} (moved, deleted, or another project): {stale}")

    if "Issue Type" in df.columns:
        complaints = df[df["Issue Type"] == "Complaint"]
        missing = complaints[complaints.get("Jira Key", pd.Series(dtype=str)).str.strip() == ""]
        print(f"\n{len(missing)} of {len(complaints)} complaint row(s) carry no Jira Key.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
