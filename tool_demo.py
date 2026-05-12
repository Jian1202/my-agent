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

# 定义一个工具函数，用于获取当前系统的日期和时间；来自定义工具的示例：https://deepseek.com/docs/tools/function-tool
def get_current_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 定义工具列表，包含一个函数工具；工具的定义需要符合OpenAI工具规范：https://deepseek.com/docs/tools/overview
tools = [{
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
}]

# 模拟用户输入，询问当前时间；在实际应用中，这些消息可以来自用户的输入或者其他系统事件
messages = [{"role": "user", "content": "现在几点了？"}]

# 第一次调LLM
response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=messages,
    tools=tools
)
msg = response.choices[0].message
print("=== 第一次返回 ===")
print("content:", msg.content)
print("tool_calls:", msg.tool_calls)

# 把模型的回复加入历史
messages.append(msg.model_dump())

# 执行工具
if msg.tool_calls:
    for tool_call in msg.tool_calls:
        # 真正调用Python函数
        result = get_current_time()
        print(f"\n=== 工具执行结果 ===")
        print(f"函数：{tool_call.function.name}")
        print(f"结果：{result}")

        # 把结果塞进messages，role是“tool”
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result
        })

    # 第二次调LLM，这次它能看到工具结果了
    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=messages,
        tools=tools
    )
    msg = response.choices[0].message
    print("\n=== 第二次返回 （最终回答）===")
    print("content:", msg.content)