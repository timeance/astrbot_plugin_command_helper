"""Specific user-facing reminders and optional model wording through real dispatch."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "text,mention,config,expected",
    [
        ("mc绑定THQHHK8T", True, {}, ["命令可能漏了空格", "mc 绑定 THQHHK8T"]),
        ("mc绑定THQHHK8T", False, {}, ["命令可能漏了空格", "未唤醒", "命令前加“/”"]),
        ("mc 绑定 THQHHK8T", False, {}, ["未唤醒", "群成员列表", "mc 绑定 THQHHK8T"]),
        ("白明单申请 Legend_lio", True, {}, ["命令名称可能有误", "白名单申请 Legend_lio"]),
        (
            "白名单",
            True,
            {"hint_aliases": ["白名单"], "usage": "{command} <游戏ID>"},
            ["提示词", "完整命令", "必填参数", "白名单申请 <游戏ID>"],
        ),
        (
            "白名单申请+Legend_lio",
            True,
            {"allow_plus": True, "argument_pattern": "[A-Za-z0-9_]{3,16}"},
            ["“+”应改为空格", "白名单申请 Legend_lio"],
        ),
        (
            "/白名单申请 Legend_lio",
            False,
            {"require_at": True},
            ["该命令必须真正 @机器人", "白名单申请 Legend_lio"],
        ),
        (
            "白名单申请Legend_lio",
            False,
            {"require_at": True},
            ["命令可能漏了空格", "该命令必须真正 @机器人", "白名单申请 Legend_lio"],
        ),
    ],
)
async def test_each_problem_has_specific_resend_guidance(
    framework, text, mention, config, expected
):
    rules = [{"plugin": "example_business", "handler": "whitelist", **config}] if config else []
    runtime = await framework.setup(config={"command_overrides": rules})
    item = await runtime.dispatch(runtime.event(text, mention=mention))
    assert item.is_stopped() and len(item.sent) == 1
    assert all(value in item.texts[0] for value in expected)
    assert not runtime.calls and not runtime.ai_calls


@pytest.mark.parametrize("late_load", [False, True])
async def test_phcraft_detection_logs_once_for_either_load_order(framework, monkeypatch, late_load):
    runtime = await framework.setup()
    logs = []
    monkeypatch.setattr(runtime.module.logger, "info", logs.append)
    metadata = SimpleNamespace(name="astrbot_plugin_phcraft", activated=False, star_cls=object())
    from astrbot.core.star.star import star_map

    star_map["test.phcraft"] = metadata
    await runtime.plugin.initialize()
    assert not logs
    metadata.activated = True
    if late_load:
        await runtime.plugin.on_plugin_loaded(metadata)
    else:
        await runtime.plugin.initialize()
    await runtime.plugin.on_plugin_loaded(metadata)
    await runtime.plugin.on_plugin_loaded(runtime.metadata)
    assert len(logs) == 1 and "检测到 PhCraft-Astrbot" in logs[0]


@pytest.mark.parametrize("mode", ["无大模型", "仅大模型提示", "大模型+提醒"])
async def test_three_modes_and_model_payload(framework, mode):
    runtime = await framework.setup(config={"hint_mode": mode})
    model_text = "模型提示：请补齐空格，重发 mc 绑定 THQHHK8T。"
    runtime.context.get_current_chat_provider_id = AsyncMock(return_value="session-model")
    runtime.context.llm_generate = AsyncMock(
        return_value=SimpleNamespace(completion_text=model_text)
    )
    item = await runtime.dispatch(runtime.event("mc绑定THQHHK8T", mention=True))
    assert item.is_stopped() and len(item.sent) == 1
    assert (model_text in item.texts[0]) is (mode != "无大模型")
    assert ("命令可能漏了空格" in item.texts[0]) is (mode != "仅大模型提示")
    if mode == "无大模型":
        runtime.context.llm_generate.assert_not_awaited()
        runtime.context.get_current_chat_provider_id.assert_not_awaited()
    else:
        request = runtime.context.llm_generate.await_args.kwargs
        payload = json.loads(request["prompt"])
        assert request["chat_provider_id"] == "session-model" and request["contexts"] == []
        assert payload["用户输入"] == "mc绑定THQHHK8T"
        assert payload["已真正@机器人"] is True
        assert payload["候选命令"][0]["重发示例"] == "mc 绑定 THQHHK8T"
        assert "用法" in payload["候选命令"][0]
        assert "漏了空格" in payload["候选命令"][0]["问题"]
        second = await runtime.dispatch(runtime.event("mc绑定THQHHK8T", mention=True))
        assert second.is_stopped() and not second.sent
        runtime.context.llm_generate.assert_awaited_once()
    assert not runtime.calls and not runtime.ai_calls


async def test_explicit_model_and_non_command_messages(framework):
    runtime = await framework.setup(
        config={"hint_mode": "大模型+提醒", "llm_provider_id": "hint-model"}
    )
    runtime.context.get_current_chat_provider_id = AsyncMock()
    runtime.context.llm_generate = AsyncMock(
        return_value=SimpleNamespace(completion_text="请补全空格。")
    )
    await runtime.dispatch(runtime.event("今天的天气怎么样", mention=True))
    runtime.context.llm_generate.assert_not_awaited()
    item = await runtime.dispatch(runtime.event("mc绑定THQHHK8T", mention=True))
    assert len(item.sent) == 1
    assert runtime.context.llm_generate.await_args.kwargs["chat_provider_id"] == "hint-model"
    runtime.context.get_current_chat_provider_id.assert_not_awaited()


@pytest.mark.parametrize("result", [None, "", "   ", "冗长输出" * 60, TimeoutError(), OSError()])
async def test_model_failure_keeps_specific_hint_and_stops_chat(framework, result):
    runtime = await framework.setup(
        config={"hint_mode": "仅大模型提示", "llm_provider_id": "hint-model"}
    )
    runtime.context.llm_generate = AsyncMock()
    if isinstance(result, Exception):
        runtime.context.llm_generate.side_effect = result
    else:
        runtime.context.llm_generate.return_value = SimpleNamespace(completion_text=result)
    item = await runtime.dispatch(runtime.event("mc绑定THQHHK8T", mention=True))
    assert item.is_stopped() and len(item.sent) == 1
    assert "命令可能漏了空格" in item.texts[0] and "mc 绑定 THQHHK8T" in item.texts[0]
    assert not runtime.calls and not runtime.ai_calls


async def test_model_only_preserves_target_at(framework):
    runtime = await framework.setup(
        config={"hint_mode": "仅大模型提示", "llm_provider_id": "hint-model"}
    )
    from astrbot.api.message_components import At, Plain

    runtime.context.llm_generate = AsyncMock(
        return_value=SimpleNamespace(completion_text="请重发 mc 绑定 [At:99999]。")
    )
    item = runtime.event("mc绑定", mention=True)
    item.message_obj.message.extend([Plain(text=" "), At(qq="99999")])
    await runtime.dispatch(item)
    assert item.is_stopped() and len(item.sent) == 1
    assert any(isinstance(part, At) and str(part.qq) == "99999" for part in item.sent[0].chain)
    assert "[At:" not in item.texts[0]


async def test_model_receives_original_prefix_and_preserves_argument_spacing(framework):
    runtime = await framework.setup(
        config={
            "hint_mode": "仅大模型提示",
            "llm_provider_id": "hint-model",
            "command_overrides": [
                {"plugin": "example_business", "handler": "bind", "argument_pattern": ".+"}
            ],
        }
    )
    text = "请重发 mc 绑定 Ab_Cd   X-9。"
    runtime.context.llm_generate = AsyncMock(return_value=SimpleNamespace(completion_text=text))
    item = await runtime.dispatch(runtime.event("/mc绑定Ab_Cd   X-9"))
    request = runtime.context.llm_generate.await_args.kwargs
    payload = json.loads(request["prompt"])
    assert payload["用户输入"] == "/mc绑定Ab_Cd   X-9"
    assert payload["已真正@机器人"] is False
    assert text in item.texts[0]


@pytest.mark.parametrize("config", [{"hint_mode": "未知模式"}, {"llm_provider_id": 42}])
async def test_invalid_model_configuration_is_rejected(framework, config):
    runtime = await framework.setup()
    with pytest.raises(ValueError):
        runtime.module.Main(runtime.context, config)
