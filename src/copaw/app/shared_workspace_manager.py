# -*- coding: utf-8 -*-
"""SharedWorkspaceManager: Manages shared agent workspace with user isolation.

In SHARED_AGENT mode, all users share a single Agent instance,
but each user has their own isolated file space for privacy.

Directory structure:
    workspaces/shared/
    ├── agent.json          # Shared agent config
    ├── AGENTS.md           # Agent prompts with user isolation rules
    ├── SOUL.md
    ├── PROFILE.md
    ├── sessions/           # Session storage (user_id_session_id.json)
    └── users/              # User file spaces
        ├── user_001/
        │   ├── files/      # User uploaded files
        │   └── tasks/      # User generated tasks/files
        └── user_002/
            ├── files/
            └── tasks/
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING

from .workspace import Workspace
from .runner.session import sanitize_filename

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SharedWorkspaceManager:
    """Manages shared workspace with user file space isolation.

    Features:
    - Single shared Workspace instance for all users
    - Per-user file space isolation (users/{user_id}/files, users/{user_id}/tasks)
    - Thread-safe user space creation
    - User context injection for agent prompts
    - Caching for improved performance
    """

    def __init__(self, workspace_dir: Path):
        """Initialize shared workspace manager.

        Args:
            workspace_dir: Path to the shared workspace directory
        """
        self.workspace_dir = Path(workspace_dir).expanduser()
        self.workspace: Optional[Workspace] = None
        self._lock = asyncio.Lock()
        self._user_spaces: Dict[str, Path] = {}  # user_id -> user_space_path cache
        self._user_context_cache: Dict[str, Dict[str, str]] = {}  # user_id -> context cache

        logger.debug(
            f"SharedWorkspaceManager initialized for: {self.workspace_dir}"
        )

    async def get_or_create_workspace(self) -> Workspace:
        """Get or create the shared workspace instance.

        Returns:
            Workspace: The shared workspace instance
        """
        if self.workspace is not None:
            return self.workspace

        async with self._lock:
            # Double-check after acquiring lock
            if self.workspace is not None:
                return self.workspace

            logger.info(f"Creating shared workspace at: {self.workspace_dir}")

            # Create and start workspace
            instance = Workspace(
                agent_id="shared",
                workspace_dir=str(self.workspace_dir),
            )

            try:
                await instance.start()
                self.workspace = instance
                logger.info("Shared workspace created and started successfully")
                return self.workspace
            except Exception as e:
                logger.error(f"Failed to start shared workspace: {e}")
                raise

    def get_user_space_dir(self, user_id: str) -> Path:
        """Get user's file space directory.

        Args:
            user_id: User identifier

        Returns:
            Path: Path to user's space directory

        Note:
            If user_id is empty or None, returns path for 'unknown' user.
        """
        if not user_id or not user_id.strip():
            safe_user_id = "unknown"
        else:
            safe_user_id = sanitize_filename(user_id)
        return self.workspace_dir / "users" / safe_user_id

    def ensure_user_space(self, user_id: str) -> Path:
        """Ensure user space exists and return the path.

        Creates the user space directory structure if it doesn't exist:
        - users/{user_id}/files/  - for uploaded files
        - users/{user_id}/tasks/  - for generated task files

        Args:
            user_id: User identifier

        Returns:
            Path: Path to user's space directory
        """
        user_dir = self.get_user_space_dir(user_id)

        # Check cache first
        if user_id in self._user_spaces:
            return self._user_spaces[user_id]

        # Create directories
        files_dir = user_dir / "files"
        tasks_dir = user_dir / "tasks"

        files_dir.mkdir(parents=True, exist_ok=True)
        tasks_dir.mkdir(parents=True, exist_ok=True)

        # Cache the path
        self._user_spaces[user_id] = user_dir

        logger.debug(f"Ensured user space for {user_id}: {user_dir}")
        return user_dir

    def get_user_files_dir(self, user_id: str) -> Path:
        """Get user's files directory for uploaded files.

        Args:
            user_id: User identifier

        Returns:
            Path: Path to user's files directory
        """
        self.ensure_user_space(user_id)
        return self.get_user_space_dir(user_id) / "files"

    def get_user_tasks_dir(self, user_id: str) -> Path:
        """Get user's tasks directory for generated task files.

        Args:
            user_id: User identifier

        Returns:
            Path: Path to user's tasks directory
        """
        self.ensure_user_space(user_id)
        return self.get_user_space_dir(user_id) / "tasks"

    def get_users_root(self) -> Path:
        """Get the root directory containing all user spaces.

        Returns:
            Path: Path to users root directory
        """
        return self.workspace_dir / "users"

    def get_user_context(self, user_id: str) -> Dict[str, str]:
        """Get user context for agent prompt injection.

        Uses caching to avoid redundant path computations.

        Args:
            user_id: User identifier

        Returns:
            Dict with user paths for prompt context
        """
        # Check cache first
        if user_id in self._user_context_cache:
            return self._user_context_cache[user_id]

        # Ensure space exists and build context
        self.ensure_user_space(user_id)
        user_space = str(self.get_user_space_dir(user_id))

        context = {
            "user_id": user_id,
            "user_space": user_space,
            "user_files": f"{user_space}/files",
            "user_tasks": f"{user_space}/tasks",
            "users_root": str(self.get_users_root()),
        }

        # Cache the result
        self._user_context_cache[user_id] = context
        return context

    def list_user_spaces(self) -> list[str]:
        """List all user IDs that have spaces created.

        Returns:
            List of user IDs (directory names under users/)
        """
        users_root = self.get_users_root()
        if not users_root.exists():
            return []

        user_ids = []
        for user_dir in users_root.iterdir():
            if user_dir.is_dir() and not user_dir.name.startswith("."):
                user_ids.append(user_dir.name)
        return sorted(user_ids)

    def clear_user_cache(self, user_id: Optional[str] = None) -> None:
        """Clear user space cache.

        Args:
            user_id: Specific user ID to clear, or None to clear all
        """
        if user_id:
            self._user_spaces.pop(user_id, None)
            self._user_context_cache.pop(user_id, None)
            logger.debug(f"Cleared cache for user: {user_id}")
        else:
            self._user_spaces.clear()
            self._user_context_cache.clear()
            logger.debug("Cleared all user space cache")

    async def stop(self):
        """Stop the shared workspace."""
        if self.workspace is None:
            return

        async with self._lock:
            if self.workspace is None:
                return

            logger.info("Stopping shared workspace")
            await self.workspace.stop()
            self.workspace = None
            logger.info("Shared workspace stopped")

    def __repr__(self) -> str:
        """String representation."""
        status = "running" if self.workspace else "stopped"
        user_count = len(self._user_spaces)
        return (
            f"SharedWorkspaceManager("
            f"workspace={self.workspace_dir}, "
            f"status={status}, "
            f"users={user_count})"
        )


__all__ = ["SharedWorkspaceManager"]
