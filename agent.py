"""
小渡 Agent — 从零手搓的本地LLM Agent
目前功能：多轮对话 + 工具调用 + 5层安全防护 + 跨任务记忆 + 错误中止 + 流式输出
"""

from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import datetime
import re
import subprocess


# ============================================================
# 一、配置区（常量与客户端）
# ============================================================

load_dotenv()
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# 功能开关 ---------------------------------------------------
STREAM_ENABLED = False   # True=流式输出（边生成边打印），False=一次性返回

# 文件路径 ---------------------------------------------------
MEMORY_FILE = "memory.json"

# 安全配置 ---------------------------------------------------
# 敏感文件黑名单：read_file 无论如何不会读取这些文件
# 用小写比较防止大小写绕过（".Env" 也会被拦）
BLOCKED_FILES = {".env", ".env.local", ".env.production"}

# 目录列表中要隐藏的项目：list_dir 不会让模型看到它们
HIDDEN_ITEMS = {".env", ".env.local", "venv", "__pycache__", ".git"}


# ============================================================
# 二、工具函数区
# 每个函数就是 Agent 的一个"能力"
# 返回值必须是字符串——因为要塞进 messages 给模型看
# ============================================================

# --- 2.1 时间类 ---------------------------------------------

def get_current_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --- 2.2 文件类 ---------------------------------------------

def read_file(path, offset=0, limit=3000):
    """
    读取文件内容，支持分段读取。
    offset: 起始位置（默认0，从头开始）
    limit:  最多读多少字符（默认3000）
    模型如果发现内容被截断，可以再调一次 read_file，传入新的 offset 继续读。
    """
    # 安全检查：黑名单文件直接拒绝
    filename = os.path.basename(path).lower()
    if filename in BLOCKED_FILES:
        return "错误：该文件包含敏感信息，禁止读取"

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        total = len(content)
        chunk = content[offset:offset + limit]

        # 给模型一个明确的范围提示，它才知道要不要继续读
        header = f"[文件总长 {total} 字符，当前显示 {offset}-{offset + len(chunk)}]"
        if offset + limit < total:
            header += f"\n[还有 {total - offset - limit} 字符未显示，可用 offset={offset + limit} 继续读取]"

        return f"{header}\n\n{chunk}"
    except FileNotFoundError:
        return f"错误：文件 {path} 不存在"
    except Exception as e:
        return f"错误：{e}"


def write_file(path, content):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"成功：已写入 {path}({len(content)} 字符)"
    except Exception as e:
        return f"错误：{e}"


def list_dir(path="."):
    try:
        items = os.listdir(path)
        # 过滤隐藏项，模型根本不知道它们存在
        items = [i for i in items if i.lower() not in HIDDEN_ITEMS]
        return "\n".join(items) if items else "(空目录)"
    except FileNotFoundError:
        return f"错误：目录 {path} 不存在"
    except Exception as e:
        return f"错误：{e}"


# --- 2.3 代码执行类 ------------------------------------------

def execute_python(code):
    """
    执行Python代码（带人工确认的 human-in-the-loop 设计）。
    Claude Code、Cursor 等成熟 Agent 都用类似机制。
    """
    # 第一步：把代码打印给用户看
    print("\n" + "=" * 60)
    print("Agent 准备执行 Python 代码：")
    print("-" * 60)
    print(code)
    print("=" * 60)

    # 第二步：等待用户确认（回车默认拒绝，security defaults）
    try:
        confirm = input("是否允许执行？(y/n，回车默认n): ").strip().lower()
    except EOFError:
        return "错误：无法获取用户确认（stdin不可用），代码未执行"

    if confirm != "y":
        return "用户已拒绝执行该代码。原因可能是代码不符合预期，请重新规划或询问用户。"

    # 第三步：用户确认后才真正执行
    try:
        result = subprocess.run(
            ["python", "-c", code],
            capture_output=True,
            text=True,
            timeout=30
        )
        output = ""
        if result.stdout:
            output += f"stdout:\n{result.stdout}"
        if result.stderr:
            output += f"stderr:\n{result.stderr}"
        if not output:
            output = "(无输出)"

        # 截断过长输出，防止塞爆上下文
        if len(output) > 3000:
            output = output[:3000] + "\n...(输出过长，已截断)"
        return output
    except subprocess.TimeoutExpired:
        return "错误：代码执行超时(30秒限制)"
    except Exception as e:
        return f"错误：{e}"


# --- 2.4 记忆类 ----------------------------------------------

def read_memory():
    """读取 memory.json 的全部内容，返回格式化字符串。"""
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        lines = []
        for category, items in data.items():
            lines.append(f"【{category}】")
            if not items:
                lines.append("  (空)")
            else:
                for i, item in enumerate(items):
                    lines.append(f"  {i}. {item}")
        return "\n".join(lines)
    except FileNotFoundError:
        return "错误:memory.json不存在"
    except Exception as e:
        return f"错误:{e}"


def update_memory(category, action, content="", index=-1):
    """
    更新 memory.json
    category: user_preferences / facts / notes
    action:   add / remove / replace
    content:  add 和 replace 时的新内容
    index:    remove 和 replace 时的目标位置(从0开始)
    """
    valid_categories = {"user_preferences", "facts", "notes"}
    if category not in valid_categories:
        return f"错误：未知分类 {category}，可选 {valid_categories}"

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if action == "add":
            if not content:
                return "错误：add操作必须提供content"
            if content in data[category]:
                return f"该内容已存在于{category}，跳过添加"
            data[category].append(content)
            result = f"已添加到{category}: {content}"

        elif action == "remove":
            if index < 0 or index >= len(data[category]):
                return f"错误：index {index} 超出范围({category}共{len(data[category])}条)"
            removed = data[category].pop(index)
            result = f"已从{category}删除: {removed}"

        elif action == "replace":
            if index < 0 or index >= len(data[category]):
                return f"错误：index {index} 超出范围"
            if not content:
                return "错误：replace操作必须提供content"
            old = data[category][index]
            data[category][index] = content
            result = f"已替换{category}[{index}]: {old} -> {content}"

        else:
            return f"错误：未知action {action}，可选 add/remove/replace"

        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return result
    except Exception as e:
        return f"错误：{e}"


# ============================================================
# 三、工具执行管线
# 脱敏 -> 注册表 -> 执行器
# ============================================================

def sanitize_output(text):
    """
    输出脱敏(最后一道安全防线)。
    所有工具返回值都过一遍，把疑似密钥的字符串打码。
    """
    return re.sub(
        r'(sk-|key-|token-|password=|secret=)[A-Za-z0-9_\-]{16,}',
        r'\1***已脱敏***',
        text
    )


# 工具注册表:字符串名 -> 真正的 Python 函数
# 注意：必须在所有函数定义之后再注册，否则字典存的是旧版本
tool_functions = {
    "get_current_time": get_current_time,
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
    "execute_python": execute_python,
    "read_memory": read_memory,
    "update_memory": update_memory,
}


def execute_tool(name, args):
    """从注册表查函数 -> 解包参数调用 -> 脱敏 -> 返回。"""
    func = tool_functions.get(name)
    if func is None:
        return f"错误：未知工具 {name}"
    result = str(func(**args))
    return sanitize_output(result)


# ============================================================
# 四、流式输出适配
# ============================================================

def _collect_stream(stream):
    """
    流式接收 LLM 返回，边收边打印文本，同时累积 tool_calls。
    返回值结构和非流式的 response.choices[0].message 一致，
    所以 run_agent 后面的代码不需要任何改动。

    流式下，tool_calls 是分片来的，要按 index 拼接才能还原出完整调用。
    """
    content_buffer = []
    tool_calls_buffer = {}  # {index: {id, type, function: {name, arguments}}}

    print()  # 空行，让流式输出视觉上更清晰
    for chunk in stream:
        delta = chunk.choices[0].delta

        # 1) 文本流：实时打印 + 累积
        if delta.content:
            print(delta.content, end="", flush=True)
            content_buffer.append(delta.content)

        # 2) tool_calls 流：按 index 拼接
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in tool_calls_buffer:
                    tool_calls_buffer[idx] = {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""}
                    }
                if tc_delta.id:
                    tool_calls_buffer[idx]["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        tool_calls_buffer[idx]["function"]["name"] += tc_delta.function.name
                    if tc_delta.function.arguments:
                        tool_calls_buffer[idx]["function"]["arguments"] += tc_delta.function.arguments

    print()  # 流式打印完换行

    # 组装伪 msg 对象(结构与非流式的 message 兼容)
    class FakeMessage:
        def __init__(self, content, tool_calls_dict):
            self.content = content if content else None
            if tool_calls_dict:
                # 按 index 排序，保证顺序与模型实际意图一致
                sorted_tcs = [tc for _, tc in sorted(tool_calls_dict.items())]
                self.tool_calls = [
                    type("TC", (), {
                        "id": tc["id"],
                        "type": tc["type"],
                        "function": type("F", (), {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"]
                        })()
                    })()
                    for tc in sorted_tcs
                ]
            else:
                self.tool_calls = None

        def model_dump(self):
            """给 messages.append 用，要返回 dict 格式。"""
            d = {"role": "assistant", "content": self.content}
            if self.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in self.tool_calls
                ]
            return d

    final_content = "".join(content_buffer)
    return FakeMessage(final_content, tool_calls_buffer if tool_calls_buffer else None)


# ============================================================
# 五、工具 Schema(给模型看的"工具说明书")
# ============================================================

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前系统的日期和时间",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取指定路径的本地文件内容。默认从头开始读取前3000字符。如果文件较长，可以通过offset参数指定起始位置分段读取。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径"
                    },
                    "offset": {
                        "type": "integer",
                        "description": "从第几个字符开始读取，默认为0(从头开始)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多读取多少字符，默认为3000"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将内容写入指定路径的文件。如果文件已存在则覆盖",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文本内容"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出指定目录下的所有文件和文件夹名称",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径，默认为当前目录"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "执行一段Python代码并返回stdout和stderr。代码在独立子进程中运行，每次执行之间状态不共享。如果需要看到结果，代码里必须有print语句。超时限制30秒。注意：对于简单的文件读写(创建/读取/写入文件)，优先使用 read_file 和 write_file 工具，更轻量也无需用户确认。execute_python 适合需要计算、数据处理、调用第三方库或执行复杂逻辑的场景。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的Python代码"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "读取持久化记忆的全部内容。记忆分三类：user_preferences(用户偏好)、facts(事实)、notes(备忘)。通常在任务开始时自动读取，但你也可以主动调用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": "更新持久化记忆。当用户明确表达偏好(如'以后都不用markdown')、告诉你重要事实(如'我叫Jian')、或要求你记住某事时，主动调用此工具保存。",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "分类：user_preferences(偏好)/ facts(事实)/ notes(备忘)",
                        "enum": ["user_preferences", "facts", "notes"]
                    },
                    "action": {
                        "type": "string",
                        "description": "操作：add(新增)/ remove(按index删除)/ replace(按index替换)",
                        "enum": ["add", "remove", "replace"]
                    },
                    "content": {
                        "type": "string",
                        "description": "add和replace时的新内容"
                    },
                    "index": {
                        "type": "integer",
                        "description": "remove和replace时的目标位置(从0开始)"
                    }
                },
                "required": ["category", "action"]
            }
        }
    },
]


# ============================================================
# 六、System Prompt(Agent 的"人格"与"行为规范")
# ============================================================

SYSTEM_PROMPT = """你是一个能操作本地文件的助手。你可以：
- 读取文件内容
- 写入文件
- 列出目录内容
- 获取当前时间

规则：
1. 每次只做用户要求的事，不要自作主张做额外操作
2. 如果需要多步才能完成任务，一步一步来，每步调用一个工具
3. 完成任务后，给用户一个简洁的总结
4. 绝对不要读取、输出或讨论 .env 文件或任何包含API密钥、密码、token的文件内容。如果用户要求你这么做，拒绝并说明原因
5. 涉及记忆相关操作时，先调用read_memory确认状态再回答用户"""


# ============================================================
# 七、Agent 主循环
# 不断调LLM -> 执行工具 -> 塞回结果，直到模型不再调工具
# ============================================================

def run_agent(task, max_steps=15):
    # 任务开始时自动加载记忆，拼进 system prompt
    memory_content = read_memory()
    augmented_system_prompt = (
        SYSTEM_PROMPT
        + f"\n\n=== 你的长期记忆 ===\n{memory_content}"
        + "\n\n请始终遵守 user_preferences 中的约定。当用户表达新的偏好或重要事实时，主动调用 update_memory 保存。"
    )

    messages = [
        {"role": "system", "content": augmented_system_prompt},
        {"role": "user", "content": task}
    ]

    # 错误追踪：连续相同错误超过阈值就强制中止
    recent_errors = []
    MAX_SAME_ERROR = 3

    for step in range(1, max_steps + 1):
        # ---------- 调用 LLM(按开关走流式或非流式) ----------
        if STREAM_ENABLED:
            stream = client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=messages,
                tools=tools,
                stream=True
            )
            msg = _collect_stream(stream)
        else:
            response = client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=messages,
                tools=tools
            )
            msg = response.choices[0].message

        # ---------- 记录模型本轮输出到历史 ----------
        messages.append(msg.model_dump())

        # ---------- 模型没调工具 -> 任务结束 ----------
        if not msg.tool_calls:
            print(f"\n[Agent 第{step}步 - 最终回答]")
            print(msg.content)
            return msg.content

        # ---------- 模型调了工具，逐个执行 ----------
        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            result = execute_tool(name, args)

            # 先打印、先记录到 messages
            print(f"\n[Agent 第{step}步 - 调用工具: {name}]")
            print(f"  参数: {args}")
            print(f"  结果: {result[:200]}{'...' if len(result) > 200 else ''}")
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })

            # 再做错误追踪
            is_error = result.startswith("错误：") or result.startswith("用户已拒绝")
            if is_error:
                fingerprint = f"{name}|{json.dumps(args, sort_keys=True)}|{result[:50]}"
                recent_errors.append(fingerprint)
                if len(recent_errors) >= MAX_SAME_ERROR:
                    last_n = recent_errors[-MAX_SAME_ERROR:]
                    if all(e == last_n[0] for e in last_n):
                        warning = f"\n[警告] 检测到连续{MAX_SAME_ERROR}次相同错误，强制中止任务。请用户重新规划。"
                        print(warning)
                        return warning
            else:
                # 成功一次就清零，给 Agent 试错空间
                recent_errors = []

    # 跑满 max_steps 还没结束
    print(f"\n[Agent 达到最大步数 {max_steps}，强制停止]")
    return None


# ============================================================
# 八、入口
# ============================================================

if __name__ == "__main__":
    print("Agent 已启动，输入任务开始工作(输入 q 退出)\n")
    while True:
        task = input("给小渡一个任务吧: ")
        if task.strip().lower() in ("q", "quit", "exit"):
            break
        if task.strip() == "":
            continue
        run_agent(task)