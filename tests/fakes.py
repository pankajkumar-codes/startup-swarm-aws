"""In-memory stand-ins for the boto3 S3 and DynamoDB clients."""

import io


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.put_calls = []

    def put_object(self, Bucket, Key, Body, **kw):
        self.put_calls.append({"Bucket": Bucket, "Key": Key, **kw})
        self.objects[(Bucket, Key)] = Body

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
        keys = sorted(k for (b, k) in self.objects if b == Bucket and k.startswith(Prefix))
        # two keys per page, to exercise pagination
        start = int(ContinuationToken or 0)
        page = keys[start : start + 2]
        more = start + 2 < len(keys)
        out = {"Contents": [{"Key": k} for k in page], "IsTruncated": more}
        if more:
            out["NextContinuationToken"] = str(start + 2)
        return out

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


class FakeDynamo:
    def __init__(self):
        self.items = {}

    def put_item(self, TableName, Item):
        self.items[(TableName, Item["PK"]["S"], Item["SK"]["S"])] = Item

    def get_item(self, TableName, Key, **kw):
        item = self.items.get((TableName, Key["PK"]["S"], Key["SK"]["S"]))
        return {"Item": item} if item else {}

    def query(self, TableName, ExpressionAttributeValues, ExclusiveStartKey=None, **kw):
        pk = ExpressionAttributeValues[":pk"]["S"]
        items = [v for (t, p, _), v in sorted(self.items.items()) if t == TableName and p == pk]
        start = int(ExclusiveStartKey["n"]) if ExclusiveStartKey else 0
        page = items[start : start + 3]
        out = {"Items": page}
        if start + 3 < len(items):
            out["LastEvaluatedKey"] = {"n": str(start + 3)}
        return out
