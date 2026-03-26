# -*- coding: utf-8 -*-
"""MultiAgentManager: Manages multiple agent workspaces with lazy loading.

Provides centralized management for multiple Workspace objects,
including lazy loading, lifecycle management, and hot reloading.

Supports two multi-user modes:
- MULTI_AGENT: Each user has their own Agent instance (default)
- SHARED_AGENT: All users share one Agent with isolated file spaces
"""
import asyncio
import json
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Optional, Set, TYPE_CHECKING

from .workspace import Workspace
from .shared_workspace_manager import SharedWorkspaceManager
from ..config.utils import load_config, get_config_path
from ..config.config import MultiUserMode

if TYPE_CHECKING:
    from ..config.config import Config

logger = logging.getLogger(__name__)


def _sanitize_agent_id(agent_id: str) -> str:
    """Sanitize agent_id to be safe for use as directory name.

    Replaces or removes characters that are not safe for file paths.

    Args:
        agent_id: Raw agent ID (e.g., from channel user_id)

    Returns:
        Sanitized agent ID safe for use as directory name
    """
    if not agent_id:
        return "unknown"

    # Replace unsafe characters with underscore
    # Unsafe: / \ : * ? " < > | and control characters
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", agent_id)

    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(" .")

    # Ensure non-empty
    if not sanitized:
        return "unknown"

    # Truncate if too long (max 100 chars for reasonable path length)
    if len(sanitized) > 100:
        sanitized = sanitized[:100]

    return sanitized


# Global reference to MultiAgentManager instance
_multi_agent_manager_instance: Optional["MultiAgentManager"] = None


def get_multi_agent_manager() -> Optional["MultiAgentManager"]:
    """Get the global MultiAgentManager instance.

    Returns:
        MultiAgentManager instance or None if not initialized
    """
    return _multi_agent_manager_instance


def set_multi_agent_manager(manager: "MultiAgentManager") -> None:
    """Set the global MultiAgentManager instance."""
    global _multi_agent_manager_instance
    _multi_agent_manager_instance = manager


class MultiAgentManager:
    """Manages multiple agent workspaces.

    Features:
    - Lazy loading: Workspaces are created only when first requested
    - Lifecycle management: Start, stop, reload workspaces
    - Thread-safe: Uses async lock for concurrent access
    - Hot reload: Reload individual workspaces without affecting others
    - Dual mode support: MULTI_AGENT or SHARED_AGENT
    """

    def __init__(self):
        """Initialize multi-agent manager."""
        self.agents: Dict[str, Workspace] = {}
        self._lock = asyncio.Lock()
        self._cleanup_tasks: Set[asyncio.Task] = set()
        self._shared_workspace_manager: Optional[SharedWorkspaceManager] = None
        logger.debug("MultiAgentManager initialized")

    async def get_agent(
        self,
        agent_id: str,
        display_name: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Workspace:
        """Get agent workspace by ID (lazy loading).

        If workspace doesn't exist in memory, it will be created and started.
        Thread-safe using async lock.

        In MULTI_AGENT mode: Each user gets their own workspace.
        In SHARED_AGENT mode: All users share one workspace with isolated file spaces.

        Args:
            agent_id: Agent ID to retrieve
            display_name: Optional display name for the agent (used when creating new agent)
            user_id: Optional user ID for shared mode (to ensure user space exists)

        Returns:
            Workspace: The requested workspace instance

        Raises:
            ValueError: If agent ID not found in configuration
        """
        config = load_config()

        # SHARED_AGENT mode: Return shared workspace
        if config.multi_user_mode == MultiUserMode.SHARED_AGENT:
            return await self._get_shared_workspace(config, user_id)

        # MULTI_AGENT mode: Each user has their own workspace
        return await self._get_multi_agent_workspace(agent_id, display_name)

    async def _get_shared_workspace(
        self,
        config: "Config",
        user_id: Optional[str] = None,
    ) -> Workspace:
        """Get shared workspace for SHARED_AGENT mode.

        Args:
            config: Current configuration
            user_id: Optional user ID to ensure user space exists

        Returns:
            Workspace: The shared workspace instance
        """
        async with self._lock:
            # Initialize shared workspace manager if needed
            if self._shared_workspace_manager is None:
                if "shared" not in config.agents.profiles:
                    # Create shared workspace configuration
                    await self._ensure_shared_agent_exists(config)
                    config = load_config()

                shared_ref = config.agents.profiles.get("shared")
                if not shared_ref:
                    raise ValueError(
                        "Shared workspace not found in configuration. "
                        "Please create 'shared' agent profile.",
                    )

                self._shared_workspace_manager = SharedWorkspaceManager(
                    workspace_dir=Path(shared_ref.workspace_dir),
                )

            # Get or create the shared workspace
            workspace = (
                await self._shared_workspace_manager.get_or_create_workspace()
            )

            # Ensure user space exists if user_id provided
            if user_id:
                self._shared_workspace_manager.ensure_user_space(user_id)
                logger.debug(f"Ensured user space for: {user_id}")

            return workspace

    async def _get_multi_agent_workspace(
        self,
        agent_id: str,
        display_name: Optional[str] = None,
    ) -> Workspace:
        """Get per-user workspace for MULTI_AGENT mode.

        Args:
            agent_id: Agent ID to retrieve
            display_name: Optional display name for the agent

        Returns:
            Workspace: The requested workspace instance
        """
        # Sanitize agent_id for multi-user support
        safe_agent_id = _sanitize_agent_id(agent_id) if agent_id else "default"

        async with self._lock:
            # Return existing agent if already loaded
            if safe_agent_id in self.agents:
                logger.debug(f"Returning cached agent: {safe_agent_id}")
                return self.agents[safe_agent_id]

            # Load configuration to get agent reference
            config = load_config()

            # Auto-create agent config if not exists (for multi-user support)
            if safe_agent_id not in config.agents.profiles:
                logger.info(
                    f"Agent '{safe_agent_id}' not found in configuration. "
                    f"Auto-creating for multi-user support...",
                )
                await self._ensure_user_agent_exists(
                    safe_agent_id, display_name
                )
                # Reload config after creation
                config = load_config()

            if safe_agent_id not in config.agents.profiles:
                raise ValueError(
                    f"Agent '{safe_agent_id}' not found in configuration. "
                    f"Available agents: {list(config.agents.profiles.keys())}",
                )

            agent_ref = config.agents.profiles[safe_agent_id]

            # Create and start new workspace
            logger.info(f"Creating new workspace: {safe_agent_id}")
            instance = Workspace(
                agent_id=safe_agent_id,
                workspace_dir=agent_ref.workspace_dir,
            )

            try:
                await instance.start()
                instance.set_manager(self)  # Set manager reference
                self.agents[safe_agent_id] = instance
                logger.info(f"Workspace created and started: {safe_agent_id}")
                return instance
            except Exception as e:
                logger.error(f"Failed to start workspace {safe_agent_id}: {e}")
                raise

    async def _ensure_shared_agent_exists(self, config: "Config") -> None:
        """Ensure shared agent workspace exists in configuration.

        Creates the shared workspace directory and configuration if needed.

        Args:
            config: Current configuration
        """
        from ..config.utils import WORKING_DIR

        working_dir = Path(WORKING_DIR)
        shared_workspace_dir = working_dir / "workspaces" / "shared"

        # Check if already exists
        if "shared" in config.agents.profiles:
            logger.debug("Shared workspace already in config")
            return

        logger.info("Creating shared workspace configuration...")

        # Create directory if needed
        shared_workspace_dir.mkdir(parents=True, exist_ok=True)

        # Copy from default if exists, otherwise create minimal
        default_dir = working_dir / "workspaces" / "default"
        if default_dir.exists():
            # Create agent.json based on default
            self._create_shared_agent_config(
                shared_workspace_dir,
                default_dir,
            )
        else:
            self._create_minimal_agent_config(
                shared_workspace_dir,
                "shared",
                "Shared Agent",
            )

        # Add to root config
        self._add_agent_to_config(
            "shared", str(shared_workspace_dir), "Shared Agent"
        )

        logger.info(f"Shared workspace created at: {shared_workspace_dir}")

    def _create_shared_agent_config(
        self,
        workspace_dir: Path,
        default_dir: Path,
    ) -> None:
        """Create shared agent.json based on default workspace.

        Args:
            workspace_dir: Target workspace directory
            default_dir: Default workspace directory to copy from
        """
        default_agent_json = default_dir / "agent.json"

        if default_agent_json.exists():
            try:
                with open(default_agent_json, encoding="utf-8") as f:
                    config = json.load(f)

                config["id"] = "shared"
                config["name"] = "Shared Agent"
                config["workspace_dir"] = str(workspace_dir)

                agent_json_path = workspace_dir / "agent.json"
                with open(agent_json_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)

                logger.debug("Created shared agent.json from default")
                return
            except Exception as e:
                logger.warning(f"Failed to copy default config: {e}")

        # Fallback to minimal config
        self._create_minimal_agent_config(
            workspace_dir, "shared", "Shared Agent"
        )

    def get_shared_workspace_manager(self) -> Optional[SharedWorkspaceManager]:
        """Get the SharedWorkspaceManager instance.

        Returns:
            SharedWorkspaceManager or None if not in shared mode
        """
        return self._shared_workspace_manager

    def get_user_space_dir(self, user_id: str) -> Optional[Path]:
        """Get user's file space directory (shared mode only).

        Args:
            user_id: User identifier

        Returns:
            Path to user's space directory, or None if not in shared mode
        """
        if self._shared_workspace_manager:
            return self._shared_workspace_manager.get_user_space_dir(user_id)
        return None

    def get_user_files_dir(self, user_id: str) -> Optional[Path]:
        """Get user's files directory for uploads (shared mode only).

        Args:
            user_id: User identifier

        Returns:
            Path to user's files directory, or None if not in shared mode
        """
        if self._shared_workspace_manager:
            return self._shared_workspace_manager.get_user_files_dir(user_id)
        return None

    def get_user_tasks_dir(self, user_id: str) -> Optional[Path]:
        """Get user's tasks directory for generated files (shared mode only).

        Args:
            user_id: User identifier

        Returns:
            Path to user's tasks directory, or None if not in shared mode
        """
        if self._shared_workspace_manager:
            return self._shared_workspace_manager.get_user_tasks_dir(user_id)
        return None

    def get_user_context(self, user_id: str) -> Optional[Dict[str, str]]:
        """Get user context for prompt injection (shared mode only).

        Args:
            user_id: User identifier

        Returns:
            Dict with user paths, or None if not in shared mode
        """
        if self._shared_workspace_manager:
            return self._shared_workspace_manager.get_user_context(user_id)
        return None

    async def _ensure_user_agent_exists(
        self,
        agent_id: str,
        display_name: Optional[str] = None,
    ) -> None:
        """Ensure user agent config exists, create if not.

        This method creates a workspace directory and configuration for
        a new user agent, copying from the default agent as template.

        Note: agent_id should already be sanitized by caller.
        This method is called within the lock in get_agent(), so it's
        thread-safe for concurrent access.

        Args:
            agent_id: The sanitized agent ID to create an agent for
            display_name: Optional display name for the agent

        Raises:
            RuntimeError: If failed to create user agent workspace
        """
        from ..config.utils import WORKING_DIR

        working_dir = Path(WORKING_DIR)

        # User agent workspace directory
        user_workspace_dir = working_dir / "workspaces" / agent_id

        # Check if config already has this agent
        config = load_config()
        config_has_agent = agent_id in config.agents.profiles

        # Check if workspace directory exists
        dir_exists = user_workspace_dir.exists()

        if config_has_agent:
            logger.debug(f"User agent already in config: {agent_id}")
            return

        if dir_exists:
            logger.debug(
                f"User workspace directory exists but not in config: {agent_id}"
            )
            # Directory exists but config missing - update agent.json and add config entry
            agent_name = display_name or agent_id
            self._update_agent_config(user_workspace_dir, agent_id, agent_name)
            self._add_agent_to_config(
                agent_id, str(user_workspace_dir), agent_name
            )
            logger.info(
                f"Added existing workspace to config for user: {agent_name}"
            )
            return

        # Use display_name if provided, otherwise use agent_id
        agent_name = display_name or agent_id

        try:
            # Copy default agent config as template
            default_dir = working_dir / "workspaces" / "default"

            if default_dir.exists():
                shutil.copytree(default_dir, user_workspace_dir)
                # Update agent.json with correct id and name
                self._update_agent_config(
                    user_workspace_dir, agent_id, agent_name
                )
                logger.info(f"Copied default workspace for user: {agent_name}")
            else:
                # Create minimal config if no default exists
                user_workspace_dir.mkdir(parents=True, exist_ok=True)
                self._create_minimal_agent_config(
                    user_workspace_dir, agent_id, agent_name
                )
                logger.info(
                    f"Created minimal workspace for user: {agent_name}"
                )

            # Add agent reference to root config
            self._add_agent_to_config(
                agent_id, str(user_workspace_dir), agent_name
            )

        except Exception as e:
            # Clean up partially created directory on failure
            if user_workspace_dir.exists():
                try:
                    shutil.rmtree(user_workspace_dir)
                except Exception:
                    pass
            logger.error(f"Failed to create user agent workspace: {e}")
            raise RuntimeError(
                f"Failed to create workspace for agent '{agent_id}': {e}",
            ) from e

    def _update_agent_config(
        self,
        workspace_dir: Path,
        agent_id: str,
        agent_name: Optional[str] = None,
    ) -> None:
        """Update agent.json with correct id and name."""
        agent_json_path = workspace_dir / "agent.json"
        if not agent_json_path.exists():
            return

        try:
            with open(agent_json_path, encoding="utf-8") as f:
                config = json.load(f)

            config["id"] = agent_id
            config["name"] = agent_name or agent_id

            with open(agent_json_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to update agent config: {e}")

    def _create_minimal_agent_config(
        self,
        workspace_dir: Path,
        agent_id: str,
        agent_name: Optional[str] = None,
    ) -> None:
        """Create minimal agent.json for a new user.

        Args:
            workspace_dir: Path to the workspace directory
            agent_id: The user ID
            agent_name: The display name for the agent
        """
        config = {
            "id": agent_id,
            "name": agent_name or agent_id,
            "workspace_dir": str(workspace_dir),
            "channels": {},
            "mcp": {"servers": {}},
            "running": {
                "max_iters": 10,
                "max_input_length": 128000,
            },
        }

        agent_json_path = workspace_dir / "agent.json"
        with open(agent_json_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # Create AGENTS.md placeholder
        agents_md_path = workspace_dir / "AGENTS.md"
        if not agents_md_path.exists():
            agents_md_path.write_text(
                f"# {agent_id}\n\nUser-specific agent workspace.\n",
                encoding="utf-8",
            )

    def _add_agent_to_config(
        self,
        agent_id: str,
        workspace_dir: str,
        agent_name: Optional[str] = None,
    ) -> None:
        """Add agent reference to root config.json.

        Uses atomic write (write to temp file, then rename) to prevent
        config corruption during concurrent access.

        Args:
            agent_id: The user ID
            workspace_dir: Path to the workspace directory
            agent_name: The display name for the agent
        """
        config_path = get_config_path()

        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Failed to load config, creating new: {e}")
            config = {}

        if "agents" not in config:
            config["agents"] = {"active_agent": "default", "profiles": {}}

        if "profiles" not in config["agents"]:
            config["agents"]["profiles"] = {}

        config["agents"]["profiles"][agent_id] = {
            "id": agent_id,
            "name": agent_name or agent_id,
            "workspace_dir": workspace_dir,
        }

        # Atomic write: write to temp file first, then rename
        config_path_obj = Path(config_path)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path_obj.parent,
            prefix=".config.tmp",
            suffix=".json",
            delete=False,
        ) as tmp_file:
            json.dump(config, tmp_file, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp_file.name)

        # Atomic rename (on POSIX systems, and works on Windows too)
        try:
            tmp_path.replace(config_path_obj)
            logger.info(
                f"Successfully added agent '{agent_id}' to config.json"
            )
        except Exception as e:
            logger.error(f"Failed to replace config file: {e}")
            # Try to clean up temp file
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    async def _graceful_stop_old_instance(
        self,
        old_instance: Workspace,
        agent_id: str,
    ) -> None:
        """Gracefully stop old instance after checking for active tasks.

        If active tasks exist, schedule delayed cleanup in background.
        Otherwise, stop immediately.

        Args:
            old_instance: The old workspace instance to stop
            agent_id: Agent ID for logging
        """
        has_active = await old_instance.task_tracker.has_active_tasks()

        if has_active:
            # Active tasks - schedule delayed cleanup in background
            active_tasks = await old_instance.task_tracker.list_active_tasks()
            logger.info(
                f"Old workspace instance has {len(active_tasks)} active "
                f"task(s): {active_tasks}. Scheduling delayed cleanup for "
                f"{agent_id}.",
            )

            async def delayed_cleanup():
                """Wait for tasks to complete, then stop old instance."""
                try:
                    # Wait up to 1 minutes for tasks to complete
                    completed = await old_instance.task_tracker.wait_all_done(
                        timeout=60.0,
                    )
                    if completed:
                        logger.info(
                            f"All tasks completed for old instance "
                            f"{agent_id}. Stopping now.",
                        )
                    else:
                        logger.warning(
                            f"Timeout waiting for tasks to complete for "
                            f"{agent_id}. Forcing stop after 5 minutes.",
                        )

                    await old_instance.stop(final=False)
                    logger.info(
                        f"Old workspace instance stopped: {agent_id}. "
                        f"Delayed cleanup completed.",
                    )
                except Exception as e:
                    logger.warning(
                        f"Error during delayed cleanup for {agent_id}: {e}. "
                        f"New instance is serving requests.",
                    )

            # Create background task for delayed cleanup and track it
            cleanup_task = asyncio.create_task(delayed_cleanup())
            self._cleanup_tasks.add(cleanup_task)

            def _on_cleanup_done(task: asyncio.Task) -> None:
                """Remove task from tracking set and log errors."""
                self._cleanup_tasks.discard(task)
                if task.cancelled():
                    logger.info(
                        f"Delayed cleanup task for {agent_id} was cancelled.",
                    )
                    return
                exc = task.exception()
                if exc is not None:
                    logger.warning(
                        f"Error in delayed cleanup task for {agent_id}: "
                        f"{exc}.",
                    )

            cleanup_task.add_done_callback(_on_cleanup_done)
            logger.info(
                f"Zero-downtime reload completed: {agent_id}. "
                f"Old instance cleanup scheduled in background.",
            )
        else:
            # No active tasks - stop immediately
            logger.debug(
                f"No active tasks in old instance {agent_id}. "
                f"Stopping immediately.",
            )
            try:
                await old_instance.stop(final=False)
                logger.info(
                    f"Old workspace instance stopped: {agent_id}. "
                    f"Zero-downtime reload completed.",
                )
            except Exception as e:
                logger.warning(
                    f"Failed to stop old workspace instance for "
                    f"{agent_id}: {e}. "
                    f"New instance is active and serving requests.",
                )

    async def stop_agent(self, agent_id: str) -> bool:
        """Stop a specific agent instance.

        Args:
            agent_id: Agent ID to stop

        Returns:
            bool: True if agent was stopped, False if not running
        """
        async with self._lock:
            # Handle shared workspace
            if agent_id == "shared":
                if self._shared_workspace_manager:
                    await self._shared_workspace_manager.stop()
                    logger.info("Shared workspace stopped")
                    return True
                logger.warning("Shared workspace not running")
                return False

            if agent_id not in self.agents:
                logger.warning(f"Agent not running: {agent_id}")
                return False

            instance = self.agents[agent_id]
            await instance.stop()
            del self.agents[agent_id]
            logger.info(f"Agent stopped and removed: {agent_id}")
            return True

    async def reload_agent(self, agent_id: str) -> bool:
        """Reload a specific agent instance with zero-downtime.

        This method performs a seamless reload by:
        1. Creating and fully starting a new workspace instance (no lock)
        2. Atomically replacing the old instance with the new one (with lock)
        3. Gracefully stopping the old instance (no lock):
           - If active tasks exist: schedule delayed cleanup in background
           - If no active tasks: stop immediately

        The lock is only held during the atomic swap to minimize blocking
        time for other agent operations.

        This ensures that:
        - New requests are immediately handled by the new instance
        - Ongoing SSE/streaming tasks continue uninterrupted
        - Other agents remain accessible during reload
        - The manager returns quickly without waiting for old tasks
        - Old instance is automatically cleaned up after tasks complete

        Args:
            agent_id: Agent ID to reload

        Returns:
            bool: True if agent was reloaded, False if not running
        """
        # Step 1: Check if agent exists (quick check with lock)
        async with self._lock:
            if agent_id not in self.agents:
                logger.debug(
                    f"Agent not running, will be loaded on next "
                    f"request: {agent_id}",
                )
                return False
            old_instance = self.agents[agent_id]

        logger.info(f"Reloading agent (zero-downtime): {agent_id}")

        # Step 2: Load configuration (outside lock)
        config = load_config()
        if agent_id not in config.agents.profiles:
            logger.error(
                f"Agent '{agent_id}' not found in configuration "
                f"during reload",
            )
            return False

        agent_ref = config.agents.profiles[agent_id]

        # Step 3: Create and start new workspace instance (outside lock)
        # This is the slow part, but doesn't block other agents
        logger.info(f"Creating new workspace instance: {agent_id}")
        new_instance = Workspace(
            agent_id=agent_id,
            workspace_dir=agent_ref.workspace_dir,
        )

        # Step 3.5: Set reusable components from old instance (if any)
        async with self._lock:
            old_instance = self.agents.get(agent_id)

        if old_instance:
            # Get all reusable services from old instance's ServiceManager
            # pylint: disable=protected-access
            reusable = old_instance._service_manager.get_reusable_services()
            # pylint: enable=protected-access

            if reusable:
                await new_instance.set_reusable_components(reusable)
                logger.info(
                    f"Set reusable components for {agent_id}: "
                    f"{list(reusable.keys())}",
                )

        try:
            await new_instance.start()
            new_instance.set_manager(self)  # Set manager reference
            logger.info(f"New workspace instance started: {agent_id}")
        except Exception as e:
            logger.exception(
                f"Failed to start new workspace instance for {agent_id}: {e}",
            )
            # Try to clean up the failed new instance
            try:
                await new_instance.stop()
            except Exception:
                pass  # Best effort cleanup
            # Old instance is still running and serving requests
            return False

        # Step 4: Atomic swap (minimal lock time)
        # From this point, reload is considered successful
        async with self._lock:
            # Double-check agent still exists
            if agent_id not in self.agents:
                logger.warning(
                    f"Agent {agent_id} was removed during reload, "
                    f"stopping new instance",
                )
                await new_instance.stop()
                return False

            # Swap instances atomically
            old_instance = self.agents[agent_id]
            self.agents[agent_id] = new_instance
            logger.info(f"Workspace instance replaced: {agent_id}")

        # Step 5: Gracefully stop old instance (outside lock)
        # Delegates to helper method to avoid too-many-statements
        await self._graceful_stop_old_instance(old_instance, agent_id)

        return True

    async def cancel_all_cleanup_tasks(self) -> None:
        """Cancel and await all pending delayed cleanup tasks.

        This ensures that any in-progress background cleanups are either
        completed or cleanly cancelled before the manager is torn down.
        Called by stop_all() during shutdown.
        """
        if not self._cleanup_tasks:
            return

        logger.info(
            f"Cancelling {len(self._cleanup_tasks)} pending cleanup "
            f"task(s)...",
        )
        tasks = list(self._cleanup_tasks)
        self._cleanup_tasks.clear()

        for task in tasks:
            if not task.done():
                task.cancel()

        # Await completion of all tasks, collecting exceptions
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All cleanup tasks cancelled/completed")

    async def stop_all(self):
        """Stop all agent instances.

        Called during application shutdown to clean up resources.
        Cancels any pending delayed cleanup tasks and stops all agents.
        """
        logger.info(f"Stopping all agents ({len(self.agents)} running)...")

        # First, cancel pending cleanup tasks to avoid orphaned instances
        await self.cancel_all_cleanup_tasks()

        # Create list of agent IDs to avoid modifying dict during iteration
        agent_ids = list(self.agents.keys())

        for agent_id in agent_ids:
            try:
                instance = self.agents[agent_id]
                await instance.stop()
                logger.debug(f"Agent stopped: {agent_id}")
            except Exception as e:
                logger.error(f"Error stopping agent {agent_id}: {e}")

        self.agents.clear()

        # Stop shared workspace if exists
        if self._shared_workspace_manager:
            await self._shared_workspace_manager.stop()
            self._shared_workspace_manager = None

        logger.info("All agents stopped")

    def list_loaded_agents(self) -> list[str]:
        """List currently loaded agent IDs.

        Returns:
            list[str]: List of loaded agent IDs
        """
        agents = list(self.agents.keys())
        # Include shared workspace if active
        if (
            self._shared_workspace_manager
            and self._shared_workspace_manager.workspace
        ):
            if "shared" not in agents:
                agents.append("shared")
        return agents

    def is_agent_loaded(self, agent_id: str) -> bool:
        """Check if agent is currently loaded.

        Args:
            agent_id: Agent ID to check

        Returns:
            bool: True if agent is loaded and running
        """
        if agent_id in self.agents:
            return True
        # Check shared workspace
        if agent_id == "shared" and self._shared_workspace_manager:
            return self._shared_workspace_manager.workspace is not None
        return False

    async def preload_agent(self, agent_id: str) -> bool:
        """Preload an agent instance during startup.

        Args:
            agent_id: Agent ID to preload

        Returns:
            bool: True if successfully preloaded, False if failed
        """
        try:
            await self.get_agent(agent_id)
            logger.info(f"Successfully preloaded agent: {agent_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to preload agent {agent_id}: {e}")
            return False

    async def start_all_configured_agents(self) -> dict[str, bool]:
        """Start all agents defined in configuration concurrently.

        This method loads the current configuration and starts all
        configured agents in parallel for optimal performance.

        Returns:
            dict[str, bool]: Mapping of agent_id to success status
        """
        config = load_config()
        agent_ids = list(config.agents.profiles.keys())

        if not agent_ids:
            logger.warning("No agents configured in config")
            return {}

        logger.info(f"Starting {len(agent_ids)} configured agent(s)")

        async def start_single_agent(agent_id: str) -> tuple[str, bool]:
            """Start a single agent with error handling."""
            try:
                logger.info(f"Starting agent: {agent_id}")
                await self.preload_agent(agent_id)
                logger.info(f"Agent started successfully: {agent_id}")
                return (agent_id, True)
            except Exception as e:
                logger.error(
                    f"Failed to start agent {agent_id}: {e}. "
                    f"Continuing with other agents...",
                )
                return (agent_id, False)

        # Start all agents concurrently
        results = await asyncio.gather(
            *[start_single_agent(agent_id) for agent_id in agent_ids],
            return_exceptions=False,
        )

        # Build result mapping
        result_map = dict(results)
        success_count = sum(1 for success in result_map.values() if success)
        logger.info(
            f"Agent startup complete: {success_count}/{len(agent_ids)} "
            f"agents started successfully",
        )

        return result_map

    def __repr__(self) -> str:
        """String representation of manager."""
        loaded = list(self.agents.keys())
        return f"MultiAgentManager(loaded_agents={loaded})"
