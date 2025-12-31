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
