# Retries & Delays

## Retry Configuration

Configure automatic retries with exponential backoff:

```python
@driver.task(http=True, retries=3, retry_delay=2.0, backoff=2.0)
def call_flaky_api():
    return {"url": "https://api.example.com/endpoint"}
```

Parameters:
- `retries`: Number of retry attempts (default: 0)
- `retry_delay`: Initial delay between retries in seconds (default: 1.0)
- `backoff`: Multiplier for exponential backoff (default: 1.0)

Example with backoff=2.0 and retry_delay=2.0:
- Attempt 1: immediate
- Attempt 2: wait 2s
- Attempt 3: wait 4s
- Attempt 4: wait 8s

## Durable Delays

Use Highway's native WaitOperator for delays that consume zero worker resources:

```python
from datetime import timedelta

@driver.task(shell=True, delay=timedelta(hours=2))
def delayed_task():
    return "echo 'Runs after 2 hour delay'"
```

The delay is durable - if the system restarts, the timer continues.

## Task Timeouts

Set timeouts for individual tasks:

```python
@driver.task(shell=True, timeout=120)  # 2 minute timeout
def long_running_task():
    return "sleep 90 && echo 'Done'"
```

## Workflow Timeouts

Set overall workflow timeout:

```python
result = driver.run(timeout=300)  # 5 minute workflow timeout
```
