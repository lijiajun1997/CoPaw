# -*- coding: utf-8 -*-
"""User input queue for message injection during agent task execution.

This module provides a session-level queue for user messages when the
session has a running task. Messages are injected at the next checkpoint
(after tool call completion or before reasoning).

Similar pattern to session_task_registry.py and approval service.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class UserInputItem:
    """User input item for injection queue."""

    request_id: str
    session_id: str
    user_id: str
    content: str  # User message text
    created_at: float = field(default_factory=time.time)
    processed: bool = False


class UserInputQueue:
    """Session-level user message injection queue.

    When a session has a running task, new user messages are enqueued
    and injected at the next checkpoint (after tool call or before reasoning).
    """

    def __init__(self):
        self._queues: dict[str, list[UserInputItem]] = {}
        self._lock = asyncio.Lock()

    async def enqueue(
        self,
        session_id: str,
        content: str,
        user_id: str = "",
    ) -> UserInputItem:
        """Enqueue a user message for injection.

        Args:
            session_id: Session identifier
            content: User message content
            user_id: User identifier

        Returns:
            Created queue item
        """
        item = UserInputItem(
            request_id=uuid.uuid4().hex,
            session_id=session_id,
            user_id=user_id,
            content=content,
        )

        async with self._lock:
            if session_id not in self._queues:
                self._queues[session_id] = []
            self._queues[session_id].append(item)
            logger.info(
                "User input enqueued for session %s: %s",
                session_id[:16],
                content[:50] + "..." if len(content) > 50 else content,
            )

        return item

    async def dequeue(self, session_id: str) -> Optional[UserInputItem]:
        """Dequeue the earliest user message.

        Args:
            session_id: Session identifier

        Returns:
            Earliest queue item, or None if empty
        """
        async with self._lock:
            queue = self._queues.get(session_id, [])
            if not queue:
                return None
            item = queue.pop(0)
            item.processed = True

            # Clean up empty queue
            if not queue:
                del self._queues[session_id]

            logger.info(
                "User input dequeued for session %s",
                session_id[:16],
            )
            return item

    async def peek(self, session_id: str) -> Optional[UserInputItem]:
        """Peek at the earliest user message without removing.

        Args:
            session_id: Session identifier

        Returns:
            Earliest queue item, or None if empty
        """
        async with self._lock:
            queue = self._queues.get(session_id, [])
            return queue[0] if queue else None

    async def has_pending(self, session_id: str) -> bool:
        """Check if there are pending user messages.

        Args:
            session_id: Session identifier

        Returns:
            True if there are pending messages
        """
        async with self._lock:
            queue = self._queues.get(session_id, [])
            return len(queue) > 0

    def has_pending_sync(self, session_id: str) -> bool:
        """Synchronous check for pending user messages (for quick checks).

        Args:
            session_id: Session identifier

        Returns:
            True if there are pending messages
        """
        queue = self._queues.get(session_id, [])
        return len(queue) > 0

    async def clear(self, session_id: str) -> int:
        """Clear the queue for a session.

        Args:
            session_id: Session identifier

        Returns:
            Number of cleared messages
        """
        async with self._lock:
            queue = self._queues.pop(session_id, [])
            if queue:
                logger.info(
                    "Cleared %d user input(s) for session %s",
                    len(queue),
                    session_id[:16],
                )
            return len(queue)

    async def get_pending_count(self, session_id: str) -> int:
        """Get the count of pending messages.

        Args:
            session_id: Session identifier

        Returns:
            Number of pending messages
        """
        async with self._lock:
            queue = self._queues.get(session_id, [])
            return len(queue)

    async def cleanup_processed(self) -> int:
        """Remove processed items from all queues.

        Returns:
            Number of items removed
        """
        async with self._lock:
            removed = 0
            for session_id in list(self._queues.keys()):
                queue = self._queues[session_id]
                original_len = len(queue)
                self._queues[session_id] = [
                    item for item in queue if not item.processed
                ]
                if not self._queues[session_id]:
                    del self._queues[session_id]
                removed += original_len - len(self._queues.get(session_id, []))
            return removed


# Global singleton
_queue: Optional[UserInputQueue] = None


def get_user_input_queue() -> UserInputQueue:
    """Get the global UserInputQueue instance."""
    global _queue
    if _queue is None:
        _queue = UserInputQueue()
    return _queue


def reset_user_input_queue() -> None:
    """Reset the global queue (for testing)."""
    global _queue
    _queue = None
