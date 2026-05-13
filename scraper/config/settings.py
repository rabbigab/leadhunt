import os
import random
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent.parent


def load_config() -> dict:
    config_path = ROOT / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Settings:
    # Supabase
    SUPABASE_URL: str = os.environ["SUPABASE_URL"]
    SUPABASE_SERVICE_ROLE_KEY: str = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    # Facebook
    FB_EMAIL: str = os.environ["FB_EMAIL"]
    FB_PASSWORD: str = os.environ["FB_PASSWORD"]

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
    TELEGRAM_CHAT_ID: str = os.environ["TELEGRAM_CHAT_ID"]

    # Proxies
    PROXY_ENABLED: bool = os.getenv("PROXY_ENABLED", "false").lower() == "true"
    _proxy_list_raw: str = os.getenv("PROXY_LIST", "")
    PROXY_LIST: list[str] = [p.strip() for p in _proxy_list_raw.split(",") if p.strip()]

    # Options
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"

    SESSIONS_DIR: Path = ROOT / "sessions"
    LOGS_DIR: Path = ROOT / "logs"

    def get_next_proxy(self) -> str | None:
        """Retourne un proxy aléatoire depuis le pool, ou None si désactivé."""
        if not self.PROXY_ENABLED or not self.PROXY_LIST:
            return None
        return random.choice(self.PROXY_LIST)


settings = Settings()
