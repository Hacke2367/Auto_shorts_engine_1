import asyncio
import aiohttp
import os
import json
from dotenv import load_dotenv

# Load default .env if it exists
load_dotenv()

# The model name we want to verify
MODEL_NAME = "gemini-2.5-flash"
API_KEY = os.environ.get("GEMINI_API_KEY", "")

async def test_gemini():
    if not API_KEY:
        print("❌ Error: GEMINI_API_KEY environment variable is not set.")
        return

    # Using the standard v1beta REST endpoint format
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={API_KEY}"
    
    payload = {
        "contents": [{
            "parts": [{"text": "Hello, simply reply with the word 'PONG'."}]
        }]
    }
    
    headers = {"Content-Type": "application/json"}
    
    print(f"Testing Gemini API Connection...")
    print(f"URL: {url.replace(API_KEY, 'API_KEY_HIDDEN')}")
    print(f"Model: {MODEL_NAME}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                status = response.status
                print(f"HTTP Status: {status}")
                
                try:
                    data = await response.json()
                except Exception:
                    data = await response.text()
                
                if status == 200:
                    print("✅ Success! Gemini is responding.")
                    # Extract the response text
                    try:
                        reply = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        print(f"🤖 Gemini replied: '{reply}'")
                    except KeyError:
                        print(f"⚠️ Unexpected payload format: {json.dumps(data, indent=2)}")
                else:
                    print("❌ Failure! Gemini returned an error.")
                    print(json.dumps(data, indent=2))
        except Exception as e:
            print(f"❌ Network or Execution Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini())
