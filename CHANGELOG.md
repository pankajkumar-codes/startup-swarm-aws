# Changelog

## 0.1.0 (2026-10-25)

First release, split out of startup-swarm 0.2.0.

- `aws` storage backend for startup-swarm: S3 document mirror and DynamoDB state store,
  registered through the `startup_swarm.backends` entry point.
- AgentCore Runtime entrypoint (`startup_swarm_aws.agentcore_main`) and
  `scripts/prepare_agentcore.py` to stage it into an AgentCore CLI project.
- CDK app: `StartupSwarm-Beta` / `StartupSwarm-Prod` (S3, DynamoDB, AgentCore role, runner
  policy) and optional `GitHubDeployStack-<Stage>` (GitHub OIDC deploy role). Resources are
  now named `startup-swarm-*` (were `startup-agent-*` in 0.2.0).
- AWS-ready `config.yaml` (Bedrock provider, aws backend).
- CI: lint, tests, backend registration check, offline dry run, `cdk synth`.
- Deploy: push to `main` deploys beta; tag `vX.Y.Z` deploys prod after approval; manual
  dispatch for either stage. Skips cleanly until AWS is connected.
- Depends on startup-swarm v0.3.0.
