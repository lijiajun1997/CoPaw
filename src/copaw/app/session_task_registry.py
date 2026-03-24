# -*- coding: utf-8 -*-
"""Session task registry for tracking and cancelling running tasks.

This module provides a global registry to track session tasks across
all channels and agents, enabling /stop command functionality.
Includes timeout monitoring to automatically cancel stuck sessions.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Default session timeout in seconds (10 minutes)
DEFAULT_SESSION_TIMEOUT_SECONDS = 600


@dataclass
class SessionTaskInfo:
    """Information about a running session task."""

    task: asyncio.Task
    started_at: float = field(default_factory=time.time)
    session_id: str = ""
    channel_id: str = ""
    user_id: str = ""

    def elapsed_seconds(self) -> float:
        """Get elapsed time since task started."""
        return time.time() - self.started_at

    def is_timed_out(self, timeout_seconds: float = DEFAULT_SESSION_TIMEOUT_SECONDS) -> bool:
        """Check if task has exceeded timeout."""
        return self.elapsed_seconds() > timeout_seconds


class SessionTaskRegistry:
    """Thread-safe registry for session tasks with timeout monitoring.

    Provides centralized tracking of all session tasks with:
    - Thread-safe operations via asyncio.Lock
    - Automatic timeout detection
    - Batch cleanup of stale tasks
    """

    def __init__(self, timeout_seconds: float = DEFAULT_SESSION_TIMEOUT_SECONDS):
        self._tasks: dict[str, SessionTaskInfo] = {}
        self._lock = asyncio.Lock()
        self._timeout_seconds = timeout_seconds

    async def register(
        self,
        session_id: str,
        task: asyncio.Task,
        channel_id: str = "",
        user_id: str = "",
    ) -> None:
        """Register a task for a session.

        Args:
            session_id: Session identifier
            task: The asyncio task to register
            channel_id: Optional channel identifier
            user_id: Optional user identifier
        """
        if not session_id:
            return

        async with self._lock:
            # Cancel any existing task for this session
            existing = self._tasks.get(session_id)
            if existing and not existing.task.done():
                logger.warning(
                    "Registering new task for session %s, cancelling existing task",
                    session_id,
                )
                existing.task.cancel()

            self._tasks[session_id] = SessionTaskInfo(
                task=task,
                session_id=session_id,
                channel_id=channel_id,
                user_id=user_id,
            )
            logger.debug("Registered task for session: %s", session_id)

    async def unregister(self, session_id: str) -> None:
        """Unregister a task for a session.

        Args:
            session_id: Session identifier
        """
        async with self._lock:
            if session_id in self._tasks:
                del self._tasks[session_id]
                logger.debug("Unregistered task for session: %s", session_id)

    async def cancel(self, session_id: str) -> bool:
        """Cancel a running session task.

        Args:
            session_id: Session ID to cancel

        Returns:
            True if a task was cancelled, False otherwise
        """
        async with self._lock:
            info = self._tasks.get(session_id)
            if info is not None and not info.task.done():
                logger.info("Cancelling session task: %s", session_id)
                info.task.cancel()
                return True
            logger.debug("No running task found for session: %s", session_id)
            return False

    def is_running(self, session_id: str) -> bool:
        """Check if a session has a running task.

        Args:
            session_id: Session ID to check

        Returns:
            True if the session has an active task
        """
        info = self._tasks.get(session_id)
        return info is not None and not info.task.done()

    def get_elapsed_seconds(self, session_id: str) -> Optional[float]:
        """Get elapsed time for a session task.

        Args:
            session_id: Session ID to check

        Returns:
            Elapsed seconds if session is running, None otherwise
        """
        info = self._tasks.get(session_id)
        if info is not None and not info.task.done():
            return info.elapsed_seconds()
        return None

    async def get_timed_out_sessions(self) -> list[str]:
        """Get list of session IDs that have exceeded timeout.

        Returns:
            List of timed-out session IDs
        """
        async with self._lock:
            timed_out = []
            for session_id, info in self._tasks.items():
                if not info.task.done() and info.is_timed_out(self._timeout_seconds):
                    timed_out.append(session_id)
            return timed_out

    async def cleanup_timed_out_sessions(self) -> list[str]:
        """Cancel and clean up all timed-out sessions.

        Returns:
            List of cancelled session IDs
        """
        async with self._lock:
            cancelled = []
            for session_id, info in list(self._tasks.items()):
                if not info.task.done() and info.is_timed_out(self._timeout_seconds):
                    logger.warning(
                        "Session %s timed out after %.1f seconds, cancelling",
                        session_id,
                        info.elapsed_seconds(),
                    )
                    info.task.cancel()
                    cancelled.append(session_id)
                    del self._tasks[session_id]
            return cancelled

    async def cleanup_finished_tasks(self) -> int:
        """Remove finished tasks from registry.

        Returns:
            Number of tasks cleaned up
        """
        async with self._lock:
            finished = [
                session_id
                for session_id, info in self._tasks.items()
                if info.task.done()
            ]
            for session_id in finished:
                del self._tasks[session_id]
            return len(finished)

    def get_running_sessions(self) -> list[str]:
        """Get list of session IDs with running tasks.

        Returns:
            List of session IDs with active tasks
        """
        return [
            session_id
            for session_id, info in self._tasks.items()
            if not info.task.done()
        ]

    def get_task_for_session(self, session_id: str) -> Optional[asyncio.Task]:
        """Get the task for a session.

        Args:
            session_id: Session ID to get task for

        Returns:
            The asyncio.Task if exists, None otherwise
        """
        info = self._tasks.get(session_id)
        return info.task if info else None

    def get_all_task_info(self) -> dict[str, SessionTaskInfo]:
        """Get all task info (for monitoring/debugging).

        Returns:
            Copy of all task info
        """
        return dict(self._tasks)


# Global registry instance
_registry: Optional[SessionTaskRegistry] = None


def get_session_task_registry() -> SessionTaskRegistry:
    """Get the global session task registry instance."""
    global _registry
    if _registry is None:
        _registry = SessionTaskRegistry()
    return _registry


def set_session_task_registry(registry: SessionTaskRegistry) -> None:
    """Set the global session task registry instance."""
    global _registry
    _registry = registry


# Legacy API for backward compatibility (wraps global registry)
_session_tasks: dict[str, asyncio.Task] = {}  # Kept for legacy compatibility


def register_session_task(session_id: str, task: asyncio.Task) -> None:
    """Register a task for a session (legacy API).

    Args:
        session_id: Session identifier
        task: The asyncio task to register
    """
    if session_id:
        _session_tasks[session_id] = task
        logger.debug("Registered task for session: %s", session_id)
        # Also update the new registry if available
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # Schedule registration in the running loop
                asyncio.create_task(
                    get_session_task_registry().register(session_id, task),
                )
        except RuntimeError:
            pass


def unregister_session_task(session_id: str) -> None:
    """Unregister a task for a session (legacy API).

    Args:
        session_id: Session identifier
    """
    if session_id in _session_tasks:
        del _session_tasks[session_id]
        logger.debug("Unregistered task for session: %s", session_id)
    # Also update the new registry
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            asyncio.create_task(
                get_session_task_registry().unregister(session_id),
            )
    except RuntimeError:
        pass


def cancel_session_task(session_id: str) -> bool:
    """Cancel a running session task (legacy API).

    Args:
        session_id: Session ID to cancel

    Returns:
        True if a task was cancelled, False otherwise
    """
    task = _session_tasks.get(session_id)
    if task is not None and not task.done():
        logger.info("Cancelling session task: %s", session_id)
        task.cancel()
        return True
    logger.debug("No running task found for session: %s", session_id)
    return False


def is_session_running(session_id: str) -> bool:
    """Check if a session has a running task (legacy API).

    Args:
        session_id: Session ID to check

    Returns:
        True if the session has an active task
    """
    task = _session_tasks.get(session_id)
    return task is not None and not task.done()


def get_running_sessions() -> list[str]:
    """Get list of session IDs with running tasks (legacy API).

    Returns:
        List of session IDs with active tasks
    """
    return [
        sid
        for sid, task in _session_tasks.items()
        if not task.done()
    ]


def get_task_for_session(session_id: str) -> Optional[asyncio.Task]:
    """Get the task for a session (legacy API).

    Args:
        session_id: Session ID to get task for

    Returns:
        The asyncio.Task if exists, None otherwise
    """
    return _session_tasks.get(session_id)
