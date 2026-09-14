import os
from pathlib import Path
from pydantic import BaseModel

class AppSettings(BaseModel):
    APP_NAME: str = "PDF Safe Normalizer"
    APP_VERSION: str = "1.0.0"
    HOST: str = "127.0.0.1"
    PORT: int = int(os.environ.get("PORT", "8000"))
    DEFAULT_DPI: int = 200
    MAX_CONCURRENCY: int = 2
    ALLOWED_EXTENSIONS: tuple[str, ...] = (".pdf",)
    IGNORED_FILES: tuple[str, ...] = (".ds_store", "thumbs.db", "desktop.ini")
    IGNORED_PREFIXES: tuple[str, ...] = ("._", ".", "~$")

settings = AppSettings()
