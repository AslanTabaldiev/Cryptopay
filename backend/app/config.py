"""Application settings, read once from environment variables (12-factor)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so local development needs no extra dependency."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    database_url: str
    rpc_url: str
    chain_id: int
    network_name: str
    explorer_url: str
    merchant_address: str
    merchant_api_key: str
    required_confirmations: int
    default_ttl_minutes: int
    tx_not_found_timeout_minutes: int
    poll_interval_seconds: float
    webhook_url: str | None
    webhook_secret: str
    cors_origins: list[str] = field(default_factory=list)
    run_watcher: bool = True
    static_dir: str | None = None  # собранный React (frontend/dist); в Docker — /app/static

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        env = os.environ.get

        database_url = env("DATABASE_URL", "sqlite:///./cryptopay.db")
        # Render / Neon give "postgres://" or "postgresql://"; use the psycopg 3 driver.
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://"):]
        if database_url.startswith("postgresql://"):
            database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]

        return cls(
            database_url=database_url,
            rpc_url=env("RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com"),
            chain_id=int(env("CHAIN_ID", "11155111")),
            network_name=env("NETWORK_NAME", "Sepolia"),
            explorer_url=env("EXPLORER_URL", "https://sepolia.etherscan.io").rstrip("/"),
            merchant_address=env("MERCHANT_ADDRESS", "0x0000000000000000000000000000000000000000"),
            merchant_api_key=env("MERCHANT_API_KEY", "dev-secret-key"),
            required_confirmations=int(env("REQUIRED_CONFIRMATIONS", "2")),
            default_ttl_minutes=int(env("DEFAULT_TTL_MINUTES", "15")),
            tx_not_found_timeout_minutes=int(env("TX_NOT_FOUND_TIMEOUT_MINUTES", "10")),
            poll_interval_seconds=float(env("POLL_INTERVAL_SECONDS", "5")),
            webhook_url=env("WEBHOOK_URL") or None,
            webhook_secret=env("WEBHOOK_SECRET", "dev-webhook-secret"),
            cors_origins=[o.strip() for o in env("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
            run_watcher=env("RUN_WATCHER", "true").lower() == "true",
            static_dir=env("STATIC_DIR") or _default_static_dir(),
        )


def _default_static_dir() -> str | None:
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    return str(dist) if (dist / "index.html").exists() else None
