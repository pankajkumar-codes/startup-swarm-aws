"""S3 implementation of startup-swarm's ``RemoteMirror``.

Every document the agents write is copied to ``s3://<bucket>/<project>/<name>``.
``pull_all`` restores a project's working copy, which the AgentCore runtime needs
because its local disk does not survive between sessions.
"""

from __future__ import annotations

from typing import Any, Optional

from startup_swarm.artifact_bus import validate_name


class S3Mirror:
    def __init__(self, bucket: str, prefix: str, client: Any = None, region: Optional[str] = None):
        if not bucket:
            raise ValueError("S3Mirror needs a bucket name")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        if client is None:
            import boto3

            client = boto3.client("s3", region_name=region)
        self.client = client

    def key(self, name: str) -> str:
        return f"{self.prefix}/{validate_name(name)}"

    def describe(self) -> str:
        return f"s3://{self.bucket}/{self.prefix}/"

    def put(self, name: str, body: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self.key(name), Body=body, ServerSideEncryption="AES256")

    def pull_all(self, dest_dir: str) -> int:
        import os

        count = 0
        token: Optional[str] = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": self.prefix + "/"}
            if token:
                kwargs["ContinuationToken"] = token
            page = self.client.list_objects_v2(**kwargs)
            for obj in page.get("Contents", []):
                rel = validate_name(obj["Key"][len(self.prefix) + 1 :])
                path = os.path.join(dest_dir, rel)
                os.makedirs(os.path.dirname(path) or dest_dir, exist_ok=True)
                body = self.client.get_object(Bucket=self.bucket, Key=obj["Key"])["Body"].read()
                with open(path, "wb") as fh:
                    fh.write(body)
                count += 1
            if not page.get("IsTruncated"):
                return count
            token = page.get("NextContinuationToken")
