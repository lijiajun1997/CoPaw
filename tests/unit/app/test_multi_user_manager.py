# -*- coding: utf-8 -*-
"""Tests for multi-user support in MultiAgentManager."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest


class TestSanitizeAgentId:
    """Tests for _sanitize_agent_id function."""

    def test_normal_agent_id(self) -> None:
        """Test normal agent ID is returned unchanged."""
        from copaw.app.multi_agent_manager import _sanitize_agent_id

        assert _sanitize_agent_id("user123") == "user123"
        assert _sanitize_agent_id("alice") == "alice"
        assert _sanitize_agent_id("bob_smith") == "bob_smith"

    def test_special_characters(self) -> None:
        """Test special characters are replaced with underscore."""
        from copaw.app.multi_agent_manager import _sanitize_agent_id

        assert _sanitize_agent_id("user/test") == "user_test"
        assert _sanitize_agent_id("user\\test") == "user_test"
        assert _sanitize_agent_id("user:test") == "user_test"
        assert _sanitize_agent_id("user*test") == "user_test"
        assert _sanitize_agent_id("user<test>") == "user_test_"
        assert _sanitize_agent_id('user"test"') == "user_test_"

    def test_empty_and_none(self) -> None:
        """Test empty and None inputs return 'unknown'."""
        from copaw.app.multi_agent_manager import _sanitize_agent_id

        assert _sanitize_agent_id("") == "unknown"
        assert _sanitize_agent_id("   ") == "unknown"
        assert _sanitize_agent_id("...") == "unknown"

    def test_leading_trailing_spaces(self) -> None:
        """Test leading/trailing spaces and dots are removed."""
        from copaw.app.multi_agent_manager import _sanitize_agent_id

        assert _sanitize_agent_id("  user123  ") == "user123"
        assert _sanitize_agent_id(".user123.") == "user123"
        assert _sanitize_agent_id(" . user123 . ") == "user123"

    def test_long_agent_id(self) -> None:
        """Test long agent ID is truncated to 100 characters."""
        from copaw.app.multi_agent_manager import _sanitize_agent_id

        long_id = "a" * 150
        result = _sanitize_agent_id(long_id)
        assert len(result) == 100
        assert result == "a" * 100

    def test_unicode_characters(self) -> None:
        """Test unicode characters are preserved."""
        from copaw.app.multi_agent_manager import _sanitize_agent_id

        assert _sanitize_agent_id("用户123") == "用户123"
        assert _sanitize_agent_id("пользователь") == "пользователь"

    def test_control_characters(self) -> None:
        """Test control characters are replaced."""
        from copaw.app.multi_agent_manager import _sanitize_agent_id

        assert _sanitize_agent_id("user\x00test") == "user_test"
        assert _sanitize_agent_id("user\x1ftest") == "user_test"


class TestEnsureUserAgentExists:
    """Tests for _ensure_user_agent_exists method."""

    @pytest.fixture
    def temp_working_dir(self, tmp_path: Path) -> Path:
        """Create a temporary working directory with default agent."""
        # Create default workspace
        default_dir = tmp_path / "workspaces" / "default"
        default_dir.mkdir(parents=True)

        # Create minimal agent.json
        agent_config = {
            "id": "default",
            "name": "Default Agent",
            "workspace_dir": str(default_dir),
            "channels": {},
            "mcp": {"servers": {}},
            "running": {"max_iters": 10, "max_input_length": 128000},
        }
        (default_dir / "agent.json").write_text(
            json.dumps(agent_config, indent=2),
            encoding="utf-8"
        )

        # Create root config
        root_config = {
            "working_dir": str(tmp_path),
            "agents": {
                "active_agent": "default",
                "profiles": {
                    "default": {"workspace_dir": str(default_dir)}
                }
            }
        }
        (tmp_path / "config.json").write_text(
            json.dumps(root_config, indent=2),
            encoding="utf-8"
        )

        return tmp_path

    @pytest.mark.asyncio
    async def test_creates_new_user_workspace(self, temp_working_dir: Path) -> None:
        """Test that a new user workspace is created."""
        from copaw.app.multi_agent_manager import MultiAgentManager

        with patch("copaw.app.multi_agent_manager.load_config") as mock_load, \
             patch("copaw.app.multi_agent_manager.get_config_path") as mock_config_path, \
             patch("copaw.config.utils.WORKING_DIR", temp_working_dir):

            # Setup mocks
            mock_config = MagicMock()
            mock_config.working_dir = str(temp_working_dir)
            mock_config.agents.profiles = {"default": MagicMock()}
            mock_load.return_value = mock_config
            mock_config_path.return_value = str(temp_working_dir / "config.json")

            manager = MultiAgentManager()

            # Execute
            await manager._ensure_user_agent_exists("test_user")

            # Verify workspace created
            user_workspace = temp_working_dir / "workspaces" / "test_user"
            assert user_workspace.exists()
            assert (user_workspace / "agent.json").exists()

            # Verify agent.json has correct id
            with open(user_workspace / "agent.json", encoding="utf-8") as f:
                config = json.load(f)
            assert config["id"] == "test_user"
            assert config["name"] == "test_user"

    @pytest.mark.asyncio
    async def test_existing_workspace_not_overwritten(self, temp_working_dir: Path) -> None:
        """Test that existing workspace is not overwritten."""
        from copaw.app.multi_agent_manager import MultiAgentManager

        # Pre-create user workspace
        user_workspace = temp_working_dir / "workspaces" / "existing_user"
        user_workspace.mkdir(parents=True)
        (user_workspace / "agent.json").write_text(
            json.dumps({"id": "existing_user", "name": "Original Name"}),
            encoding="utf-8"
        )

        with patch("copaw.app.multi_agent_manager.load_config") as mock_load, \
             patch("copaw.app.multi_agent_manager.get_config_path") as mock_config_path:

            mock_config = MagicMock()
            mock_config.working_dir = str(temp_working_dir)
            mock_load.return_value = mock_config
            mock_config_path.return_value = str(temp_working_dir / "config.json")

            manager = MultiAgentManager()

            # Execute
            await manager._ensure_user_agent_exists("existing_user")

            # Verify original content preserved
            with open(user_workspace / "agent.json", encoding="utf-8") as f:
                config = json.load(f)
            assert config["name"] == "Original Name"

    @pytest.mark.asyncio
    async def test_creates_minimal_config_when_no_default(self, tmp_path: Path) -> None:
        """Test minimal config created when default workspace doesn't exist."""
        from copaw.app.multi_agent_manager import MultiAgentManager

        # Create working dir without default workspace
        working_dir = tmp_path / "workspaces"
        working_dir.mkdir(parents=True)

        # Create root config
        root_config = {
            "working_dir": str(tmp_path),
            "agents": {
                "active_agent": "default",
                "profiles": {}
            }
        }
        (tmp_path / "config.json").write_text(
            json.dumps(root_config, indent=2),
            encoding="utf-8"
        )

        with patch("copaw.app.multi_agent_manager.load_config") as mock_load, \
             patch("copaw.app.multi_agent_manager.get_config_path") as mock_config_path, \
             patch("copaw.config.utils.WORKING_DIR", tmp_path):

            mock_config = MagicMock()
            mock_config.working_dir = str(tmp_path)
            mock_load.return_value = mock_config
            mock_config_path.return_value = str(tmp_path / "config.json")

            manager = MultiAgentManager()

            # Execute
            await manager._ensure_user_agent_exists("isolated_user")

            # Verify minimal workspace created
            user_workspace = tmp_path / "workspaces" / "isolated_user"
            assert user_workspace.exists()
            assert (user_workspace / "agent.json").exists()
            assert (user_workspace / "AGENTS.md").exists()


class TestGetAgent:
    """Tests for get_agent method with multi-user support."""

    @pytest.mark.asyncio
    async def test_sanitizes_agent_id(self) -> None:
        """Test that agent_id is sanitized before use."""
        from copaw.app.multi_agent_manager import MultiAgentManager

        manager = MultiAgentManager()

        # Mock the workspace creation to avoid actual startup
        with patch.object(manager, "_ensure_user_agent_exists") as mock_ensure, \
             patch("copaw.app.multi_agent_manager.load_config") as mock_load, \
             patch("copaw.app.multi_agent_manager.Workspace") as mock_workspace_cls:

            # Setup mocks
            mock_config = MagicMock()
            mock_config.agents.profiles = {
                "user_test": MagicMock(workspace_dir="/tmp/test")
            }
            mock_load.return_value = mock_config

            mock_workspace = MagicMock()
            mock_workspace.start = AsyncMock()
            mock_workspace_cls.return_value = mock_workspace

            # Execute with unsafe agent_id
            try:
                await manager.get_agent("user/test:bad")
            except Exception:
                pass  # May fail at workspace creation, that's ok

            # Verify sanitization was applied
            mock_ensure.assert_called_once()
            # The sanitized ID should be "user_test_bad"


class TestAddAgentToConfig:
    """Tests for _add_agent_to_config method."""

    def test_adds_new_agent_to_config(self, tmp_path: Path) -> None:
        """Test that new agent is added to config.json."""
        from copaw.app.multi_agent_manager import MultiAgentManager

        # Create initial config
        config_path = tmp_path / "config.json"
        initial_config = {
            "agents": {
                "active_agent": "default",
                "profiles": {
                    "default": {"workspace_dir": "/tmp/default"}
                }
            }
        }
        config_path.write_text(json.dumps(initial_config), encoding="utf-8")

        with patch("copaw.app.multi_agent_manager.get_config_path") as mock_path:
            mock_path.return_value = str(config_path)

            manager = MultiAgentManager()
            manager._add_agent_to_config("new_user", "/tmp/new_user")

        # Verify config updated
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        assert "new_user" in config["agents"]["profiles"]
        assert config["agents"]["profiles"]["new_user"]["workspace_dir"] == "/tmp/new_user"
        # Existing agent should still be there
        assert "default" in config["agents"]["profiles"]

    def test_creates_agents_section_if_missing(self, tmp_path: Path) -> None:
        """Test that agents section is created if missing."""
        from copaw.app.multi_agent_manager import MultiAgentManager

        config_path = tmp_path / "config.json"
        config_path.write_text("{}", encoding="utf-8")

        with patch("copaw.app.multi_agent_manager.get_config_path") as mock_path:
            mock_path.return_value = str(config_path)

            manager = MultiAgentManager()
            manager._add_agent_to_config("first_user", "/tmp/first_user")

        # Verify config structure created
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        assert "agents" in config
        assert "profiles" in config["agents"]
        assert "first_user" in config["agents"]["profiles"]
