# 认证与故障排查

> 中国区 Garmin 登录、Token管理、常见错误处理。

---

## 一、中国区登录（Garmin.cn）Monkey-Patch

### 问题背景

- 国际区使用 `connect.garmin.com`
- 中国区使用 `connect.garmin.cn`，DI token 端点为 `diauth.garmin.cn`

### Monkey-Patch 代码（`scripts/garmin_auth.py` 自动应用）

```python
if region == "cn":
    # Patch 1: JWT_WEB 错误不终止策略链
    def _patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._auth_properties["JWT_WEB"] = {
            "url": "https://connect.garmin.cn/api/auth/jwt",
            "redirect": "https://connect.garmin.cn",
        }

    # Patch 2: CN DI token 端点
    def _patched_exchange(self, client_id, token):
        try:
            return original_exchange(client_id, token)
        except GarminConnectConnectionError:
            return self._exchange_cn_token(client_id, token)

    # Patch 3: token 保存修复
    def _patched_dump(self):
        return client.client.dump()
```

### Token 存储

- 路径：`~/.clawdbot/garmin-tokens.json`
- 不同区域 token 不互通，切换区域后需重新登录

---

## 二、配置文件模板

`config.example.json`（不包含敏感信息，复制到 `~/.clawdbot/garmin-config/config.json` 后填写）：

```json
{
  "email": "your-email@example.com",
  "password": "your-password",
  "region": "cn",
  "location": {
    "latitude": 26.07,
    "longitude": 119.30,
    "timezone": "Asia/Shanghai"
  }
}
```

---

## 三、常见错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| `GarminConnectAuthenticationError` | 凭据无效 | 检查邮箱/密码，尝试网页登录验证 |
| `GarminConnectConnectionError` | 网络/频率限制 | 等待几分钟后重试 |
| 返回 `None` | 设备未佩戴/不支持 | 确认当天有佩戴设备 |
| Token 过期 | 会话超时 | 重新 `python3 scripts/garmin_auth.py login` |

### 重试策略

```python
def fetch_with_retry(func, max_retries=3, delay=5):
    for attempt in range(max_retries):
        try:
            return func()
        except GarminConnectConnectionError:
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                raise
```
