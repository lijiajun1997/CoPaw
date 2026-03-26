# -*- coding: utf-8 -*-
"""Tests for MultiAgentManager dual mode support."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from copaw.app.multi_agent_manager import MultiAgentManager
from copaw.config.config import MultiUserMode, Config, AgentProfileRef


class TestMultiAgentManagerDualMode:
    """Tests for MultiAgentManager with dual mode support."""

    def test_init(self) -> None:
        """Test initialization."""
        manager = MultiAgentManager()
        assert manager.agents == {}
        assert manager._shared_workspace_manager is None

    def test_get_shared_workspace_manager_none_when_not_shared(self) -> None:
        """Test get_shared_workspace_manager returns None in MULTI_AGENT mode."""
        manager = MultiAgentManager()
        assert manager.get_shared_workspace_manager() is None

    def test_get_user_space_dir_returns_none_in_multi_agent_mode(self) -> None:
        """Test get_user_space_dir returns None in MULTI_AGENT mode."""
        manager = MultiAgentManager()
        assert manager.get_user_space_dir("user123") is None

    def test_get_user_files_dir_returns_none_in_multi_agent_mode(self) -> None:
        """Test get_user_files_dir returns None in MULTI_AGENT mode."""
        manager = MultiAgentManager()
        assert manager.get_user_files_dir("user123") is None

    def test_get_user_tasks_dir_returns_none_in_multi_agent_mode(self) -> None:
        """Test get_user_tasks_dir returns None in MULTI_AGENT mode."""
        manager = MultiAgentManager()
        assert manager.get_user_tasks_dir("user123") is None

    def test_get_user_context_returns_none_in_multi_agent_mode(self) -> None:
        """Test get_user_context returns None in MULTI_AGENT mode."""
        manager = MultiAgentManager()
        assert manager.get_user_context("user123") is None

    def test_is_agent_loaded_shared_mode(self) -> None:
        """Test is_agent_loaded for shared workspace."""
        manager = MultiAgentManager()

        # Initially not loaded
        assert not manager.is_agent_loaded("shared")

        # Mock shared workspace manager
        mock_shared_manager = MagicMock()
        mock_shared_manager.workspace = MagicMock()
        manager._shared_workspace_manager = mock_shared_manager

        assert manager.is_agent_loaded("shared")

    def test_list_loaded_agents_includes_shared(self) -> None:
        """Test list_loaded_agents includes shared when active."""
        manager = MultiAgentManager()

        # No shared workspace
        assert "shared" not in manager.list_loaded_agents()

        # Mock shared workspace manager
        mock_shared_manager = MagicMock()
        mock_shared_manager.workspace = MagicMock()
        manager._shared_workspace_manager = mock_shared_manager

        assert "shared" in manager.list_loaded_agents()

    @pytest.mark.asyncio
    async def test_stop_agent_for_shared_workspace(self) -> None:
        """Test stop_agent for shared workspace."""
        manager = MultiAgentManager()

        # Mock shared workspace manager
        mock_shared_manager = MagicMock()
        mock_shared_manager.stop = AsyncMock()
        manager._shared_workspace_manager = mock_shared_manager

        result = await manager.stop_agent("shared")

        assert result is True
        mock_shared_manager.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_agent_for_shared_when_not_running(self) -> None:
        """Test stop_agent for shared when not running."""
        manager = MultiAgentManager()

        result = await manager.stop_agent("shared")

        assert result is False


class TestMultiAgentManagerSharedMode:
    """Tests for MultiAgentManager in SHARED_AGENT mode."""

    @pytest.fixture
    def mock_config_shared(self, tmp_path: Path) -> MagicMock:
        """Create mock config for shared mode."""
        config = MagicMock(spec=Config)
        config.multi_user_mode = MultiUserMode.SHARED_AGENT
        config.agents = MagicMock()
        config.agents.profiles = {
            "shared": AgentProfileRef(
                id="shared",
                workspace_dir=str(tmp_path / "workspaces" / "shared"),
            ),
        }
        return config

    @pytest.mark.asyncio
    async def test_get_agent_in_shared_mode(
        self,
        tmp_path: Path,
        mock_config_shared: MagicMock,
    ) -> None:
        """Test get_agent returns shared workspace in SHARED_AGENT mode."""
        manager = MultiAgentManager()

        with patch(
            "copaw.app.multi_agent_manager.load_config",
            return_value=mock_config_shared,
        ):
            with patch(
                "copaw.app.multi_agent_manager.SharedWorkspaceManager",
            ) as MockSharedManager:
                mock_shared_manager = MagicMock()
                mock_workspace = MagicMock()
                mock_shared_manager.get_or_create_workspace = AsyncMock(
                    return_value=mock_workspace,
                )
                mock_shared_manager.ensure_user_space = MagicMock()
                MockSharedManager.return_value = mock_shared_manager

                workspace = await manager.get_agent(
                    agent_id="any",
                    user_id="user123",
                )

                assert workspace is mock_workspace
                mock_shared_manager.ensure_user_space.assert_called_with(
                    "user123"
                )

    @pytest.mark.asyncio
    async def test_get_user_space_dir_in_shared_mode(
        self,
        tmp_path: Path,
        mock_config_shared: MagicMock,
    ) -> None:
        """Test get_user_space_dir works after shared workspace is created."""
        manager = MultiAgentManager()

        with patch(
            "copaw.app.multi_agent_manager.load_config",
            return_value=mock_config_shared,
        ):
            with patch(
                "copaw.app.multi_agent_manager.SharedWorkspaceManager",
            ) as MockSharedManager:
                mock_shared_manager = MagicMock()
                mock_shared_manager.get_user_space_dir = MagicMock(
                    return_value=tmp_path / "users" / "user123",
                )
                MockSharedManager.return_value = mock_shared_manager

                # First, initialize the shared workspace manager
                manager._shared_workspace_manager = mock_shared_manager

                user_dir = manager.get_user_space_dir("user123")
                assert user_dir == tmp_path / "users" / "user123"


class TestMultiAgentManagerMultiAgentMode:
    """Tests for MultiAgentManager in MULTI_AGENT mode."""

    @pytest.fixture
    def mock_config_multi(self, tmp_path: Path) -> MagicMock:
        """Create mock config for multi-agent mode."""
        config = MagicMock(spec=Config)
        config.multi_user_mode = MultiUserMode.MULTI_AGENT
        config.agents = MagicMock()
        config.agents.profiles = {
            "default": AgentProfileRef(
                id="default",
                workspace_dir=str(tmp_path / "workspaces" / "default"),
            ),
            "user123": AgentProfileRef(
                id="user123",
                workspace_dir=str(tmp_path / "workspaces" / "user123"),
            ),
        }
        return config

    @pytest.mark.asyncio
    async def test_get_agent_creates_user_workspace(
        self,
        tmp_path: Path,
        mock_config_multi: MagicMock,
    ) -> None:
        """Test get_agent creates workspace for user in MULTI_AGENT mode."""
        manager = MultiAgentManager()

        with patch(
            "copaw.app.multi_agent_manager.load_config",
            return_value=mock_config_multi,
        ):
            with patch(
                "copaw.app.multi_agent_manager.Workspace",
            ) as MockWorkspace:
                mock_workspace = MagicMock()
                mock_workspace.start = AsyncMock()
                mock_workspace.agent_id = "user123"
                mock_workspace.runner = MagicMock()
                MockWorkspace.return_value = mock_workspace

                workspace = await manager.get_agent("user123")

                assert workspace is mock_workspace
                assert "user123" in manager.agents
