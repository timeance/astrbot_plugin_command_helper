import pytest
from astrbot_plugin_command_helper.matching import (
    CommandSpec,
    arguments_fit,
    match_command,
    one_edit,
    select_hints,
)


def spec(**kwargs):
    return CommandSpec(
        key="business.bind",
        plugin="business",
        handler_name="bind",
        names=kwargs.pop("names", ("mc 绑定", "绑定账号")),
        params=kwargs.pop("params", {"code": ""}),
        **kwargs,
    )


@pytest.mark.parametrize("text", ["mc绑定 THQHHK8T", "mc绑定THQHHK8T", "mc 绑定THQHHK8T"])
def test_spacing_keeps_original_code(text):
    hints = match_command(spec(), text, has_at=True, woken=True)
    assert select_hints(hints)[0].example() == "mc 绑定 THQHHK8T"
    assert hints[0].reason == "spacing"


def test_free_form_natural_language_is_not_a_passive_command():
    weather = spec(names=("天气",), params={"city": ""})
    for text in ("天气真好", "天气 不错，出去玩吧", "怎么申请白名单"):
        assert not match_command(weather, text, has_at=False, woken=False)


def test_chinese_head_ascii_argument_and_plus_are_explicit():
    whitelist = spec(names=("白名单申请",), argument_pattern=r"[A-Za-z0-9_]{3,16}")
    assert (
        match_command(whitelist, "白名单申请legend_lio", has_at=False, woken=False)[0].tail
        == "legend_lio"
    )
    assert not match_command(whitelist, "白名单申请+Legend_lio", has_at=False, woken=False)
    whitelist.allow_plus = True
    assert (
        match_command(whitelist, "白名单申请+Legend_lio", has_at=False, woken=False)[0].tail
        == "Legend_lio"
    )


def test_arguments_are_not_lowercased_or_rewritten():
    command = spec(names=("mc 发送",), params={"text": str, "rest": type("GreedyStr", (str,), {})})
    hint = match_command(command, "mc发送 Ab_Cd   X-9", has_at=True, woken=True)[0]
    assert hint.example() == "mc 发送 Ab_Cd   X-9"


def test_fuzzy_head_only_and_only_after_real_at():
    command = spec()
    assert not match_command(command, "mc 绑订 S6SGBC93", has_at=False, woken=False)
    hint = match_command(command, "mc 绑订 S6SGBC93", has_at=True, woken=True)[0]
    assert hint.reason == "similar" and hint.tail == "S6SGBC93"
    assert not match_command(spec(names=("绑定",)), "绑订 S6SGBC93", has_at=True, woken=True)


def test_alias_suggestion_is_not_a_new_command():
    command = spec(names=("白名单申请",), hint_aliases=("白名单",))
    assert not match_command(command, "白名单", has_at=False, woken=False)
    assert match_command(command, "白名单", has_at=True, woken=True)[0].command == "白名单申请"


def test_longest_command_and_same_handler_aliases():
    root = spec(names=("mc",), params={})
    binding = spec()
    status = spec(names=("mc 绑定状态",), params={})
    status.key = "business.status"
    hints = [
        hint
        for command in (root, binding, status)
        for hint in match_command(command, "mc绑定状态", has_at=True, woken=True)
    ]
    assert select_hints(hints)[0].spec.key == "business.status"


def test_explicit_at_precedes_wake_prefix():
    command = spec(require_at=True)
    assert (
        match_command(command, "mc 绑定 AbCd1234", has_at=False, woken=True)[0].reason
        == "missing_at"
    )
    command.require_at = False
    assert match_command(command, "mc 绑定 AbCd1234", has_at=False, woken=True)[0].reason == "valid"


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("abcd", "abce", True),
        ("abcd", "abc", True),
        ("abcd", "abxcd", True),
        ("abcd", "abcd", False),
        ("abcd", "abXY", False),
    ],
)
def test_single_edit_boundary(left, right, expected):
    assert one_edit(left, right) is expected


def test_declared_parameter_types_and_usage():
    command = spec(names=("等级设置",), params={"level": int, "enabled": True})
    assert arguments_fit(command, "2 true")
    assert not arguments_fit(command, "two true")
    assert not arguments_fit(command, "2 true extra")
    hint = match_command(command, "等级设置", has_at=False, woken=False)[0]
    assert hint.usage() == "等级设置 <level> [enabled]"


def test_ambiguous_commands_are_capped_without_executing_a_choice():
    hints = []
    for index in range(5):
        command = spec()
        command.key = f"plugin{index}.bind"
        hints.extend(match_command(command, "mc绑定 AbCd1234", has_at=True, woken=True))
    chosen = select_hints(hints)
    assert len(chosen) == 3
    assert len({hint.spec.key for hint in chosen}) == 3
