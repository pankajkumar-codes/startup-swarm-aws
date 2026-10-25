"""DynamoDB implementation of startup-swarm's ``StateStore``.

Table ``startup-swarm-state-<stage>`` (created by the CDK stack). One item per record:
PK = "PROJECT#<name>", SK = "PHASE#<id>" | "GATE#<id>" | "META#<key>", and attribute
``data`` holds the JSON payload. Reads are strongly consistent, so a gate approved from
one machine is seen immediately by a run on another.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from startup_swarm.state_store import StateStore


class DynamoDBStateStore(StateStore):
    def __init__(self, table_name: str, project: str, region: Optional[str] = None, client: Any = None):
        if not table_name:
            raise ValueError("DynamoDBStateStore needs a table name")
        if client is None:
            import boto3

            client = boto3.client("dynamodb", region_name=region)
        self.client = client
        self.table = table_name
        self.pk = f"PROJECT#{project}"

    def _get(self, sk: str) -> Optional[Dict[str, Any]]:
        res = self.client.get_item(
            TableName=self.table, Key={"PK": {"S": self.pk}, "SK": {"S": sk}}, ConsistentRead=True
        )
        item = res.get("Item")
        return json.loads(item["data"]["S"]) if item else None

    def _put(self, sk: str, data: Dict[str, Any]) -> None:
        self.client.put_item(
            TableName=self.table,
            Item={"PK": {"S": self.pk}, "SK": {"S": sk}, "data": {"S": json.dumps(data)}},
        )

    def _all(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        kwargs: Dict[str, Any] = {
            "TableName": self.table,
            "KeyConditionExpression": "PK = :pk",
            "ExpressionAttributeValues": {":pk": {"S": self.pk}},
            "ConsistentRead": True,
        }
        while True:
            res = self.client.query(**kwargs)
            for item in res.get("Items", []):
                out[item["SK"]["S"]] = json.loads(item["data"]["S"])
            if "LastEvaluatedKey" not in res:
                return out
            kwargs["ExclusiveStartKey"] = res["LastEvaluatedKey"]
