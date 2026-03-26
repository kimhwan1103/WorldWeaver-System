"""WorldWeaver 웹 서버 실행."""

import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    is_dev = os.getenv("DEMO_MODE", "true").lower() != "true"

    uvicorn.run(
        "worldweaver.api.server:app",
        host="0.0.0.0",
        port=port,
        reload=is_dev,
    )
