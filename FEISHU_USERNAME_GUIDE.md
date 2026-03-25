# 飞书频道用户名获取配置指南

## 功能概述

CoPaw 飞书频道现在支持获取并显示用户的真实姓名/昵称，而不仅仅是 user_id。

## 新增字段

在消息的 `meta` 中新增了 `feishu_sender_name` 字段：

```python
meta = {
    "feishu_message_id": "om_xxx",
    "feishu_chat_id": "oc_xxx",
    "feishu_chat_type": "group",
    "feishu_sender_id": "ou_xxx",        # 用户 open_id
    "feishu_sender_name": "张三",        # ⭐ 新增：用户真实姓名
    "is_group": true,
}
```

## 日志输出

日志现在会显示用户名：

```
feishu recv from=张三#5678 (张三) chat=oc_xxx msg_id=om_xxx type=text text_len=42
```

格式：`from=显示名 (用户名) chat=...`

## 权限配置

### 必需权限

要获取用户姓名，需要在飞书开放平台配置以下权限：

**权限名称：** `contact:user.base:readonly`

**权限说明：** 获得获取用户基本信息权限

**权限等级：** 普通权限

**返回字段：**
- `name`: 用户名
- `en_name`: 用户英文名
- `avatar`: 用户头像 URL

### 配置步骤

1. **登录飞书开放平台**
   - 访问：https://open.feishu.cn/
   - 使用自建应用账号登录

2. **进入应用管理**
   - 进入你的应用 → 权限管理

3. **添加权限**
   - 搜索：`contact:user.base:readonly`
   - 或者在「获取用户基本信息」分类中找到
   - 点击添加权限

4. **发布应用**
   - 保存权限配置
   - 发布应用（或发布到版本）

5. **验证权限**
   - 在应用权限页面确认 `contact:user.base:readonly` 已启用

## API 说明

**接口：** `GET https://open.feishu.cn/open-apis/contact/v3/users/:user_id`

**请求参数：**
- `user_id`: 用户 open_id
- `user_id_type`: "open_id"

**频率限制：**
- 1000 次/分钟
- 50 次/秒

**使用场景：**
- 用户发送消息时自动调用
- 结果会被缓存（默认最多 1000 条）
- 超出缓存后自动清理最旧记录

## 错误处理

### 权限缺失

如果应用没有 `contact:user.base:readonly` 权限，日志会显示：

```
feishu get user name: no name in response (open_id=ou_xxx).
App likely missing 'contact:user.base:readonly' permission.
Available fields in response: ['avatar', 'union_id', ...]
```

**解决方法：** 按照上述步骤添加权限

### API 调用失败

```
feishu get user info api error: open_id=ou_xxx code=9999 msg=...
```

**可能原因：**
- 应用无权访问该用户信息
- 网络问题
- API 频率限制

### 超时

```
feishu get user name timeout: open_id=ou_xxx
```

**说明：** API 调用超时（默认 2 秒），不会阻塞消息处理

## 字段优先级

系统按以下优先级获取用户名：

1. `name` - 用户名（中文名）
2. `en_name` - 用户英文名
3. `nickname` - 用户昵称

如果以上字段都为空，则返回 None。

## 兼容性

**向后兼容：**
- `feishu_sender_id` 字段保持不变
- 原有的 `sender_id` 和 `user_id` 显示格式不变（"昵称#后4位"）

**新增内容：**
- `meta["feishu_sender_name"]` - 完整的用户名（如果有）

## 使用示例

### 在 Agent 中访问用户名

```python
def get_username_from_meta(meta: dict) -> str:
    """从消息 metadata 中获取用户名"""
    user_id = meta.get("feishu_sender_id", "")
    user_name = meta.get("feishu_sender_name", "")

    if user_name:
        return f"{user_name} ({user_id})"
    return user_id

# 在 Agent 工具中使用
async def send_greeting(content):
    meta = content.get("meta", {})
    username = get_username_from_meta(meta)
    return f"你好，{username}！有什么可以帮助你的吗？"
```

### 日志查询

```bash
# 查看带用户名的接收日志
tail -f /tmp/copaw_final.log | grep "feishu recv"

# 输出示例
# feishu recv from=李四#1234 (李四) chat=oc_xxx msg_id=om_xxx type=text text_len=10
```

## 性能考虑

- **缓存机制**：用户名会被缓存，避免重复 API 调用
- **异步调用**：API 调用是异步的，不阻塞消息处理
- **超时控制**：默认 2 秒超时，避免长时间等待
- **缓存大小**：最多缓存 1000 个用户的昵称

## 常见问题

**Q: 为什么有些用户显示姓名，有些只显示 ID？**

A: 可能原因：
1. 用户信息在飞书中未设置（所有字段都为空）
2. 应用没有 `contact:user.base:readonly` 权限
3. API 调用超时或频率限制

**Q: 用户名会实时更新吗？**

A: 不会。用户名在首次获取后会被缓存。如果需要更新，需要重启服务或等待缓存自动清理（最旧记录被删除）。

**Q: 如何确认权限配置成功？**

A:
1. 查看日志，确认没有 "App likely missing contact name permission" 的警告
2. 发送测试消息，查看日志中是否显示 `(用户名)`
3. 在 Agent 中打印 `meta["feishu_sender_name"]` 确认有值

**Q: 是否支持英文名？**

A: 是。系统会依次尝试 `name`、`en_name`、`nickname` 字段，只要有一个有值就会返回。

**Q: 如何查看所有缓存的用户名？**

A: 当前版本不提供查询接口。可以通过日志查看获取成功的记录。
