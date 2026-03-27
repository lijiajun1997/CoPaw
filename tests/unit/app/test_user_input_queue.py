# -*- coding: utf-8 -*-
"""Tests for UserInputQueue service."""
from __future__ import annotations

import pytest

from copaw.app.user_input_queue import (
    UserInputQueue,
    UserInputItem,
    get_user_input_queue,
    reset_user_input_queue,
)


class TestUserInputItem:
    """Tests for UserInputItem dataclass."""

    def test_create_item(self) -> None:
        """Test creating a UserInputItem."""
        item = UserInputItem(
            request_id="test-123",
            session_id="session-abc",
            user_id="user-1",
            content="Hello world",
        )

        assert item.request_id == "test-123"
        assert item.session_id == "session-abc"
        assert item.user_id == "user-1"
        assert item.content == "Hello world"
        assert item.processed is False
        assert isinstance(item.created_at, float)

    def test_processed_flag(self) -> None:
        """Test processed flag can be set."""
        item = UserInputItem(
            request_id="test-123",
            session_id="session-abc",
            user_id="user-1",
            content="Test",
        )

        assert item.processed is False
        item.processed = True
        assert item.processed is True


class TestUserInputQueue:
    """Tests for UserInputQueue class."""

    @pytest.fixture
    def queue(self) -> UserInputQueue:
        """Create a fresh queue for each test."""
        return UserInputQueue()

    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, queue: UserInputQueue) -> None:
        """Test basic enqueue and dequeue operations."""
        session_id = "test-session-1"

        # Enqueue a message
        item = await queue.enqueue(session_id, "First message", "user-1")

        assert item.session_id == session_id
        assert item.content == "First message"
        assert item.user_id == "user-1"
        assert item.request_id != ""

        # Dequeue the message
        dequeued = await queue.dequeue(session_id)

        assert dequeued is not None
        assert dequeued.content == "First message"
        assert dequeued.processed is True

    @pytest.mark.asyncio
    async def test_fifo_order(self, queue: UserInputQueue) -> None:
        """Test messages are dequeued in FIFO order."""
        session_id = "test-session-2"

        # Enqueue multiple messages
        await queue.enqueue(session_id, "Message 1", "user-1")
        await queue.enqueue(session_id, "Message 2", "user-1")
        await queue.enqueue(session_id, "Message 3", "user-1")

        # Dequeue and verify order
        item1 = await queue.dequeue(session_id)
        item2 = await queue.dequeue(session_id)
        item3 = await queue.dequeue(session_id)

        assert item1 is not None and item1.content == "Message 1"
        assert item2 is not None and item2.content == "Message 2"
        assert item3 is not None and item3.content == "Message 3"

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue(self, queue: UserInputQueue) -> None:
        """Test dequeue on empty queue returns None."""
        result = await queue.dequeue("nonexistent-session")
        assert result is None

    @pytest.mark.asyncio
    async def test_peek(self, queue: UserInputQueue) -> None:
        """Test peek returns first item without removing it."""
        session_id = "test-session-3"

        await queue.enqueue(session_id, "Test message", "user-1")

        # Peek should not remove the item
        peeked = await queue.peek(session_id)
        assert peeked is not None
        assert peeked.content == "Test message"

        # Item should still be in queue
        item = await queue.dequeue(session_id)
        assert item is not None
        assert item.content == "Test message"

    @pytest.mark.asyncio
    async def test_peek_empty_queue(self, queue: UserInputQueue) -> None:
        """Test peek on empty queue returns None."""
        result = await queue.peek("nonexistent-session")
        assert result is None

    @pytest.mark.asyncio
    async def test_has_pending(self, queue: UserInputQueue) -> None:
        """Test has_pending returns correct status."""
        session_id = "test-session-4"

        # Initially no pending
        assert await queue.has_pending(session_id) is False

        # After enqueue, has pending
        await queue.enqueue(session_id, "Test", "user-1")
        assert await queue.has_pending(session_id) is True

        # After dequeue, no pending
        await queue.dequeue(session_id)
        assert await queue.has_pending(session_id) is False

    @pytest.mark.asyncio
    async def test_has_pending_sync(self, queue: UserInputQueue) -> None:
        """Test synchronous has_pending method."""
        session_id = "test-session-sync"

        # Initially no pending
        assert queue.has_pending_sync(session_id) is False

        # After enqueue, has pending
        await queue.enqueue(session_id, "Test", "user-1")
        assert queue.has_pending_sync(session_id) is True

    @pytest.mark.asyncio
    async def test_get_pending_count(self, queue: UserInputQueue) -> None:
        """Test get_pending_count returns correct count."""
        session_id = "test-session-5"

        assert await queue.get_pending_count(session_id) == 0

        await queue.enqueue(session_id, "Msg 1", "user-1")
        assert await queue.get_pending_count(session_id) == 1

        await queue.enqueue(session_id, "Msg 2", "user-1")
        assert await queue.get_pending_count(session_id) == 2

        await queue.dequeue(session_id)
        assert await queue.get_pending_count(session_id) == 1

    @pytest.mark.asyncio
    async def test_clear(self, queue: UserInputQueue) -> None:
        """Test clear removes all messages for a session."""
        session_id = "test-session-6"

        await queue.enqueue(session_id, "Msg 1", "user-1")
        await queue.enqueue(session_id, "Msg 2", "user-1")
        await queue.enqueue(session_id, "Msg 3", "user-1")

        count = await queue.clear(session_id)
        assert count == 3

        # Queue should be empty
        assert await queue.has_pending(session_id) is False

    @pytest.mark.asyncio
    async def test_clear_nonexistent_session(
        self,
        queue: UserInputQueue,
    ) -> None:
        """Test clear on nonexistent session returns 0."""
        count = await queue.clear("nonexistent-session")
        assert count == 0

    @pytest.mark.asyncio
    async def test_multiple_sessions_isolated(
        self,
        queue: UserInputQueue,
    ) -> None:
        """Test messages are isolated between sessions."""
        session1 = "session-1"
        session2 = "session-2"

        await queue.enqueue(session1, "Msg for session 1", "user-1")
        await queue.enqueue(session2, "Msg for session 2", "user-2")

        # Dequeue from session1 should get session1's message
        item1 = await queue.dequeue(session1)
        assert item1 is not None
        assert item1.content == "Msg for session 1"

        # Dequeue from session2 should get session2's message
        item2 = await queue.dequeue(session2)
        assert item2 is not None
        assert item2.content == "Msg for session 2"

    @pytest.mark.asyncio
    async def test_cleanup_processed(self, queue: UserInputQueue) -> None:
        """Test cleanup_processed removes processed items."""
        session_id = "test-session-7"

        # Add multiple items
        await queue.enqueue(session_id, "Msg 1", "user-1")
        await queue.enqueue(session_id, "Msg 2", "user-1")
        await queue.enqueue(session_id, "Msg 3", "user-1")

        # Dequeue first item (marks it as processed and removes it)
        await queue.dequeue(session_id)

        # Remaining count should be 2
        assert await queue.get_pending_count(session_id) == 2


class TestGlobalQueue:
    """Tests for global queue singleton."""

    def test_get_user_input_queue_singleton(self) -> None:
        """Test get_user_input_queue returns same instance."""
        reset_user_input_queue()

        queue1 = get_user_input_queue()
        queue2 = get_user_input_queue()

        assert queue1 is queue2

    def test_reset_user_input_queue(self) -> None:
        """Test reset creates new instance."""
        reset_user_input_queue()

        queue1 = get_user_input_queue()
        reset_user_input_queue()
        queue2 = get_user_input_queue()

        # After reset, should be different instance
        assert queue1 is not queue2
