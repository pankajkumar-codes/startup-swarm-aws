"""Amazon Bedrock AgentCore Runtime entrypoint.

``scripts/prepare_agentcore.py`` copies this module (as ``main.py``) with the
``startup_swarm`` and ``startup_swarm_aws`` packages and your ``config.yaml`` into an
AgentCore CLI project.

Invoke payloads (JSON):
  {"action": "run",    "project": "my-app", "idea": "..."}      # run or resume
  {"action": "task",   "project": "my-app", "task": "..."}      # direct engineering task
  {"action": "status", "project": "my-app"}
  {"action": "approve_gate", "project": "my-app", "gate": "founder", "note": "..."}

The runtime always uses the Bedrock provider and the AWS backend. State is in DynamoDB
and documents in S3 (names come from env vars set by the prepare script), so every
invocation picks up where the last one stopped. If a long invocation times out,
invoking "run" again resumes from the last finished phase.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, Optional

from startup_swarm import status as status_mod
from startup_swarm.pipeline import StartupPipeline

from startup_swarm_aws.backend import AWSBackend

HERE = os.path.dirname(os.path.abspath(__file__))


def _config_path() -> Optional[str]:
    if os.environ.get("SWARM_CONFIG"):
        return os.environ["SWARM_CONFIG"]
    for candidate in (os.path.join(HERE, "config.yaml"), os.path.join(os.path.dirname(HERE), "config.yaml")):
        if os.path.exists(candidate):
            return candidate
    return None


def _mock() -> bool:
    return os.environ.get("SWARM_MOCK", os.environ.get("AWS_MOCK_MODE", "0")).lower() in ("1", "true", "yes")


def handle(payload: Dict[str, Any], backend: Optional[AWSBackend] = None) -> Dict[str, Any]:
    payload = payload or {}
    action = payload.get("action", "status")
    project = payload.get("project")
    stage = os.environ.get("STAGE", "beta")
    workspace = os.path.join(tempfile.gettempdir(), "swarm", stage, project or "default")
    pipeline = StartupPipeline.build(
        stage=stage,
        config_path=_config_path(),
        mock=_mock(),
        project=project,
        workspace=workspace,
        provider="bedrock",
        backend_impl=backend or AWSBackend(),
    )

    if action == "status":
        return status_mod.collect(pipeline)
    if action == "run":
        outcome = pipeline.run(payload.get("idea"))
    elif action == "task":
        if not payload.get("task"):
            return {"status": "FAILED", "message": "payload.task is required"}
        outcome = pipeline.run_task(payload["task"])
    elif action == "approve_gate":
        outcome = pipeline.approve_gate(payload.get("gate", ""), payload.get("note", ""))
    else:
        return {"status": "FAILED", "message": f"unknown action {action!r}"}

    result: Dict[str, Any] = outcome.as_dict()
    result["usage"] = pipeline.client.usage.as_dict()
    result["documents"] = pipeline.bus.mirror.describe() if pipeline.bus.mirror else pipeline.bus.workspace_dir
    return result


try:
    from bedrock_agentcore import BedrockAgentCoreApp
except ImportError:  # local tests without the AgentCore SDK
    BedrockAgentCoreApp = None

if BedrockAgentCoreApp is not None:
    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload):
        return handle(payload)


if __name__ == "__main__":
    if BedrockAgentCoreApp is None:
        raise SystemExit('pip install "startup-swarm-aws[agentcore]" to serve this entrypoint locally')
    app.run()
