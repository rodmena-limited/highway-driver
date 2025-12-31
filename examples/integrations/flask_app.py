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
