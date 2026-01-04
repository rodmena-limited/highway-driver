"""Simple HTTP client for Highway API.

This module provides a direct HTTP client for the Highway Workflow Engine API.
It handles authentication, workflow submission, status polling, and completion waiting.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from highway.exceptions import ConfigurationError, ExecutionError, SubmissionError


class HighwayClient:
    """Direct HTTP client for Highway API.

    This client provides low-level HTTP operations for:
    - Submitting workflow definitions
    - Polling workflow status
    - Waiting for workflow completion

    Example:
        client = HighwayClient(api_key="hw_k1_...", endpoint="https://highway.run")
        run_id = client.submit_workflow(workflow_json, inputs={"x": 1})
        result = client.wait_for_completion(run_id, timeout=300.0)
    """

    TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})

    def __init__(
        self,
        api_key: str,
        endpoint: str = "https://highway.run",
        timeout: float = 30.0,
    ):
        """Initialize the Highway client.

        Args:
            api_key: Highway API key (format: hw_k1_*)
            endpoint: Highway API endpoint URL
            timeout: HTTP request timeout in seconds
        """
        if not api_key:
            raise ConfigurationError("api_key is required")

        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "HighwayClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def submit_workflow(
        self,
        workflow_definition: dict[str, Any],
        inputs: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        """Submit a workflow to Highway.

        Args:
            workflow_definition: Highway workflow JSON definition
            inputs: Workflow input parameters
            idempotency_key: Optional idempotency key for crash recovery

        Returns:
            The workflow run ID

        Raises:
            SubmissionError: If submission fails
        """
        url = f"{self.endpoint}/api/v1/workflows"
        payload: dict[str, Any] = {
            "workflow_definition": workflow_definition,
            "inputs": inputs or {},
        }

        headers = {}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key

        try:
            response = self._client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Highway API returns: {"data": {"workflow_run_id": "..."}}
            run_id = None
            if isinstance(data, dict):
                inner = data.get("data", data)
                run_id = inner.get("workflow_run_id") or inner.get("run_id")

            if not run_id:
                raise SubmissionError(f"Response missing workflow_run_id: {data}")

            return run_id

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                raise SubmissionError(f"Authentication failed: {e.response.text}")
            if e.response.status_code == 404:
                raise SubmissionError(f"Endpoint not found: {url}")
            if e.response.status_code == 409:
                # Idempotency conflict - try to extract existing run_id
                try:
                    error_data = e.response.json()
                    existing_run_id = error_data.get("existing_run_id")
                    if existing_run_id:
                        return existing_run_id
                except Exception:
                    pass
                raise SubmissionError(f"Idempotency conflict: {e.response.text}")
            raise SubmissionError(f"HTTP {e.response.status_code}: {e.response.text}")

        except httpx.RequestError as e:
            raise SubmissionError(f"Network error: {e}")

    def get_status(self, run_id: str) -> dict[str, Any]:
        """Get workflow run status.

        Args:
            run_id: The workflow run ID

        Returns:
            Status data including state, result, current_step, etc.

        Raises:
            ExecutionError: If status check fails
        """
        url = f"{self.endpoint}/api/v1/workflows/{run_id}"

        try:
            response = self._client.get(url)
            response.raise_for_status()
            data = response.json()

            # Highway API returns: {"data": {"state": "...", "result": ...}}
            return data.get("data", data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                raise ExecutionError(f"Authentication failed: {e.response.text}")
            if e.response.status_code == 404:
                raise ExecutionError(f"Workflow run not found: {run_id}")
            raise ExecutionError(f"HTTP {e.response.status_code}: {e.response.text}")

        except httpx.RequestError as e:
            raise ExecutionError(f"Network error: {e}")

    def wait_for_completion(
        self,
        run_id: str,
        poll_interval: float = 1.0,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        """Poll until workflow completes.

        Args:
            run_id: The workflow run ID
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait

        Returns:
            Final status data including state and result

        Raises:
            ExecutionError: If workflow fails or is cancelled
            TimeoutError: If workflow doesn't complete within timeout
        """
        start = time.time()

        while time.time() - start < timeout:
            status = self.get_status(run_id)
            # Highway uses "status" field, not "state"
            state = status.get("status", status.get("state", "unknown"))

            if state in self.TERMINAL_STATES:
                if state == "failed":
                    error = status.get("error") or status.get("failure_reason") or "Unknown error"
                    raise ExecutionError(f"Workflow failed: {error}")
                if state == "cancelled":
                    raise ExecutionError("Workflow was cancelled")
                return status

            time.sleep(poll_interval)

        raise TimeoutError(f"Workflow {run_id} did not complete in {timeout}s")

    def cancel_workflow(self, run_id: str) -> bool:
        """Cancel a running workflow.

        Args:
            run_id: The workflow run ID

        Returns:
            True if cancelled successfully, False if already completed

        Raises:
            ExecutionError: If cancellation fails for other reasons
        """
        url = f"{self.endpoint}/api/v1/workflows/{run_id}/cancel"

        try:
            response = self._client.post(url)
            response.raise_for_status()
            return True

        except httpx.HTTPStatusError as e:
            # CONFLICT (409) typically means already completed
            if e.response.status_code == 409:
                return False
            raise ExecutionError(f"Failed to cancel: {e.response.text}")

        except httpx.RequestError as e:
            raise ExecutionError(f"Network error: {e}")
