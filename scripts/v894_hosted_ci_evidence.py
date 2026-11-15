#!/usr/bin/env python3
"""Read-only, fail-closed GitHub-hosted synthetic CI metadata gate.

This does not authenticate test artifacts, certify corporate MFA, grant source
rights, or approve an industrial or financial release. A GitHub bearer token is
required to read private repository metadata; it is never written to receipts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")

# These names are taken from repository workflows. Matrix jobs are grouped by
# their prefix followed by " (...)". The required names and actions must be
# updated deliberately if the workflow topology changes.
POLICY = {
    "v89": {
        "path": ".github/workflows/v89-source-quarantine.yml",
        "jobs": {"v89-source-rights-hourly-grain-dedup": 1},
        "steps": (
            "Execute source quarantine and load dedup regression",
            "Static production/HOLD invariants",
            "Validate embedded Python syntax in both CI release gates",
            "Verify hosted CI metadata gate with negative synthetic fixtures",
        ),
    },
    "full": {
        "path": ".github/workflows/v84-full-regression.yml",
        "jobs": {
            "provenance-and-parser": 1,
            "python-regression": 4,
            "monolithic-python-order-probe": 1,
            "javascript": 1,
            "engineering-synthetic": 1,
            "chromium-browser-lab": 1,
            "final-check": 1,
        },
        "steps": (
            "Original immutable 452-file baseline and exact checkout",
            "Embedded release workflow Python compile gate",
            "Hosted evidence gate negative fixture regression",
            "Execute synthetic shard with timeout and fail-closed JUnit gate",
            "All non-native Python tests in ONE pytest process (including seed)",
            "Legacy JS and current UI syntax",
            "Reproduce independent synthetic route, integral and 60 branches",
            "Real authenticated Chromium role journeys and responsive widths",
            "Incomplete, failed or skipped jobs cannot be GREEN",
        ),
    },
    "unified": {
        "path": ".github/workflows/v87-unified-staging.yml",
        "jobs": {"unified-pg17-oidc-chromium-backup": 1},
        "steps": (
            "Real HTTP synthetic OIDC + actual PG17 + six independent Chromium sessions",
            "Recheck native PostgreSQL17 RLS tenant rollback and concurrency on same database",
            "Real PG17 logical backup restore and RLS policy parity",
        ),
    },
}


class AuditRejected(ValueError):
    """A proof is missing, ambiguous, or inconsistent with release policy."""


def _positive_id(value: object) -> bool:
    return type(value) is int and value > 0


def _group(name: str, required: dict[str, int]) -> str | None:
    for key in required:
        if name == key or (name.startswith(key + " (") and name.endswith(")")):
            return key
    return None


def inspect_hosted_runs(fetch, repo: str, sha: str, branch: str, run_ids: dict[str, int], pr_number: int = 15) -> dict:
    """Verify *live API metadata* on one exact commit, not underlying artifacts."""
    if not REPO_RE.fullmatch(repo) or not SHA_RE.fullmatch(sha) or not branch.strip():
        raise AuditRejected("INVALID_REPOSITORY_COMMIT_OR_BRANCH")
    if not _positive_id(pr_number):
        raise AuditRejected("INVALID_PR_NUMBER")

    def verify_pr_head() -> None:
        pr = fetch(f"/repos/{repo}/pulls/{pr_number}")
        if not isinstance(pr, dict) or pr.get("number") != pr_number:
            raise AuditRejected("PR_ID_MISMATCH")
        head = pr.get("head") or {}
        base = pr.get("base") or {}
        if (pr.get("state") != "open" or pr.get("draft") is not True
                or pr.get("merged") is not False
                or head.get("sha") != sha or head.get("ref") != branch
                or (head.get("repo") or {}).get("full_name") != repo
                or base.get("ref") != "feature/v84-full-regression-gates"):
            raise AuditRejected("PR_HEAD_BASE_OR_DRAFT_CHANGED")

    verify_pr_head()
    if set(run_ids) != set(POLICY) or len(set(run_ids.values())) != len(POLICY):
        raise AuditRejected("EXACTLY_THREE_DISTINCT_RUNS_REQUIRED")
    if not all(_positive_id(x) for x in run_ids.values()):
        raise AuditRejected("INVALID_RUN_ID")
    receipts = []
    for scope, policy in POLICY.items():
        run_id = run_ids[scope]
        prefix = f"/repos/{repo}/actions/runs/{run_id}"
        run = fetch(prefix)
        if not isinstance(run, dict) or run.get("id") != run_id:
            raise AuditRejected(f"{scope}:RUN_ID_MISMATCH")
        if (run.get("head_sha") != sha or run.get("head_branch") != branch
                or run.get("path") != policy["path"]):
            raise AuditRejected(f"{scope}:RUN_SOURCE_OR_WORKFLOW_MISMATCH")
        if run.get("event") not in ("pull_request", "workflow_dispatch"):
            raise AuditRejected(f"{scope}:UNEXPECTED_RUN_EVENT")
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            raise AuditRejected(f"{scope}:RUN_NOT_SUCCESSFUL")
        job_rows = []
        page = 1
        while True:
            data = fetch(prefix + f"/jobs?per_page=100&page={page}")
            if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
                raise AuditRejected(f"{scope}:JOB_RESPONSE_INVALID")
            total = data.get("total_count")
            if type(total) is not int or total < 1 or total > 2000:
                raise AuditRejected(f"{scope}:JOB_TOTAL_INVALID")
            if job_rows and total != expected_total:
                raise AuditRejected(f"{scope}:JOB_TOTAL_CHANGED")
            expected_total = total
            job_rows.extend(data["jobs"])
            if len(job_rows) >= expected_total:
                if len(job_rows) != expected_total:
                    raise AuditRejected(f"{scope}:JOB_PAGE_OVERFLOW")
                break
            if not data["jobs"] or page >= 20:
                raise AuditRejected(f"{scope}:INCOMPLETE_JOB_PAGINATION")
            page += 1
        seen_job_ids: set[int] = set()
        groups: Counter[str] = Counter()
        actions: set[str] = set()
        step_count = 0
        for job in job_rows:
            if not isinstance(job, dict) or not _positive_id(job.get("id")):
                raise AuditRejected(f"{scope}:INVALID_JOB_ID")
            job_id = job["id"]
            if job_id in seen_job_ids:
                raise AuditRejected(f"{scope}:DUPLICATE_JOB_ID")
            seen_job_ids.add(job_id)
            if job.get("run_id") != run_id or job.get("head_sha") != sha:
                raise AuditRejected(f"{scope}:JOB_SOURCE_MISMATCH")
            group = _group(str(job.get("name", "")), policy["jobs"])
            if group is None:
                raise AuditRejected(f"{scope}:UNKNOWN_JOB")
            groups[group] += 1
            if (job.get("status") != "completed" or job.get("conclusion") != "success"
                    or not _positive_id(job.get("runner_id"))):
                raise AuditRejected(f"{scope}:NO_EXECUTED_SUCCESSFUL_RUNNER")
            steps = job.get("steps")
            if not isinstance(steps, list) or not steps:
                raise AuditRejected(f"{scope}:NO_EXECUTED_STEPS")
            for step in steps:
                if (not isinstance(step, dict) or not step.get("name")
                        or step.get("status") != "completed"
                        or step.get("conclusion") != "success"):
                    raise AuditRejected(f"{scope}:INCOMPLETE_FAILED_OR_SKIPPED_STEP")
                actions.add(step["name"])
                step_count += 1
        if dict(groups) != policy["jobs"]:
            raise AuditRejected(f"{scope}:REQUIRED_JOB_MATRIX_INCOMPLETE")
        missing = set(policy["steps"]) - actions
        if missing:
            raise AuditRejected(f"{scope}:REQUIRED_TEST_STEP_NOT_EXECUTED")
        receipts.append({
            "scope": scope,
            "run_id": run_id,
            "workflow_path": policy["path"],
            "job_count": len(job_rows),
            "executed_step_count": step_count,
            "run_url": f"https://github.com/{repo}/actions/runs/{run_id}",
        })
    verify_pr_head()  # Fail if the draft PR advanced during the audit.
    report = {
        "status": "GITHUB_HOSTED_METADATA_SUCCESS_ONLY",
        "draft_pr_number": pr_number,
        "repository": repo,
        "source_sha": sha,
        "source_branch": branch,
        "workflows": receipts,
        "test_artifact_contents_independently_verified": False,
        "corporate_oidc_mfa_verified": False,
        "external_worm_verified": False,
        "real_source_rights_verified": False,
        "real_available_capacity_mw": None,
        "investment_decision": "HOLD",
        "production_ready": False,
    }
    blob = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    report["receipt_sha256"] = hashlib.sha256(blob).hexdigest()
    return report


def github_fetcher(token: str):
    if not token.strip():
        raise AuditRejected("GITHUB_READ_TOKEN_REQUIRED")

    def fetch(path: str):
        request = Request(
            "https://api.github.com" + path,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "HydroKontur-read-only-ci-audit",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except (URLError, OSError, ValueError) as exc:
            raise AuditRejected("GITHUB_API_UNAVAILABLE_OR_INVALID") from exc
    return fetch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="PetrFedin/magadan")
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch", default="feature/v89-provenance-and-load-reconciliation")
    parser.add_argument("--pr", type=int, default=15)
    parser.add_argument("--run", action="append", default=[], help="scope=run_id (v89/full/unified)")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        ids = {}
        for item in args.run:
            name, sep, value = item.partition("=")
            if not sep or name in ids or not value.isdecimal():
                raise AuditRejected("INVALID_OR_DUPLICATE_RUN_ARGUMENT")
            ids[name] = int(value)
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
        report = inspect_hosted_runs(github_fetcher(token), args.repo, args.sha, args.branch, ids, args.pr)
        payload = json.dumps(report, sort_keys=True, indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(args.out, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
        else:
            sys.stdout.write(payload)
        return 0
    except (AuditRejected, OSError) as exc:
        # No auth token or HTTP error bodies are ever included in error output.
        message = str(exc) if isinstance(exc, AuditRejected) else "RECEIPT_WRITE_REJECTED"
        print("HOSTED_CI_HOLD:" + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
