import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Generator
import requests
from flask import Flask, Response, jsonify, request
logger = logging.getLogger(__name__)
HIGHWAY_API_ENDPOINT = os.environ.get("HIGHWAY_API_ENDPOINT", "http://localhost:7822")
HIGHWAY_API_KEY = os.environ.get("HIGHWAY_API_KEY", "")
executor = ThreadPoolExecutor(max_workers=10)
app = Flask(__name__)
highway_client = HighwayClient(HIGHWAY_API_ENDPOINT, HIGHWAY_API_KEY)

def submit_workflow():
    """Submit a workflow for execution (non-blocking)."""
    data = request.get_json()

    if not data or "workflow_definition" not in data:
        return jsonify({"error": "Missing workflow_definition"}), 400

    try:
        result = highway_client.submit(
            data["workflow_definition"],
            data.get("inputs", {}),
        )
        return (
            jsonify(
                {
                    "workflow_run_id": result["workflow_run_id"],
                    "run_id": result["run_id"],
                    "status": "submitted",
                }
            ),
            201,
        )
    except requests.HTTPError as e:
        return jsonify({"error": str(e)}), e.response.status_code
    except Exception as e:
        logger.exception("Error submitting workflow")
        return jsonify({"error": str(e)}), 500

def get_status(workflow_run_id: str):
    """Get current workflow status."""
    try:
        result = highway_client.status(workflow_run_id)
        return jsonify(
            {
                "workflow_run_id": result.get("workflow_run_id", workflow_run_id),
                "status": result.get("status", "unknown"),
                "progress_percentage": result.get("progress_percentage", 0),
                "current_step": result.get("current_step"),
                "result": result.get("result"),
                "error": result.get("error"),
            }
        )
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return jsonify({"error": "Workflow not found"}), 404
        return jsonify({"error": str(e)}), e.response.status_code

def cancel_workflow(workflow_run_id: str):
    """Cancel a running workflow."""
    try:
        highway_client.cancel(workflow_run_id)
        return jsonify({"status": "cancelled", "workflow_run_id": workflow_run_id})
    except requests.HTTPError as e:
        return jsonify({"error": str(e)}), e.response.status_code

def stream_status(workflow_run_id: str):
    """Real-time workflow updates via Server-Sent Events."""

    def generate() -> Generator[str, None, None]:
        try:
            for event in highway_client.stream_events(workflow_run_id):
                yield "data: %s\n\n" % json.dumps(event)

                if event.get("status") in ("completed", "failed", "cancelled"):
                    break
        except requests.HTTPError as e:
            yield "data: %s\n\n" % json.dumps({"error": str(e)})
        except Exception as e:
            logger.exception("SSE stream error")
            yield "data: %s\n\n" % json.dumps({"error": str(e)})

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

class HighwayClient:
    """Sync HTTP client for Highway API (thread-safe)."""
    def __init__(self, api_endpoint: str, api_key: str):
        self.api_endpoint = api_endpoint.rstrip("/")
        self.headers = {
            "Authorization": "Bearer %s" % api_key,
            "Content-Type": "application/json",
        }
        # Session with connection pooling (thread-safe)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def submit(self, workflow_definition: dict, inputs: dict | None = None) -> dict:
        """Submit workflow (non-blocking)."""
        response = self.session.post(
            "%s/api/v1/workflows" % self.api_endpoint,
            json={
                "workflow_definition": workflow_definition,
                "inputs": inputs or {},
            },
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["data"]

    def status(self, workflow_run_id: str) -> dict:
        """Get workflow status."""
        response = self.session.get(
            "%s/api/v1/workflows/%s" % (self.api_endpoint, workflow_run_id),
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["data"]

    def cancel(self, workflow_run_id: str) -> dict:
        """Cancel running workflow."""
        response = self.session.post(
            "%s/api/v1/workflows/%s/cancel" % (self.api_endpoint, workflow_run_id),
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["data"]

    def wait_for_completion(
        self, workflow_run_id: str, timeout: float = 300.0, poll_interval: float = 2.0
    ) -> dict:
        """Wait for workflow completion (blocking)."""
        start = time.time()
        while time.time() - start < timeout:
            status = self.status(workflow_run_id)
            if status.get("status") in ("completed", "failed", "cancelled"):
                return status
            time.sleep(poll_interval)
        raise TimeoutError(
            "Workflow %s did not complete within %ss" % (workflow_run_id, timeout)
        )

    def stream_events(self, workflow_run_id: str) -> Generator[dict, None, None]:
        """Stream workflow events via SSE."""
        response = self.session.get(
            "%s/api/v1/workflows/%s/stream" % (self.api_endpoint, workflow_run_id),
            headers={**self.headers, "Accept": "text/event-stream"},
            stream=True,
            timeout=None,
        )
        response.raise_for_status()

        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                yield json.loads(line[6:])
