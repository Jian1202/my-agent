from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

messages = [
    {"role": "system", "content": "你是一个简洁的助手，回答尽量短。"}
]

while True:
    
    user_input = input("\n你: ")

    # 如果用户输入为空，或者输入了退出指令，则跳过或退出循环
    if user_input.strip() == "":
        continue
    if user_input.strip().lower() in ("exit", "quit", "q"):
        break
    
    # 将用户输入添加到消息列表中：为了保持上下文，messages列表会随着对话进行不断增长
    messages.append({"role": "user", "content": user_input})
    
    
    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=messages
    )
    
    # 从API响应中提取AI的回复，并将其添加到消息列表中，以便在下一轮对话中保持上下文
    reply = response.choices[0].message.content
    messages.append({"role": "assistant", "content": reply})
    
    print(f"AI: {reply}")
    print(f"  (当前messages共{len(messages)}条)")