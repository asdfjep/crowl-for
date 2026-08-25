"""
Central LLM configuration for the analyzer.

All LLM needs (weekly-report polish, title translation) read the same
OpenAI-compatible endpoint configured once in the web 「系统设置」. The config is
persisted in the data directory (survives container rebuilds) and applied to
env vars the existing analysers already read.

Config file search order:
  1. <NEWS_DATA_DIR>/llm_config.json      # written by the web settings UI
  2. <project root>/llm_config.local.json # legacy CLI file
"""
import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_ENV_MAP = {
    "api_key": "NEWS_LLM_API_KEY",
    "base_url": "NEWS_LLM_BASE_URL",
    "model": "NEWS_LLM_MODEL",
    "timeout": "NEWS_LLM_TIMEOUT",
}


def config_paths():
    data_dir = os.getenv("NEWS_DATA_DIR", "").strip()
    paths = []
    if data_dir:
        paths.append(Path(data_dir).expanduser().resolve() / "llm_config.json")
    paths.append(PROJECT_ROOT / "llm_config.json")
    paths.append(PROJECT_ROOT / "llm_config.local.json")
    return paths


def load_config() -> Dict[str, Optional[str]]:
    """Return the persisted LLM config (per-value None when unset)."""
    for path in config_paths():
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {
                        "api_key": str(data.get("api_key") or "").strip() or None,
                        "base_url": str(data.get("base_url") or "").strip() or None,
                        "model": str(data.get("model") or "").strip() or None,
                        "timeout": int(data.get("timeout") or 60),
                    }
            except Exception as exc:
                logger.warning("Failed to read LLM config %s: %s", path, exc)
    return {"api_key": None, "base_url": None, "model": None, "timeout": 60}


def save_config(cfg: dict) -> Path:
    """Persist LLM config into the data dir so it survives container rebuilds."""
    data_dir = os.getenv("NEWS_DATA_DIR", "").strip()
    target = (Path(data_dir).expanduser().resolve() if data_dir else PROJECT_ROOT) / "llm_config.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({
            "api_key": str(cfg.get("api_key") or "").strip(),
            "base_url": str(cfg.get("base_url") or "").strip(),
            "model": str(cfg.get("model") or "").strip(),
            "timeout": int(cfg.get("timeout") or 60),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Saved LLM config to %s", target)
    return target


def apply_llm_env() -> None:
    """Put the persisted LLM config into env the way analysers read it."""
    config = load_config()
    mapping = {"api_key": "NEWS_LLM_API_KEY", "base_url": "NEWS_LLM_BASE_URL", "model": "NEWS_LLM_MODEL"}
    for key, env_name in mapping.items():
        value = config.get(key)
        if value:
            os.environ[env_name] = value
    if config.get("timeout"):
        os.environ["NEWS_LLM_TIMEOUT"] = str(config["timeout"])
    if not config.get("base_url"):
        os.environ.setdefault("NEWS_LLM_BASE_URL", "https://api.openai.com/v1")


def _env_config() -> Dict[str, Optional[str]]:
    return {
        "base_url": os.getenv("NEWS_LLM_BASE_URL") or "",
        "model": os.getenv("NEWS_LLM_MODEL") or "gpt-4o-mini",
        "api_key": os.getenv("NEWS_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "",
        "timeout": int(os.getenv("NEWS_LLM_TIMEOUT") or "60"),
    }


def chat_completion(user_text: str, system: Optional[str] = None,
                    max_tokens: int = 400, temperature: float = 0.2,
                    timeout: Optional[int] = None) -> str:
    """Minimal OpenAI-compatible chat call (no extra dependency)."""
    cfg = _env_config()
    base_url = cfg["base_url"].rstrip("/")
    if not base_url or not cfg["api_key"]:
        raise RuntimeError("LLM not configured: base_url or api_key is missing")
    messages = [{"role": "user", "content": user_text}]
    if system:
        messages.insert(0, {"role": "system", "content": system})
    body = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")
    req = urllib.request.Request(base_url + "/chat/completions", data=body, headers={
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout or cfg["timeout"]) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return (payload["choices"][0]["message"]["content"] or "").strip()


def translate_title(title: str) -> str:
    """Translate a news headline into Chinese via the configured LLM."""
    prompt = (
        "Translate this news headline into natural, concise Chinese. "
        "Keep proper nouns, company and product names in their original form "
        "(e.g. OpenAI, GPT, 英伟达 stays as is). Return ONLY the translation, "
        "no quotes or explanation.\n\n" + title
    )
    # 标题翻译是高频小请求：用短超时，端点异常时快速失败降级，避免拖慢整次分析。
    return chat_completion(prompt, system="You are a precise news-headline translator.",
                           max_tokens=120, temperature=0.1, timeout=10)