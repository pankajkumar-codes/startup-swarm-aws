# Testing the AWS backend locally

The backend needs no code change to talk to an emulator: boto3 reads `AWS_ENDPOINT_URL`
from the environment, so S3 and DynamoDB calls go to whatever endpoint you set.

## Important: `--mock` skips the AWS backend

`--mock` forces the local backend, so nothing reaches S3 or DynamoDB. To exercise the
AWS backend without model calls, use the mock *provider* instead:

```powershell
startup-swarm run --idea "A todo app" --backend aws --provider mock --project demo --workspace .\ws
```

## 1. Start an emulator

Use the AWS Emulator (https://github.com/aws/aws-emulator). On Windows it runs in Docker;
follow the Docker guide in its user guide (build the image, then `docker run` with
`-p 127.0.0.1:9297:9297` and `-v $env:USERPROFILE\.aws\emulator:/home/emulator/.aws/emulator`).
Any S3/DynamoDB-compatible emulator (for example moto server) works the same way.

## 2. Point the SDK at it (PowerShell)

For the AWS Emulator on port 9297:

```powershell
$env:AWS_ENDPOINT_URL = "https://127.0.0.1:9297"
$env:AWS_SHARED_CREDENTIALS_FILE = "$env:USERPROFILE\.aws\emulator\9297\emulator_credentials"
$env:AWS_CONFIG_FILE = "$env:USERPROFILE\.aws\emulator\9297\config"
$env:AWS_CA_BUNDLE = "$env:USERPROFILE\.aws\emulator\9297\ca.pem"
$env:AWS_EC2_METADATA_DISABLED = "true"
$env:AWS_DISABLE_HOST_PREFIX_INJECTION = "true"
$env:AWS_REGION = "us-east-1"
$env:AWS_DEFAULT_REGION = "us-east-1"
Remove-Item Env:AWS_ACCESS_KEY_ID, Env:AWS_SECRET_ACCESS_KEY, Env:AWS_SESSION_TOKEN, Env:AWS_PROFILE -ErrorAction SilentlyContinue
```

For a plain HTTP emulator (moto on port 5555): set `AWS_ENDPOINT_URL=http://127.0.0.1:5555`
and dummy `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.

## 3. Create the resources

The emulator starts empty. Create a bucket and a table with key schema `PK` (S, HASH) and
`SK` (S, RANGE), then:

```powershell
$env:S3_ARTIFACT_BUCKET = "swarm-test"
$env:DYNAMODB_STATE_TABLE = "swarm-state"
```

## 4. Run and check

```powershell
startup-swarm run --idea "A todo app" --backend aws --provider mock --project demo --workspace .\ws
```

Expect `COMPLETED`, objects under `demo/` in the bucket, and `PROJECT#demo` items in the
table. To confirm state lives in DynamoDB, check it from a fresh, empty workspace; it should
still report the finished phases:

```powershell
startup-swarm status --backend aws --provider mock --project demo --workspace .\ws2
```

## Tested status

Verified with moto server (S3 + DynamoDB): a full mock-provider run wrote 55 S3 objects and
14 DynamoDB items, and a fresh workspace read the state back. Not verified: the AWS Emulator
itself, real AWS, and real Bedrock calls.
