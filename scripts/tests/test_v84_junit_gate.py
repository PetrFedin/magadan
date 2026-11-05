"""Unit checks for V8.4 JUnit acceptance; all data here are artificial."""
import tempfile
from pathlib import Path
import unittest

from scripts.v84_junit_gate import EvidenceError, evaluate

SHA = "a" * 40


def document(cases, *, declared=None, failures=0, errors=0, skipped=0):
    count = len(cases) if declared is None else declared
    return ('<testsuites><testsuite name="pytest" tests="%s" failures="%s" '
            'errors="%s" skipped="%s">%s</testsuite></testsuites>' %
            (count, failures, errors, skipped, "".join(cases)))


def case_xml(name="test_ok", body=""):
    return '<testcase classname="tests.fixture" name="%s">%s</testcase>' % (name, body)


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "report.xml"

    def check(self, content, **kw):
        self.path.write_text(content, encoding="utf-8")
        return evaluate(self.path, shard="lab",
                        min_passed=kw.pop("min_passed", 1),
                        max_skipped=kw.pop("max_skipped", 0),
                        actual_sha=kw.pop("actual_sha", SHA),
                        expected_sha=SHA, **kw)

    def test_success(self):
        r = self.check(document([case_xml()]), required_cases=("test_ok",))
        self.assertEqual(r["passed"], 1)
        self.assertFalse(r["production_ready"])

    def test_allowed_skip_is_explicit(self):
        r = self.check(document([case_xml(), case_xml("native",
               '<skipped message="PG17 absent"/>')], skipped=1), max_skipped=1)
        self.assertEqual((r["executed"], r["passed"], r["skipped"]), (2, 1, 1))
        self.assertEqual(r["status"], "SYNTHETIC_LAB_PASS_WITH_SKIPS")

    def test_unbudgeted_skip(self):
        with self.assertRaisesRegex(EvidenceError, "EXCESSIVE_SKIPS"):
            self.check(document([case_xml(), case_xml("native",
                       '<skipped message="blocked"/>')], skipped=1))

    def test_required_case_skipped(self):
        with self.assertRaisesRegex(EvidenceError, "REQUIRED_CASE_DID_NOT_PASS"):
            self.check(document([case_xml(), case_xml("critical",
                       '<skipped message="blocked"/>')], skipped=1),
                       max_skipped=1, required_cases=("critical",))

    def test_failed_case(self):
        with self.assertRaisesRegex(EvidenceError, "FAILED_OR_ERRORED"):
            self.check(document([case_xml(body='<failure message="bad"/>')], failures=1))

    def test_errored_case(self):
        with self.assertRaisesRegex(EvidenceError, "FAILED_OR_ERRORED"):
            self.check(document([case_xml(body='<error message="crash"/>')], errors=1))

    def test_inconsistent_test_count(self):
        with self.assertRaisesRegex(EvidenceError, "JUNIT_TEST_COUNT_MISMATCH"):
            self.check(document([case_xml()], declared=99))

    def test_inconsistent_skip_count(self):
        with self.assertRaisesRegex(EvidenceError, "JUNIT_DECLARED_OUTCOME_MISMATCH"):
            self.check(document([case_xml()], skipped=1))

    def test_empty_suite(self):
        with self.assertRaisesRegex(EvidenceError, "INSUFFICIENT_PASS_COUNT"):
            self.check(document([]))

    def test_corrupt_xml(self):
        with self.assertRaisesRegex(EvidenceError, "JUNIT_XML_MALFORMED"):
            self.check("<testsuite><testcase")

    def test_wrong_sha(self):
        with self.assertRaisesRegex(EvidenceError, "TESTED_SHA_DOES_NOT_MATCH_EXPECTED_SHA"):
            self.check(document([case_xml()]), actual_sha="b" * 40)

    def test_duplicate_identity(self):
        with self.assertRaisesRegex(EvidenceError, "DUPLICATE_TESTCASE_IDENTITY"):
            self.check(document([case_xml(), case_xml()]))

    def test_skip_without_reason(self):
        with self.assertRaisesRegex(EvidenceError, "SKIP_WITHOUT_EXPLANATION"):
            self.check(document([case_xml(), case_xml("native", "<skipped/>")], skipped=1),
                       max_skipped=1)

    def test_xfail_not_a_pass(self):
        with self.assertRaisesRegex(EvidenceError, "EXPECTED_FAILURE_NOT_A_PASS"):
            self.check(document([case_xml(), case_xml("x",
                       '<skipped type="pytest.xfail" message="expected"/>')], skipped=1),
                       max_skipped=1)

    def test_minimum_pass_requirement(self):
        with self.assertRaisesRegex(EvidenceError, "INSUFFICIENT_PASS_COUNT"):
            self.check(document([case_xml()]), min_passed=2)

    def test_empty_file(self):
        self.path.write_text("")
        with self.assertRaisesRegex(EvidenceError, "JUNIT_FILE_MISSING_OR_EMPTY"):
            evaluate(self.path, shard="lab", min_passed=1,
                     max_skipped=0, actual_sha=SHA, expected_sha=SHA)



    def test_nested_suite_aggregate_is_reconciled(self):
        xml = ('<testsuites tests="2" failures="0" errors="0" skipped="0">'
               '<testsuite tests="2"><testcase classname="cases" name="root"/>'
               '<testsuite tests="1"><testcase classname="cases" name="nested"/>'
               '</testsuite></testsuite></testsuites>')
        result = self.check(xml, min_passed=2)
        self.assertEqual(result["executed"], 2)

    def test_forged_parent_aggregate_cannot_be_green(self):
        xml = ('<testsuites tests="3"><testsuite tests="1">'
               '<testcase classname="cases" name="actual"/>'
               '</testsuite></testsuites>')
        with self.assertRaisesRegex(EvidenceError, "JUNIT_DECLARED_OUTCOME_MISMATCH"):
            self.check(xml)

    def test_direct_case_outside_suite_is_rejected(self):
        xml = ('<testsuites><testcase classname="outside" name="false_pass"/>'
               '<testsuite tests="1"><testcase classname="real" name="valid"/>'
               '</testsuite></testsuites>')
        with self.assertRaisesRegex(EvidenceError, "JUNIT_WRAPPER_UNEXPECTED_CHILD"):
            self.check(xml)

    def test_conflicting_outcomes_cannot_be_green(self):
        xml = document([case_xml("conflict",
                       '<failure message="f"/><skipped message="s"/>')],
                       failures=1, skipped=1)
        with self.assertRaisesRegex(EvidenceError, "JUNIT_CONFLICTING_TESTCASE_OUTCOME"):
            self.check(xml, max_skipped=1)

    def test_suite_without_declared_test_count_is_rejected(self):
        xml = ('<testsuites><testsuite><testcase classname="a" name="b"/>'
               '</testsuite></testsuites>')
        with self.assertRaisesRegex(EvidenceError, "JUNIT_TEST_COUNT_NOT_DECLARED"):
            self.check(xml)

    def test_unexpected_child_cannot_be_ignored(self):
        xml = ('<testsuites><testsuite tests="1"><untrusted-result/>'
               '<testcase classname="real" name="valid"/>'
               '</testsuite></testsuites>')
        with self.assertRaisesRegex(EvidenceError, "JUNIT_UNEXPECTED_SUITE_CHILD"):
            self.check(xml)

    def test_negative_count_is_rejected(self):
        xml = ('<testsuites><testsuite tests="-1">'
               '<testcase classname="a" name="b"/></testsuite></testsuites>')
        with self.assertRaisesRegex(EvidenceError, "JUNIT_DECLARED_OUTCOME_MISMATCH"):
            self.check(xml)


if __name__ == "__main__":
    unittest.main()
