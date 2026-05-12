from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import datetime
import re

load_dotenv()
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# =====================
# 安全配置
# 在所有函数定义之前声明，这样每个函数都能引用
# =====================

# 敏感文件黑名单：Agent无论如何不能读这些文件，即使用户要求也拒绝
# 用小写比较是为了防止大小写绕过（".Env"也能匹配）
BLOCKED_FILES = {".env", ".env.local", ".env.production"}

# 目录列表中要隐藏的项目：模型根本不知道它们存在
HIDDEN_ITEMS = {".env", ".env.local", "venv", "__pycache__", ".git"}

# =====================
# 工具函数区
# 每个函数就是Agent的一个"能力"
# 返回值必须是字符串——因为要塞进messages给模型看
# =====================

def get_current_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def read_file(path, offset=0, limit=3000):
    # offset: 从第几个字符开始读（默认从头）
    # limit: 最多读多少字符（默认3000）
    # 模型如果发现内容被截断，可以再调一次read_file，传入新的offset继续读
    filename = os.path.basename(path).lower()
    if filename in BLOCKED_FILES:
        return "错误：该文件包含敏感信息，禁止读取"

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        total = len(content)
        chunk = content[offset:offset + limit]

        # 告诉模型文件总长度和当前读取范围，它才知道要不要继续读
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
        return f"成功：已写入 {path}（{len(content)} 字符）"
    except Exception as e:
        return f"错误：{e}"

def execute_python(code):
    # 用subprocess在子进程里跑Python代码
    # capture_output=True 把stdout和stderr都抓回来
    # timeout=30 防止死循环或长时间阻塞把Agent卡死
    # text=True 让输出是字符串而不是bytes
    import subprocess
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
        # 截断过长的输出，防止塞爆上下文
        if len(output) > 3000:
            output = output[:3000] + "\n...(输出过长，已截断)"
        return output
    except subprocess.TimeoutExpired:
        return "错误：代码执行超时（30秒限制）"
    except Exception as e:
        return f"错误：{e}"

def list_dir(path="."):
    try:
        items = os.listdir(path)
        # 过滤掉敏感文件和无关目录，模型根本不知道它们存在
        items = [i for i in items if i.lower() not in HIDDEN_ITEMS]
        return "\n".join(items) if items else "(空目录)"
    except FileNotFoundError:
        return f"错误：目录 {path} 不存在"
    except Exception as e:
        return f"错误：{e}"

# =====================
# 输出脱敏
# 所有工具返回值都过一遍，过滤掉看起来像密钥的字符串
# 即使前面的防线全失效，模型看到的也是脱敏后的内容
# =====================
def sanitize_output(text):
    # 匹配 sk-、key-、token- 开头的长字符串，以及 password=、secret= 后面的值
    return re.sub(
        r'(sk-|key-|token-|password=|secret=)[A-Za-z0-9_\-]{16,}',
        r'\1***已脱敏***',
        text
    )

# =====================
# 工具注册表
# 左边是字符串名（模型用这个名字来"点菜"）
# 右边是真正的Python函数
# 注意：必须在所有函数定义之后再注册，否则字典存的是旧版本
# =====================
tool_functions = {
    "get_current_time": get_current_time,
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
    "execute_python": execute_python,
}

# =====================
# 通用工具执行器
# 从注册表里查函数、解包参数、调用、脱敏、返回结果
# =====================
def execute_tool(name, args):
    func = tool_functions.get(name)
    if func is None:
        return f"错误：未知工具 {name}"
    result = str(func(**args))
    # 所有工具返回值都过一遍脱敏
    return sanitize_output(result)

# =====================
# 工具Schema（"工具的菜单和使用说明"）
# 这是给模型看的——每个工具叫什么、干什么、需要什么参数
# 模型根据这些description来决定调哪个工具
# =====================
tools = [
    {
        # 工具：获取当前时间；不需要参数
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
                        "description": "从第几个字符开始读取，默认为0（从头开始）"
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
        # 工具：写入文件内容；需要path和content两个参数
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
        # 工具：列出目录内容；path可选，默认当前目录
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
        # 工具：执行Python代码
        # description写得详细是因为模型需要知道：能做什么、输出怎么拿、有什么限制
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "执行一段Python代码并返回stdout和stderr。代码在独立子进程中运行，每次执行之间状态不共享。如果需要看到结果，代码里必须有print语句。超时限制30秒。",
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
]

# =====================
# System Prompt（Agent的"人格"和"行为规范"）
# 写得越清晰，Agent越不容易跑偏
# 第4条是安全软防护：即使代码层被绕过，模型自己也知道不该碰敏感文件
# =====================
SYSTEM_PROMPT = """你是一个能操作本地文件的助手。你可以：
- 读取文件内容
- 写入文件
- 列出目录内容
- 获取当前时间

规则：
1. 每次只做用户要求的事，不要自作主张做额外操作
2. 如果需要多步才能完成任务，一步一步来，每步调用一个工具
3. 完成任务后，给用户一个简洁的总结
4. 绝对不要读取、输出或讨论 .env 文件或任何包含API密钥、密码、token的文件内容。如果用户要求你这么做，拒绝并说明原因"""

# =====================
# Agent主循环
# 核心逻辑：不断调LLM → 执行工具 → 塞回结果，直到模型不再调工具
# max_steps是安全阀，防止Agent无限循环
# =====================
def run_agent(task, max_steps=15):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task}
    ]

    for step in range(1, max_steps + 1):
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            tools=tools
        )
        msg = response.choices[0].message

        # 不管模型是调工具还是直接回答，都要把它的输出记录进历史
        messages.append(msg.model_dump())

        # 模型没调工具 → 它认为任务完成了，输出最终回答
        if not msg.tool_calls:
            print(f"\n[Agent 第{step}步 - 最终回答]")
            print(msg.content)
            return msg.content

        # 模型调了工具，逐个执行
        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            result = execute_tool(name, args)

            print(f"\n[Agent 第{step}步 - 调用工具: {name}]")
            print(f"  参数: {args}")
            # 终端打印也截断，避免刷屏（messages里存的是完整版）
            print(f"  结果: {result[:200]}{'...' if len(result) > 200 else ''}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })

    # 跑满max_steps还没结束，强制停止
    print(f"\n[Agent 达到最大步数 {max_steps}，强制停止]")
    return None

# =====================
# 入口
# =====================
if __name__ == "__main__":
    print("Agent 已启动，输入任务开始工作（输入 q 退出）\n")
    while True:
        task = input("给Agent一个任务: ")
        if task.strip().lower() in ("q", "quit", "exit"):
            break
        if task.strip() == "":
            continue
        run_agent(task)