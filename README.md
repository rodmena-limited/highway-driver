# Highway Driver

Python SDK for Highway Workflow Engine. Build durable workflows with simple decorators.

![Highway Workflow Engine UI](https://raw.githubusercontent.com/rodmena-limited/highway-driver/refs/heads/main/images/ux.png)

## Installation

```bash
pip install highway
```

## Quick Start

```python
from highway import Driver

driver = Driver()  # Uses HIGHWAY_API_KEY env var

# Define tasks that will run in parallel
@driver.task(py=True)
def fetch_users():
    return {"users": ["alice", "bob"], "count": 2}

@driver.task(py=True)
def fetch_orders():
    return {"orders": [1, 2, 3], "count": 3}

# Group them for parallel execution
driver.parallel("fetch_data", branches=["fetch_users", "fetch_orders"])

# This waits for the parallel group to complete
@driver.task(shell=True, depends=["fetch_data"])
def notify():
    return "echo 'All data fetched!'"

result = driver.run()
print(result.status)  # "completed"
```

## Features

- **Shell, Python, HTTP tasks** - Run commands, code, or API calls
- **Task dependencies** - Build DAGs with `depends=["task_name"]`
- **Retries with backoff** - Automatic retry on failure
- **Durable delays** - Sleep without consuming resources
- **LLM tool integration** - Build agentic workflows
- **Scheduling** - Cron or interval-based execution

## Documentation

- [Task Types](docs/tasks.md) - Shell, Python, HTTP, Tool, Workflow
- [Dependencies](docs/dependencies.md) - Task DAGs and inputs
- [Retries & Delays](docs/retries.md) - Retry config, durable delays
- [Scheduling](docs/scheduling.md) - Cron and interval scheduling
- [Observability](docs/observability.md) - Status, cancel, idempotency
- [Framework Integration](docs/integrations.md) - FastAPI, Flask

## Examples

See [`examples/`](examples/) for runnable examples:
- `simple_shell.py` - Basic shell task
- `multi_step.py` - Task dependencies
- `python_func.py` - Python code execution
- `parallel.py` - Parallel execution
- `llm_agentic.py` - LLM-powered workflow
- `integrations/` - Flask/FastAPI integration

```bash
export HIGHWAY_API_KEY="your-key"
python examples/simple_shell.py
```

## Configuration

```bash
export HIGHWAY_API_KEY="hw_k1_..."
export HIGHWAY_API_ENDPOINT="https://highway.solutions"  # optional
```

Or pass directly:

```python
driver = Driver(api_key="hw_k1_...", endpoint="https://highway.solutions")
```

## Requirements

- Python 3.11+
- Highway API key ([get one](https://highway.solutions))

## License

Apache 2.0
