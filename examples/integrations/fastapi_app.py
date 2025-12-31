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
