# -*- coding: utf-8 -*-
"""Tests for user input formatting utilities."""
from __future__ import annotations

from copaw.agents.user_input_formatter import (
    format_user_interrupt,
    format_user_interrupt_ack,
    format_user_interrupt_batch_ack,
)


class TestFormatUserInterrupt:
    """Tests for format_user_interrupt function."""

    def test_basic_format(self) -> None:
        """Test basic message formatting."""
        msg = format_user_interrupt("Please use Python 3.11")

        assert msg.name == "system"
        assert msg.role == "system"
        assert isinstance(msg.content, list)
        assert len(msg.content) == 1

        text = msg.content[0].get("text", "")
        assert "用户补充信息" in text
        assert "Please use Python 3.11" in text
        assert "调整当前计划" in text

    def test_format_with_pending_count(self) -> None:
        """Test formatting with pending count hint."""
        msg = format_user_interrupt("Fix the bug", pending_count=2)

        text = msg.content[0].get("text", "")
        assert "还有 2 条待处理消息" in text

    def test_format_with_zero_pending(self) -> None:
        """Test formatting with zero pending count (no hint shown)."""
        msg = format_user_interrupt("Continue", pending_count=0)

        text = msg.content[0].get("text", "")
        assert "待处理消息" not in text

    def test_format_long_message(self) -> None:
        """Test formatting a long message."""
        long_msg = "A" * 500
        msg = format_user_interrupt(long_msg)

        text = msg.content[0].get("text", "")
        assert long_msg in text

    def test_format_multiline_message(self) -> None:
        """Test formatting a multiline message."""
        multiline = "Line 1\nLine 2\nLine 3"
        msg = format_user_interrupt(multiline)

        text = msg.content[0].get("text", "")
        assert "Line 1" in text
        assert "Line 2" in text
        assert "Line 3" in text

    def test_format_chinese_message(self) -> None:
        """Test formatting a Chinese message."""
        msg = format_user_interrupt("请修改文件名为 test.py")

        text = msg.content[0].get("text", "")
        assert "请修改文件名为 test.py" in text


class TestFormatUserInterruptAck:
    """Tests for format_user_interrupt_ack function."""

    def test_basic_ack(self) -> None:
        """Test basic acknowledgment message."""
        ack = format_user_interrupt_ack("Please use Python 3.11")

        assert "已收到补充信息" in ack
        assert "Please use Python 3.11" in ack
        assert "将在当前操作完成后处理" in ack

    def test_ack_truncates_long_message(self) -> None:
        """Test long message is truncated in preview."""
        long_msg = "A" * 100
        ack = format_user_interrupt_ack(long_msg)

        # Should contain preview with ellipsis
        assert "..." in ack
        assert len(ack) < len(long_msg) + 200  # Should be reasonably short

    def test_ack_short_message_unchanged(self) -> None:
        """Test short message is shown in full."""
        short_msg = "Fix this"
        ack = format_user_interrupt_ack(short_msg)

        assert short_msg in ack
        assert "..." not in ack or "..." not in ack.split("\n")[1]

    def test_ack_format_structure(self) -> None:
        """Test acknowledgment message structure."""
        ack = format_user_interrupt_ack("Test message")

        # Should have checkmark icon
        assert "✅" in ack
        # Should have quote format
        assert ">" in ack


class TestFormatUserInterruptBatchAck:
    """Tests for format_user_interrupt_batch_ack function."""

    def test_single_message(self) -> None:
        """Test batch ack for single message."""
        ack = format_user_interrupt_batch_ack(1)

        assert "已收到 1 条补充信息" in ack
        assert "将在当前操作完成后依次处理" in ack

    def test_multiple_messages(self) -> None:
        """Test batch ack for multiple messages."""
        ack = format_user_interrupt_batch_ack(5)

        assert "已收到 5 条补充信息" in ack
        assert "依次处理" in ack

    def test_format_structure(self) -> None:
        """Test batch ack message structure."""
        ack = format_user_interrupt_batch_ack(3)

        # Should have checkmark icon
        assert "✅" in ack
