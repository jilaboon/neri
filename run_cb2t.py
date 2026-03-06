from __future__ import annotations

import webbrowser
from threading import Timer

import uvicorn

from app.main import app as fastapi_app


def open_browser() -> None:
    webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    Timer(1.2, open_browser).start()
    uvicorn.run(fastapi_app, host="127.0.0.1", port=8000, log_level="info")
