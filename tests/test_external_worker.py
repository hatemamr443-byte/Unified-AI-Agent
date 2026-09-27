import sys

from unified_agent.external import JsonLineProcessWorker
from unified_agent.models import Task


def test_external_worker_jsonl_round_trip():
    worker = JsonLineProcessWorker(
        "echo-worker",
        ["external.echo"],
        [
            sys.executable,
            "-c",
            "import json,sys; x=json.loads(sys.stdin.readline()); print(json.dumps({'answer': x['goal']}))",
        ],
        timeout_seconds=5,
    )
    result = worker.execute(Task(task_id="external-1", goal="hello"), "external.echo")
    assert result["answer"] == "hello"
    assert worker.status("external-1") == "completed"
