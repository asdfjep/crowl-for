"""
Topic configuration loader for the shared weekly-news analyzer.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOPIC_CONFIG_DIR = PROJECT_ROOT / "configs" / "topics"


def resolve_project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def load_topic_config(topic: str | None = None) -> Dict[str, Any]:
    topic_key = topic or os.getenv("NEWS_TOPIC") or "ai"
    topic_key = topic_key.strip()
    config_path = TOPIC_CONFIG_DIR / f"{topic_key}.json"
    if not config_path.exists():
        available = ", ".join(sorted(p.stem for p in TOPIC_CONFIG_DIR.glob("*.json")))
        raise FileNotFoundError(
            f"Topic config not found: {config_path}. Available topics: {available}"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["topic_key"] = topic_key
    config["_config_path"] = str(config_path)
    if config.get("data_dir"):
        config["_data_dir"] = str(resolve_project_path(config["data_dir"]))
    else:
        config["_data_dir"] = str(PROJECT_ROOT / "data")
    return config
