"""WorkflowHandle for async workflow management.

Provides a simple interface for tracking and managing workflow execution.
Uses descriptors for lazy-loaded properties and supports async/await.

Example:
    handle = driver.start_workflow()
    print(handle.status)      # Property access - fetches fresh status
    result = handle.result    # Blocks until complete, then cached

    # Or with async
    result = await handle     # WorkflowHandle is awaitable!
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from highway.result import WorkflowResult

if TYPE_CHECKING:
    from highway.driver import Driver


class _LazyResult:
    """Descriptor for lazy-loaded, cached workflow result.

    On first access, polls until workflow completes, then caches the result.
    Subsequent accesses return the cached value without polling.
    """

    def __get__(self, obj: WorkflowHandle | None, objtype: type | None = None) -> WorkflowResult:
        if obj is None:
            # Class-level access
            return self  # type: ignore
        if not hasattr(obj, "_cached_result"):
            obj._cached_result = obj._poll_until_complete()
        return obj._cached_result

    def __set__(self, obj: WorkflowHandle, value: WorkflowResult) -> None:
        obj._cached_result = value


class WorkflowHandle:
    """Handle for tracking and managing a workflow execution.

    Provides a simple, property-based interface for workflow management.
    All complexity is hidden - just access properties like .status and .result.

    Attributes:
        run_id: The workflow run ID (read-only)
        status: Current workflow status (always fetches fresh, no caching)
        result: Final workflow result (blocks until complete, then cached)
        logs: Execution logs (always fetches fresh)

    Example:
        # Start workflow and get handle
        handle = driver.start_workflow()

        # Check status (fresh each time)
        print(handle.status.state)

        # Get result (blocks until done, then cached)
        result = handle.result
        print(result.tasks)

        # Cancel if needed
        handle.cancel()

        # Async usage
        result = await handle  # Awaitable!
    """

    # Descriptor for lazy-loaded result
    result = _LazyResult()

    def __init__(
        self,
        run_id: str,
        driver: Driver,
        timeout: float = 300,
    ) -> None:
        """Initialize workflow handle.

        Args:
            run_id: The workflow run ID
            driver: The Driver instance that created this workflow
            timeout: Default timeout for blocking operations (seconds)
        """
        self._run_id = run_id
        self._driver = driver
        self._timeout = timeout

    @property
    def run_id(self) -> str:
        """Get the workflow run ID."""
        return self._run_id

    @property
    def status(self) -> WorkflowResult:
        """Get current workflow status (fresh, not cached).

        Returns:
            WorkflowResult with current state and task statuses
        """
        return self._driver.status(self._run_id)

    @property
    def logs(self) -> list[dict[str, Any]]:
        """Get execution logs (fresh, not cached).

        Returns:
            List of log entries from the workflow execution
        """
        return self._driver.logs(self._run_id)

    def cancel(self) -> bool:
        """Cancel the workflow execution.

        Returns:
            True if cancellation was successful
        """
        return self._driver.cancel(self._run_id)

    def wait(self, timeout: float | None = None) -> WorkflowResult:
        """Wait for workflow completion.

        Unlike accessing .result, this doesn't cache and allows custom timeout.

        Args:
            timeout: Maximum time to wait (seconds). Uses default if None.

        Returns:
            WorkflowResult with final state
        """
        return self._poll_until_complete(timeout or self._timeout)

    def _poll_until_complete(self, timeout: float | None = None) -> WorkflowResult:
        """Poll until workflow completes or times out.

        Uses exponential backoff: starts at 0.1s, increases to max 5s.

        Args:
            timeout: Maximum time to wait (seconds)

        Returns:
            WorkflowResult with final state
        """
        timeout = timeout or self._timeout
        start_time = time.time()
        poll_interval = 0.1  # Start with 100ms
        max_interval = 5.0  # Max 5 seconds between polls

        while True:
            status = self._driver.status(self._run_id)

            if status.state.is_terminal():
                return status

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                # Return current status even if not terminal
                return status

            # Exponential backoff
            time.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, max_interval)

    def __await__(self):
        """Make WorkflowHandle awaitable.

        Allows: result = await handle

        Returns:
            Generator that yields the final WorkflowResult
        """
        return self._poll_until_complete_async().__await__()

    async def _poll_until_complete_async(self, timeout: float | None = None) -> WorkflowResult:
        """Async version of polling.

        Uses asyncio.sleep for non-blocking waits.

        Args:
            timeout: Maximum time to wait (seconds)

        Returns:
            WorkflowResult with final state
        """
        timeout = timeout or self._timeout
        start_time = time.time()
        poll_interval = 0.1
        max_interval = 5.0

        while True:
            # TODO: Use async status when available
            status = self._driver.status(self._run_id)

            if status.state.is_terminal():
                return status

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                return status

            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, max_interval)

    def __repr__(self) -> str:
        """String representation."""
        try:
            state = self.status.state.value
        except Exception:
            state = "unknown"
        return f"<WorkflowHandle run_id={self._run_id!r} state={state!r}>"
