# Multi-Agent 设计深度分析

> 本文档为 Multi-User 开发提供架构参考，记录了 CoPaw 多 Agent 系统的完整设计。

## 一、整体架构

```
FastAPI 应用 (_app.py)
    ↓
MultiAgentManager (多 Agent 管理)
    ↓
Workspace (单个 Agent 实例)
    ↓
AgentRunner (请求处理) + CoPawAgent (核心逻辑)
```

### 核心设计原则

| 原则 | 说明 |
|------|------|
| **隔离性** | 每个 Agent 拥有独立的 Workspace 目录 |
| **懒加载** | Workspace 按需创建，首次访问时才初始化 |
| **热重载** | 支持零停机时间重新加载 Agent 配置 |
| **复用性** | 通过 ServiceManager 统一管理组件 |

---

## 二、核心组件

### 2.1 CoPawAgent (`agents/react_agent.py`)

ReAct Agent 的核心实现，集成工具、技能、记忆管理。

**初始化参数**：
```python
CoPawAgent(
    agent_config,      # Agent 配置
    env_context,       # 环境上下文
    mcp_clients,       # MCP 客户端
    memory_manager,    # 记忆管理器
    request_context,   # 请求上下文 ⭐ Multi-User 关键
    workspace_dir,     # 工作目录
)
```

**关键属性**：
- `_request_context`: 包含 `session_id`, `user_id`, `channel`, `agent_id`
- `_agent_config`: Agent 完整配置
- `_mcp_clients`: MCP 工具客户端列表
- `toolkit`: 内置工具 + 动态加载的技能

**工具注册**：
- 内置：`execute_shell_command`, `read_file`, `write_file`, `edit_file`, `grep_search`, `glob_search`, `browser_use`, `desktop_screenshot`, `view_image`, `send_file_to_user`, `get_current_time`, `set_user_timezone`, `get_token_usage`
- 动态技能：从 `{workspace_dir}/skills/` 目录加载

**钩子系统**：
- `BootstrapHook`: 首次启动引导（检查 BOOTSTRAP.md）
- `MemoryCompactionHook`: 记忆自动压缩

### 2.2 AgentRunner (`runner/runner.py`)

处理 Agent 请求，管理会话状态。

**请求处理流程** (`query_handler`)：

```
1. 检查待审批的 Tool Guard 请求
2. 检查是否为系统命令 (/daemon, /approve 等)
3. 构建 Agent 实例
   - 加载配置: load_agent_config(agent_id)
   - 构建 env_context: build_env_context(session_id, user_id, channel)
   - 创建 CoPawAgent，传递 request_context
4. 获取或创建 Chat
5. 加载会话状态
6. 重建系统提示
7. 流式处理消息
8. 保存会话状态
```

**request_context 构建**（关键代码）：
```python
# runner.py:289-294
agent = CoPawAgent(
    request_context={
        "session_id": session_id,
        "user_id": user_id,
        "channel": channel,
        "agent_id": self.agent_id,
    },
)
```

### 2.3 Workspace (`workspace/workspace.py`)

封装完整的独立 Agent 运行时环境。

**组件结构**：
```
Workspace
├── AgentRunner (priority=10)
├── MemoryManager (priority=20, reusable=True)
├── MCPClientManager (priority=20)
├── ChatManager (priority=20, reusable=True)
├── ChannelManager (priority=30)
├── CronManager (priority=40)
├── AgentConfigWatcher (priority=50)
└── MCPConfigWatcher (priority=51)
```

**ServiceManager 特性**：
- 声明式服务注册（ServiceDescriptor）
- 依赖注入和启动顺序控制
- 支持并发初始化（`concurrent_init=True`）
- 支持可复用组件（`reusable=True`）用于热重载

### 2.4 会话管理 (`runner/session.py`)

**SafeJSONSession**：
- 路径：`{workspace_dir}/sessions/`
- 文件命名：`{user_id}_{session_id}.json`（跨平台安全）
- 功能：`save_session_state()`, `load_session_state()`, `update_session_state()`

---

## 三、数据流图

### 完整请求流程

```
用户请求 (Channel / API)
    │ { session_id, user_id, channel, content }
    ▼
FastAPI 路由
    │ 提取 session_id, user_id, channel
    │ 调用 runner.query_handler()
    ▼
AgentRunner.query_handler()
    │ 1. 检查 Tool Guard 审批
    │ 2. 检查系统命令
    │ 3. 构建环境上下文
    │ 4. 加载配置
    │ 5. 获取 MCP 客户端
    ▼
创建 CoPawAgent
    │ request_context = { session_id, user_id, channel, agent_id }
    ▼
加载会话状态
    │ session.load_session_state(session_id, user_id, agent)
    │ → {workspace_dir}/sessions/{user_id}_{session_id}.json
    ▼
CoPawAgent._reasoning()
    │ 1. 构建系统提示（含 agent_id）
    │ 2. 格式化消息
    │ 3. 调用 LLM
    ▼
CoPawAgent._acting()
    │ 1. 工具可访问 request_context
    │ 2. 执行工具
    │ 3. 返回结果
    ▼
保存会话状态
    │ session.save_session_state()
    ▼
更新 Chat
    └→ chat_manager.update_chat(chat)
```

### 用户信息流动

```
用户请求
    ↓ session_id, user_id
AgentRunner.query_handler()
    ↓
build_env_context(session_id, user_id, channel, working_dir)
    ↓
CoPawAgent(request_context={...})
    ↓
agent.memory.content.append(Msg(role="user", ...))
    ↓
agent._request_context  # 工具可访问
    ↓
agent.tools.execute()  # 工具获取用户上下文
    ↓
session.save_session_state()  # 保存到 {user_id}_{session_id}.json
```

---

## 四、关键类/函数索引

### 核心类

| 类 | 文件 | 职责 |
|---|---|------|
| `CoPawAgent` | `agents/react_agent.py` | ReAct Agent 核心实现 |
| `AgentRunner` | `runner/runner.py` | 请求处理、会话管理 |
| `Workspace` | `workspace/workspace.py` | Agent 实例管理、服务编排 |
| `MultiAgentManager` | `multi_agent_manager.py` | 多 Workspace 管理 |
| `MemoryManager` | `agents/memory/memory_manager.py` | 记忆压缩、搜索 |
| `SafeJSONSession` | `runner/session.py` | 会话状态持久化 |
| `ChatManager` | `runner/manager.py` | Chat 规范 CRUD |
| `ServiceManager` | `workspace/service_manager.py` | 声明式服务管理 |
| `BaseChannel` | `channels/base.py` | 渠道抽象 |

### 关键函数

| 函数 | 文件 | 职责 |
|---|---|------|
| `build_env_context()` | `runner/utils.py` | 构建环境上下文字符串 |
| `build_system_prompt_from_working_dir()` | `agents/prompt.py` | 构建系统提示 |
| `load_agent_config()` | `config/config.py` | 加载 Agent 配置 |
| `resolve_session_id()` | `channels/base.py` | 解析会话 ID |

---

## 五、Multi-User 扩展点

### 5.1 当前隔离机制

| 维度 | 实现 | 效果 |
|------|------|------|
| Agent | 独立 Workspace 目录 | ✅ 完全隔离 |
| Channel | `session_id` 包含 channel 前缀 | ✅ 隔离 |
| User | `user_id` 在 request_context | ⚠️ 逻辑隔离，数据未隔离 |

### 5.2 扩展建议

#### 用户索引层

```python
# src/copaw/app/users/user_index.py
class UserIndex:
    """用户到 Workspace 映射索引"""

    def __init__(self):
        self._user_workspaces: Dict[str, str] = {}  # user_id -> agent_id

    async def get_agent_id(self, user_id: str) -> str:
        return self._user_workspaces.get(user_id, "default")

    async def set_user_agent(self, user_id: str, agent_id: str):
        self._user_workspaces[user_id] = agent_id

    async def get_user_info(self, user_id: str) -> Optional[UserInfo]:
        """获取用户完整信息"""
```

#### AgentRunner 扩展

```python
# 在 query_handler 中添加用户信息查找
user_info = await self._user_index.get_user_info(user_id)

agent = CoPawAgent(
    request_context={
        "session_id": session_id,
        "user_id": user_id,
        "user_name": user_info.name,       # ⭐ 新增
        "user_timezone": user_info.timezone, # ⭐ 新增
        "channel": channel,
        "agent_id": self.agent_id,
    },
)
```

#### 系统提示扩展

```python
# react_agent.py _build_sys_prompt
def _build_sys_prompt(self) -> str:
    user_name = self._request_context.get("user_name")

    sys_prompt = build_system_prompt_from_working_dir(
        working_dir=self._workspace_dir,
        agent_id=self._request_context.get("agent_id"),
    )

    if user_name:
        sys_prompt += f"\n\n当前用户: {user_name}"

    return sys_prompt
```

#### 数据隔离策略

| 维度 | 路径 | 说明 |
|------|------|------|
| 会话数据 | `{workspace_dir}/users/{user_id}/sessions/` | 用户会话隔离 |
| 记忆数据 | `{workspace_dir}/users/{user_id}/memory/` | 用户记忆隔离 |
| 工作目录 | `{workspace_dir}/users/{user_id}/files/` | 用户文件隔离 |

---

## 六、配置结构

### 根配置 (`config.json`)

```python
Config {
    agents: AgentsConfig {
        active_agent: str,
        profiles: Dict[str, AgentProfileRef]  # Agent ID -> 引用
    },
    channels: ChannelConfig,
    tools: ToolsConfig,
    mcp: MCPConfig,
    security: SecurityConfig,
}
```

### Agent 配置 (`workspace/agent.json`)

```python
AgentProfileConfig {
    id: str,
    name: str,
    workspace_dir: str,
    channels: ChannelConfig,
    mcp: MCPConfig,
    heartbeat: HeartbeatConfig,
    running: AgentsRunningConfig {
        max_iters: int,
        max_input_length: int,
        memory_compact_ratio: float,
        memory_reserve_ratio: float,
    },
    llm_routing: AgentsLLMRoutingConfig,
    active_model: ModelSlotConfig,
    language: str,
    tools: ToolsConfig,
    security: SecurityConfig,
}
```

---

## 七、实施路线图

### 第一阶段：最小可行

1. 创建 `UserManager` 和 `User` 模型
2. 在 `AgentRunner` 中集成 `UserIndex`
3. 扩展 `request_context` 包含 `user_name`
4. 添加基础用户 API 端点

### 第二阶段：数据隔离

1. 实现用户专属目录结构
2. 迁移现有会话到用户目录
3. 更新 `MemoryManager` 支持用户隔离

### 第三阶段：高级功能

1. 用户级配置覆盖
2. 用户配额和权限管理
3. 用户活动监控和审计日志

---

## 八、相关文件

| 文件 | 说明 |
|------|------|
| `src/copaw/agents/react_agent.py` | Agent 核心实现 |
| `src/copaw/app/runner/runner.py` | 请求处理 |
| `src/copaw/app/workspace/workspace.py` | Workspace 管理 |
| `src/copaw/app/multi_agent_manager.py` | 多 Agent 管理 |
| `src/copaw/config/config.py` | 配置模型 |
| `src/copaw/agents/memory/memory_manager.py` | 记忆管理 |
