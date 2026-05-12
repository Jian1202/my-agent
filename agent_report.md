# agent.py 代码总结报告

**文件总行数：** 330 行

---

## 一、文件概述

`agent.py` 是一个基于 **DeepSeek API** 构建的 **本地文件操作 AI Agent**。它通过 Function Calling 机制让大语言模型能够安全地调用本地工具，完成文件读取、写入、目录浏览、代码执行和获取时间等任务。

---

## 二、核心功能模块

### 1. 环境与客户端初始化（~15 行）
- 使用 `python-dotenv` 加载 `.env` 环境变量
- 初始化 `OpenAI` 客户端，连接 DeepSeek API（`api.deepseek.com`）

### 2. 安全配置（~10 行）
- **敏感文件黑名单** `BLOCKED_FILES`：`.env`、`.env.local`、`.env.production`
- **目录隐藏项** `HIDDEN_ITEMS`：`.env`、`.env.local`、`venv`、`__pycache__`、`.git`
- 所有比较均做小写转换，防止大小写绕过

### 3. 工具函数（~90 行）

| 工具名 | 功能 | 关键特性 |
|--------|------|----------|
| `get_current_time()` | 获取当前系统时间 | 无参数 |
| `read_file(path, offset, limit)` | 分段读取文件内容 | 支持 offset/limit 分段，防敏感文件，显示读取进度 |
| `write_file(path, content)` | 写入/覆盖文件 | 返回写入字符数 |
| `list_dir(path)` | 列出目录 | 自动过滤隐藏项 |
| `execute_python(code)` | 子进程执行 Python 代码 | 30 秒超时，截断过长输出，capture_output |

### 4. 输出脱敏（`sanitize_output`，~8 行）
- 对工具返回结果做正则替换，过滤以 `sk-`、`key-`、`token-` 开头或 `password=`、`secret=` 后跟长字符串的内容
- 替换为 `***已脱敏***`，作为最后一道安全防线

### 5. 工具注册与执行器（~10 行）
- `tool_functions` 字典：名称 → 函数的映射
- `execute_tool(name, args)`：查表、调用、脱敏、返回

### 6. 工具 Schema（~80 行）
- 为每个工具定义 JSON Schema（name、description、parameters）
- 供 LLM 理解工具的调用方式

### 7. System Prompt（~15 行）
- 定义 Agent 行为规则：只做用户要求的事、逐步执行、简洁总结、禁止读取敏感文件

### 8. 主循环 `run_agent(task, max_steps=15)`（~60 行）
- 核心逻辑：不断调 LLM → 执行工具 → 塞回结果 → 直到模型不再调工具
- `max_steps=15` 作为安全阀防止死循环
- 每步打印日志（工具名、参数、结果摘要）

### 9. 入口 `if __name__ == "__main__"`（~12 行）
- 交互式 REPL 循环，输入 `q/quit/exit` 退出

---

## 三、安全防护体系（多层防御）

| 层级 | 机制 | 说明 |
|------|------|------|
| ① 代码层 | `BLOCKED_FILES` 黑名单 | `read_file()` 直接拒绝读取敏感文件 |
| ② 目录层 | `HIDDEN_ITEMS` 过滤 | `list_dir()` 不让模型感知敏感文件存在 |
| ③ 输出层 | `sanitize_output()` | 所有工具返回值过正则过滤，脱敏密钥 |
| ④ 提示层 | System Prompt 规则#4 | 即使代码层被绕过，模型自身也被告知不该碰敏感文件 |

---

## 四、技术要点

- **API 模型**：`deepseek-v4-flash`
- **Function Calling 机制**：通过 `tools` 参数注册工具，模型自主选择调用
- **上下文管理**：每次 LLM 回复和工具结果都追加到 `messages` 列表中
- **分段读取**：支持大文件分段读取（默认 3000 字符/段）
- **子进程隔离**：`execute_python` 在独立子进程运行，状态不共享

---

## 五、整体架构图（概念）

```
用户输入 → run_agent()
              ↓
       LLM (DeepSeek) ←→ tools schema
              ↓
        tool_calls?
         ↙        ↘
       是          否
        ↓           ↓
  execute_tool()   输出最终回答
        ↓
   sanitize_output()
        ↓
  结果追加到 messages
        ↓
      回到 LLM（下一轮）
```

---

*报告生成时间：2026 年 5 月 12 日*  
*工具：read_file + execute_python*
