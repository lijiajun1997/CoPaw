# -*- coding: utf-8 -*-
"""Integration tests for multi-user mode switching.

Tests the complete flow of switching between MULTI_AGENT and SHARED_AGENT modes.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from copaw.config.config import (
    Config,
    MultiUserMode,
    AgentsConfig,
    AgentProfileRef,
)
from copaw.app.multi_agent_manager import MultiAgentManager
from copaw.app.shared_workspace_manager import SharedWorkspaceManager


class TestModeSwitching:
    """Integration tests for mode switching."""

    @pytest.fixture
    def temp_workspace(self, tmp_path: Path) -> Path:
        """Create a temporary workspace directory."""
        workspace = tmp_path / "workspaces"
        workspace.mkdir(parents=True, exist_ok=True)

        # Create default workspace
        default_dir = workspace / "default"
        default_dir.mkdir(parents=True, exist_ok=True)

        # Create minimal agent.json
        agent_config = {
            "id": "default",
            "name": "Default Agent",
            "workspace_dir": str(default_dir),
        }
        with open(default_dir / "agent.json", "w", encoding="utf-8") as f:
            json.dump(agent_config, f)

        return workspace

    @pytest.fixture
    def multi_agent_config(self, temp_workspace: Path) -> Config:
        """Create config for MULTI_AGENT mode."""
        return Config(
            multi_user_mode=MultiUserMode.MULTI_AGENT,
            agents=AgentsConfig(
                active_agent="default",
                profiles={
                    "default": AgentProfileRef(
                        id="default",
                        workspace_dir=str(temp_workspace / "default"),
                    ),
                },
            ),
        )

    @pytest.fixture
    def shared_agent_config(self, temp_workspace: Path) -> Config:
        """Create config for SHARED_AGENT mode."""
        shared_dir = temp_workspace / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)

        return Config(
            multi_user_mode=MultiUserMode.SHARED_AGENT,
            agents=AgentsConfig(
                active_agent="shared",
                profiles={
                    "shared": AgentProfileRef(
                        id="shared",
                        workspace_dir=str(shared_dir),
                    ),
                },
            ),
        )

    @pytest.mark.asyncio
    async def test_multi_agent_mode_creates_separate_workspaces(
        self,
        multi_agent_config: Config,
    ) -> None:
        """Test MULTI_AGENT mode creates separate workspaces for different users."""
        manager = MultiAgentManager()

        with patch(
            "copaw.app.multi_agent_manager.load_config",
            return_value=multi_agent_config,
        ):
            with patch(
                "copaw.app.multi_agent_manager.Workspace"
            ) as MockWorkspace:
                # Mock workspace creation
                mock_ws1 = MagicMock()
                mock_ws1.start = AsyncMock()
                mock_ws1.agent_id = "user1"
                mock_ws1.runner = MagicMock()
                mock_ws1.set_manager = MagicMock()

                mock_ws2 = MagicMock()
                mock_ws2.start = AsyncMock()
                mock_ws2.agent_id = "user2"
                mock_ws2.runner = MagicMock()
                mock_ws2.set_manager = MagicMock()

                # First call creates user1, second creates user2
                MockWorkspace.side_effect = [mock_ws1, mock_ws2]

                # Mock the _ensure_user_agent_exists to add to config

                def mock_ensure(agent_id, _display_name):
                    # Simulate adding agent to config
                    multi_agent_config.agents.profiles[
                        agent_id
                    ] = AgentProfileRef(
                        id=agent_id,
                        workspace_dir=f"/workspaces/{agent_id}",
                    )

                with patch.object(
                    manager,
                    "_ensure_user_agent_exists",
                    side_effect=lambda aid, dn=None: mock_ensure(aid, dn),
                ):
                    # Get workspaces for two different users
                    ws1 = await manager.get_agent("user1")
                    ws2 = await manager.get_agent("user2")

                # Verify they are different instances
                assert ws1 is not ws2
                assert "user1" in manager.agents
                assert "user2" in manager.agents
                assert len(manager.agents) == 2

    @pytest.mark.asyncio
    async def test_shared_agent_mode_reuses_workspace(
        self,
        shared_agent_config: Config,
    ) -> None:
        """Test SHARED_AGENT mode reuses same workspace for different users."""
        manager = MultiAgentManager()

        with patch(
            "copaw.app.multi_agent_manager.load_config",
            return_value=shared_agent_config,
        ):
            with patch(
                "copaw.app.multi_agent_manager.SharedWorkspaceManager",
            ) as MockSharedManager:
                # Mock shared workspace manager
                mock_shared = MagicMock()
                mock_workspace = MagicMock()
                mock_shared.get_or_create_workspace = AsyncMock(
                    return_value=mock_workspace,
                )
                mock_shared.ensure_user_space = MagicMock()
                MockSharedManager.return_value = mock_shared

                # Get workspaces for two different users
                ws1 = await manager.get_agent("shared", user_id="user1")
                ws2 = await manager.get_agent("shared", user_id="user2")

                # Verify same workspace instance is returned
                assert ws1 is ws2
                assert ws1 is mock_workspace

                # Verify user spaces were created
                assert mock_shared.ensure_user_space.call_count == 2

    @pytest.mark.asyncio
    async def test_shared_mode_user_spaces_are_isolated(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that user spaces are properly isolated in shared mode."""
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)

        manager = SharedWorkspaceManager(workspace_dir=shared_dir)

        # Create spaces for multiple users
        user1_space = manager.ensure_user_space("user1")
        user2_space = manager.ensure_user_space("user2")

        # Verify isolation
        assert user1_space != user2_space
        assert "user1" in str(user1_space)
        assert "user2" in str(user2_space)

        # Verify directory structure
        assert (user1_space / "files").exists()
        assert (user1_space / "tasks").exists()
        assert (user2_space / "files").exists()
        assert (user2_space / "tasks").exists()

    def test_config_serialization_preserves_mode(self) -> None:
        """Test that config serialization preserves the multi_user_mode."""
        config = Config(multi_user_mode=MultiUserMode.SHARED_AGENT)

        # Serialize
        data = config.model_dump()

        # Deserialize
        config2 = Config(**data)

        assert config2.multi_user_mode == MultiUserMode.SHARED_AGENT

    def test_mode_switch_in_config(self) -> None:
        """Test switching modes in config."""
        config = Config()

        # Default is MULTI_AGENT
        assert config.multi_user_mode == MultiUserMode.MULTI_AGENT

        # Switch to SHARED_AGENT
        config.multi_user_mode = MultiUserMode.SHARED_AGENT
        assert config.multi_user_mode == MultiUserMode.SHARED_AGENT

        # Switch back
        config.multi_user_mode = MultiUserMode.MULTI_AGENT
        assert config.multi_user_mode == MultiUserMode.MULTI_AGENT


class TestEnvironmentContext:
    """Tests for environment context in different modes."""

    def test_env_context_includes_user_space_in_shared_mode(self) -> None:
        """Test env context includes user space info."""
        from copaw.app.runner.utils import build_env_context

        ctx = build_env_context(
            session_id="session1",
            user_id="user1",
            channel="test",
            working_dir="/workspace",
            user_space_dir="/workspace/users/user1",
            users_root="/workspace/users",
        )

        assert "User space:" in ctx
        assert "/workspace/users/user1" in ctx
        assert "Users root:" in ctx
        assert "/workspace/users" in ctx

    def test_env_context_without_user_space(self) -> None:
        """Test env context without user space info (MULTI_AGENT mode)."""
        from copaw.app.runner.utils import build_env_context

        ctx = build_env_context(
            session_id="session1",
            user_id="user1",
            channel="test",
            working_dir="/workspace",
        )

        assert "User space:" not in ctx
        assert "Users root:" not in ctx


class TestSystemPrompt:
    """Tests for system prompt generation in different modes."""

    def test_system_prompt_includes_user_isolation_rules(self) -> None:
        """Test system prompt includes user isolation rules in shared mode."""
        from copaw.agents.prompt import build_system_prompt_from_working_dir

        prompt = build_system_prompt_from_working_dir(
            agent_id="shared",
            user_id="user123",
            user_space_dir="/workspace/users/user123",
            users_root="/workspace/users",
        )

        assert "Current User Context" in prompt
        assert "user123" in prompt
        assert "User Data Isolation Rules" in prompt
        assert "/workspace/users/user123/files/" in prompt
        assert "/workspace/users/user123/tasks/" in prompt

    def test_system_prompt_without_user_context(self) -> None:
        """Test system prompt without user context (MULTI_AGENT mode)."""
        from copaw.agents.prompt import build_system_prompt_from_working_dir

        prompt = build_system_prompt_from_working_dir(
            agent_id="agent1",
        )

        assert "Current User Context" not in prompt
        assert "User Data Isolation Rules" not in prompt


class TestUserSpaceManagement:
    """Tests for user space management."""

    def test_user_space_file_operations(self, tmp_path: Path) -> None:
        """Test file operations within user spaces."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        # Get user files directory
        files_dir = manager.get_user_files_dir("test_user")

        # Create a test file
        test_file = files_dir / "test.txt"
        test_file.write_text("Hello, World!")

        assert test_file.exists()
        assert test_file.read_text() == "Hello, World!"

    def test_user_space_tasks_directory(self, tmp_path: Path) -> None:
        """Test tasks directory for user spaces."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        # Get user tasks directory
        tasks_dir = manager.get_user_tasks_dir("test_user")

        # Create a test task file
        task_file = tasks_dir / "task_001.md"
        task_file.write_text("# Task 001\n\nDescription...")

        assert task_file.exists()
        assert "Task 001" in task_file.read_text()

    def test_user_context_dict_structure(self, tmp_path: Path) -> None:
        """Test user context dictionary structure."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        context = manager.get_user_context("test_user")

        # Verify all expected keys
        expected_keys = [
            "user_id",
            "user_space",
            "user_files",
            "user_tasks",
            "users_root",
        ]
        for key in expected_keys:
            assert key in context

        # Verify values
        assert context["user_id"] == "test_user"
        assert "test_user" in context["user_space"]
        assert context["user_space"] in context["user_files"]
        assert context["user_space"] in context["user_tasks"]
