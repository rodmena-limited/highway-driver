# Framework Integration

Highway Driver integrates with web frameworks for async workflow execution.

## FastAPI

```python
from fastapi import FastAPI
from highway import Driver

app = FastAPI()
driver = Driver()

@driver.task(shell=True)
def process_order():
    return "echo 'Processing order'"

@app.post("/submit")
async def submit_workflow(data: dict):
    result = driver.run(wait=False, inputs=data)
    return {"run_id": result.run_id}

@app.get("/status/{run_id}")
async def get_status(run_id: str):
    status = driver.status(run_id)
    return {
        "state": status.state.value,
        "is_terminal": status.is_terminal,
        "tasks": status.tasks
    }

@app.delete("/cancel/{run_id}")
async def cancel_workflow(run_id: str):
    driver.cancel(run_id)
    return {"cancelled": True}
```

## Flask

```python
from flask import Flask, jsonify, request
from highway import Driver

app = Flask(__name__)
driver = Driver()

@driver.task(shell=True)
def process_order():
    return "echo 'Processing order'"

@app.post("/submit")
def submit_workflow():
    data = request.get_json()
    result = driver.run(wait=False, inputs=data)
    return jsonify({"run_id": result.run_id})

@app.get("/status/<run_id>")
def get_status(run_id):
    status = driver.status(run_id)
    return jsonify({
        "state": status.state.value,
        "is_terminal": status.is_terminal,
        "tasks": {k: v.result for k, v in (status.tasks or {}).items()}
    })
```

## Best Practices

1. **Use `wait=False`** for HTTP endpoints - don't block the request
2. **Store run_id** - return it to clients for status polling
3. **Set timeouts** - prevent workflows from running indefinitely
4. **Use workflow_id** - enable idempotent retries

## Full Examples

See `examples/integrations/` for complete implementations with:
- WebSocket/SSE status updates
- Error handling
- Background task queues
