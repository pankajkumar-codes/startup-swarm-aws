# startup-swarm-aws

[![CI](https://github.com/pankajkumar-codes/startup-swarm-aws/actions/workflows/test.yml/badge.svg)](https://github.com/pankajkumar-codes/startup-swarm-aws/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Run [startup-swarm](https://github.com/pankajkumar-codes/startup-swarm), the ten-agent AI
software startup, on AWS:

- **`aws` storage backend.** Documents go to S3 and project state (phases, gates, token use)
  to DynamoDB, so runs resume from any machine.
- **Amazon Bedrock** for the models (Claude Sonnet 5.5 / Haiku 5.5 by default).
- **Two stages.** `beta` is disposable. `prod` is retained, with point-in-time recovery. Both are defined in AWS CDK.
- **Optional hosted mode** on Bedrock AgentCore Runtime.
- **CI/CD with GitHub OIDC.** No AWS keys are stored in GitHub. Merges to `main` deploy beta, and version tags deploy prod.

The agents, pipeline and CLI live in the core repo. This repo installs it as a dependency,
pinned to a release tag, and adds only the AWS parts.

```
startup-swarm (core)              startup-swarm-aws (this repo)
  agents, pipeline, CLI    <----    backend "aws": S3Mirror + DynamoDBStateStore
  providers incl. bedrock           AgentCore entrypoint + prepare script
  local backend                     CDK stacks (beta/prod) + GitHub OIDC role
                                    CI/CD: main -> beta, tag -> prod
```

## 1. Try it offline (no AWS account)

Requires Python 3.11+.

```bash
git clone https://github.com/pankajkumar-codes/startup-swarm-aws.git
cd startup-swarm-aws
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"                                   # also installs the startup-swarm core

python -m pytest -q
startup-swarm info                                        # Backends should list: aws, local
startup-swarm run --mock --idea "A CLI that turns meeting notes into Jira tickets"
startup-swarm status --mock
```

Mock mode uses the local backend and no AWS calls. It checks the plumbing, gates and resume
logic. It does not check real model output quality.

## 2. Prerequisites for AWS

- An AWS account, and AWS CLI credentials that work (`aws sts get-caller-identity` succeeds).
- Node.js 20+ and the CDK CLI: `npm install -g aws-cdk`.
- Bedrock model access for the models in `config.yaml`, in your region. Check the Bedrock
  console's Model catalog. Anthropic models may ask for a one-time use-case form. Model IDs
  change over time, so update `config.yaml` if one is retired.

## 3. Deploy beta and run against it

```bash
cd infrastructure
pip install -r requirements.txt
cdk bootstrap                                   # once per account/region
cdk deploy StartupSwarm-Beta -c stage=beta --outputs-file cdk-outputs-beta.json
cd ..
```

The stack creates:

| Resource | Name | Notes |
|---|---|---|
| S3 bucket | `startup-swarm-artifacts-beta-<account>-<region>` | Versioned, encrypted, TLS-only, no public access |
| DynamoDB table | `startup-swarm-state-beta` | On-demand billing |
| IAM role | `startup-swarm-agentcore-beta` | For hosted mode (AgentCore Runtime) |
| Managed policy | `startup-swarm-runner-beta` | Attach this to the IAM user or role you run the CLI with |

Then run from your laptop:

```bash
cp .env.example .env.beta     # fill S3_ARTIFACT_BUCKET and DYNAMODB_STATE_TABLE from cdk-outputs-beta.json
set -a; source .env.beta; set +a
startup-swarm run --stage beta --project demo --idea "..."
startup-swarm status --stage beta --project demo
```

`config.yaml` in this repo already sets `provider: bedrock` and `backend: aws`. You can put the
bucket and table names there instead of in env vars. Start with a small idea and a low
`token_controls.budget_cap_tokens` so you see the real cost before larger runs.

## 4. Promote to prod

```bash
cd infrastructure
cdk deploy StartupSwarm-Prod -c stage=prod --outputs-file cdk-outputs-prod.json
```

Then use `.env.prod` and `--stage prod`. The prod bucket and table are kept even if the stack
is deleted.

## Hosted mode on AgentCore Runtime (optional)

This runs the company as a managed endpoint instead of from a laptop. It needs the AgentCore
CLI (`npm install -g @aws/agentcore`, Node 20.12+, and `uv`).

```bash
# once: create an AgentCore project next to this repo
cd .. && agentcore create --name SwarmRuntime && cd startup-swarm-aws

# stage the runtime for beta (copies the installed packages + config.yaml, uses the CDK role)
python scripts/prepare_agentcore.py --stage beta --project-dir ../SwarmRuntime \
  --outputs infrastructure/cdk-outputs-beta.json

cd ../SwarmRuntime && agentcore validate && agentcore deploy
agentcore invoke --runtime startup_swarm_beta --payload '{"action": "run", "project": "demo", "idea": "..."}'
agentcore invoke --runtime startup_swarm_beta --payload '{"action": "status", "project": "demo"}'
agentcore logs runtime
```

The other payload actions are `task` (`{"action": "task", "project": "demo", "task": "..."}`)
and `approve_gate` (`{"action": "approve_gate", "project": "demo", "gate": "founder"}`).

If the project template also created a sample runtime you don't need, remove it with
`agentcore remove`. If a long invocation times out, invoke `run` again and it resumes. This
flow follows the AgentCore CLI docs as of October 2026, so check `agentcore --help` if a
command has changed.

## CI/CD

| Workflow | When | What |
|---|---|---|
| `test.yml` | Every PR and push to `main` | flake8, black, tests, backend-registration check, offline dry run, `cdk synth` for both stages |
| `deploy.yml` | Push to `main` | CI, then deploy **beta** |
| `deploy.yml` | Push a tag `vX.Y.Z` | CI, then deploy **prod** (waits for a required reviewer) |
| `deploy.yml` | Manual (Actions → Deploy → Run workflow) | Deploy the stage you pick |

Until AWS is connected, the deploy job skips with a notice, so the repo stays green.

**One-time setup for automatic deploys:**

1. Create the GitHub OIDC deploy roles from your machine:
   ```bash
   cd infrastructure
   cdk deploy GitHubDeployStack-Beta -c stage=beta -c github_repo=pankajkumar-codes/startup-swarm-aws
   cdk deploy GitHubDeployStack-Prod -c stage=prod -c github_repo=pankajkumar-codes/startup-swarm-aws \
     -c github_oidc_provider_arn=arn:aws:iam::<account>:oidc-provider/token.actions.githubusercontent.com
   ```
   The first command creates the account's GitHub OIDC provider. The second reuses it, so
   pass its ARN.
2. In GitHub, go to **Settings → Environments** and create `beta` and `prod`. On each, add the
   variables `AWS_DEPLOY_ROLE_ARN` (the `DeployRoleArn` output) and `AWS_REGION`.
3. On `prod`, add **Required reviewers** (yourself). Under **Deployment branches and tags**,
   choose **Selected branches and tags** and add the tag rule `v*`.

To release to prod: `git tag v0.1.0 && git push origin v0.1.0`, then approve the deployment in
the Actions tab.

## Configuration reference

| Setting | Where | Default |
|---|---|---|
| Provider | `provider.name` / `SWARM_PROVIDER` | `bedrock` |
| Region | `stages.<stage>.region` / `SWARM_REGION` | `us-east-1` |
| Backend | `stages.<stage>.backend` / `SWARM_BACKEND` | `aws` |
| S3 bucket | `stages.<stage>.s3_artifact_bucket` / `S3_ARTIFACT_BUCKET` | none (local disk) |
| DynamoDB table | `stages.<stage>.dynamodb_state_table` / `DYNAMODB_STATE_TABLE` | none (local `state.json`) |

Environment variables win over `config.yaml`. Everything else (models, roles, reviewers,
gates, token limits) is documented in the core README.

## Upgrading the core

`pyproject.toml` pins the core to a tag:

```toml
"startup-swarm[bedrock] @ git+https://github.com/pankajkumar-codes/startup-swarm.git@v0.3.0"
```

To upgrade, release the core first (tag `vX.Y.Z` there). Then change the tag here, run
`pip install -e ".[dev]"` and the tests, and open a PR.

## Development

```bash
pip install -e ".[dev]"
black --check startup_swarm_aws scripts tests infrastructure
flake8 startup_swarm_aws scripts tests infrastructure
python -m pytest -q
```

Work on a branch and open a PR into `main`; CI must pass before merging. Before you push,
check that `git status` shows no `.env.*`, `cdk-outputs*.json`, `cdk.out/` or `artifacts/`
files.

## Repository layout

```
startup_swarm_aws/
  backend.py          AWSBackend (registered as entry point "aws")
  s3_mirror.py        documents in S3
  dynamodb_state.py   phases, gates and usage in DynamoDB
  agentcore_main.py   AgentCore Runtime entrypoint
scripts/
  prepare_agentcore.py   stage the runtime into an AgentCore CLI project
infrastructure/       CDK app: StartupSwarm-<Stage> and optional GitHubDeployStack-<Stage>
config.yaml           AWS-ready founder brief (bedrock + aws backend)
tests/                offline tests with fake S3 and DynamoDB clients
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `pip install` can't find `startup-swarm@v0.3.0` | The core tag doesn't exist yet. Release the core first. |
| `Unknown backend 'aws'` | Install this package (`pip install -e .`) in the same environment as the core. |
| `Backend 'aws' needs S3_ARTIFACT_BUCKET...` | Set the bucket and/or table from the CDK outputs. |
| `AccessDeniedException` | Attach the `startup-swarm-runner-<stage>` policy to your IAM identity, and enable the model in Bedrock. |
| Error mentioning `ttl` | Set `cache_ttl: "5m"` in `config.yaml`. |
| Deploy job says "skipped" | Set `AWS_DEPLOY_ROLE_ARN` on that GitHub environment (see CI/CD). |

## License

MIT. See `LICENSE`.
