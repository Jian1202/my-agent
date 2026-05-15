# 🤖 从零手搓 AI Agent

> 这是一个从零开始、不依赖任何 Agent 框架，纯手工搭建的 AI 智能代理（Agent）项目。用于练手和学习大模型工具调用（Function Calling）的核心原理。

---

## 📖 项目简介

本项目从最基础的 API 调用开始，**一步步实现了一个具备文件操作能力的自主 Agent**。代码演进路径清晰可见：

- **Step 1** → 验证 API 连通性（`test.py`）
- **Step 2** → 实现简单的命令行对话（`chat.py`）
- **Step 3** → 演示单次工具调用（`tool_demo.py`）
- **Step 4** → 演示多次工具调用与动态调度（`tool_demo2.py`）
- **Step 5** → 完整的 Agent 系统，支持多轮对话、工具自主调用、安全机制、记忆持久化（`agent.py`）

最终版的 Agent 能够理解用户的任务，自主决定调用哪些工具、按什么顺序调用，逐步完成任务并给出总结。

---

## ✨ 功能列表

| 功能 | 说明 |
|------|------|
| 🧠 **多轮对话** | 维护对话历史，支持连续交互 |
| 🛠️ **工具调用** | 集成 OpenAI Function Calling，模型自主决定调哪个工具 |
| 📂 **读取文件** | 支持分段读取大文件，自动提示文件总长度 |
| ✏️ **写入文件** | 将内容写入指定路径 |
| 📋 **列出目录** | 查看当前目录下的文件列表 |
| 🕐 **获取时间** | 获取系统当前日期和时间 |
| 🐍 **执行代码** | 在子进程中安全执行 Python 代码并返回输出 |
| 🧠 **记忆持久化** | 记录用户偏好、事实和备忘，跨会话持久化存储与读取 |
| 🔒 **安全机制** | 敏感文件黑名单、输出脱敏（过滤密钥/token）、目录隐藏 |

---

## 🔧 安全特性

Agent 内置了三层安全防线：

1. **代码层硬拦截** — `.env` 等敏感文件在工具函数中直接被拒绝读取
2. **目录隐藏** — `.env`、`venv`、`__pycache__`、`.git` 等目录不暴露给模型
3. **输出脱敏** — 所有工具返回值经过正则过滤，`sk-`、`key-`、`token-` 等疑似密钥字符串自动打码

---

## 📂 项目文件结构

```
.
├── agent.py          # 🎯 核心 Agent 系统（含工具 + 安全机制 + 记忆 + 主循环）
├── chat.py           # 💬 简易命令行聊天机器人
├── test.py           # 🔌 API 连通性测试脚本
├── tool_demo.py      # 🛠️ 单工具调用流程演示（获取时间）
├── tool_demo2.py     # 🛠️ 多工具调用流程演示（获取时间 + 读取文件）
├── .gitignore        # Git 忽略配置
├── .env              # API 密钥配置（已加入 .gitignore，不上传）
├── README.md         # 📄 本文件
├── notes.txt         # 中文笔记
├── notes_en.txt      # 英文笔记
├── agent_report.md   # Agent 运行报告
├── eda_report.md     # 数据分析报告
├── kc_house_data.csv # 房价数据集（已加入 .gitignore，不上传）
├── 九九乘法表.txt     # 测试生成文件
└── 水仙花数.java      # 测试生成文件
```

> 💡 `memory.json`（记忆持久化文件）和 `kc_house_data.csv` 一样，已加入 `.gitignore`，仅本地使用。

---

## 🚀 环境要求

- Python 3.10+
- 一个 [DeepSeek API Key](https://platform.deepseek.com/)

---

## 📦 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/Jian1202/my-agent.git
cd my-agent

# 2. 安装依赖
pip install openai python-dotenv

# 3. 配置 API 密钥
# 在项目根目录创建 .env 文件，写入：
echo "DEEPSEEK_API_KEY=你的API密钥" > .env
```

---

## ▶️ 运行方式

### 运行完整 Agent

```bash
python agent.py
```

启动后输入任务即可，例如：
- _"帮我列出当前目录下的所有文件"_
- _"读取 README.md 的前 200 个字符"_
- _"现在几点了？"_
- _"写一个 Python 脚本，打印 1 到 10 的平方"_

输入 `q`、`quit` 或 `exit` 退出。

### 运行各学习阶段的脚本

```bash
# 测试 API 连通性
python test.py

# 运行简易聊天机器人
python chat.py

# 单工具调用演示
python tool_demo.py

# 多工具调用演示
python tool_demo2.py
```

---

## 🧠 学习路径

如果你想理解 Agent 的工作原理，建议按以下顺序阅读代码：

1. **`test.py`** → 最简 API 调用，了解怎么连大模型
2. **`chat.py`** → 多轮对话，了解 messages 上下文管理
3. **`tool_demo.py`** → 单工具调用，理解 Function Calling 的完整 4 步流程
4. **`tool_demo2.py`** → 多工具动态调度，理解工具注册表 + 通用执行器模式
5. **`agent.py`** → 完整 Agent，综合以上所有概念 + 安全机制 + 记忆持久化 + 自动循环

---

## 📝 目前已实现的核心能力（agent.py）

- ✅ 基于 DeepSeek API 的 Function Calling
- ✅ 7 个内置工具（时间、读写文件、列目录、执行代码、读取/更新记忆）
- ✅ 工具注册表 + 通用执行器模式
- ✅ 敏感文件黑名单防御
- ✅ 输出脱敏（密钥/Token 自动过滤）
- ✅ 目录列表隐藏敏感项
- ✅ 大文件分段读取支持
- ✅ 30 秒子进程超时保护
- ✅ 最大执行步数限制（防止无限循环）
- ✅ 终端输出截断防刷屏
- ✅ 记忆持久化（用户偏好、事实、备忘，跨会话存储）

---

> ✍️ **特别说明**：本文档由 Agent 自身生成并更新。没错，就是你面前的这个 AI Agent 读取了项目中的所有代码，理解了项目结构，然后写下了这份 README — 这正是它能做的事情之一 📝🤖
