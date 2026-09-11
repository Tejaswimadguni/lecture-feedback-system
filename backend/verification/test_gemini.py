# pyrefly: ignore [missing-import]
from google import genai
import os


api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is not set")


client = genai.Client(
    api_key=api_key
)


interaction = client.interactions.create(
    model="gemini-3.6-flash",
    input="In one sentence, explain what declarative knowledge means."
)


print("\n===================================")
print("GEMINI TEST")
print("===================================")

print(interaction.output_text)