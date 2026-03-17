# -*- coding: utf-8 -*-
"""Session task registry for tracking and cancelling running tasks.

This module provides a global registry to track session tasks across
all channels and agents, enabling /stop command functionality.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Global registry: session_id -> asyncio.Task
_session_tasks: dict[str, asyncio.Task] = {}


def register_session_task(session_id: str, task: asyncio.Task) -> None:
    """Register a task for a session.

    Args:
        session_id: Session identifier
        task: The asyncio task to register
    """
    if session_id:
        _session_tasks[session_id] = task
        logger.debug("Registered task for session: %s", session_id)


def unregister_session_task(session_id: str) -> None:
    """Unregister a task for a session.

    Args:
        session_id: Session identifier
    """
    if session_id in _session_tasks:
        del _session_tasks[session_id]
        logger.debug("Unregistered task for session: %s", session_id)


def cancel_session_task(session_id: str) -> bool:
    """Cancel a running session task.

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
    """Check if a session has a running task.

    Args:
        session_id: Session ID to check

    Returns:
        True if the session has an active task
    """
    task = _session_tasks.get(session_id)
    return task is not None and not task.done()


def get_running_sessions() -> list[str]:
    """Get list of session IDs with running tasks.

    Returns:
        List of session IDs with active tasks
    """
    return [
        sid
        for sid, task in _session_tasks.items()
        if not task.done()
    ]


def get_task_for_session(session_id: str) -> Optional[asyncio.Task]:
    """Get the task for a session.

    Args:
        session_id: Session ID to get task for

    Returns:
        The asyncio.Task if exists, None otherwise
    """
    return _session_tasks.get(session_id)
