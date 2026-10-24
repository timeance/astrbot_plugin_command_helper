import re
from dataclasses import dataclass, field

import pytest
from astrbot_plugin_command_helper.phcraft import (
    command_visible,
    is_phcraft,
    requires_at,
    rule_for,
    visible_filter,
)


@dataclass
class At:
    qq: str


@dataclass
class Event:
    sender: str = "20000"
    group: str = "10000"
    bot: str = "30000"
    platform: str = "aiocqhttp"
    messages: list = field(default_factory=list)

    def get_sender_id(self):
        return self.sender

    def get_group_id(self):
        return self.group

    def get_self_id(self):
        return self.bot

    def get_platform_name(self):
        return self.platform

    def get_messages(self):
        return self.messages


def test_only_registered_phcraft_name_is_recognized():
    assert is_phcraft("astrbot_plugin_phcraft")
    assert not is_phcraft("another_astrbot_plugin_phcraft")
    assert not is_phcraft("PhCraft 群服务")


def test_binding_uses_actual_eight_character_code_without_requiring_at():
    rule = rule_for("cmd_bind")
    for code in ("S6SGBC93", "THQHHK8T", "a1B2c3D4"):
        assert re.fullmatch(rule["argument_pattern"], code)
    assert not re.fullmatch(rule["argument_pattern"], "ABC_1234")
    assert not re.fullmatch(rule["argument_pattern"], "ＡＢＣＤ１２３４")
    assert not requires_at("cmd_bind", Event(), "THQHHK8T")
    assert not rule["allow_plus"]


@pytest.mark.parametrize("handler", ["cmd_whitelist_apply", "cmd_whitelist_manage"])
def test_whitelist_accepts_minecraft_names_and_both_uuid_formats(handler):
    rule = rule_for(handler)
    for text in (
        "legend_lio",
        "Legend_lio",
        "Legend_lio 123456781234123412341234567890ab",
        "Legend_lio 12345678-1234-1234-1234-1234567890ab",
    ):
        assert re.fullmatch(rule["argument_pattern"], text)
    assert rule["allow_plus"]
    assert not re.fullmatch(rule["argument_pattern"], "有空再申请")


def test_rule_aliases_and_usage_are_independent_copies():
    rule = rule_for("cmd_whitelist_apply")
    assert rule["hint_aliases"] == ["白名单"]
    assert rule["usage"].format(command="新申请命令") == "新申请命令 <游戏ID> [UUID]"
    rule["hint_aliases"].append("不能泄露到下次调用")
    assert rule_for("cmd_whitelist_apply")["hint_aliases"] == ["白名单"]
    assert rule_for("unknown_handler") == {}


def test_whitelist_real_mention_requirement_matches_business_branches():
    event = Event()
    assert requires_at("cmd_whitelist_apply", event, "legend_lio")
    assert requires_at("cmd_whitelist_replace", event, "WL-" + "A" * 20)
    assert not requires_at("cmd_whitelist_confirm", event, "WL-" + "A" * 20)
    assert requires_at("cmd_whitelist_manage", event, "")
    assert requires_at("cmd_whitelist_manage", event, "legend_lio")
    assert not requires_at("cmd_whitelist_manage", event, "列表 2")
    assert not requires_at("cmd_whitelist_manage", event, "重试")
    assert not requires_at("cmd_whitelist_manage", Event(messages=[At("40000")]), "")
    assert requires_at("cmd_whitelist_manage", Event(messages=[At("30000")]), "legend_lio")


def test_known_filter_gates_read_current_config_without_running_filters():
    def unexpected_filter(*args):
        raise AssertionError("Other plugins' filter methods must never be called")

    allowed_group = type("AllowedGroup", (), {"filter": unexpected_filter})()
    admin = type("PluginAdmin", (), {"filter": unexpected_filter})()
    cfg = {"allowed_group_ids": ["10000"], "plugin_admin_ids": ["20000"]}
    assert visible_filter(allowed_group, "cmd_bind", cfg, Event()) is True
    assert visible_filter(allowed_group, "cmd_bind", cfg, Event(group="99999")) is False
    assert visible_filter(allowed_group, "cmd_bind", cfg, Event(platform="telegram")) is False
    assert visible_filter(admin, "cmd_diagnostics", cfg, Event()) is True
    assert visible_filter(admin, "cmd_diagnostics", cfg, Event(sender="40000")) is False
    cfg["allowed_group_ids"] = []
    assert visible_filter(allowed_group, "cmd_bind", cfg, Event()) is False
    assert visible_filter(object(), "cmd_bind", cfg, Event()) is None


def test_status_query_never_claims_a_command_argument():
    exact_query = type("ExactStatusQuery", (), {})()
    assert visible_filter(exact_query, "cmd_client_status", {}, Event()) is True
    assert command_visible("cmd_client_status", {}, Event(), "  ")
    assert not command_visible("cmd_client_status", {}, Event(), "绑定 THQHHK8T")


@pytest.mark.parametrize("text", ["列表", "列表 2", "删除", "重试"])
def test_whitelist_management_keywords_are_not_suggested_to_members(text):
    cfg = {"plugin_admin_ids": ["50000"]}
    assert not command_visible("cmd_whitelist_manage", cfg, Event(), text)
    assert command_visible("cmd_whitelist_manage", cfg, Event(sender="50000"), text)


def test_whitelist_other_mentions_require_plugin_admin_but_applications_do_not():
    cfg = {"plugin_admin_ids": ["50000"]}
    assert not command_visible("cmd_whitelist_manage", cfg, Event(messages=[At("40000")]), "")
    assert command_visible(
        "cmd_whitelist_manage", cfg, Event(sender="50000", messages=[At("40000")]), ""
    )
    assert command_visible("cmd_whitelist_manage", cfg, Event(), "Legend_lio")
    assert command_visible("cmd_whitelist_apply", cfg, Event(), "Legend_lio")
