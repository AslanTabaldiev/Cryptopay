"""Настройки приложения. Читаются один раз из переменных окружения (или файла .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Простейший загрузчик .env, чтобы для локального запуска не нужна была отдельная библиотека."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./cryptopay.db"
    rpc_url: str = "https://ethereum-sepolia-rpc.publicnode.com"
    chain_id: int = 11155111  # Ethereum Sepolia
    network_name: str = "Sepolia"
    explorer_url: str = "https://sepolia.etherscan.io"
    merchant_address: str = "0x0000000000000000000000000000000000000000"
    # API-ключ магазина. Учебный проект: ключ показывается на сайте,
    # а его проверку можно включить или выключить переключателем в кабинете.
    api_key: str = "cryptopay-demo-key"
    api_key_required: bool = False  # значение переключателя при запуске сервера
    required_confirmations: int = 2
    default_ttl_minutes: int = 15
    tx_not_found_timeout_minutes: int = 10
    poll_interval_seconds: float = 5
    public_url: str = "http://localhost:8000"  # адрес сайта; на Render подставляется сам
    # Куда слать вебхуки. По умолчанию — во встроенный демо-магазин (/api/shop/webhook).
    webhook_url: str | None = None
    webhook_secret: str = "dev-webhook-secret"
    # Telegram-бот для уведомлений продавца (необязательно). Создаётся у @BotFather.
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    run_watcher: bool = True
    static_dir: str | None = None  # папка с собранным сайтом (frontend/dist)

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(BACKEND_DIR / ".env")
        env = os.environ.get

        database_url = env("DATABASE_URL", cls.database_url)
        # Render выдаёт адрес вида postgres://… — подставляем драйвер psycopg.
        for prefix in ("postgres://", "postgresql://"):
            if database_url.startswith(prefix):
                database_url = "postgresql+psycopg://" + database_url[len(prefix):]

        dist = BACKEND_DIR.parent / "frontend" / "dist"
        # Render сам задаёт RENDER_EXTERNAL_URL — адрес сервиса в интернете.
        public_url = (env("PUBLIC_URL") or env("RENDER_EXTERNAL_URL") or cls.public_url).rstrip("/")
        return cls(
            database_url=database_url,
            rpc_url=env("RPC_URL", cls.rpc_url),
            chain_id=int(env("CHAIN_ID", cls.chain_id)),
            network_name=env("NETWORK_NAME", cls.network_name),
            explorer_url=env("EXPLORER_URL", cls.explorer_url).rstrip("/"),
            merchant_address=env("MERCHANT_ADDRESS", cls.merchant_address),
            api_key=env("MERCHANT_API_KEY", "").strip() or cls.api_key,
            api_key_required=env("API_KEY_REQUIRED", "false").lower() == "true",
            required_confirmations=int(env("REQUIRED_CONFIRMATIONS", cls.required_confirmations)),
            default_ttl_minutes=int(env("DEFAULT_TTL_MINUTES", cls.default_ttl_minutes)),
            tx_not_found_timeout_minutes=int(env("TX_NOT_FOUND_TIMEOUT_MINUTES", cls.tx_not_found_timeout_minutes)),
            poll_interval_seconds=float(env("POLL_INTERVAL_SECONDS", cls.poll_interval_seconds)),
            public_url=public_url,
            webhook_url=env("WEBHOOK_URL") or f"{public_url}/api/shop/webhook",
            telegram_bot_token=env("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=env("TELEGRAM_CHAT_ID") or None,
            webhook_secret=env("WEBHOOK_SECRET", cls.webhook_secret),
            cors_origins=[o.strip() for o in env("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
            run_watcher=env("RUN_WATCHER", "true").lower() == "true",
            static_dir=env("STATIC_DIR") or (str(dist) if (dist / "index.html").exists() else None),
        )
