"""Read-only command hints for the optional PhCraft plugin."""

UUID_PATTERN = r"(?:[0-9A-Fa-f]{32}|[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})"
APPLICATION_PATTERN = r"WL-[A-F0-9]{20}"

_RULES = {
    "cmd_bind": {
        "usage": "{command} [8位验证码]",
        "require_at": False,
        "argument_pattern": r"[A-Za-z0-9]{8}",
        "hint_aliases": [],
        "allow_plus": False,
    },
    "cmd_whitelist_apply": {
        "usage": "{command} <游戏ID> [UUID]",
        "require_at": True,
        "argument_pattern": rf"[A-Za-z0-9_]{{3,16}}(?:\s+{UUID_PATTERN})?",
        "hint_aliases": ["白名单"],
        "allow_plus": True,
    },
    "cmd_whitelist_manage": {
        "usage": "{command} <游戏ID> [UUID]",
        "require_at": True,
        "argument_pattern": rf"[A-Za-z0-9_]{{3,16}}(?:\s+{UUID_PATTERN})?",
        "hint_aliases": [],
        "allow_plus": True,
    },
    "cmd_whitelist_confirm": {
        "usage": "{command} <申请编号>",
        "require_at": False,
        "argument_pattern": APPLICATION_PATTERN,
        "hint_aliases": [],
        "allow_plus": False,
    },
    "cmd_whitelist_replace": {
        "usage": "{command} <申请编号>",
        "require_at": True,
        "argument_pattern": APPLICATION_PATTERN,
        "hint_aliases": [],
        "allow_plus": False,
    },
    "cmd_whitelist_verify": {
        "usage": "{command} <申请编号> <答案或验证码>",
        "require_at": False,
        "argument_pattern": rf"{APPLICATION_PATTERN}\s+(?:[0-9]{{1,3}}|[A-Za-z0-9]{{6}})",
        "hint_aliases": [],
        "allow_plus": False,
    },
}


def is_phcraft(plugin_name: str) -> bool:
    """Return whether the plugin declares PhCraft's registered name."""
    return plugin_name == "astrbot_plugin_phcraft"


def rule_for(handler_name: str) -> dict:
    """Return an independent copy of the handler's supplementary hint rule."""
    rule = _RULES.get(handler_name)
    return {**rule, "hint_aliases": list(rule["hint_aliases"])} if rule else {}


def visible_filter(filter_obj, handler_name: str, config: dict, event) -> bool | None:
    """Read known PhCraft gates without invoking another plugin's filter.

    The caller must first verify the filter belongs to the handler's module.
    ExactStatusQuery's argument restriction is checked by command_visible once
    the candidate command head has been removed.
    """
    name = type(filter_obj).__name__
    if name == "AllowedGroup":
        return event.get_platform_name() == "aiocqhttp" and str(event.get_group_id() or "") in {
            str(value) for value in config.get("allowed_group_ids", [])
        }
    if name == "PluginAdmin":
        return str(event.get_sender_id()) in {
            str(value) for value in config.get("plugin_admin_ids", [])
        }
    if name == "ExactStatusQuery":
        return handler_name == "cmd_client_status"
    return None


def requires_at(handler_name: str, event, text: str) -> bool:
    """Read the real-mention requirement for a command's argument tail."""
    if handler_name == "cmd_whitelist_manage":
        targets = any(
            type(component).__name__ == "At" and str(component.qq) != str(event.get_self_id())
            for component in event.get_messages()
        )
        tokens = text.split()
        return not targets and (not tokens or tokens[0] not in {"列表", "删除", "重试"})
    return bool(_RULES.get(handler_name, {}).get("require_at", False))


def command_visible(handler_name: str, config: dict, event, text: str) -> bool:
    """Check candidate-specific rules using the command's argument tail."""
    if handler_name == "cmd_client_status":
        return not text.strip()
    if handler_name == "cmd_whitelist_manage":
        targets = any(
            type(component).__name__ == "At" and str(component.qq) != str(event.get_self_id())
            for component in event.get_messages()
        )
        tokens = text.split()
        if targets or (tokens and tokens[0] in {"列表", "删除", "重试"}):
            return str(event.get_sender_id()) in {
                str(value) for value in config.get("plugin_admin_ids", [])
            }
    return True
