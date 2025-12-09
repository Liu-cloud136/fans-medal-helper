# 项目结构说明

```
fans-medal-helper/
├── README.md                 # 项目说明文档（已整合所有说明）
├── CHANGELOG.md             # 版本更新日志
├── LICENSE                  # 开源协议
├── .gitignore              # Git忽略文件
├── Dockerfile              # Docker构建文件
├── entrypoint.sh           # Docker入口脚本
│
├── requirements.txt         # Python依赖清单
├── users.example.yaml      # 配置文件示例
│
├── index.py                # 青龙面板入口文件
├── main.py                 # 主程序入口
│
├── src/                    # 核心源码目录
│   ├── __init__.py
│   ├── api.py             # B站API接口封装
│   └── user.py            # 用户任务逻辑
│
└── onepush/               # 推送通知库
    ├── __init__.py
    ├── __version__.py
    ├── core.py            # 核心推送逻辑
    ├── exceptions.py      # 异常定义
    └── providers/         # 各推送服务商实现
```

## 文件说明

### 核心文件
- **main.py**: 程序主入口，负责配置加载和任务调度
- **index.py**: 青龙面板专用入口文件
- **src/user.py**: 用户任务核心逻辑，包含点赞、观看等功能
- **src/api.py**: B站API接口封装，处理网络请求

### 配置文件
- **users.example.yaml**: 配置文件模板，包含所有可用参数
- **requirements.txt**: Python依赖包列表

### 部署相关
- **Dockerfile**: Docker镜像构建文件
- **entrypoint.sh**: Docker容器启动脚本
- **.gitignore**: Git版本控制忽略文件

### 文档
- **README.md**: 完整的项目说明文档
- **CHANGELOG.md**: 版本更新记录
- **LICENSE**: MIT开源协议

### 第三方库
- **onepush/**: 轻量级推送通知库，支持多种推送方式

## 运行流程

1. **启动**: main.py → 读取配置 → 创建用户实例
2. **登录**: BiliUser.loginVerify() → 验证access_key
3. **获取任务**: BiliUser.get_medals() → 获取粉丝牌列表
4. **执行任务**: 
   - 点赞任务: like_room() → 智能点赞
   - 观看任务: watch_room() → 并行观看
5. **通知**: 任务完成后推送结果
6. **退出**: 清理资源，程序结束

## 依赖关系

```
main.py
├── src/user.py (BiliUser)
│   ├── src/api.py (BiliApi)
│   ├── onepush/ (通知推送)
│   └── aiohttp (HTTP客户端)
├── PyYAML (配置解析)
├── loguru (日志系统)
└── pytz (时区处理)
```

## 目录清理说明

### 已删除的文件
- `test_like_fix.py` - 测试文件
- `API限流优化说明.md` - 已整合到README
- `代码逻辑错误修复报告.md` - 已整合到README
- `代码错误检查与修复报告.md` - 已整合到README
- `青龙面板定时功能移除说明.md` - 已整合到README
- `青龙面板部署说明.md` - 已整合到README

### 已移除的依赖
- `APScheduler>=3.10.0` - 定时任务框架（青龙面板不需要）
- `croniter>=1.4.0` - cron表达式解析（青龙面板不需要）

## 优化效果

- **文件数量**: 从25个减少到20个（减少20%）
- **文档整合**: 6个分散文档合并为1个统一README
- **依赖优化**: 减少2个定时相关依赖包
- **结构清晰**: 功能模块明确分离，便于维护