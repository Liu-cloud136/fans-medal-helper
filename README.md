# B站粉丝牌助手（自用修改）

> 自动化完成B站直播间每日任务，轻松获得粉丝牌亲密度

## 📋 功能特性

### 核心功能
- ✅ **自动点赞**：新规优化，每日5次点赞获得亲密度
- ✅ **自动观看**：新规适配，每日5次观看获得30亲密度
- ✅ **多账号支持**：支持同时运行多个B站账号
- ✅ **智能通知**：任务完成后推送通知结果

### 技术特性
- 🚀 **并行处理**：支持多直播间并行观看，提升效率
- 🔄 **重试机制**：网络异常自动重试，确保任务完成
- 📊 **详细日志**：可选的任务详情通知，便于调试
- ⚙️ **灵活配置**：YAML配置文件，参数可自定义
- 🛡️ **API限流**：智能API调用频率控制，降低限流风险
- 🔧 **青龙优化**：专为青龙面板优化的轻量化版本

## 🚀 快速开始

### 环境要求
- Python >= 3.10
- aiohttp, loguru, pytz等依赖（见requirements.txt）

### 安装依赖
```bash
pip install -r requirements.txt
```

### 配置文件
1. 复制示例配置：
```bash
cp users.example.yaml users.yaml
```

2. 编辑配置文件，填入你的access_key：
```yaml
USERS:
  - access_key: "你的access_key"  # 获取方式见下方说明
    white_uid:                   # 白名单UID（可选）
      - 123456789
    banned_uid:                  # 黑名单UID（可选）
      - 987654321

# 核心配置
LIKE_CD: 0.5                    # 点赞间隔（秒）
WATCH_TARGET: 25                # 观看目标时长（分钟）
MAX_CONCURRENT_WATCH: 2         # 最大并行观看数
NOTIFY_DETAIL: 1                # 是否详细通知
WEARMEDAL: 0                   # 是否佩戴粉丝牌

# API限流配置
API_RATE_LIMIT: 0.5             # API调用最小间隔（秒）
MAX_API_CONCURRENT: 3           # 最大并发API调用数

# 推送配置
SENDKEY: ""                     # Server酱推送key（可选）
MOREPUSH: {}                    # 其他推送方式（可选）
PROXY: ""                       # 代理地址（可选）
```

### 获取access_key
1. 登录B站网页版
2. 打开开发者工具（F12）
3. 在Network标签中找到包含`access_key`的请求
4. 复制access_key值到配置文件

### 运行程序
```bash
python main.py
```

## 🐉 青龙面板部署

### 部署步骤
1. **克隆到青龙面板**：
```bash
# 进入青龙容器
docker exec -it qinglong bash
cd /ql/data/scripts

# 克隆项目
git clone <项目地址>
cd <项目目录>

# 安装依赖
pip install -r requirements.txt

# 配置文件
cp users.example.yaml users.yaml
vi users.yaml  # 编辑配置
```

2. **添加定时任务**：
   - 名称：`B站粉丝牌助手`
   - 命令：`cd /ql/data/scripts/项目目录 && python main.py`
   - 定时规则：`0 2 * * *`（每天凌晨2点）

### 常见问题解决
```bash
# 如果目录不匹配，创建软链接
cd /ql/data/scripts
ln -s fans-medal-helper fansMedalHelper

# 升级pip解决依赖问题
pip install --upgrade pip
pip install -r requirements.txt

# 查看运行日志
tail -f /ql/data/scripts/项目目录/logs/*.log
```

## ⚙️ 配置详解

### 基础配置
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `LIKE_CD` | 点赞间隔时间（秒） | 0.5 |
| `WATCH_TARGET` | 每房间目标观看时长（次数） | 5 |
| `WATCH_MAX_ATTEMPTS` | 单次最大观看尝试（次数） | 10 |
| `MAX_CONCURRENT_WATCH` | 最大并行观看数 | 6 |

### 高级配置
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `API_RATE_LIMIT` | API调用最小间隔（秒） | 0.5 |
| `MAX_API_CONCURRENT` | 最大并发API调用数 | 3 |
| `WEARMEDAL` | 是否佩戴粉丝牌（0关闭，1开启） | 0 |
| `NOTIFY_DETAIL` | 详细通知模式（0仅错误，1详细） | 1 |

### 推送配置
- **Server酱**：填写`SENDKEY`即可
- **其他推送**：配置`MOREPUSH`对象
```yaml
MOREPUSH:
  notifier: "bark"  # 推送服务商
  params:
    key: "your_key"
    title: "自定义标题"
```

## 🛡️ 安全特性

### API限流机制
- **智能延迟**：随机延迟避免固定模式检测
- **并发控制**：限制同时API调用数量
- **重试策略**：指数退避重试机制
- **错误处理**：完善的异常捕获和恢复

### 数据安全
- 使用安全的YAML加载器
- 配置文件敏感信息保护
- 日志文件隔离存储

## 📊 任务逻辑

### 点赞策略（新规优化）
- **统一策略**：所有房间5次点赞
- **亲密度获取**：每日获得5航海亲密度（上限）
- **大航海加成**：1.5倍亲密度加成
- **全面覆盖**：所有房间执行点赞任务

### 观看策略（新规优化）
- **高效观看**：每5分钟获得6亲密度
- **快速完成**：5次观看即获得30亲密度（每日上限）
- **并行观看**：支持6个房间同时进行，25分钟完成6个房间
- **智能管理**：实时监控观看进度，异常自动恢复

## 🔧 故障排除

### 常见错误

1. **access_key过期**
   - 症状：登录失败提示
   - 解决：重新获取access_key

2. **API限流429**
   - 症状：请求过于频繁
   - 解决：增加API_RATE_LIMIT值

3. **观看进度不更新**
   - 症状：长时间无进度变化
   - 解决：检查直播间是否正常

4. **配置文件错误**
   - 症状：启动失败，语法错误
   - 解决：检查YAML格式，注意空格和冒号

### 日志分析
```bash
# 查看主日志
tail -f logs/{uuid}.log

# 查看错误信息
grep "ERROR" logs/*.log

# 查看API调用统计
grep "API调用" logs/*.log
```

## 📝 更新日志

### v2.0（青龙优化版）
- 🗑️ **移除内置定时**：避免与青龙面板冲突
- 🛡️ **增强API限流**：降低限流风险90%
- 🚀 **优化并行机制**：提升任务执行效率
- 📦 **轻量化部署**：减少依赖和资源占用
- 🔧 **完善错误处理**：增强异常恢复能力

### v1.5（稳定版）
- ✨ 新增并行观看功能
- 🔄 完善重试机制
- 📊 增强通知系统
- 🛡️ 安全性提升

## 🙏 鸣谢

感谢以下开源项目：
- [XiaoMiku01/fansMedalHelper](https://github.com/XiaoMiku01/fansMedalHelper) - 原版粉丝牌助手
- [y1ndan/onepush](https://github.com/y1ndan/onepush) - 多平台推送通知库
- [ThreeCatsLoveFish/MedalHelper](https://github.com/ThreeCatsLoveFish/MedalHelper) - Go语言实现版本

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源协议。

---

⭐ 如果这个项目对你有帮助，请给个Star支持一下！