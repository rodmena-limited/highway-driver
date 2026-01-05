# Task Types

Highway Driver supports multiple task types for different execution needs.

## Shell Tasks

Execute shell commands:

```python
@driver.task(shell=True)
def list_files():
    return "ls -la /tmp"
```

## Python Tasks

Execute Python code in Highway's sandboxed environment:

```python
@driver.task(py=True)
def compute():
    import math
    return {"factorial": math.factorial(10)}
```

## HTTP Tasks

Make HTTP requests:

```python
@driver.task(http=True)
def call_api():
    return {
        "url": "https://api.example.com/webhook",
        "method": "POST",
        "json": {"status": "done"},
    }
```

## Generic Tool Tasks

Call any Highway tool directly:

```python
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
```

## LLM Agentic Workflows

Build multi-step LLM workflows using `tools.llm.call`:

```python
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
```

## Workflow Execution

Execute other workflows:

```python
@driver.task(workflow="daily_report")
def run_report():
    return {"inputs": {"date": "2024-01-01"}}

@driver.task(workflow_id="uuid-here")
def run_specific_version():
    return {"inputs": {"mode": "production"}}
```
