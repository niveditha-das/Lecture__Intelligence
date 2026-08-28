"""Evaluate a running API and optionally fail the build.

    python -m app.evaluation.runner --label "hybrid+rerank"
    python -m app.evaluation.runner --label "no rerank" --no-rerank --retrieval-only
    python -m app.evaluation.runner --retrieval-only --fail-under recall_at_k=0.80

This is a client, not a worker. The evaluation itself runs inside the API
process (see app/routers/evaluation.py) because loading a second copy of the
embedding model in a separate interpreter exhausts memory under Docker Desktop.
Keeping the CLI thin also means CI evaluates the same container it would deploy.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_API = os.environ.get("API_URL", "http://localhost:8000")


def post(url: str, payload: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def markdown_table(metrics: dict) -> str:
    lines = ["| metric | value |", "|---|---|"]
    for key, val in metrics.items():
        lines.append(f"| {key} | {val} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--course-id")
    ap.add_argument("--label", default="run")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--retrieval-only", action="store_true",
                    help="skip generation: fast, free, still catches most regressions")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--fail-under", action="append", default=[], metavar="metric=value",
                    help="CI gate, repeatable, e.g. --fail-under recall_at_k=0.8")
    args = ap.parse_args()

    payload = {
        "label": args.label,
        "course_id": args.course_id,
        "k": args.k,
        "rerank": not args.no_rerank,
        "generate": not args.retrieval_only,
        "limit": args.limit,
    }

    try:
        res = post(f"{args.api}/eval/run", payload, args.timeout)
    except urllib.error.URLError as exc:
        print(f"cannot reach the API at {args.api}: {exc}", file=sys.stderr)
        print("start it with `make up` and wait for /health", file=sys.stderr)
        return 2

    if res.get("error"):
        print(res["error"], file=sys.stderr)
        return 2

    metrics = res["metrics"]
    print(f"\n### {args.label}  ({res.get('git_sha') or 'no-sha'})\n")
    print(markdown_table(metrics))
    print(f"\nconfig: {json.dumps(res['config'])}")
    print(f"run_id: {res['run_id']}")

    failed = False
    for gate in args.fail_under:
        name, _, target = gate.partition("=")
        got = metrics.get(name)
        if got is None or got < float(target):
            print(f"FAIL {name}={got} < {target}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
