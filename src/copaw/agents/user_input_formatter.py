# -*- coding: utf-8 -*-
"""Format user interrupt messages for injection into Agent memory.

This module provides formatting utilities for user messages that are
injected during agent task execution.
"""
from __future__ import annotations

from agentscope.message import Msg


def format_user_interrupt(
    content: str,
    pending_count: int = 0,
) -> Msg:
    """Format user interrupt message as system prompt.

    Args:
        content: User message content
        pending_count: Number of remaining pending messages

    Returns:
        Formatted Msg object for injection into agent memory
    """
    hint = "📌 **用户补充信息 / User Additional Input**\n\n" f"{content}\n\n"

    if pending_count > 0:
        hint += f"_（还有 {pending_count} 条待处理消息）_\n\n"

    hint += (
        "请结合此信息判断是否需要：\n" "1. 调整当前计划\n" "2. 回应用户的问题\n" "3. 继续原定任务\n\n" "---"
    )

    return Msg(
        name="system",
        role="system",
        content=[
            {
                "type": "text",
                "text": hint,
            },
        ],
    )


def format_user_interrupt_ack(content: str) -> str:
    """Format acknowledgment message for user.

    Args:
        content: User message content (for preview)

    Returns:
        Acknowledgment message text
    """
    preview = content[:50] + "..." if len(content) > 50 else content
    return f"✅ **已收到补充信息**\n\n" f"> {preview}\n\n" f"将在当前操作完成后处理..."


def format_user_interrupt_batch_ack(count: int) -> str:
    """Format acknowledgment for multiple messages.

    Args:
        count: Number of messages received

    Returns:
        Acknowledgment message text
    """
    return f"✅ **已收到 {count} 条补充信息**\n\n" f"将在当前操作完成后依次处理..."
