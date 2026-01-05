# Task Dependencies

Tasks can depend on other tasks to create execution DAGs (Directed Acyclic Graphs).

## Basic Dependencies

Use the `depends` parameter to specify which tasks must complete first:

```python
@driver.task(shell=True)
def step_1():
    return "echo 'Step 1'"

@driver.task(shell=True, depends=["step_1"])
def step_2():
    return "echo 'Step 2'"

@driver.task(shell=True, depends=["step_2"])
def step_3():
    return "echo 'Step 3'"
```

## Multiple Dependencies

A task can depend on multiple upstream tasks:

```python
@driver.task(shell=True)
def fetch_users():
    return "curl https://api.example.com/users"

@driver.task(shell=True)
def fetch_orders():
    return "curl https://api.example.com/orders"

@driver.task(py=True, depends=["fetch_users", "fetch_orders"])
def combine_data():
    # Both fetch tasks complete before this runs
    return {"combined": True}
```

## Parallel Execution

Tasks without dependencies run in parallel:

```python
@driver.task(shell=True)
def task_a():
    return "echo 'A'"

@driver.task(shell=True)
def task_b():
    return "echo 'B'"

@driver.task(shell=True)
def task_c():
    return "echo 'C'"

# A, B, C all run in parallel
```

## Accessing Upstream Results

Use template syntax to access results from upstream tasks:

```python
@driver.task(shell=True)
def get_date():
    return "date +%Y-%m-%d"

@driver.task(shell=True, depends=["get_date"])
def use_date():
    return "echo 'Today is {{get_date.stdout}}'"
```

## Workflow Inputs

Pass variables when running:

```python
result = driver.run(
    inputs={"email": "user@example.com", "env": "prod"},
    timeout=300
)
```

Access inputs in tasks via `{{inputs.key}}` syntax.
