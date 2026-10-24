import pytest

pytestmark = pytest.mark.asyncio


async def test_configuration_schema_defaults_are_accepted_by_astrbot(framework):
    import json
    from pathlib import Path

    from astrbot.api import AstrBotConfig

    runtime = await framework.setup()
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "_conf_schema.json").read_text(encoding="utf-8"))
    # Exercise AstrBot's actual schema parser without testing unrelated file ACLs.
    cfg = AstrBotConfig.__new__(AstrBotConfig)._config_schema_to_default_config(schema)
    assert cfg == {
        "allowed_group_ids": [],
        "cooldown_seconds": 30,
        "hint_mode": "无大模型",
        "llm_provider_id": "",
        "command_overrides": [],
    }
    runtime.module.Main(runtime.context, cfg)
    assert "phcraft_enabled" not in schema


async def test_plus_separator_can_be_configured_without_phcraft(framework):
    runtime = await framework.setup(
        config={
            "command_overrides": [
                {
                    "plugin": "example_business",
                    "handler": "whitelist",
                    "allow_plus": True,
                    "argument_pattern": "[A-Za-z0-9_]{3,16}",
                }
            ]
        }
    )
    item = await runtime.dispatch(runtime.event("白名单申请+Legend_lio", mention=True))
    assert item.is_stopped() and "白名单申请 Legend_lio" in item.texts[0]
    assert not runtime.calls and not runtime.ai_calls


async def test_disabled_parent_group_is_not_suggested(framework):
    runtime = await framework.setup(astrbot_config={"admins_id": ["12345"]})
    runtime.handlers["manage"].enabled = False
    item = await runtime.dispatch(runtime.event("管理删除 Steve"))
    assert not item.sent and not runtime.calls and not runtime.ai_calls


async def test_textual_mention_does_not_count_as_real_at(framework):
    runtime = await framework.setup(
        config={
            "command_overrides": [
                {
                    "plugin": "example_business",
                    "handler": "whitelist",
                    "require_at": True,
                }
            ]
        }
    )
    item = await runtime.dispatch(runtime.event("@zar 白名单申请 Legend_lio"))
    assert item.is_stopped() and len(item.sent) == 1
    assert "群成员列表" in item.texts[0]
    assert not runtime.calls and not runtime.ai_calls


async def test_require_at_catches_silent_rejection_even_after_prefix_match(framework):
    runtime = await framework.setup(
        config={
            "command_overrides": [
                {
                    "plugin": "example_business",
                    "handler": "whitelist",
                    "require_at": True,
                }
            ]
        }
    )
    item = await runtime.dispatch(runtime.event("/白名单申请 Legend_lio"))
    assert item.is_stopped() and len(item.sent) == 1
    assert not runtime.calls and not runtime.ai_calls


async def test_quote_only_and_forward_are_not_commands(framework):
    runtime = await framework.setup()
    from astrbot.api.message_components import Forward, Reply

    item = runtime.event("mc绑定AbCd1234")
    item.message_obj.message = [Reply(id="quoted", message_str="mc绑定AbCd1234")]
    assert not runtime.plugin.find_hints(item)
    item.message_obj.message = [Forward(id="forward")]
    assert not runtime.plugin.find_hints(item)


async def test_at_argument_is_preserved_as_a_component(framework):
    runtime = await framework.setup()
    from astrbot.api.message_components import At, Plain

    item = runtime.event("mc绑定", mention=True)
    item.message_obj.message.extend([Plain(text=" "), At(qq="99999")])
    await runtime.dispatch(item)
    assert len(item.sent) == 1
    assert any(isinstance(part, At) and str(part.qq) == "99999" for part in item.sent[0].chain)
    assert "[At:" not in item.texts[0]
    assert not runtime.calls and not runtime.ai_calls


async def test_non_qq_and_private_chat_not_handled(framework):
    runtime = await framework.setup()
    item = runtime.event("mc绑定AbCd1234", group="")
    assert not runtime.plugin.find_hints(item)
    item = runtime.event("mc绑定AbCd1234")
    item.platform_meta.name = "telegram"
    assert not runtime.plugin.find_hints(item)


async def test_sending_failure_stops_ai_but_allows_next_retry(framework):
    runtime = await framework.setup()
    item = runtime.event("mc绑定AbCd1234")

    async def failed(message):
        raise OSError("test connection failure")

    item.send = failed
    await runtime.dispatch(item)
    assert item.is_stopped() and not runtime.ai_calls
    retry = await runtime.dispatch(runtime.event("mc绑定AbCd1234"))
    assert len(retry.sent) == 1


async def test_bad_rule_rejected_before_processing_messages(framework):
    runtime = await framework.setup()
    for rule in ({"plugin": "x"}, {"plugin": "x", "handler": "y", "argument_pattern": "["}):
        with pytest.raises(ValueError):
            runtime.module.Main(runtime.context, {"command_overrides": [rule]})
