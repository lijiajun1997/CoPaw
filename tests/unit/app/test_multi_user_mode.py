# -*- coding: utf-8 -*-
"""Tests for MultiUserMode configuration."""
from __future__ import annotations

import pytest

from copaw.config.config import MultiUserMode, Config, AgentsConfig


class TestMultiUserMode:
    """Tests for MultiUserMode enum."""

    def test_enum_values(self) -> None:
        """Test MultiUserMode enum values."""
        assert MultiUserMode.MULTI_AGENT.value == "multi_agent"
        assert MultiUserMode.SHARED_AGENT.value == "shared_agent"

    def test_enum_count(self) -> None:
        """Test we have exactly two modes."""
        assert len(list(MultiUserMode)) == 2


class TestConfigWithMultiUserMode:
    """Tests for Config with multi_user_mode field."""

    def test_default_mode_is_multi_agent(self) -> None:
        """Test default mode is MULTI_AGENT."""
        config = Config()
        assert config.multi_user_mode == MultiUserMode.MULTI_AGENT

    def test_can_set_shared_agent_mode(self) -> None:
        """Test can set SHARED_AGENT mode."""
        config = Config(multi_user_mode=MultiUserMode.SHARED_AGENT)
        assert config.multi_user_mode == MultiUserMode.SHARED_AGENT

    def test_mode_from_string(self) -> None:
        """Test mode can be set from string value."""
        config = Config(multi_user_mode="shared_agent")  # type: ignore
        assert config.multi_user_mode == MultiUserMode.SHARED_AGENT

    def test_mode_serialization(self) -> None:
        """Test mode serializes correctly."""
        config = Config(multi_user_mode=MultiUserMode.SHARED_AGENT)
        data = config.model_dump()
        assert data["multi_user_mode"] == "shared_agent"

    def test_mode_deserialization(self) -> None:
        """Test mode deserializes correctly."""
        data = {"multi_user_mode": "shared_agent"}
        config = Config(**data)
        assert config.multi_user_mode == MultiUserMode.SHARED_AGENT

    def test_invalid_mode_raises_error(self) -> None:
        """Test invalid mode raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            Config(multi_user_mode="invalid_mode")  # type: ignore
