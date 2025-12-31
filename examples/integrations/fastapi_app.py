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
