# -*- coding: utf-8 -*-
"""Tests for SharedWorkspaceManager."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from copaw.app.shared_workspace_manager import SharedWorkspaceManager


class TestSharedWorkspaceManager:
    """Tests for SharedWorkspaceManager class."""

    def test_init(self, tmp_path: Path) -> None:
        """Test initialization."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)
        assert manager.workspace_dir == tmp_path
        assert manager.workspace is None
        assert manager._user_spaces == {}

    def test_get_user_space_dir(self, tmp_path: Path) -> None:
        """Test user space directory path generation."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        user_dir = manager.get_user_space_dir("user123")
        assert user_dir == tmp_path / "users" / "user123"

    def test_get_user_space_dir_sanitizes_user_id(
        self, tmp_path: Path
    ) -> None:
        """Test user ID is sanitized for directory name."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        # Test with special characters (should be sanitized)
        user_dir = manager.get_user_space_dir("user:test/123")
        assert "user:test" not in str(user_dir)
        assert "users" in str(user_dir)

    def test_ensure_user_space_creates_directories(
        self, tmp_path: Path
    ) -> None:
        """Test ensure_user_space creates required directories."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        user_dir = manager.ensure_user_space("user123")

        assert user_dir.exists()
        assert (user_dir / "files").exists()
        assert (user_dir / "tasks").exists()

    def test_ensure_user_space_caches_path(self, tmp_path: Path) -> None:
        """Test ensure_user_space caches the path."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        manager.ensure_user_space("user123")
        assert "user123" in manager._user_spaces

        # Second call should use cache (path object equality)
        user_dir2 = manager.ensure_user_space("user123")
        assert manager._user_spaces["user123"] == user_dir2

    def test_get_user_files_dir(self, tmp_path: Path) -> None:
        """Test user files directory path."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        files_dir = manager.get_user_files_dir("user123")
        assert files_dir == tmp_path / "users" / "user123" / "files"
        assert files_dir.exists()

    def test_get_user_tasks_dir(self, tmp_path: Path) -> None:
        """Test user tasks directory path."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        tasks_dir = manager.get_user_tasks_dir("user123")
        assert tasks_dir == tmp_path / "users" / "user123" / "tasks"
        assert tasks_dir.exists()

    def test_get_users_root(self, tmp_path: Path) -> None:
        """Test users root directory path."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        users_root = manager.get_users_root()
        assert users_root == tmp_path / "users"

    def test_get_user_context(self, tmp_path: Path) -> None:
        """Test user context generation."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        context = manager.get_user_context("user123")

        assert context["user_id"] == "user123"
        assert "user_space" in context
        assert "user_files" in context
        assert "user_tasks" in context
        assert "users_root" in context
        assert "user123" in context["user_space"]

    def test_multiple_users(self, tmp_path: Path) -> None:
        """Test multiple users have separate spaces."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        manager.ensure_user_space("user1")
        manager.ensure_user_space("user2")
        manager.ensure_user_space("user3")

        assert len(manager._user_spaces) == 3
        assert (tmp_path / "users" / "user1").exists()
        assert (tmp_path / "users" / "user2").exists()
        assert (tmp_path / "users" / "user3").exists()

    def test_repr(self, tmp_path: Path) -> None:
        """Test string representation."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        repr_str = repr(manager)
        assert "SharedWorkspaceManager" in repr_str
        assert "stopped" in repr_str
        assert "users=0" in repr_str

    @pytest.mark.asyncio
    async def test_get_or_create_workspace_creates_on_first_call(
        self,
        tmp_path: Path,
    ) -> None:
        """Test get_or_create_workspace creates workspace on first call."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        with patch(
            "copaw.app.shared_workspace_manager.Workspace"
        ) as MockWorkspace:
            mock_workspace = MagicMock()
            mock_workspace.start = AsyncMock()
            MockWorkspace.return_value = mock_workspace

            workspace = await manager.get_or_create_workspace()

            assert workspace is mock_workspace
            assert manager.workspace is mock_workspace
            MockWorkspace.assert_called_once_with(
                agent_id="shared",
                workspace_dir=str(tmp_path),
            )

    @pytest.mark.asyncio
    async def test_get_or_create_workspace_returns_existing(
        self, tmp_path: Path
    ) -> None:
        """Test get_or_create_workspace returns existing workspace."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        mock_workspace = MagicMock()
        manager.workspace = mock_workspace

        workspace = await manager.get_or_create_workspace()

        assert workspace is mock_workspace

    @pytest.mark.asyncio
    async def test_stop(self, tmp_path: Path) -> None:
        """Test stop method."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        mock_workspace = MagicMock()
        mock_workspace.stop = AsyncMock()
        manager.workspace = mock_workspace

        await manager.stop()

        mock_workspace.stop.assert_called_once()
        assert manager.workspace is None

    @pytest.mark.asyncio
    async def test_stop_when_no_workspace(self, tmp_path: Path) -> None:
        """Test stop when no workspace exists."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        # Should not raise
        await manager.stop()
        assert manager.workspace is None

    def test_list_user_spaces(self, tmp_path: Path) -> None:
        """Test listing all user spaces."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        # Initially empty
        assert manager.list_user_spaces() == []

        # Create some user spaces
        manager.ensure_user_space("user1")
        manager.ensure_user_space("user2")
        manager.ensure_user_space("user3")

        user_ids = manager.list_user_spaces()
        assert len(user_ids) == 3
        assert "user1" in user_ids
        assert "user2" in user_ids
        assert "user3" in user_ids

    def test_clear_user_cache_single(self, tmp_path: Path) -> None:
        """Test clearing cache for a single user."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        manager.ensure_user_space("user1")
        manager.ensure_user_space("user2")

        assert len(manager._user_spaces) == 2

        manager.clear_user_cache("user1")

        assert len(manager._user_spaces) == 1
        assert "user1" not in manager._user_spaces
        assert "user2" in manager._user_spaces

        # Directory should still exist (cache only)
        assert (tmp_path / "users" / "user1").exists()

    def test_clear_user_cache_all(self, tmp_path: Path) -> None:
        """Test clearing cache for all users."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        manager.ensure_user_space("user1")
        manager.ensure_user_space("user2")

        assert len(manager._user_spaces) == 2

        manager.clear_user_cache()

        assert len(manager._user_spaces) == 0

    def test_empty_user_id_handling(self, tmp_path: Path) -> None:
        """Test handling of empty user ID."""
        manager = SharedWorkspaceManager(workspace_dir=tmp_path)

        # Empty string
        user_dir = manager.get_user_space_dir("")
        assert user_dir.name == "unknown"

        # Whitespace only
        user_dir2 = manager.get_user_space_dir("   ")
        assert user_dir2.name == "unknown"

        # None-like (would fail type check but test sanitization)
        user_dir3 = manager.get_user_space_dir("valid_user")
        assert user_dir3.name == "valid_user"
