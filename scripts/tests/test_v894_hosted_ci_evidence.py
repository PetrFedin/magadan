"""Synthetic GitHub API fixtures: never proof that actual hosted CI ran."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v894_hosted_ci_evidence import AuditRejected, POLICY, inspect_hosted_runs

SHA = "9" * 40
REPO = "PetrFedin/magadan"
BRANCH = "feature/v89-provenance-and-load-reconciliation"
IDS = {"v89": 101, "full": 102, "unified": 103}


def fixture():
    snapshots = {}
    for scope, policy in POLICY.items():
        run_id = IDS[scope]
        url = f"/repos/{REPO}/actions/runs/{run_id}"
        snapshots[url] = {
            "id": run_id, "head_sha": SHA, "head_branch": BRANCH,
            "path": policy["path"], "event": "pull_request",
            "status": "completed", "conclusion": "success",
        }
        jobs = []
        for group, number in policy["jobs"].items():
            for part in range(number):
                name = group + (f" ({part + 1})" if number > 1 else "")
                jobs.append({
                    "id": run_id * 100 + len(jobs) + 1,
                    "run_id": run_id, "head_sha": SHA,
                    "name": name, "runner_id": 1234,
                    "status": "completed", "conclusion": "success",
                    "steps": [{"name": "Execute", "status": "completed", "conclusion": "success"}],
                })
        for index, step in enumerate(policy["steps"]):
            jobs[index % len(jobs)]["steps"].append({
                "name": step, "status": "completed", "conclusion": "success",
            })
        snapshots[url + "/jobs?per_page=100&page=1"] = {"total_count": len(jobs), "jobs": jobs}
    return snapshots


class HostedCIFailClosedTest(unittest.TestCase):
    def audit(self, snapshots, runs=None, sha=SHA, branch=BRANCH):
        def fetch(path):
            if path not in snapshots:
                raise AuditRejected("UNEXPECTED_API_PATH")
            return snapshots[path]
        return inspect_hosted_runs(fetch, REPO, sha, branch, IDS if runs is None else runs)

    def test_valid_three_workflow_metadata_is_lab_only(self):
        result = self.audit(fixture())
        self.assertEqual(result["status"], "GITHUB_HOSTED_METADATA_SUCCESS_ONLY")
        self.assertEqual(len(result["workflows"]), 3)
        self.assertFalse(result["production_ready"])
        self.assertIsNone(result["real_available_capacity_mw"])
        self.assertFalse(result["corporate_oidc_mfa_verified"])
        self.assertEqual(result["receipt_sha256"], self.audit(fixture())["receipt_sha256"])

    def test_not_ready_if_runner_never_started(self):
        snapshots = fixture()
        snapshots[self.job_url("v89")]["jobs"][0]["runner_id"] = 0
        self.reject(snapshots, "NO_EXECUTED_SUCCESSFUL_RUNNER")

    def test_not_ready_if_job_has_no_steps(self):
        snapshots = fixture()
        snapshots[self.job_url("v89")]["jobs"][0]["steps"] = []
        self.reject(snapshots, "NO_EXECUTED_STEPS")

    def test_not_ready_if_step_skipped(self):
        snapshots = fixture()
        snapshots[self.job_url("v89")]["jobs"][0]["steps"][0]["conclusion"] = "skipped"
        self.reject(snapshots, "INCOMPLETE_FAILED_OR_SKIPPED_STEP")

    def test_not_ready_if_full_matrix_is_missing(self):
        snapshots = fixture()
        jobs = snapshots[self.job_url("full")]
        jobs["jobs"] = jobs["jobs"][:-1]
        jobs["total_count"] -= 1
        self.reject(snapshots, "REQUIRED_JOB_MATRIX_INCOMPLETE")

    def test_not_ready_if_job_has_mismatched_sha(self):
        snapshots = fixture()
        snapshots[self.job_url("v89")]["jobs"][0]["head_sha"] = "8" * 40
        self.reject(snapshots, "JOB_SOURCE_MISMATCH")

    def test_not_ready_if_run_has_mismatched_sha(self):
        snapshots = fixture()
        snapshots[self.run_url("unified")]["head_sha"] = "8" * 40
        self.reject(snapshots, "RUN_SOURCE_OR_WORKFLOW_MISMATCH")

    def test_not_ready_if_wrong_branch(self):
        self.reject(fixture(), "RUN_SOURCE_OR_WORKFLOW_MISMATCH", branch="main")

    def test_not_ready_if_missing_mandatory_test_action(self):
        snapshots = fixture()
        for job in snapshots[self.job_url("v89")]["jobs"]:
            job["steps"] = [x for x in job["steps"] if x["name"] != "Static production/HOLD invariants"]
        self.reject(snapshots, "REQUIRED_TEST_STEP_NOT_EXECUTED")

    def test_not_ready_if_duplicate_job_id(self):
        snapshots = fixture()
        jobs = snapshots[self.job_url("full")]["jobs"]
        jobs[1]["id"] = jobs[0]["id"]
        self.reject(snapshots, "DUPLICATE_JOB_ID")

    def test_not_ready_if_job_rows_are_truncated(self):
        snapshots = fixture()
        snapshots[self.job_url("v89")]["total_count"] += 1
        self.reject(snapshots, "UNEXPECTED_API_PATH")

    def test_not_ready_if_run_is_failure(self):
        snapshots = fixture()
        snapshots[self.run_url("v89")]["conclusion"] = "failure"
        self.reject(snapshots, "RUN_NOT_SUCCESSFUL")

    def test_not_ready_if_missing_entire_workflow(self):
        self.reject(fixture(), "EXACTLY_THREE_DISTINCT_RUNS_REQUIRED", runs={"v89": 101, "full": 102})

    def test_not_ready_if_run_ids_duplicate(self):
        self.reject(fixture(), "EXACTLY_THREE_DISTINCT_RUNS_REQUIRED", runs={"v89":101,"full":101,"unified":103})

    def test_not_ready_if_unknown_extra_job(self):
        snapshots = fixture()
        jobs = snapshots[self.job_url("v89")]
        jobs["jobs"][0]["name"] = "some-other-job"
        self.reject(snapshots, "UNKNOWN_JOB")

    def reject(self, snapshots, reason, **kwargs):
        with self.assertRaisesRegex(AuditRejected, reason):
            self.audit(snapshots, **kwargs)

    @staticmethod
    def run_url(scope):
        return f"/repos/{REPO}/actions/runs/{IDS[scope]}"

    @classmethod
    def job_url(cls, scope):
        return cls.run_url(scope) + "/jobs?per_page=100&page=1"


if __name__ == "__main__":
    unittest.main()
