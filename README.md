# B站粉丝牌助手（自用修改）

> 自动化完成B站直播间每日任务，轻松获得粉丝牌亲密度


## 📋 功能特性

### 核心功能
- ✅ **自动点赞**：根据用户身份智能调整点赞次数
- ✅ **自动观看**：每日观看25分钟（每5分钟获得6亲密度，共30亲密度）
- ✅ **多账号支持**：支持同时运行多个B站账号
- ✅ **智能通知**：任务完成后推送通知结果

### 技术特性
- 🚀 **并行处理**：支持多直播间并行观看，提升效率
- 🔄 **重试机制**：网络异常自动重试，确保任务完成
- 📊 **详细日志**：可选的任务详情通知，便于调试
- ⚙️ **灵活配置**：YAML配置文件，参数可自定义


## 📝 更新日志

### v1
- ✨ 新增并行观看功能，提升任务效率
- 🗑️ 移除弹幕发送功能，简化代码结构
- 🗑️ 移除自动更新检查，减少网络请求
- 📊 增强通知系统，支持详细日志模式
- 🔧 优化项目结构，删除无用文件

## 🙏 鸣谢

感谢以下开源项目为本项目提供的支持：

- [XiaoMiku01/fansMedalHelper](https://github.com/XiaoMiku01/fansMedalHelper) - 原版粉丝牌助手
- [y1ndan/onepush](https://github.com/y1ndan/onepush) - 多平台推送通知库
- [ThreeCatsLoveFish/MedalHelper](https://github.com/ThreeCatsLoveFish/MedalHelper) - Go语言实现版本
- [andywang425/BLTH](https://github.com/andywang425/BLTH) - B站挂机助手

---

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源协议。
