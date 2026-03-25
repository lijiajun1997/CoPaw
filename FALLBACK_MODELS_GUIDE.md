# 主备模型容错配置指南

## 功能概述

CoPaw 现在支持**主备模型容错机制**。当主模型失败时，系统会自动按配置的顺序尝试备选模型，确保服务的高可用性。

## 配置方式

### 通过配置文件

编辑 `~/.proudai/workspaces/shared/agent.json`（或其他 workspace 的 agent.json）：

```json
{
  "active_model": {
    "provider_id": "openai",
    "model": "gpt-4.1",
    "fallback_models": [
      {
        "provider_id": "anthropic",
        "model": "claude-3-5-sonnet-20241022"
      },
      {
        "provider_id": "deepseek",
        "model": "deepseek-chat"
      },
      {
        "provider_id": "ollama",
        "model": "llama3.1"
      }
    ],
    "max_retries_per_model": 2
  }
}
```

### 配置参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `provider_id` | string | 是 | 主模型的 Provider ID |
| `model` | string | 是 | 主模型的模型名称 |
| `fallback_models` | array | 否 | 备选模型列表 |
| `fallback_models[].provider_id` | string | 是 | 备选模型的 Provider ID |
| `fallback_models[].model` | string | 是 | 备选模型的模型名称 |
| `max_retries_per_model` | int | 否 | 每个模型的最大重试次数（默认 1，范围 1-5） |

## 工作原理

```
请求 → 主模型 (重试 N 次)
        ↓ 失败
       备选模型 1 (重试 N 次)
        ↓ 失败
       备选模型 2 (重试 N 次)
        ↓ 失败
       ...
        ↓ 失败
       抛出异常
```

### 触发条件

系统会在以下情况触发模型切换：
- API 调用失败（网络错误、超时等）
- API 返回错误（如 429、500、502、503 等可重试错误）
- 连续失败次数达到 `max_retries_per_model`

### 日志输出

```
WARNING: Model openai/gpt-4.1 failed (attempt 1/2): Rate limit exceeded. Retrying...
WARNING: Model openai/gpt-4.1 failed after 2 attempts. Switching to fallback: anthropic/claude-3-5-sonnet-20241022
INFO: ✓ Fallback to anthropic/claude-3-5-sonnet-20241022 succeeded (primary failed, model 2/4)
```

## 配置示例

### 示例 1：云 + 本地混合

```json
{
  "active_model": {
    "provider_id": "openai",
    "model": "gpt-4.1",
    "fallback_models": [
      {
        "provider_id": "ollama",
        "model": "llama3.1"
      },
      {
        "provider_id": "lmstudio",
        "model": "local-model"
      }
    ],
    "max_retries_per_model": 2
  }
}
```

**场景**：主模型使用云服务，故障时降级到本地模型。

### 示例 2：多云容灾

```json
{
  "active_model": {
    "provider_id": "openai",
    "model": "gpt-4.1",
    "fallback_models": [
      {
        "provider_id": "anthropic",
        "model": "claude-3-5-sonnet-20241022"
      },
      {
        "provider_id": "gemini",
        "model": "gemini-2.0-flash"
      }
    ],
    "max_retries_per_model": 3
  }
}
```

**场景**：跨多个云服务商容灾，确保服务连续性。

### 示例 3：成本优化

```json
{
  "active_model": {
    "provider_id": "deepseek",
    "model": "deepseek-chat",
    "fallback_models": [
      {
        "provider_id": "openai",
        "model": "gpt-4o-mini"
      }
    ],
    "max_retries_per_model": 2
  }
}
```

**场景**：优先使用低成本模型，失败时使用高质量模型。

## 注意事项

1. **兼容性**：确保备选模型的 API 兼容（如都是 OpenAI 兼容的）
2. **性能差异**：不同模型的速度和质量可能有差异
3. **成本差异**：备选模型的成本可能与主模型不同
4. **配置验证**：启动时会验证备选模型是否可加载

## 与重试机制的关系

CoPaw 有两层容错机制：

1. **RetryChatModel**：对单个模型的暂时性错误进行重试（指数退避）
2. **FallbackChatModel**：在模型级别进行切换

当两者都启用时：
```
请求 → 主模型（重试机制）
        ↓ 仍然失败
       备选模型 1（重试机制）
        ↓ 仍然失败
       备选模型 2（重试机制）
```

## 禁用备选模型

如果不使用备选模型，只需不配置 `fallback_models` 或设置为空数组：

```json
{
  "active_model": {
    "provider_id": "openai",
    "model": "gpt-4.1",
    "fallback_models": [],
    "max_retries_per_model": 1
  }
}
```

或

```json
{
  "active_model": {
    "provider_id": "openai",
    "model": "gpt-4.1"
  }
}
```

## 测试建议

1. **测试主模型**：验证主模型正常工作
2. **测试容错**：故意使用错误的 API Key，观察是否切换到备选模型
3. **查看日志**：检查日志中的 fallback 切换信息
4. **性能测试**：评估不同模型之间的性能差异

## 常见问题

**Q: 如何确认备选模型是否配置成功？**

A: 启动服务时查看日志，会显示类似信息：
```
INFO: Model fallback enabled: primary=openai/gpt-4.1, fallbacks=['anthropic/claude-3-5-sonnet-20241022', 'deepseek/deepseek-chat']
INFO: Loaded fallback model: anthropic/claude-3-5-sonnet-20241022
INFO: Loaded fallback model: deepseek/deepseek-chat
```

**Q: 备选模型也失败了怎么办？**

A: 系统会按顺序尝试所有配置的备选模型，如果全部失败，会抛出最后的异常。

**Q: 如何动态更新备选模型配置？**

A: 修改 `agent.json` 后，可以：
1. 重启服务（简单）
2. 或等待配置热重载（如果启用了配置监听）

**Q: 支持不同协议的模型吗？**

A: 支持，但建议使用相同协议的模型（如都是 OpenAI 兼容），以确保 API 格式一致。
