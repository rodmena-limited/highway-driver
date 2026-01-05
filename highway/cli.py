"""CLI commands for monitoring Highway workflows.

This module provides command-line tools for monitoring workflows
stored in the local SQLite database.

Usage:
    highway list                  # List all workflows
    highway list --status running # List running workflows
    highway status <id>           # Get workflow status
    highway stats                 # Show aggregate statistics
"""

from __future__ import annotations

# Use simple argparse to avoid adding click dependency
import argparse
import sys
from typing import cast


def list_workflows(args: argparse.Namespace) -> int:
    """List workflows from local store."""
    try:
        from highway.monitor import WorkflowMonitor

        monitor = WorkflowMonitor(args.db)
        workflows = monitor.list_workflows(
            status=args.status,
            limit=args.limit,
        )

        if not workflows:
            print("No workflows found.")
            return 0

        # Print header
        print(f"{'ID':<40} {'STATUS':<12} {'HIGHWAY':<12} {'DURATION':<10} NAME")
        print("-" * 100)

        for wf in workflows:
            highway_status = wf.highway_status or "-"
            print(
                f"{wf.execution_id:<40} "
                f"{wf.status:<12} "
                f"{highway_status:<12} "
                f"{wf.duration:<10} "
                f"{wf.name}"
            )

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def show_status(args: argparse.Namespace) -> int:
    """Show detailed workflow status."""
    try:
        from highway.monitor import WorkflowMonitor

        monitor = WorkflowMonitor(args.db)
        wf = monitor.get_workflow(args.execution_id)

        if not wf:
            print(f"Workflow not found: {args.execution_id}", file=sys.stderr)
            return 1

        print(f"Execution ID:    {wf.execution_id}")
        print(f"Name:            {wf.name}")
        print(f"Status:          {wf.status}")
        print(f"Duration:        {wf.duration}")

        if wf.highway_run_id:
            print(f"Highway Run ID:  {wf.highway_run_id}")
        if wf.highway_status:
            print(f"Highway Status:  {wf.highway_status}")
        if wf.highway_current_step:
            print(f"Current Step:    {wf.highway_current_step}")

        completed, total = wf.progress
        print(f"Progress:        {completed}/{total} stages")

        if wf.started_at:
            print(f"Started:         {wf.started_at}")
        if wf.completed_at:
            print(f"Completed:       {wf.completed_at}")

        if wf.error:
            print(f"Error:           {wf.error}")

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def show_stats(args: argparse.Namespace) -> int:
    """Show aggregate workflow statistics."""
    try:
        from highway.monitor import WorkflowMonitor

        monitor = WorkflowMonitor(args.db)
        stats = monitor.get_stats()
        queue = monitor.get_queue_stats()

        print("Workflow Statistics")
        print("-" * 30)
        print(f"Running:    {stats['running']}")
        print(f"Succeeded:  {stats['succeeded']}")
        print(f"Failed:     {stats['failed']}")
        print(f"Total:      {stats['total']}")

        print()
        print("Queue Statistics")
        print("-" * 30)
        print(f"Pending:    {queue['pending']}")
        print(f"Processing: {queue['processing']}")
        print(f"Stuck:      {queue['stuck']}")

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="highway",
        description="Highway workflow monitoring CLI",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to SQLite database (default: ~/.highway/workflows.db)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list command
    list_parser = subparsers.add_parser("list", help="List workflows")
    list_parser.add_argument(
        "--status",
        choices=["running", "succeeded", "failed", "all"],
        default=None,
        help="Filter by status",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of workflows to show",
    )
    list_parser.set_defaults(func=list_workflows)

    # status command
    status_parser = subparsers.add_parser("status", help="Show workflow status")
    status_parser.add_argument("execution_id", help="Workflow execution ID")
    status_parser.set_defaults(func=show_status)

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Show aggregate statistics")
    stats_parser.set_defaults(func=show_stats)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    return cast(int, args.func(args))


if __name__ == "__main__":
    sys.exit(main())
