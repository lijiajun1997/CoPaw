# CoPaw 飞书用户名功能更新日志

## 更新时间
2026-03-25 17:22

## 新增功能

### 飞书频道用户名显示

**功能描述：**
- 除了用户的 `open_id`，现在还可以获取并显示用户的真实姓名/昵称
- 用户名会被存储在消息的 `meta` 字段中
- 日志输出会同时显示显示名和真实姓名

**新增字段：**
```json
{
  "meta": {
    "feishu_sender_id": "ou_xxx",           // 用户 open_id
    "feishu_sender_name": "张三"            // ⭐ 新增：用户真实姓名
  }
}
```

**日志输出示例：**
```
# 之前
feishu recv from=张三#5678 chat=oc_xxx msg_id=om_xxx type=text text_len=42

# 现在
feishu recv from=张三#5678 (张三) chat=oc_xxx msg_id=om_xxx type=text text_len=42
#           ^^^^^^^^^^ 显示名      ^^^^^ 真实姓名
```

## 权限配置要求

### 必需权限

**权限名称：** `contact:contact.base:readonly`（或 `contact:contact:readonly_as_app`）

**权限等级：** 普通权限

**返回字段：**
- `name`: 用户名（中文名）
- `en_name`: 用户英文名
- `avatar`: 用户头像 URL

### 配置步骤

1. 登录飞书开放平台：https://open.feishu.cn/
2. 进入你的自建应用 → 权限管理
3. 搜索并添加权限：`contact:user.base:readonly`
4. 保存并发布应用
5. 重启 CoPaw 服务

### API 信息

- **接口：** `GET https://open.feishu.cn/open-apis/contact/v3/users/:user_id`
- **频率限制：** 1000 次/分钟，50 次/秒
- **超时时间：** 2 秒

## 字段优先级

系统按以下顺序获取用户名：
1. `name` - 用户名
2. `en_name` - 用户英文名
3. `nickname` - 用户昵称

只要有一个字段有值，就会返回该字段。

## 错误处理

### 权限缺失
```
feishu get user name: no name in response (open_id=ou_xxx).
App likely missing 'contact:user.base:readonly' permission.
```
**解决方法：** 添加 `contact:user.base:readonly` 权限

### API 调用失败
```
feishu get user info api error: open_id=ou_xxx code=9999 msg=...
```
**可能原因：**
- 应用无权访问该用户
- 网络问题
- API 频率限制

### 超时
```
feishu get user name timeout: open_id=ou_xxx
```
**说明：** API 调用超时，不会阻塞消息处理

## 性能优化

- **缓存机制**：用户名自动缓存（最多 1000 条）
- **异步调用**：不阻塞消息处理流程
- **超时控制**：避免长时间等待

## 在 Agent 中使用

### 示例 1：获取用户信息

```python
async def greet_user(content):
    """获取用户信息并打招呼"""
    meta = content.get("meta", {})

    # 获取用户 open_id
    user_id = meta.get("feishu_sender_id", "")

    # 获取用户姓名
    user_name = meta.get("feishu_sender_name", "")

    if user_name:
        return f"你好，{user_name}！有什么我可以帮助你的吗？"
    else:
        return f"你好！有什么我可以帮助你的吗？"
```

### 示例 2：记录用户行为

```python
async def log_user_action(content, action):
    """记录用户行为"""
    meta = content.get("meta", {})

    user_id = meta.get("feishu_sender_id", "")
    user_name = meta.get("feishu_sender_name", "")

    logger.info(f"用户 {user_name} ({user_id}) 执行了操作: {action}")
```

## 配套更新

### 1. 主备模型容错功能
- 支持配置多个备选模型
- 主模型失败时自动切换
- 详细文档：`FALLBACK_MODELS_GUIDE.md`

### 2. 默认数据目录修改
- 从 `~/.copaw` 改为 `~/.proudai`
- 支持自定义工作目录

### 3. Provider 热重载
- 多 worker 环境下自动同步配置
- 文件修改时自动更新

## 服务状态

- **后端服务：** ✅ http://127.0.0.1:8088
- **前端控制台：** ✅ http://localhost:5174
- **多用户模式：** ✅ shared_agent (单 Agent 多用户)
- **Worker 数量：** ✅ 4

## 文件清单

新增/修改的文件：
1. `src/copaw/app/channels/feishu/channel.py` - 添加用户名获取和存储
2. `FEISHU_USERNAME_GUIDE.md` - 用户名功能配置指南
3. `FALLBACK_MODELS_GUIDE.md` - 主备模型容错配置指南
4. `src/copaw/providers/fallback_chat_model.py` - Fallback 模型实现
5. `src/copaw/providers/models.py` - 扩展配置模型
6. `src/copaw/agents/model_factory.py` - 集成 fallback 逻辑

## 注意事项

1. **权限配置：** 必须在飞书开放平台配置 `contact:contact.base:readonly` 权限
2. **兼容性：** 向后兼容，不影响现有功能
3. **性能：** 用户名缓存会占用内存，但影响很小
4. **隐私：** 用户名仅用于日志和 Agent 上下文，不会被共享

## 验证方法

### 1. 检查日志
发送消息后查看日志：
```bash
tail -f /tmp/copaw_restart.log | grep "feishu recv"
```

### 2. Agent 中测试
在 Agent 的工具中打印 meta：
```python
print(json.dumps(content.get("meta"), indent=2))
```

### 3. 确认权限
如果没有获取到用户名，检查：
- 飞书开放平台权限配置
- 应用是否已发布
- 日志中是否有权限相关错误信息

## 相关链接

- 飞书开放平台：https://open.feishu.cn/
- API 文档：https://open.feishu.cn/document/ukTMukTMukTMuEjTMwNjNxM
- CoPaw 文档：`FEISHU_USERNAME_GUIDE.md`
