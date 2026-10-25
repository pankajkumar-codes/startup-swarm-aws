"""The ``aws`` backend for startup-swarm, registered through an entry point.

Where it finds the stage's resources (environment variables win over config.yaml):

    S3_ARTIFACT_BUCKET    or  stages.<stage>.s3_artifact_bucket
    DYNAMODB_STATE_TABLE  or  stages.<stage>.dynamodb_state_table
    SWARM_REGION          or  stages.<stage>.region  /  provider.region

Values come from the CDK stack outputs (ArtifactBucketName, StateTableName).
If the bucket is not set, documents stay on local disk; if the table is not set,
state stays in the local state.json. Both missing is an error, since then the
backend would do nothing.
"""

from __future__ import annotations

from typing import Any, Optional

from startup_swarm.backends import Backend
from startup_swarm.state_store import LocalStateStore, StateStore

from startup_swarm_aws.dynamodb_state import DynamoDBStateStore
from startup_swarm_aws.s3_mirror import S3Mirror


class AWSBackend(Backend):
    name = "aws"

    def __init__(self, s3_client: Any = None, dynamodb_client: Any = None):
        self._s3 = s3_client
        self._ddb = dynamodb_client

    @staticmethod
    def resources(settings) -> tuple:
        bucket = settings.stage_option("s3_artifact_bucket", env="S3_ARTIFACT_BUCKET", default="")
        table = settings.stage_option("dynamodb_state_table", env="DYNAMODB_STATE_TABLE", default="")
        if not bucket and not table:
            raise ValueError(
                f"Backend 'aws' needs S3_ARTIFACT_BUCKET and/or DYNAMODB_STATE_TABLE for stage "
                f"'{settings.stage}' (from the CDK outputs). See the startup-swarm-aws README."
            )
        return bucket, table

    def make_state(self, settings, project: str, workspace: str) -> StateStore:
        _, table = self.resources(settings)
        if not table:
            return LocalStateStore(workspace)
        return DynamoDBStateStore(table, project, region=settings.region, client=self._ddb)

    def make_mirror(self, settings, project: str) -> Optional[S3Mirror]:
        bucket, _ = self.resources(settings)
        if not bucket:
            return None
        return S3Mirror(bucket, project, client=self._s3, region=settings.region)
