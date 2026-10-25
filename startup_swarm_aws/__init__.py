"""startup-swarm-aws: run startup-swarm on AWS.

Adds the ``aws`` storage backend to startup-swarm (documents in S3, state in DynamoDB)
and ships the AgentCore Runtime entrypoint, CDK stacks and deploy workflows.

    pip install startup-swarm-aws          # registers backend "aws"
    startup-swarm run --provider bedrock --backend aws ...
"""

__version__ = "0.1.0"

from startup_swarm_aws.backend import AWSBackend  # noqa: E402
from startup_swarm_aws.dynamodb_state import DynamoDBStateStore  # noqa: E402
from startup_swarm_aws.s3_mirror import S3Mirror  # noqa: E402

__all__ = ["__version__", "AWSBackend", "DynamoDBStateStore", "S3Mirror"]
