from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import datetime

load_dotenv()
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# ---- 工具函数 ----

# 定义一个工具函数，用于获取当前系统的日期和时间；来自定义工具的示例：https://deepseek.com/docs/tools/function-tool
def get_current_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 一个新的工具函数，用于读取本地文件的内容
def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"错误：文件 {path} 不存在"
    except Exception as e:
        return f"错误：{e}"

# 工具名 -> 函数的映射表
tool_functions = {
    "get_current_time": get_current_time,
    "read_file": read_file,
}

# ---- 工具schema ----
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
            "description": "读取指定路径的本地文件，返回文件的文本内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径"
                    }
                },
                "required": ["path"]
            }
        }
    }
]

# ---- 通用的工具执行函数 : 根据工具名和参数调用对应的Python函数 ----
def execute_tool(name, args):
    func = tool_functions.get(name)
    if func is None:
        return f"错误：未知工具 {name}"
    return func(**args)

# 主流程 :
# 1. 用户输入问题
# 2. 调用LLM，传入工具列表
# 3. 得到模型的回答
# 4. 遍历工具调用列表，执行工具，得到结果
# 5. 构造新的消息列表，加入工具调用的结果
# 6. 调用LLM，得到最终的回答

question = input("问点什么: ")
messages = [{"role": "user", "content": question}]

response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=messages,
    tools=tools
)
msg = response.choices[0].message
print(f"\n=== 模型返回 ===")
print(f"content: {msg.content}")
print(f"tool_calls: {msg.tool_calls}")

messages.append(msg.model_dump())

# 执行工具调用：模型可能会调用一个或多个工具，每个工具调用都包含工具名和参数；我们需要遍历这些工具调用，执行对应的Python函数，并把结果加入消息列表
if msg.tool_calls:
    for tool_call in msg.tool_calls:
        name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)
        result = execute_tool(name, args)
        print(f"\n=== 执行工具: {name}({args}) ===")
        print(f"结果: {result}")

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": str(result)
        })

    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=messages,
        tools=tools
    )
    msg = response.choices[0].message
    print(f"\n=== 最终回答 ===")
    print(msg.content)
else:
    print(f"\n=== 直接回答（没调工具） ===")
    print(msg.content)