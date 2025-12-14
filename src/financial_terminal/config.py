from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass
class AppConfig:
    poll_interval_seconds: int = 900
    cache_dir: Path = Path("cache")
    sec_enabled: bool = True
    sec_user_agent: str = "IQterminal/0.1 (contact: example@example.com)"
    sec_filings_per_ticker: int = 50
    sec_throttle_seconds: float = 0.2
    theme: str = "light"


def load_config(path: Path | None = None) -> AppConfig:
    """
    Load configuration from a TOML file, falling back to defaults if missing.
    """
    cfg = AppConfig()
    config_path = path or Path("config.default.toml")
    if config_path.exists():
        with config_path.open("rb") as f:
            raw = tomllib.load(f)
        cfg.poll_interval_seconds = int(raw.get("poll_interval_seconds", cfg.poll_interval_seconds))
        cfg.cache_dir = Path(raw.get("cache_dir", cfg.cache_dir))
        sources = raw.get("sources", {})
        cfg.sec_enabled = bool(sources.get("sec_enabled", cfg.sec_enabled))
        cfg.sec_user_agent = str(sources.get("sec_user_agent", cfg.sec_user_agent))
        cfg.sec_filings_per_ticker = int(sources.get("sec_filings_per_ticker", cfg.sec_filings_per_ticker))
        cfg.sec_throttle_seconds = float(sources.get("sec_throttle_seconds", cfg.sec_throttle_seconds))
        ui = raw.get("ui", {})
        cfg.theme = str(ui.get("theme", cfg.theme))
    return cfg
