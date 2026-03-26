# -*- coding: utf-8 -*-
"""Edge case tests for multi-user mode functionality."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from copaw.app.shared_workspace_manager import SharedWorkspaceManager
from copaw.app.runner.session import sanitize_filename


class TestUserIdEdgeCases:
    """Tests for edge cases in user ID handling."""

    def test_user_id_with_special_characters(self) -> None:
        """Test user IDs with special characters are sanitized."""
        special_ids = [
            "user@example.com",
            "user/name",
            "user\\name",
            "user:name",
            "user*name",
            'user"name',
            "user<name>",
            "user|name",
            "user?name",
        ]

        for user_id in special_ids:
            sanitized = sanitize_filename(user_id)
            # Should not contain any unsafe characters
            assert "/" not in sanitized
            assert "\\" not in sanitized
            assert ":" not in sanitized
            assert "*" not in sanitized
            assert '"' not in sanitized
            assert "<" not in sanitized
            assert ">" not in sanitized
            assert "|" not in sanitized
            assert "?" not in sanitized

    def test_user_id_with_unicode(self) -> None:
        """Test user IDs with unicode characters."""
        unicode_ids = [
            "用户123",
            "пользователь",
            "ユーザー",
            "user",
        ]

        for user_id in unicode_ids:
            sanitized = sanitize_filename(user_id)
            # Should return a valid string
            assert isinstance(sanitized, str)
            assert len(sanitized) > 0

    def test_sanitize_filename_replaces_unsafe_chars(self) -> None:
        """Test sanitize_filename replaces unsafe characters with --."""
        result = sanitize_filename("discord:dm:12345")
        assert result == "discord--dm--12345"

    def test_agent_id_sanitization_is_more_strict(self) -> None:
        """Test _sanitize_agent_id is more strict than sanitize_filename."""
        from copaw.app.multi_agent_manager import _sanitize_agent_id

        # Test control characters
        result = _sanitize_agent_id("user\x00name")
        assert "\x00" not in result

        # Test length truncation
        long_id = "a" * 200
        result = _sanitize_agent_id(long_id)
        assert len(result) <= 100

        # Test whitespace trimming
        result = _sanitize_agent_id("  user123  ")
        assert result == "user123"

        # Test empty/None handling
        assert _sanitize_agent_id("") == "unknown"
        assert _sanitize_agent_id(None) == "unknown"


class TestSharedWorkspaceManagerEdgeCases:
    """Edge case tests for SharedWorkspaceManager."""

    @pytest.mark.asyncio
    async def test_concurrent_ensure_user_space(self, tmp_path: Path) -> None:
        """Test concurrent calls to ensure_user_space for same user."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        # Run multiple times
        results = []
        for _ in range(10):
            results.append(manager.ensure_user_space("concurrent_user"))

        # All should return the same path
        assert len(set(str(r) for r in results)) == 1

    def test_user_space_with_existing_files(self, tmp_path: Path) -> None:
        """Test user space when files already exist."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        # Pre-create some files
        user_dir = manager.get_user_space_dir("existing_user")
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "existing_file.txt").write_text("existing content")

        # Ensure user space should not remove existing files
        manager.ensure_user_space("existing_user")

        assert (user_dir / "existing_file.txt").exists()
        assert (
            user_dir / "existing_file.txt"
        ).read_text() == "existing content"

    def test_workspace_manager_repr_when_running(self, tmp_path: Path) -> None:
        """Test repr when workspace is running."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        # Mock a running workspace
        manager.workspace = MagicMock()

        repr_str = repr(manager)
        assert "running" in repr_str

    def test_get_user_context_creates_space(self, tmp_path: Path) -> None:
        """Test get_user_context creates space if not exists."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        # Space should not exist yet
        user_dir = manager.get_user_space_dir("new_user")
        assert not user_dir.exists()

        # get_user_context should create it
        context = manager.get_user_context("new_user")

        assert user_dir.exists()
        assert context["user_id"] == "new_user"

    def test_list_user_spaces_empty(self, tmp_path: Path) -> None:
        """Test list_user_spaces when no spaces exist."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        assert manager.list_user_spaces() == []

    def test_list_user_spaces_ignores_hidden(self, tmp_path: Path) -> None:
        """Test list_user_spaces ignores hidden directories."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        # Create regular user spaces
        manager.ensure_user_space("user1")
        manager.ensure_user_space("user2")

        # Create hidden directory
        users_root = manager.get_users_root()
        hidden_dir = users_root / ".hidden"
        hidden_dir.mkdir(parents=True, exist_ok=True)

        user_ids = manager.list_user_spaces()
        assert "user1" in user_ids
        assert "user2" in user_ids
        assert ".hidden" not in user_ids


class TestConfigEdgeCases:
    """Edge case tests for configuration."""

    def test_config_with_missing_agents(self) -> None:
        """Test config with missing agents section."""
        from copaw.config.config import Config

        config = Config()
        assert config.agents is not None
        assert config.agents.active_agent == "default"

    def test_mode_from_invalid_string(self) -> None:
        """Test invalid mode string raises error."""
        from pydantic import ValidationError
        from copaw.config.config import Config

        with pytest.raises(ValidationError):
            Config(multi_user_mode="invalid_mode")  # type: ignore

    def test_config_json_roundtrip(self) -> None:
        """Test config can be serialized and deserialized."""
        from copaw.config.config import Config, MultiUserMode

        original = Config(
            multi_user_mode=MultiUserMode.SHARED_AGENT,
        )

        # Serialize to JSON
        json_str = original.model_dump_json()

        # Deserialize
        restored = Config.model_validate_json(json_str)

        assert restored.multi_user_mode == MultiUserMode.SHARED_AGENT


class TestEnvContextEdgeCases:
    """Edge case tests for environment context."""

    def test_env_context_with_none_values(self) -> None:
        """Test env context with None values."""
        from copaw.app.runner.utils import build_env_context

        ctx = build_env_context(
            session_id=None,
            user_id=None,
            channel=None,
            working_dir=None,
            user_space_dir=None,
            users_root=None,
        )

        # Should still have valid output
        assert "====================" in ctx
        assert "OS:" in ctx
        assert "Current date:" in ctx

    def test_env_context_with_empty_strings(self) -> None:
        """Test env context with empty strings."""
        from copaw.app.runner.utils import build_env_context

        ctx = build_env_context(
            session_id="",
            user_id="",
            channel="",
            working_dir="",
        )

        # Should handle gracefully
        assert isinstance(ctx, str)

    def test_env_context_with_very_long_values(self) -> None:
        """Test env context with very long values."""
        from copaw.app.runner.utils import build_env_context

        long_id = "a" * 1000

        ctx = build_env_context(
            session_id=long_id,
            user_id=long_id,
            working_dir="/path/" + long_id,
        )

        assert long_id in ctx


class TestSystemPromptEdgeCases:
    """Edge case tests for system prompt generation."""

    def test_prompt_with_special_user_id(self) -> None:
        """Test prompt with special characters in user_id."""
        from copaw.agents.prompt import build_system_prompt_from_working_dir

        prompt = build_system_prompt_from_working_dir(
            agent_id="shared",
            user_id="user@example.com",
            user_space_dir="/users/user@example.com",
            users_root="/users",
        )

        assert "user@example.com" in prompt

    def test_prompt_with_empty_user_context(self) -> None:
        """Test prompt with empty user context values."""
        from copaw.agents.prompt import build_system_prompt_from_working_dir

        # Empty user_id should not add user context
        prompt = build_system_prompt_from_working_dir(
            agent_id="shared",
            user_id="",
            user_space_dir="",
            users_root="",
        )

        # Should not have user context section
        assert "Current User Context" not in prompt

    def test_prompt_with_unicode_paths(self) -> None:
        """Test prompt with unicode in paths."""
        from copaw.agents.prompt import build_system_prompt_from_working_dir

        prompt = build_system_prompt_from_working_dir(
            agent_id="shared",
            user_id="用户",
            user_space_dir="/users/用户",
            users_root="/users",
        )

        assert "用户" in prompt
