# Observability

Track and manage running workflows.

## Non-Blocking Execution

Submit a workflow without waiting:

```python
result = driver.run(wait=False)
run_id = result.run_id
print(f"Submitted: {run_id}")
```

## Check Status

Query workflow status:

```python
status = driver.status(run_id)
print(status.state)       # RUNNING, COMPLETED, FAILED, etc.
print(status.is_terminal) # True when workflow finished (completed/failed)
print(status.tasks)       # Task results when complete
```

## Cancel Workflow

Cancel a running workflow:

```python
driver.cancel(run_id)
```

## Logs

> **Note:** The `logs()` method returns an empty list. Stabilize stores workflow state but not execution logs. For detailed logs, use the Highway dashboard.

```python
logs = driver.logs(run_id)  # Returns []
```

## List Workflows

List recent workflow executions:

```python
workflows = driver.list_workflows(limit=10)
for wf in workflows:
    print(f"{wf.run_id}: {wf.state}")
```

## Long-Running Workflows

For workflows that take minutes to complete, submit and check later:

```python
# Submit and exit immediately
result = driver.run(wait=False, timeout=600)
print(f"Run ID: {result.run_id}")
# Driver can exit, workflow continues on Highway

# Later, check status
status = driver.status(result.run_id)
if status.is_terminal:
    print("Workflow finished!")
    print(status.tasks)
```

## Idempotency

Use workflow IDs for idempotent execution:

```python
result1 = driver.run(workflow_id="order-12345")
result2 = driver.run(workflow_id="order-12345")  # Returns cached result
```

Same workflow_id = same execution. Safe for retries.
