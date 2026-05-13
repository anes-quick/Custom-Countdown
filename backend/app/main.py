from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os

from .api import router as api_router


def load_local_env() -> None:
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#") or "=" not in cleaned:
            continue
        key, value = cleaned.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def create_app() -> FastAPI:
    load_local_env()
    app = FastAPI(title="Countdown Backend", version="0.1.0")

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": "countdown-backend", "health": "/api/health"}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://custom-countdown-kappa.vercel.app"],
        allow_origin_regex=r"https://.*\.vercel\.app|^http://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")
    return app

app = create_app()
