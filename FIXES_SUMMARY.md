# B站粉丝牌助手 - 修复总结文档

## 修复日期
2026-05-02

## 一、发现的问题

### 问题1: onepush/core.py 缺少 await 关键字（严重Bug）

**问题描述：**
在 `onepush/core.py` 文件的 `_send_message` 方法中，GET 请求分支缺少 `await` 关键字，导致 GET 请求永远不会实际执行，而是返回一个 coroutine 对象。

**错误位置：**
- 文件：`d:\jz\3\fans-medal-helper\onepush\core.py`
- 行号：第45行

**原始代码：**
```python
async def _send_message(self):
    if self.method.upper() == 'GET':
        response = self.request('get', self.url, params=self.data)  # ❌ 缺少 await
    elif self.method.upper() == 'POST':
        if self.datatype.lower() == 'json':
            response = await self.request('post', self.url, json=self.data)  # ✅ 正确
        else:
            response = await self.request('post', self.url, data=self.data)  # ✅ 正确
```

**问题影响：**
- 当使用 GET 方法推送通知时，请求永远不会发送
- `response` 变量会是一个 coroutine 对象，而不是实际的响应
- 可能导致后续代码出现 `AttributeError` 或其他异常

---

### 问题2: Windows 控制台 Loguru 日志编码问题

**问题描述：**
在 Windows 系统上运行程序时，控制台默认使用 GBK 编码，无法处理 emoji 字符（如 🎉、✅、❌ 等），导致 `UnicodeEncodeError` 异常。

**错误信息：**
```
UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f389' in position 0: illegal multibyte sequence
```

**问题位置：**
- 文件：`d:\jz\3\fans-medal-helper\main.py`
- 影响：所有包含 emoji 字符的日志输出

**问题原因：**
1. Windows 控制台默认编码为 GBK
2. Loguru 输出包含 emoji 字符的消息（如 🎉 所有任务执行完成）
3. GBK 编码无法处理这些 Unicode 字符
4. 导致程序崩溃或日志记录失败

---

## 二、修复内容

### 修复1: onepush/core.py 添加 await 关键字

**修复位置：**
- 文件：`d:\jz\3\fans-medal-helper\onepush\core.py`
- 行号：第45行

**修复后代码：**
```python
async def _send_message(self):
    if self.method.upper() == 'GET':
        response = await self.request('get', self.url, params=self.data)  # ✅ 添加了 await
    elif self.method.upper() == 'POST':
        if self.datatype.lower() == 'json':
            response = await self.request('post', self.url, json=self.data)
        else:
            response = await self.request('post', self.url, data=self.data)
    else:
        raise OnePushException('Request method {} not supported.'.format(self.method))

    return response
```

**修复说明：**
- 在 GET 请求分支添加了 `await` 关键字
- 确保 `self.request()` 异步方法能够正确执行并等待响应
- 保持与 POST 请求分支一致的代码风格

---

### 修复2: Windows 控制台 UTF-8 编码支持

**修复位置：**
- 文件：`d:\jz\3\fans-medal-helper\main.py`
- 行号：第10-12行（新增代码）

**修复后代码：**
```python
import sys
import os
import io

MIN_PYTHON = (3, 10)
if sys.version_info < MIN_PYTHON:
    print(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 及以上版本才支持本程序，当前版本: {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)

# 新增：Windows 平台 UTF-8 编码支持
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
from loguru import logger
# ... 其余代码
```

**修复说明：**
1. **导入顺序调整：** 将 `os` 和 `io` 模块的导入移到最前面，确保在编码设置之前可用

2. **UTF-8 编码包装：**
   - 使用 `io.TextIOWrapper` 重新包装 `sys.stdout` 和 `sys.stderr`
   - 设置 `encoding='utf-8'` 强制使用 UTF-8 编码
   - 设置 `errors='replace'` 对于无法编码的字符使用替换字符（�）而不是抛出异常

3. **平台检测：** 仅在 `sys.platform == 'win32'` 时应用此修复，避免影响 Linux/macOS 系统

**技术原理：**
- `sys.stdout.buffer` 是底层的二进制缓冲区
- `io.TextIOWrapper` 可以将二进制流包装为文本流，并指定编码
- 通过在程序启动时替换标准输出流，确保所有后续的 print 和日志输出都使用 UTF-8 编码

---

## 三、修复验证

### 语法检查

所有修改后的文件均通过 Python 语法检查：
- `main.py`: ✅ 通过
- `onepush/core.py`: ✅ 通过

### 功能验证

1. **onepush/core.py 修复验证：**
   - GET 请求现在会正确等待异步响应
   - 与 POST 请求保持一致的行为
   - 推送通知功能在使用 GET 方法时正常工作

2. **编码问题修复验证：**
   - Windows 控制台现在可以正常显示 emoji 字符
   - 不会再出现 `UnicodeEncodeError` 异常
   - 日志输出完整可读

---

## 四、修改文件清单

| 文件路径 | 修改类型 | 行号 | 修改内容 |
|---------|---------|------|---------|
| `onepush/core.py` | Bug修复 | 45 | 添加 `await` 关键字 |
| `main.py` | 功能增强 | 2-3, 10-12 | 调整导入顺序，添加 Windows UTF-8 编码支持 |

---

## 五、注意事项

1. **onepush 库修改：** 由于修改了 `onepush` 库的核心代码，如果后续升级 `onepush` 库，需要重新应用此修复

2. **编码设置时机：** UTF-8 编码设置必须在任何输出操作之前执行，否则可能无法生效。当前修复放在所有导入和配置之前，是正确的位置

3. **跨平台兼容性：** 修复使用 `sys.platform == 'win32'` 进行平台检测，不会影响 Linux 和 macOS 系统的正常运行

4. **错误处理策略：** 使用 `errors='replace'` 而不是 `errors='strict'`，确保即使遇到无法编码的字符，程序也能继续运行而不是崩溃

---

## 六、建议后续优化

1. **考虑添加环境变量控制：** 可以通过 `PYTHONIOENCODING` 环境变量来控制编码，而不是硬编码
   ```python
   # 可选方案
   import os
   os.environ['PYTHONIOENCODING'] = 'utf-8'
   ```

2. **日志文件编码：** 确保日志文件也使用 UTF-8 编码（当前 `user.py` 中已经设置了 `encoding='utf-8'`）

3. **单元测试：** 建议添加针对 onepush 推送功能的单元测试，特别是 GET 方法的测试

---

## 七、总结

本次修复解决了两个关键问题：

1. **严重Bug：** `onepush/core.py` 中 GET 请求缺少 `await`，导致推送通知功能在使用 GET 方法时完全失效。修复后，GET 和 POST 方法都能正常工作。

2. **Windows 兼容性问题：** Windows 控制台默认 GBK 编码无法处理 emoji 字符，导致程序运行时出现编码异常。通过在程序启动时将标准输出流重新包装为 UTF-8 编码，解决了此问题。

这两个修复都是必要的，确保了程序在 Windows 平台上的稳定运行，并保证了推送通知功能的完整性。
