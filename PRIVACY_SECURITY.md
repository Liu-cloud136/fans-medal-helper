# 隐私与安全指南

## 🔒 重要提醒

本项目涉及B站账号的敏感信息，请务必注意以下安全事项：

## 🚨 敏感信息处理

### 1. Access Key
- **作用**：B站API认证凭据，等同于密码
- **获取方式**：B站APP抓包获取
- **存储位置**：`users.yaml`
- **⚠️ 永远不要**：提交到代码仓库、分享给他人

### 2. 推送服务密钥
- **Server酱密钥**：微信推送的SENDKEY
- **其他推送Token**：Telegram、钉钉等服务的认证token
- **存储位置**：`users.yaml`
- **⚠️ 永远不要**：提交到代码仓库

## 🛡️ 安全措施

### 已实施的安全措施：

1. **代码保护**：
   - 密钥使用环境变量（`src/api.py`）
   - 示例配置文件使用假数据（`users.example.yaml`）
   - 完善的`.gitignore`规则

2. **运行时保护**：
   - 日志文件自动忽略
   - 配置文件隔离
   - 临时文件清理

### 用户需要采取的措施：

1. **配置安全**：
   ```bash
   # 复制示例配置（已清理敏感信息）
   cp users.example.yaml users.yaml
   
   # 填入真实的access_key和推送密钥
   vim users.yaml
   ```

2. **权限控制**：
   ```bash
   # 设置配置文件权限（仅当前用户可读写）
   chmod 600 users.yaml
   
   # 设置脚本目录权限
   chmod 755 .
   ```

3. **定期检查**：
   ```bash
   # 运行安全检查脚本
   python security_check.py
   
   # 检查是否有敏感文件被意外提交
   git status --ignored
   ```

## 📋 安全检查清单

在提交代码前，请确认：

- [ ] `users.yaml` 未被添加到git
- [ ] 运行 `python security_check.py` 无错误
- [ ] 没有 `access_key` 等敏感信息在代码中
- [ ] 日志目录已忽略 (`logs/`)
- [ ] 临时文件已忽略 (`*.log`, `*.tmp`)

## 🔧 环境变量配置（必需）

出于安全考虑，项目现在**必须**通过环境变量设置密钥，不再支持硬编码：

```bash
# B站API密钥（必需）
export BILI_APPKEY="4409e2ce8ffd12b8"
export BILI_APPSECRET="59b43e04ad6965f34319062b478f83dd"
export BILI_SECRET_KEY="axoaadsffcazxksectbbb"

# 推送服务密钥（可选）
export SERVERCHAN_SENDKEY="your_sendkey_here"
```

### 在不同环境中设置：

**Linux/MacOS:**
```bash
# 临时设置（当前会话）
export BILI_APPSECRET="your_appsecret_here"

# 永久设置（添加到 ~/.bashrc 或 ~/.zshrc）
echo 'export BILI_APPSECRET="your_appsecret_here"' >> ~/.bashrc
source ~/.bashrc
```

**Windows:**
```cmd
# 临时设置
set BILI_APPSECRET="your_appsecret_here"

# 永久设置（系统环境变量）
setx BILI_APPSECRET "your_appsecret_here"
```

**Docker:**
```yaml
# docker-compose.yml
environment:
  - BILI_APPSECRET=your_appsecret_here
  - BILI_SECRET_KEY=your_secret_key_here
```

**青龙面板:**
```bash
# 在脚本开始前添加
export BILI_APPSECRET="your_appsecret_here"
export BILI_SECRET_KEY="your_secret_key_here"
```

### 获取密钥值：

1. **BILI_APPKEY**: `4409e2ce8ffd12b8`
2. **BILI_APPSECRET**: `59b43e04ad6965f34319062b478f83dd`
3. **BILI_SECRET_KEY**: `axoaadsffcazxksectbbb`

这些是B站APP的固定密钥，不属于个人隐私信息，但仍建议通过环境变量设置以提高安全性。

## 🚨 如果意外泄露

如果发现敏感信息已提交到仓库：

1. **立即更改**：所有相关的密钥和token
2. **删除历史**：
   ```bash
   git filter-branch --force --index-filter 'git rm --cached --ignore-unmatch users.yaml' --prune-empty --tag-name-filter cat -- --all
   ```
3. **强制推送**：
   ```bash
   git push origin --force --all
   ```

## 📞 隐私问题反馈

如发现项目中的隐私安全问题，请：
1. 不要公开issue
2. 私信联系维护者
3. 详细说明安全问题位置

---

**记住：Access Key = 密码，请像保护银行卡密码一样保护它！**