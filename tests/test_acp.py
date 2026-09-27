import json
import os
import shutil
import sys

from unified_agent.acp import ACPProcessWorker, HermesACPWorker
from unified_agent.models import Task

FAKE_ACP = r"""
import json, os, sys

log = os.environ["ACP_LOG"]
session_id = "session-test-1"

def write(value):
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(value) + "\n")

for line in sys.stdin:
    message = json.loads(line)
    if "method" in message:
        method = message["method"]
        write({"kind": "request", "method": method})
        if method == "initialize":
            print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":{"protocolVersion":1,"agentCapabilities":{"sessionCapabilities":{"resume":True}}}}), flush=True)
        elif method == "session/new":
            print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":{"sessionId":session_id}}), flush=True)
        elif method in ("session/resume", "session/load"):
            print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":{}}), flush=True)
        elif method == "session/prompt":
            permission_id = "permission-1"
            print(json.dumps({"jsonrpc":"2.0","id":permission_id,"method":"session/request_permission","params":{"sessionId":session_id}}), flush=True)
            print(json.dumps({"jsonrpc":"2.0","method":"session/update","params":{"sessionId":session_id,"update":{"sessionUpdate":"agent_message_chunk","content":{"text":"hello from fake ACP"}}}}), flush=True)
            print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":{"stopReason":"end_turn"}}), flush=True)
    else:
        write({"kind":"response","id":message.get("id"),"result":message.get("result")})
"""

def test_acp_worker_streams_and_resumes(tmp_path):
    script = tmp_path / "fake_acp.py"
    script.write_text(FAKE_ACP, encoding="utf-8")
    log = tmp_path / "acp.log"
    worker = ACPProcessWorker("fake-acp", ["test.acp"], [sys.executable, str(script)], timeout_seconds=5, env={"ACP_LOG": str(log)})
    task = Task(task_id="acp-1", goal="hello", requested_capabilities=["test.acp"])
    first = worker.execute(task, "test.acp")
    second = worker.execute(task, "test.acp")
    assert first["answer"] == "hello from fake ACP"
    assert second["answer"] == "hello from fake ACP"
    assert task.state["acp_session_id"] == "session-test-1"
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    methods = [r["method"] for r in records if r["kind"] == "request"]
    assert methods[:3] == ["initialize", "session/new", "session/prompt"]
    assert methods[3:] == ["initialize", "session/resume", "session/prompt"]
    permission_responses = [r for r in records if r["kind"] == "response" and r["id"] == "permission-1" and (r["result"] or {}).get("outcome", {}).get("outcome") == "cancelled"]
    assert len(permission_responses) == 2

def test_acp_worker_availability_checks_executable():
    worker = ACPProcessWorker("missing", ["x"], ["definitely-not-a-real-executable"])
    assert worker.is_available() is False

def test_hermes_worker_uses_expected_entrypoint():
    worker = HermesACPWorker()
    assert worker.command == ("hermes", "acp")
    assert "research" in worker.capabilities

def test_real_hermes_acp_smoke_opt_in(monkeypatch):
    if os.getenv("RUN_HERMES_ACP_SMOKE") != "1":
        import pytest
        pytest.skip("Set RUN_HERMES_ACP_SMOKE=1 to run the real Hermes smoke test")
    if shutil.which("hermes") is None:
        import pytest
        pytest.skip("Hermes executable is not installed")
    worker = HermesACPWorker(timeout_seconds=60)
    task = Task(task_id="hermes-smoke", goal="Reply with exactly: ACP_OK", requested_capabilities=["research"])
    result = worker.execute(task, "research")
    assert result["answer"].strip()
    assert result["acp_session_id"]