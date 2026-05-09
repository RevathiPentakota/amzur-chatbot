import litellm
import asyncio

print("Has acompletion:", hasattr(litellm, "acompletion"))
print("Has completion:", hasattr(litellm, "completion"))

# Test sync
try:
    r = litellm.completion(
        model="gemini/gemini-2.5-flash",
        api_base="https://litellm.amzur.com",
        api_key="sk-YLmZIK6subdXeSdRWnyCXg",
        messages=[{"role": "user", "content": "test"}],
        timeout=30,
    )
    print("SYNC OK:", r.choices[0].message.content[:50])
except Exception as e:
    print("SYNC FAIL:", type(e).__name__, str(e)[:100])

# Test async
async def test_async():
    try:
        r = await litellm.acompletion(
            model="gemini/gemini-2.5-flash",
            api_base="https://litellm.amzur.com",
            api_key="sk-YLmZIK6subdXeSdRWnyCXg",
            messages=[{"role": "user", "content": "test"}],
            timeout=30,
        )
        print("ASYNC OK:", r.choices[0].message.content[:50])
    except Exception as e:
        print("ASYNC FAIL:", type(e).__name__, str(e)[:100])

asyncio.run(test_async())
