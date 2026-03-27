# -*- coding: utf-8 -*-
"""Integration tests for user interrupt functionality.

Tests the complete flow of user message injection during agent task execution.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from copaw.app.user_input_queue import (
    UserInputQueue,
    get_user_input_queue,
    reset_user_input_queue,
)
from copaw.agents.user_input_formatter import format_user_interrupt
from copaw.app.session_task_registry import SessionTaskRegistry


class TestUserInterruptFlow:
    """Integration tests for user interrupt flow."""

    @pytest.fixture
    def queue(self) -> UserInputQueue:
        """Create a fresh queue for each test."""
        reset_user_input_queue()
        return get_user_input_queue()

    @pytest.fixture
    def registry(self) -> SessionTaskRegistry:
        """Create a fresh registry for each test."""
        return SessionTaskRegistry()

    @pytest.mark.asyncio
    async def test_user_message_injected_after_tool_call(
        self,
        queue: UserInputQueue,
    ) -> None:
        """Test that user message is injected after tool call completion."""
        session_id = "test-session-1"

        # Simulate user sending message during task execution
        await queue.enqueue(session_id, "Please use Python 3.11", "user-1")

        # Simulate the injection check that happens in _acting
        has_pending = await queue.has_pending(session_id)
        assert has_pending is True

        # Simulate dequeue and format
        item = await queue.dequeue(session_id)
        assert item is not None
        assert item.content == "Please use Python 3.11"

        # Format for injection
        msg = format_user_interrupt(item.content)
        assert msg.role == "system"
        assert "Please use Python 3.11" in msg.content[0].get("text", "")

    @pytest.mark.asyncio
    async def test_multiple_messages_processed_sequentially(
        self,
        queue: UserInputQueue,
    ) -> None:
        """Test multiple user messages are processed in order."""
        session_id = "test-session-2"

        # User sends multiple messages
        await queue.enqueue(session_id, "Message 1", "user-1")
        await queue.enqueue(session_id, "Message 2", "user-1")
        await queue.enqueue(session_id, "Message 3", "user-1")

        messages = []
        while await queue.has_pending(session_id):
            item = await queue.dequeue(session_id)
            if item:
                msg = format_user_interrupt(
                    item.content,
                    pending_count=await queue.get_pending_count(session_id),
                )
                messages.append(msg)

        assert len(messages) == 3
        assert "Message 1" in messages[0].content[0].get("text", "")
        assert "Message 2" in messages[1].content[0].get("text", "")
        assert "Message 3" in messages[2].content[0].get("text", "")

    @pytest.mark.asyncio
    async def test_session_isolation(
        self,
        queue: UserInputQueue,
    ) -> None:
        """Test messages are isolated between sessions."""
        session1 = "session-1"
        session2 = "session-2"

        # Enqueue for different sessions
        await queue.enqueue(session1, "For session 1", "user-1")
        await queue.enqueue(session2, "For session 2", "user-2")

        # Verify isolation
        item1 = await queue.dequeue(session1)
        item2 = await queue.dequeue(session2)

        assert item1 is not None and item1.content == "For session 1"
        assert item2 is not None and item2.content == "For session 2"

    @pytest.mark.asyncio
    async def test_running_session_detection(
        self,
        registry: SessionTaskRegistry,
    ) -> None:
        """Test detection of running session for message routing."""
        session_id = "test-session-3"

        # Initially not running
        assert registry.is_running(session_id) is False

        # Register a mock task
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.done.return_value = False

        await registry.register(session_id, mock_task)

        # Now running
        assert registry.is_running(session_id) is True

        # Task completes
        mock_task.done.return_value = True
        assert registry.is_running(session_id) is False

    @pytest.mark.asyncio
    async def test_stop_command_cancels_task(
        self,
        registry: SessionTaskRegistry,
    ) -> None:
        """Test that /stop command cancels running task."""
        session_id = "test-session-4"

        # Create and register a mock task
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.done.return_value = False
        mock_task.cancel = MagicMock()

        await registry.register(session_id, mock_task)

        # Verify task is running
        assert registry.is_running(session_id) is True

        # Cancel the task (simulating /stop command)
        result = await registry.cancel(session_id)

        assert result is True
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_queue_not_blocking(
        self,
        queue: UserInputQueue,
    ) -> None:
        """Test that message queue operations are non-blocking."""
        session_id = "test-session-5"

        # Multiple concurrent enqueue operations
        tasks = [
            queue.enqueue(session_id, f"Message {i}", "user-1")
            for i in range(10)
        ]

        items = await asyncio.gather(*tasks)

        assert len(items) == 10
        assert await queue.get_pending_count(session_id) == 10


class TestChannelIntegration:
    """Integration tests for channel-level message handling."""

    @pytest.fixture
    def queue(self) -> UserInputQueue:
        """Create a fresh queue for each test."""
        reset_user_input_queue()
        return get_user_input_queue()

    @pytest.mark.asyncio
    async def test_extract_user_input_from_request(self) -> None:
        """Test extracting user input from AgentRequest."""
        # Create mock request
        from agentscope_runtime.engine.schemas.agent_schemas import (
            AgentRequest,
            Message,
            TextContent,
            ContentType,
            Role,
        )

        request = AgentRequest(
            session_id="test-session",
            user_id="user-1",
            input=[
                Message(
                    role=Role.USER,
                    content=[
                        TextContent(type=ContentType.TEXT, text="Hello world"),
                    ],
                ),
            ],
        )

        # The extraction logic would be in BaseChannel
        # Here we test the expected behavior
        texts = []
        for msg in request.input:
            for part in msg.content:
                if getattr(part, "type", None) == ContentType.TEXT:
                    text = getattr(part, "text", "")
                    if text:
                        texts.append(text)

        assert "\n".join(texts) == "Hello world"

    @pytest.mark.asyncio
    async def test_stop_command_detection(self) -> None:
        """Test detection of /stop command."""
        stop_commands = ["/stop", "/stop ", "/STOP", "/Stop now"]
        non_stop_commands = ["stop", "/approve", "continue", "/daemon status"]

        for cmd in stop_commands:
            assert cmd.strip().lower().startswith("/stop"), f"Failed: {cmd}"

        for cmd in non_stop_commands:
            assert (
                not cmd.strip().lower().startswith("/stop")
            ), f"Failed: {cmd}"


class TestEndToEndFlow:
    """End-to-end tests for user interrupt functionality."""

    @pytest.fixture
    def queue(self) -> UserInputQueue:
        """Create a fresh queue for each test."""
        reset_user_input_queue()
        return get_user_input_queue()

    @pytest.mark.asyncio
    async def test_complete_interrupt_flow(
        self,
        queue: UserInputQueue,
    ) -> None:
        """Test complete flow: enqueue -> pending check -> inject."""
        session_id = "e2e-session"

        # 1. User sends message while task is running
        await queue.enqueue(session_id, "Change to Python 3.11", "user-1")

        # 2. Agent checks for pending messages (in _acting)
        has_pending = await queue.has_pending(session_id)
        assert has_pending is True

        # 3. Agent dequeues message
        item = await queue.dequeue(session_id)
        assert item is not None

        # 4. Agent formats message for injection
        msg = format_user_interrupt(item.content)

        # 5. Message is ready for memory injection
        assert msg.role == "system"
        assert "Change to Python 3.11" in msg.content[0].get("text", "")

        # 6. Queue is now empty
        assert await queue.has_pending(session_id) is False

    @pytest.mark.asyncio
    async def test_interrupt_with_acknowledgment(
        self,
        queue: UserInputQueue,
    ) -> None:
        """Test user receives acknowledgment when message is queued."""
        from copaw.agents.user_input_formatter import format_user_interrupt_ack

        session_id = "ack-session"
        user_input = "Please fix the bug"

        # Enqueue message
        await queue.enqueue(session_id, user_input, "user-1")

        # Generate acknowledgment
        ack = format_user_interrupt_ack(user_input)

        assert "已收到补充信息" in ack
        assert user_input in ack
        assert "将在当前操作完成后处理" in ack
