import os
from dotenv import load_dotenv
import requests

load_dotenv()

openrouter_key = os.getenv("OPENROUTER_API_KEY")
gemini_key = os.getenv("GEMINI_API_KEY")

print("\n===================================")
print("LLM API TEST")
print("===================================")

if openrouter_key and openrouter_key.startswith("sk-or-"):
    print("Using OpenRouter API...")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {openrouter_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "google/gemini-2.5-flash",
        "max_tokens": 1000,
        "messages": [
            {"role": "user", "content": "In one sentence, explain what declarative knowledge means."}
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        content = response.json()["choices"][0]["message"]["content"]
        print("\nAPI Response:")
        print(content)
    else:
        print(f"Error {response.status_code}: {response.text}")
elif gemini_key:
    from google import genai
    print("Using Gemini API...")
    client = genai.Client(api_key=gemini_key)
    interaction = client.interactions.create(
        model="gemini-2.5-flash",
        input="In one sentence, explain what declarative knowledge means."
    )
    print("\nAPI Response:")
    print(interaction.output_text)
else:
    raise ValueError("Neither OPENROUTER_API_KEY nor GEMINI_API_KEY found in .env")