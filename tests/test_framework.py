"""Integration checks against actual AstrBot sources, never fake framework modules."""

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "text", ["大家晚上好", "今天的白名单处理完了吗", "我刚刚绑定了账号", "123456"]
)
async def test_ordinary_group_chat_stays_asleep(framework, text):
    runtime = await framework.setup()
    item = await runtime.dispatch(runtime.event(text))
    assert not item.is_wake
    assert not item.sent and not runtime.calls and not runtime.ai_calls


@pytest.mark.parametrize("at_other", [False, True])
async def test_missing_or_wrong_mention_gets_usage(framework, at_other):
    runtime = await framework.setup()
    item = await runtime.dispatch(runtime.event("mc 绑定 S6SGBC93", at_other=at_other))
    assert item.is_stopped()
    assert len(item.sent) == 1 and "mc 绑定" in item.texts[0]
    assert not runtime.calls and not runtime.ai_calls


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mc绑定S6SGBC93", "mc 绑定"),
        ("白名单申请Legend_lio", "白名单申请"),
        ("白明单申请 Legend_lio", "白名单申请"),
    ],
)
async def test_malformed_command_hints_before_ai(framework, text, expected):
    runtime = await framework.setup()
    item = await runtime.dispatch(runtime.event(text, mention=True))
    assert item.is_stopped()
    assert len(item.sent) == 1 and expected in item.texts[0]
    assert not runtime.calls and not runtime.ai_calls


@pytest.mark.parametrize(
    ("text", "mention"),
    [("mc 绑定 S6SGBC93", True), ("/mc 绑定 S6SGBC93", False), ("绑定账号 S6SGBC93", True)],
)
async def test_valid_command_and_alias_are_not_intercepted(framework, text, mention):
    runtime = await framework.setup()
    item = await runtime.dispatch(runtime.event(text, mention=mention))
    assert runtime.calls == [("bind", "S6SGBC93")]
    assert item.texts == ["业务绑定已执行"]
    assert not runtime.ai_calls


async def test_runtime_rename_and_alias_changes_are_observed(framework):
    runtime = await framework.setup()
    from astrbot.core.star.command_management import _set_filter_fragment
    from astrbot.core.star.filter.command import CommandFilter

    command = next(
        f for f in runtime.handlers["bind"].event_filters if isinstance(f, CommandFilter)
    )
    command.get_complete_command_names()
    _set_filter_fragment(command, "账号关联")
    command.alias = {"新的绑定"}
    command._cmpl_cmd_names = None
    old = await runtime.dispatch(runtime.event("mc 绑定 S6SGBC93"))
    assert not old.sent
    new = await runtime.dispatch(runtime.event("新的绑定 S6SGBC93"))
    assert new.is_stopped() and len(new.sent) == 1
    assert "账号关联" in new.texts[0] or "新的绑定" in new.texts[0]
    assert not runtime.calls and not runtime.ai_calls


@pytest.mark.parametrize("disabled", ["handler", "plugin", "plugin_set", "session"])
async def test_disabled_commands_are_not_suggested(framework, disabled):
    runtime = await framework.setup()
    if disabled == "handler":
        runtime.handlers["bind"].enabled = False
    elif disabled == "plugin":
        runtime.metadata.activated = False
    elif disabled == "plugin_set":
        runtime.bot_cfg["plugin_set"] = ["astrbot_plugin_command_helper"]
    else:
        runtime.disabled_plugins.add("example_business")
    item = await runtime.dispatch(runtime.event("mc 绑定 S6SGBC93"))
    assert not item.sent and not runtime.calls and not runtime.ai_calls


@pytest.mark.parametrize("group", ["77777", "88888"])
async def test_unknown_custom_filter_is_skipped_without_calling_it(framework, group):
    runtime = await framework.setup(config={"allowed_group_ids": []})
    item = await runtime.dispatch(runtime.event("自定义命令 Steve", group=group))
    assert not item.sent and not runtime.calls and not runtime.ai_calls
    assert not runtime.custom_filter_calls


async def test_standard_platform_filter_is_respected(framework):
    runtime = await framework.setup()
    item = runtime.event("mc 绑定 S6SGBC93")
    item.platform_meta.name = "telegram"
    item = await runtime.dispatch(item)
    assert not item.sent and not runtime.calls and not runtime.ai_calls


async def test_helper_group_allowlist_limits_hints(framework):
    runtime = await framework.setup(config={"allowed_group_ids": ["88888"]})
    item = await runtime.dispatch(runtime.event("mc绑定S6SGBC93"))
    assert not item.sent and not runtime.calls and not runtime.ai_calls


@pytest.mark.parametrize("admin", [False, True])
async def test_native_permission_limits_hint_visibility(framework, admin):
    runtime = await framework.setup(astrbot_config={"admins_id": ["12345"] if admin else []})
    item = await runtime.dispatch(runtime.event("危险命令"))
    assert bool(item.sent) is admin
    if admin:
        assert "危险命令" in item.texts[0] and item.is_stopped()
    assert not runtime.calls and not runtime.ai_calls


@pytest.mark.parametrize("admin", [False, True])
async def test_parent_group_native_permission_limits_child_hints(framework, admin):
    runtime = await framework.setup(astrbot_config={"admins_id": ["12345"] if admin else []})
    item = await runtime.dispatch(runtime.event("管理 删除 Steve"))
    assert bool(item.sent) is admin
    if admin:
        assert "管理 删除" in item.texts[0] and item.is_stopped()
    assert not runtime.calls and not runtime.ai_calls


@pytest.mark.parametrize("admin", [False, True])
async def test_unknown_parent_group_filter_is_not_assumed_safe(framework, admin):
    runtime = await framework.setup(astrbot_config={"admins_id": ["12345"] if admin else []})
    item = await runtime.dispatch(runtime.event("私有管理 操作 Steve"))
    assert not item.sent and not runtime.calls and not runtime.ai_calls


@pytest.mark.parametrize(
    ("text", "error"), [("等级设置", "必要参数缺失"), ("等级设置 wrong", "类型错误")]
)
async def test_framework_parameter_error_is_not_repeated(framework, text, error):
    runtime = await framework.setup()
    item = await runtime.dispatch(runtime.event(text, mention=True))
    assert item.is_stopped()
    assert len(item.sent) == 1 and error in item.texts[0]
    assert not runtime.calls and not runtime.ai_calls


async def test_cooldown_suppresses_repeat_hint_and_still_suppresses_ai(framework):
    runtime = await framework.setup(config={"cooldown_seconds": 30})
    first = await runtime.dispatch(runtime.event("白名单申请Legend_lio", mention=True))
    second = await runtime.dispatch(runtime.event("白名单申请Legend_lio", mention=True))
    assert len(first.sent) == 1 and first.is_stopped()
    assert not second.sent and second.is_stopped()
    assert not runtime.calls and not runtime.ai_calls


async def test_chat_listener_does_not_count_as_a_matched_business_command(framework):
    runtime = await framework.setup()
    runtime.handlers["chat"].enabled = True
    item = await runtime.dispatch(runtime.event("白名单申请Legend_lio", mention=True))
    assert item.is_stopped() and len(item.sent) == 1
    assert "白名单申请" in item.texts[0]
    assert not runtime.calls and not runtime.ai_calls


async def test_non_command_mention_still_reaches_default_ai(framework):
    runtime = await framework.setup()
    item = await runtime.dispatch(runtime.event("今天的天气怎么样", mention=True))
    assert not item.sent and not item.is_stopped()
    assert runtime.ai_calls == ["今天的天气怎么样"]


async def test_candidate_probe_preserves_message_and_existing_parse_state(framework):
    runtime = await framework.setup()
    item = runtime.event("mc绑定S6SGBC93")
    item.set_extra("parsed_params", {"existing": "value"})
    assert runtime.plugin.find_hints(item)
    assert item.get_message_str() == "mc绑定S6SGBC93"
    assert item.get_extra("parsed_params") == {"existing": "value"}
    assert not item.is_at_or_wake_command and not item.is_wake
    assert not item.sent and not item.is_stopped()
