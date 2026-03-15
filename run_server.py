"""WorldWeaver 웹 서버 실행."""

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    uvicorn.run(
        "worldweaver.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
