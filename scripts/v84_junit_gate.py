"""Fail-closed JUnit acceptance for synthetic HydroKontur V8.4 regression.

No synthetic success may be interpreted as PG17, field, browser or production
acceptance. An absent, incomplete or inconsistent XML file is an error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

SHA40 = re.compile(r"^[0-9a-f]{40}$")


class EvidenceError(ValueError):
    """The offered evidence does not support the claimed result."""


def collect_verified_cases(root: ET.Element) -> list[ET.Element]:
    """Check all JUnit suite levels, rather than trusting leaf-only counts.

    Pytest normally emits testsuites > testsuite > testcase. Other JUnit
    producers may nest suites; every declared parent count must agree with
    the aggregate of its descendants. Unexpected structures fail closed.
    """
    if root.tag not in {"testsuites", "testsuite"}:
        raise EvidenceError("JUNIT_ROOT_UNEXPECTED")

    def check_count(node: ET.Element, key: str, actual: int,
                    mandatory: bool = False) -> None:
        if mandatory and key not in node.attrib:
            raise EvidenceError("JUNIT_TEST_COUNT_NOT_DECLARED")
        if key in node.attrib:
            try:
                declared = int(node.attrib[key])
            except (ValueError, TypeError) as exc:
                raise EvidenceError("JUNIT_INVALID_DECLARED_OUTCOME") from exc
            if declared < 0:
                raise EvidenceError("JUNIT_DECLARED_OUTCOME_MISMATCH:" + key)
            if declared != actual:
                if key == "tests" and node.tag == "testsuite":
                    raise EvidenceError("JUNIT_TEST_COUNT_MISMATCH")
                raise EvidenceError("JUNIT_DECLARED_OUTCOME_MISMATCH:" + key)

    def counters(cases: list[ET.Element]) -> dict[str, int]:
        return {
            "tests": len(cases),
            "failures": sum(t.find("failure") is not None for t in cases),
            "errors": sum(t.find("error") is not None for t in cases),
            "skipped": sum(t.find("skipped") is not None for t in cases),
        }

    def inspect_suite(suite: ET.Element) -> list[ET.Element]:
        if any(x.tag not in {"testcase", "testsuite", "properties",
                             "system-out", "system-err"} for x in suite):
            raise EvidenceError("JUNIT_UNEXPECTED_SUITE_CHILD")
        cases = list(suite.findall("testcase"))
        for child in suite.findall("testsuite"):
            cases.extend(inspect_suite(child))
        for key, actual in counters(cases).items():
            check_count(suite, key, actual, mandatory=(key == "tests"))
        return cases

    if root.tag == "testsuite":
        cases = inspect_suite(root)
    else:
        if any(child.tag != "testsuite" for child in root):
            raise EvidenceError("JUNIT_WRAPPER_UNEXPECTED_CHILD")
        cases = []
        for suite in root.findall("testsuite"):
            cases.extend(inspect_suite(suite))
        for key, actual in counters(cases).items():
            check_count(root, key, actual)

    for case in cases:
        if sum(case.find(tag) is not None for tag in
               ("failure", "error", "skipped")) > 1:
            raise EvidenceError("JUNIT_CONFLICTING_TESTCASE_OUTCOME")
        if any(child.tag not in {"failure", "error", "skipped",
                                 "properties", "system-out", "system-err"}
               for child in case):
            raise EvidenceError("JUNIT_UNEXPECTED_CASE_CHILD")
    if not cases:
        raise EvidenceError("INSUFFICIENT_PASS_COUNT")
    return cases


def evaluate(junit: Path, *, shard: str, min_passed: int,
             max_skipped: int, actual_sha: str, expected_sha: str,
             required_cases: tuple[str, ...] = ()) -> dict:
    if not SHA40.fullmatch(actual_sha) or not SHA40.fullmatch(expected_sha):
        raise EvidenceError("INVALID_COMMIT_SHA")
    if actual_sha != expected_sha:
        raise EvidenceError("TESTED_SHA_DOES_NOT_MATCH_EXPECTED_SHA")
    if min_passed < 1 or max_skipped < 0:
        raise EvidenceError("INVALID_TEST_COUNT_POLICY")
    if not junit.is_file() or junit.stat().st_size == 0:
        raise EvidenceError("JUNIT_FILE_MISSING_OR_EMPTY")
    if junit.stat().st_size > 20_000_000:
        raise EvidenceError("JUNIT_FILE_TOO_LARGE")
    raw = junit.read_bytes()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise EvidenceError("JUNIT_XML_MALFORMED") from exc
    testcases = collect_verified_cases(root)
    identities = [(t.attrib.get("classname"), t.attrib.get("name"))
                  for t in testcases]
    if any(not cls or not name for cls, name in identities):
        raise EvidenceError("JUNIT_TESTCASE_IDENTITY_MISSING")
    if len(set(identities)) != len(identities):
        raise EvidenceError("DUPLICATE_TESTCASE_IDENTITY")
    failed = [t for t in testcases
              if t.find("failure") is not None or t.find("error") is not None]
    if failed:
        raise EvidenceError("FAILED_OR_ERRORED_CASES_PRESENT:" +
                            ",".join(t.attrib["name"] for t in failed[:5]))
    skipped = [t for t in testcases if t.find("skipped") is not None]
    skipped_receipt = []
    for case in skipped:
        item = case.find("skipped")
        reason = (item.attrib.get("message", "") + " " +
                  (item.text or "")).strip()
        if not reason:
            raise EvidenceError("SKIP_WITHOUT_EXPLANATION")
        if "xfail" in (reason + " " + item.attrib.get("type", "")).lower():
            raise EvidenceError("EXPECTED_FAILURE_NOT_A_PASS")
        skipped_receipt.append({
            "case": case.attrib["classname"] + "::" + case.attrib["name"],
            "reason": reason[:300],
        })
    passed = len(testcases) - len(skipped)
    if passed < min_passed:
        raise EvidenceError("INSUFFICIENT_PASS_COUNT")
    if len(skipped) > max_skipped:
        raise EvidenceError("EXCESSIVE_SKIPS")
    passed_names = {t.attrib["name"] for t in testcases if t not in skipped}
    missing = [name for name in required_cases if name not in passed_names]
    if missing:
        raise EvidenceError("REQUIRED_CASE_DID_NOT_PASS:" + ",".join(missing))
    return {
        "shard": shard,
        "status": "SYNTHETIC_LAB_PASS_WITH_SKIPS" if skipped else "SYNTHETIC_LAB_PASS",
        "commit_sha": actual_sha,
        "junit_sha256": hashlib.sha256(raw).hexdigest(),
        "executed": len(testcases),
        "passed": passed,
        "skipped": len(skipped),
        "skip_details": skipped_receipt,
        "native_postgresql17_accepted": False,
        "authenticated_browser_e2e_accepted": False,
        "field_data_accepted": False,
        "production_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--shard", required=True)
    parser.add_argument("--min-passed", type=int, required=True)
    parser.add_argument("--max-skipped", type=int, default=0)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--actual-sha", required=True)
    parser.add_argument("--require-case", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        receipt = evaluate(
            args.junit, shard=args.shard, min_passed=args.min_passed,
            max_skipped=args.max_skipped, expected_sha=args.expected_sha,
            actual_sha=args.actual_sha, required_cases=tuple(args.require_case))
    except (EvidenceError, OSError) as exc:
        print("EVIDENCE_GATE_BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(f"### {receipt['shard']} - {receipt['status']}\n\n")
            out.write(f"- SHA: {receipt['commit_sha']}\n")
            out.write(f"- Executed/passed/skipped: {receipt['executed']} / "
                      f"{receipt['passed']} / {receipt['skipped']}\n")
            out.write(f"- JUnit SHA-256: {receipt['junit_sha256']}\n")
            for skip in receipt["skip_details"]:
                out.write(f"- Skip {skip['case']}: "
                          f"{skip['reason'].replace(chr(10), ' ')}\n")
            out.write("- NO native PG17, real browser E2E, field or production acceptance.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
