import sys
import logging
import asyncio
import traceback

logging.basicConfig(level=logging.ERROR)
from tests.phase2_scripting.test_phase2_integration import run_integration_test

async def main():
    try:
        await run_integration_test()
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, "status"):
            err_msg += f"\nHTTP Status: {e.status}"
            if hasattr(e, "message"):
                err_msg += f" - {e.message}"
        
        err_msg += "\n\n" + traceback.format_exc()
        
        with open("err.txt", "w", encoding="utf-8") as f:
            f.write(err_msg)
        print("Logged exception to err.txt")

if __name__ == "__main__":
    asyncio.run(main())
