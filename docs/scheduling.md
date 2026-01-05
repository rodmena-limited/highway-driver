# Scheduling

Schedule workflows to run at specific times or intervals.

## Cron Syntax

Use cron expressions for precise scheduling:

```python
@driver.task(shell=True, schedule="0 * * * *")  # Every hour
def hourly_backup():
    return "pg_dump mydb > backup.sql"

@driver.task(shell=True, schedule="0 0 * * *")  # Daily at midnight
def daily_report():
    return "python generate_report.py"

@driver.task(shell=True, schedule="0 9 * * 1")  # Monday 9am
def weekly_summary():
    return "python weekly_summary.py"
```

## Interval Scheduling

Use timedelta for simple intervals:

```python
from datetime import timedelta

@driver.task(shell=True, schedule=timedelta(minutes=30))
def interval_check():
    return "curl https://api.example.com/health"

@driver.task(shell=True, schedule=timedelta(hours=6))
def periodic_sync():
    return "python sync_data.py"
```

## Cron Format Reference

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, Sunday=0)
│ │ │ │ │
* * * * *
```

Examples:
- `*/15 * * * *` - Every 15 minutes
- `0 */2 * * *` - Every 2 hours
- `0 9-17 * * 1-5` - Hourly 9am-5pm weekdays
