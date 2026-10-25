"""AgentCore entrypoint and the script that stages it into an AgentCore CLI project."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestHandler(unittest.TestCase):
    def tearDown(self):
        shutil.rmtree(os.path.join(tempfile.gettempdir(), "swarm"), ignore_errors=True)

    def test_actions_in_mock_mode(self):
        from startup_swarm_aws import agentcore_main

        env = {"SWARM_MOCK": "1", "SWARM_CONFIG": os.path.join(REPO, "config.yaml"), "STAGE": "beta"}
        with mock.patch.dict(os.environ, env):
            res = agentcore_main.handle({"action": "run", "project": "ac-test", "idea": "x"})
            self.assertEqual(res["status"], "COMPLETED", res)
            self.assertEqual(agentcore_main.handle({"action": "status", "project": "ac-test"})["progress_pct"], 100)
            self.assertEqual(agentcore_main.handle({"action": "task", "project": "ac-test"})["status"], "FAILED")
            self.assertEqual(agentcore_main.handle({"action": "nope"})["status"], "FAILED")


class TestPrepareAgentCore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="swarm-ac-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_upsert_runtime_entry_and_stage_code(self):
        proj = os.path.join(self.tmp, "SwarmRuntime")
        os.makedirs(os.path.join(proj, "agentcore"))
        with open(os.path.join(proj, "agentcore", "agentcore.json"), "w") as fh:
            json.dump({"name": "SwarmRuntime", "runtimes": [{"name": "agent", "build": "CodeZip"}]}, fh)
        outputs = os.path.join(self.tmp, "out.json")
        with open(outputs, "w") as fh:
            json.dump(
                {
                    "StartupSwarm-Beta": {
                        "ArtifactBucketName": "b",
                        "StateTableName": "t",
                        "AgentRuntimeRoleArn": "arn:aws:iam::1:role/r",
                    }
                },
                fh,
            )
        cmd = [sys.executable, os.path.join(REPO, "scripts", "prepare_agentcore.py")]
        cmd += ["--stage", "beta", "--project-dir", proj, "--outputs", outputs]
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
        for _ in range(2):  # idempotent
            subprocess.run(cmd, check=True, capture_output=True, env=env)

        spec = json.load(open(os.path.join(proj, "agentcore", "agentcore.json")))
        self.assertEqual([r["name"] for r in spec["runtimes"]], ["agent", "startup_swarm_beta"])
        rt = spec["runtimes"][1]
        self.assertEqual(rt["executionRoleArn"], "arn:aws:iam::1:role/r")
        env_vars = {e["name"]: e["value"] for e in rt["envVars"]}
        self.assertEqual(env_vars["S3_ARTIFACT_BUCKET"], "b")
        self.assertEqual(env_vars["SWARM_PROVIDER"], "bedrock")

        code = os.path.join(proj, "app", "startup_swarm_beta")
        for f in (
            "main.py",
            "pyproject.toml",
            "config.yaml",
            "startup_swarm/pipeline.py",
            "startup_swarm/templates/03_HLD_TEMPLATE.md",
            "startup_swarm_aws/agentcore_main.py",
        ):
            self.assertTrue(os.path.exists(os.path.join(code, f)), f)

    def test_missing_stack_output_fails(self):
        proj = os.path.join(self.tmp, "P")
        os.makedirs(os.path.join(proj, "agentcore"))
        with open(os.path.join(proj, "agentcore", "agentcore.json"), "w") as fh:
            json.dump({}, fh)
        outputs = os.path.join(self.tmp, "out.json")
        with open(outputs, "w") as fh:
            json.dump({"Other": {}}, fh)
        cmd = [sys.executable, os.path.join(REPO, "scripts", "prepare_agentcore.py")]
        cmd += ["--stage", "beta", "--project-dir", proj, "--outputs", outputs]
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
        res = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("StartupSwarm-Beta", res.stderr + res.stdout)


if __name__ == "__main__":
    unittest.main()
