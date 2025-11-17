from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os


@dataclass
class BotConfig:
    token: str
    guild_ids: Optional[List[int]]
    owner_ids: Optional[List[int]]
    log_channel_id: Optional[int]
    welcome_channel_id: Optional[int]
    welcome_webhook_url: Optional[str]
    default_mute_role_id: Optional[int]
    staff_role_ids: Optional[List[int]]

    def sanitize(self) -> Dict[str, Any]:
        data = asdict(self)
        if "token" in data and data["token"]:
            data["token"] = "****"
        return data


def _parse_int_list(raw: Optional[str]) -> Optional[List[int]]:
    if not raw:
        return None
    values: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(part))
        except ValueError:
            continue
    return values or None


def _normalize_list(source: Any) -> Optional[List[int]]:
    if source is None:
        return None
    if isinstance(source, list):
        result: List[int] = []
        for item in source:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return result or None
    if isinstance(source, str):
        return _parse_int_list(source)
    return None


def load_config() -> BotConfig:
    base_dir = Path(__file__).resolve().parents[1]
    config_path = base_dir / "config.json"
    file_data: Dict[str, Any] = {}
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        if text.strip():
            file_data = json.loads(text)

    token = os.getenv("DISCORD_TOKEN") or file_data.get("token")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable or token in config.json is required")

    guild_ids = _normalize_list(os.getenv("DISCORD_GUILD_IDS") or file_data.get("guild_ids"))
    owner_ids = _normalize_list(os.getenv("DISCORD_OWNER_IDS") or file_data.get("owner_ids"))

    log_channel_raw = os.getenv("DISCORD_LOG_CHANNEL_ID") or file_data.get("log_channel_id")
    log_channel_id = int(log_channel_raw) if log_channel_raw else None

    welcome_channel_raw = os.getenv("DISCORD_WELCOME_CHANNEL_ID") or file_data.get("welcome_channel_id")
    welcome_channel_id = int(welcome_channel_raw) if welcome_channel_raw else None

    welcome_webhook_url = os.getenv("DISCORD_WELCOME_WEBHOOK_URL") or file_data.get("welcome_webhook_url")

    mute_role_raw = os.getenv("DISCORD_MUTE_ROLE_ID") or file_data.get("default_mute_role_id")
    default_mute_role_id = int(mute_role_raw) if mute_role_raw else None

    staff_roles_env = os.getenv("DISCORD_STAFF_ROLE_IDS")
    if staff_roles_env:
        staff_role_ids = _parse_int_list(staff_roles_env)
    else:
        staff_role_ids = _normalize_list(file_data.get("staff_role_ids"))

    return BotConfig(
        token=token,
        guild_ids=guild_ids,
        owner_ids=owner_ids,
        log_channel_id=log_channel_id,
        welcome_channel_id=welcome_channel_id,
        welcome_webhook_url=welcome_webhook_url,
        default_mute_role_id=default_mute_role_id,
        staff_role_ids=staff_role_ids,
    )
