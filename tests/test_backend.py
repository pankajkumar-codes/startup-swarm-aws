"""The aws backend: S3 mirror, DynamoDB state, and a full pipeline run on both."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from startup_swarm.artifact_bus import ArtifactBus
from startup_swarm.config import Settings
from startup_swarm.llm.mock import MockClient, MockResponder
from startup_swarm.pipeline import StartupPipeline
from startup_swarm.state_store import LocalStateStore

from startup_swarm_aws import AWSBackend, DynamoDBStateStore, S3Mirror
from tests.fakes import FakeDynamo, FakeS3

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(REPO, "config.yaml")
ENV = {"S3_ARTIFACT_BUCKET": "bucket-beta", "DYNAMODB_STATE_TABLE": "table-beta"}


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="swarm-aws-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestS3Mirror(TempDir):
    def test_round_trip_with_pagination_and_encryption(self):
        s3 = FakeS3()
        bus = ArtifactBus(os.path.join(self.tmp, "a"), mirror=S3Mirror("b", "proj", client=s3))
        for name in ("01_BRD.md", "03_HLD.md", "reviews/03_HLD.md.json"):
            bus.write_artifact(name, f"# {name}", "staff_swe")
        self.assertIn(("b", "proj/reviews/03_HLD.md.json"), s3.objects)
        self.assertTrue(all(c["ServerSideEncryption"] == "AES256" for c in s3.put_calls))

        fresh = ArtifactBus(os.path.join(self.tmp, "b"), mirror=S3Mirror("b", "proj", client=s3))
        self.assertGreater(fresh.pull(), 4)  # docs + history + metadata, across pages
        self.assertEqual(fresh.read_artifact("reviews/03_HLD.md.json"), "# reviews/03_HLD.md.json")
        self.assertEqual(fresh.list_artifacts()["03_HLD.md"]["author"], "staff_swe")
        self.assertEqual(S3Mirror("b", "proj", client=s3).describe(), "s3://b/proj/")

    def test_rejects_unsafe_keys_and_empty_bucket(self):
        with self.assertRaises(ValueError):
            S3Mirror("b", "proj", client=FakeS3()).put("../x", b"")
        with self.assertRaises(ValueError):
            S3Mirror("", "proj", client=FakeS3())


class TestDynamoDBState(unittest.TestCase):
    def test_gates_phases_meta_and_pagination(self):
        ddb = FakeDynamo()
        store = DynamoDBStateStore("t", "proj", client=ddb)
        self.assertFalse(store.gate_approved("ceo"))
        store.set_gate("ceo", "APPROVED", "ceo", "ok")
        for i in range(5):
            store.set_phase(f"p{i}", "DONE")
        store.set_meta("idea", {"text": "x"})
        self.assertTrue(store.gate_approved("ceo"))
        snap = store.snapshot()
        self.assertEqual(len(snap["phases"]), 5)
        self.assertEqual(snap["meta"]["idea"]["text"], "x")
        # projects are isolated
        self.assertFalse(DynamoDBStateStore("t", "other", client=ddb).gate_approved("ceo"))


class TestAWSBackend(TempDir):
    def settings(self):
        return Settings.load(CONFIG, "beta", provider="bedrock")

    def test_uses_env_resources(self):
        with mock.patch.dict(os.environ, ENV):
            backend = AWSBackend(s3_client=FakeS3(), dynamodb_client=FakeDynamo())
            self.assertIsInstance(backend.make_state(self.settings(), "p", self.tmp), DynamoDBStateStore)
            self.assertEqual(backend.make_mirror(self.settings(), "p").describe(), "s3://bucket-beta/p/")

    def test_partial_and_missing_config(self):
        backend = AWSBackend(s3_client=FakeS3(), dynamodb_client=FakeDynamo())
        with mock.patch.dict(os.environ, {"S3_ARTIFACT_BUCKET": "only-bucket"}):
            self.assertIsInstance(backend.make_state(self.settings(), "p", self.tmp), LocalStateStore)
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in ENV:
                os.environ.pop(key, None)
            with self.assertRaisesRegex(ValueError, "S3_ARTIFACT_BUCKET"):
                backend.make_state(self.settings(), "p", self.tmp)

    def test_full_pipeline_on_aws_backend_resumes_on_a_fresh_host(self):
        s3, ddb = FakeS3(), FakeDynamo()

        def build(workspace):
            return StartupPipeline.build(
                stage="beta",
                config_path=CONFIG,
                project="demo",
                workspace=workspace,
                provider="bedrock",
                client=MockClient(responder=MockResponder()),
                backend_impl=AWSBackend(s3_client=s3, dynamodb_client=ddb),
            )

        with mock.patch.dict(os.environ, ENV):
            first = build(os.path.join(self.tmp, "host1"))
            self.assertEqual(first.run("Test idea").status, "COMPLETED")
            self.assertTrue(first.state.gate_approved("ceo"))
            self.assertIn(("bucket-beta", "demo/03_HLD.md"), s3.objects)
            self.assertIn(("bucket-beta", "demo/generated_project/src/app/core.py"), s3.objects)

            # a second host with an empty disk sees the same project and does no new work
            second = build(os.path.join(self.tmp, "host2"))
            outcome = second.run()
            self.assertEqual(outcome.status, "COMPLETED")
            self.assertEqual(second.client.usage.calls, 0)
            self.assertTrue(second.bus.exists("04_LLD.md"))


if __name__ == "__main__":
    unittest.main()
