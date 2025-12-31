import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any
import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
logger = logging.getLogger(__name__)
HIGHWAY_API_ENDPOINT = os.environ.get("HIGHWAY_API_ENDPOINT", "http://localhost:7822")
HIGHWAY_API_KEY = os.environ.get("HIGHWAY_API_KEY", "")
app = FastAPI(
    title="Highway Workflow Integration",
    description="FastAPI integration example for Highway Driver",
    version="1.0.0",
    lifespan=lifespan,
)

async def monitor_workflow_background(workflow_run_id: str, callback_url: str):
    """Background task to monitor workflow and call webhook on completion."""
    client = HighwayClient(HIGHWAY_API_ENDPOINT, HIGHWAY_API_KEY)
    try:
        result = await client.wait_for_completion(workflow_run_id, timeout=3600)
        async with httpx.AsyncClient() as http:
            await http.post(callback_url, json=result, timeout=30)
        logger.info("Callback sent for %s", workflow_run_id)
    except Exception:
        logger.exception("Background monitor failed for %s", workflow_run_id)

async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "highway_endpoint": HIGHWAY_API_ENDPOINT}

async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    app.state.highway = HighwayClient(HIGHWAY_API_ENDPOINT, HIGHWAY_API_KEY)
    logger.info("Highway client initialized: %s", HIGHWAY_API_ENDPOINT)
    yield
    logger.info("Shutting down")

async def submit_workflow(request: WorkflowSubmitRequest):
    """Submit a workflow for execution (non-blocking)."""
    try:
        result = await app.state.highway.submit(
            request.workflow_definition,
            request.inputs,
        )
        return WorkflowSubmitResponse(
            workflow_run_id=result["workflow_run_id"],
            run_id=result["run_id"],
            status="submitted",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.exception("Error submitting workflow")
        raise HTTPException(status_code=500, detail=str(e))

async def get_status(workflow_run_id: str):
    """Get current workflow status."""
    try:
        result = await app.state.highway.status(workflow_run_id)
        return WorkflowStatusResponse(
            workflow_run_id=result.get("workflow_run_id", workflow_run_id),
            status=result.get("status", "unknown"),
            progress_percentage=result.get("progress_percentage", 0),
            current_step=result.get("current_step"),
            result=result.get("result"),
            error=result.get("error"),
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Workflow not found")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

class WorkflowSubmitRequest(BaseModel):
    """Request to submit a workflow."""
    workflow_definition: dict[str, Any]
    inputs: dict[str, Any] = {}
    queue: str = 'highway_default'

class WorkflowSubmitResponse(BaseModel):
    """Response after workflow submission."""
    workflow_run_id: str
    run_id: str
    status: str

class WorkflowStatusResponse(BaseModel):
    """Workflow status response."""
    workflow_run_id: str
    status: str
    progress_percentage: int = 0
    current_step: str | None = None
    result: Any | None = None
    error: Any | None = None

class HighwayClient:
    """Async HTTP client for Highway API."""
    def __init__(self, api_endpoint: str, api_key: str):
        self.api_endpoint = api_endpoint.rstrip("/")
        self.headers = {
            "Authorization": "Bearer %s" % api_key,
            "Content-Type": "application/json",
        }

    async def submit(
        self, workflow_definition: dict, inputs: dict | None = None
    ) -> dict:
        """Submit workflow (non-blocking)."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "%s/api/v1/workflows" % self.api_endpoint,
                json={
                    "workflow_definition": workflow_definition,
                    "inputs": inputs or {},
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()["data"]

    async def status(self, workflow_run_id: str) -> dict:
        """Get workflow status."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "%s/api/v1/workflows/%s" % (self.api_endpoint, workflow_run_id),
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()["data"]

    async def cancel(self, workflow_run_id: str) -> dict:
        """Cancel running workflow."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "%s/api/v1/workflows/%s/cancel" % (self.api_endpoint, workflow_run_id),
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()["data"]

    async def wait_for_completion(
        self, workflow_run_id: str, timeout: float = 300.0, poll_interval: float = 2.0
    ) -> dict:
        """Wait for workflow completion (blocking)."""
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            status = await self.status(workflow_run_id)
            if status.get("status") in ("completed", "failed", "cancelled"):
                return status
            await asyncio.sleep(poll_interval)
        raise TimeoutError(
            "Workflow %s did not complete within %ss" % (workflow_run_id, timeout)
        )

    async def stream_events(self, workflow_run_id: str):
        """Stream workflow events via SSE."""
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "GET",
                "%s/api/v1/workflows/%s/stream" % (self.api_endpoint, workflow_run_id),
                headers={**self.headers, "Accept": "text/event-stream"},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line and line.startswith("data: "):
                        yield json.loads(line[6:])
