Highway
=======

Python SDK for Highway Workflow Engine. Build durable rock solid workflows with ease.

.. image:: https://raw.githubusercontent.com/rodmena-limited/highway-driver/refs/heads/main/images/ux.png
   :alt: Highway Workflow Engine UI
   :align: center

Installation
------------

::

    pip install highway

Quick Start
-----------

.. code-block:: python

    from highway import Driver

    driver = Driver()  # Uses HIGHWAY_API_KEY env var

    @driver.task(shell=True)
    def backup_db():
        return "pg_dump mydb > backup.sql"

    @driver.task(py=True, depends=["backup_db"])
    def verify():
        import os
        return {"exists": os.path.exists("backup.sql")}

    result = driver.run()
    print(result.status)  # "completed"

Configuration
-------------

Set environment variables::

    export HIGHWAY_API_KEY="hw_k1_..."
    export HIGHWAY_API_ENDPOINT="https://highway.solutions"

Or pass directly:

.. code-block:: python

    driver = Driver(
        api_key="hw_k1_...",
        endpoint="https://highway.solutions"
    )

Task Types
----------

Shell Tasks
~~~~~~~~~~~

Execute shell commands:

.. code-block:: python

    @driver.task(shell=True)
    def list_files():
        return "ls -la /tmp"

Python Tasks
~~~~~~~~~~~~

Execute Python code in Highway's sandboxed environment:

.. code-block:: python

    @driver.task(py=True)
    def compute():
        import math
        return {"factorial": math.factorial(10)}

HTTP Tasks
~~~~~~~~~~

Make HTTP requests:

.. code-block:: python

    @driver.task(http=True)
    def call_api():
        return {
            "url": "https://<organisation>.highway.solutions/webhook",
            "method": "POST",
            "json": {"status": "done"},
        }

Generic Tool Tasks
~~~~~~~~~~~~~~~~~~

Call any Highway tool directly:

.. code-block:: python

    @driver.task(tool="tools.llm.call")
    def summarize():
        return {
            "provider": "ollama",
            "model": "qwen3-vl:235b-instruct-cloud",
            "prompt": "Summarize: {{backup_result.stdout}}",
            "temperature": 0.7
        }

    @driver.task(tool="tools.database.query")
    def query_users():
        return {
            "connection_string": "vault:db/postgres",
            "query": "SELECT * FROM users"
        }

LLM Agentic Workflows
~~~~~~~~~~~~~~~~~~~~~

Build multi-step LLM workflows using ``tools.llm.call``:

.. code-block:: python

    @driver.task(http=True)
    def fetch_data():
        return {"url": "https://api.example.com/data", "method": "GET"}

    @driver.task(tool="tools.llm.call", depends=["fetch_data"])
    def analyze():
        return {
            "provider": "ollama",  # or "openai", "anthropic"
            "model": "qwen3-vl:235b-instruct-cloud",
            "prompt": "Analyze: {{fetch_data_result.body}}",
            "temperature": 0.3
        }

    @driver.task(tool="tools.llm.call", depends=["analyze"])
    def summarize():
        return {
            "provider": "ollama",
            "model": "qwen3-vl:235b-instruct-cloud",
            "prompt": "Summarize: {{analyze_result.response}}"
        }

Workflow Execution
~~~~~~~~~~~~~~~~~~

Execute other workflows:

.. code-block:: python

    @driver.task(workflow="daily_report")
    def run_report():
        return {"inputs": {"date": "2024-01-01"}}

    @driver.task(workflow_id="uuid-here")
    def run_specific_version():
        return {"inputs": {"mode": "production"}}

Dependencies
------------

Tasks can depend on other tasks:

.. code-block:: python

    @driver.task(shell=True)
    def step_1():
        return "echo 'Step 1'"

    @driver.task(shell=True, depends=["step_1"])
    def step_2():
        return "echo 'Step 2'"

    @driver.task(shell=True, depends=["step_2"])
    def step_3():
        return "echo 'Step 3'"

Workflow Inputs
---------------

Pass variables to workflows:

.. code-block:: python

    result = driver.run(
        inputs={"email": "user@example.com", "env": "prod"},
        timeout=300
    )

Access inputs in tasks via ``{{inputs.key}}`` syntax.

Retry Configuration
-------------------

Configure automatic retries with exponential backoff:

.. code-block:: python

    @driver.task(http=True, retries=3, retry_delay=2.0, backoff=2.0)
    def call_flaky_api():
        return {"url": "https://<organisation>.highway.solutions/endpoint"}

Durable Delays
--------------

Use Highway's native WaitOperator for delays that consume zero worker resources:

.. code-block:: python

    from datetime import timedelta

    @driver.task(shell=True, delay=timedelta(hours=2))
    def delayed_task():
        return "echo 'Runs after 2 hour delay'"

Scheduling
----------

Schedule recurring workflows:

.. code-block:: python

    @driver.task(shell=True, schedule="0 * * * *")  # Every hour
    def hourly_backup():
        return "pg_dump mydb > backup.sql"

    @driver.task(shell=True, schedule=timedelta(minutes=30))
    def interval_check():
        return "curl https://<organisation>.highway.solutions/health"

Observability
-------------

Track running workflows:

.. code-block:: python

    # Non-blocking submit
    result = driver.run(wait=False)
    run_id = result.run_id

    # Check status
    status = driver.status(run_id)
    print(status.state)

    # Get logs
    logs = driver.logs(run_id)

    # Cancel
    driver.cancel(run_id)

Long-Running Workflows
----------------------

For workflows that take minutes to complete, submit and check status later:

.. code-block:: python

    # Submit and exit immediately
    result = driver.run(wait=False, timeout=600)
    print(f"Run ID: {result.run_id}")
    # Driver can exit, workflow continues on Highway

    # Later, check status
    status = driver.status(result.run_id)
    if status.status == "completed":
        print("Workflow finished!")

For tasks longer than 30 seconds, set appropriate ``timeout`` values:

.. code-block:: python

    @driver.task(shell=True, timeout=120)  # 2 minute timeout
    def long_running_task():
        return "sleep 90 && echo 'Done'"

Persistence
-----------

Highway Driver uses SQLite for local state persistence at ``stabilize.db``.
This enables:

- Submit workflow, exit driver, check status later
- Resume from crashes
- Idempotent execution

The database is created automatically in your working directory.

Framework Integration
---------------------

Highway Driver integrates with web frameworks. See ``examples/integrations/``:

FastAPI Example
~~~~~~~~~~~~~~~

.. code-block:: python

    from fastapi import FastAPI
    from highway import Driver

    app = FastAPI()
    driver = Driver()

    @app.post("/submit")
    async def submit_workflow(data: dict):
        result = driver.run(wait=False)
        return {"run_id": result.run_id}

    @app.get("/status/{run_id}")
    async def get_status(run_id: str):
        return driver.status(run_id)

Flask Example
~~~~~~~~~~~~~

.. code-block:: python

    from flask import Flask, jsonify
    from highway import Driver

    app = Flask(__name__)
    driver = Driver()

    @app.post("/submit")
    def submit_workflow():
        result = driver.run(wait=False)
        return jsonify({"run_id": result.run_id})

See ``examples/integrations/`` for full implementations with WebSocket/SSE support.

Idempotency
-----------

Use workflow IDs for idempotent execution:

.. code-block:: python

    result1 = driver.run(workflow_id="order-12345")
    result2 = driver.run(workflow_id="order-12345")  # Returns cached result

Examples
--------

The ``examples/`` directory contains runnable examples:

- ``simple_shell.py`` - Basic shell task
- ``multi_step.py`` - Task dependencies
- ``python_func.py`` - Python code execution
- ``http_tasks.py`` - HTTP requests
- ``parallel.py`` - Parallel execution
- ``llm_agentic.py`` - LLM-powered workflow
- ``long_running/`` - Submit and check status later
- ``integrations/`` - Flask/FastAPI integration

Run examples::

    export HIGHWAY_API_KEY="your-key"
    python examples/simple_shell.py

Requirements
------------

- Python 3.11+
- Highway API key (get from https://highway.solutions)

License
-------

Apache 2.0
