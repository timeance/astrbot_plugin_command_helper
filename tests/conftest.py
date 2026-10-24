import copy
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


@pytest.fixture
def framework(monkeypatch):
    """Run the plugin through real AstrBot filter and dispatch stages."""
    pytest.importorskip("astrbot", reason="Requires an actual AstrBot installation")
    from astrbot.api import sp
    from astrbot.api.event import filter
    from astrbot.api.message_components import At, Plain
    from astrbot.api.star import Star
    from astrbot.core.pipeline.context import PipelineContext
    from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
    from astrbot.core.platform.message_type import MessageType
    from astrbot.core.platform.platform_metadata import PlatformMetadata
    from astrbot.core.star.star import StarMetadata, star_map, star_registry
    from astrbot.core.star.star_handler import star_handlers_registry

    # Import the stage entrypoint first; its child modules import the entrypoint.
    stages = importlib.import_module("astrbot.core.pipeline.process_stage.stage")
    ProcessStage = stages.ProcessStage
    StarRequestSubStage = stages.StarRequestSubStage
    module = importlib.import_module("astrbot_plugin_command_helper.main")
    old_handlers = list(star_handlers_registry)
    old_stars = dict(star_map)
    old_registry = list(star_registry)
    hint_handlers = [copy.copy(h) for h in old_handlers if h.handler_module_path == module.__name__]
    star_handlers_registry.clear()
    star_map.clear()
    star_registry.clear()
    for handler in hint_handlers:
        star_handlers_registry.append(handler)

    runtime = SimpleNamespace(
        module=module,
        registry=star_handlers_registry,
        disabled_plugins=set(),
        calls=[],
        ai_calls=[],
        custom_filter_calls=[],
    )

    async def memory_get(*, key, scope=None, scope_id=None, default=None, **kwargs):
        if key == "session_plugin_config":
            return {scope_id: {"disabled_plugins": list(runtime.disabled_plugins)}}
        return default

    monkeypatch.setattr(sp, "get_async", memory_get)
    waking_module = importlib.import_module(WakingCheckStage.__module__)
    recorder = getattr(waking_module, "UmoAutoNameRecorder", None)
    if recorder is not None:  # Automatic UMO naming was added in AstrBot 4.28.
        monkeypatch.setattr(recorder, "schedule", lambda *args: None)

    class AllowedGroup(filter.CustomFilter):
        def filter(self, event, cfg):
            runtime.custom_filter_calls.append(event.get_message_str())
            return event.get_group_id() == "77777"

    class AdminOnly(filter.CustomFilter):
        def filter(self, event, cfg):
            return event.is_admin()

    class Business(Star):
        @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
        @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
        @filter.command("mc 绑定", alias={"绑定账号"})
        async def bind(self, event, code: str = ""):
            runtime.calls.append(("bind", code))
            yield event.plain_result("业务绑定已执行")

        @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
        @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
        @filter.command("白名单申请", alias={"申请白名单"})
        async def whitelist(self, event, player: str = ""):
            runtime.calls.append(("whitelist", player))
            yield event.plain_result("业务申请已执行")

        @filter.permission_type(filter.PermissionType.ADMIN, raise_error=False)
        @filter.command("危险命令")
        async def secret(self, event):
            runtime.calls.append(("secret", ""))
            yield event.plain_result("业务管理已执行")

        @filter.command("等级设置")
        async def level(self, event, value: int):
            runtime.calls.append(("level", value))
            yield event.plain_result("业务等级已执行")

        @filter.command_group("管理")
        def manage(self):
            pass

        @manage.command("删除")
        async def remove(self, event, value: str = ""):
            runtime.calls.append(("remove", value))
            yield event.plain_result("业务删除已执行")

        @filter.custom_filter(AllowedGroup, False)
        @filter.command("自定义命令")
        async def unknown(self, event, value: str = ""):
            runtime.calls.append(("unknown", value))
            yield event.plain_result("业务自定义命令已执行")

        @filter.custom_filter(AdminOnly, False)
        @filter.command_group("私有管理")
        def private_group(self):
            pass

        @private_group.command("操作")
        async def private_action(self, event, value: str = ""):
            runtime.calls.append(("private_action", value))
            yield event.plain_result("业务私有管理已执行")

        @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=-10)
        async def chat(self, event):
            runtime.calls.append(("chat", event.get_message_str()))

    from astrbot.core.star.filter.permission import PermissionType, PermissionTypeFilter

    Business.manage.parent_group.add_custom_filter(
        PermissionTypeFilter(PermissionType.ADMIN, raise_error=False)
    )

    class RecordingEvent(AstrMessageEvent):
        async def send(self, message):
            self.sent.append(message)
            self._has_send_oper = True

        @property
        def texts(self):
            return [
                "".join(getattr(part, "text", "") for part in result.chain) for result in self.sent
            ]

    def event(text, *, mention=False, at_other=False, group="77777", sender="12345"):
        message = AstrBotMessage()
        message.type = MessageType.GROUP_MESSAGE if group else MessageType.FRIEND_MESSAGE
        message.group_id = group
        message.sender = MessageMember(user_id=sender, nickname="测试玩家")
        message.self_id = "54321"
        message.message_id = "test-message"
        message.message = []
        if mention or at_other:
            message.message.append(At(qq="54321" if mention else "99999"))
        message.message.append(Plain(text=text))
        item = RecordingEvent(
            text,
            message,
            PlatformMetadata(name="aiocqhttp", description="test", id="test"),
            group or sender,
        )
        item.sent = []
        return item

    async def setup(config=None, astrbot_config=None):
        bot_cfg = {
            "wake_prefix": ["/"],
            "admins_id": [],
            "plugin_set": ["*"],
            "disable_builtin_commands": False,
            "platform_settings": {
                "ignore_at_all": True,
                "ignore_bot_self_message": True,
                "no_permission_reply": True,
            },
            "provider_settings": {
                "enable": True,
                "prompt_prefix": "",
                "identifier": False,
            },
        }
        bot_cfg.update(astrbot_config or {})
        context = SimpleNamespace(get_config=lambda umo=None: bot_cfg)
        cfg = {
            "allowed_group_ids": ["77777"],
            "cooldown_seconds": 30,
            "hint_mode": "无大模型",
            "llm_provider_id": "",
            "command_overrides": [],
        }
        cfg.update(config or {})
        runtime.plugin = module.Main(context, cfg)
        runtime.business = Business(context)
        runtime.bot_cfg = bot_cfg
        runtime.context = context
        star_map[module.__name__] = StarMetadata(
            name="astrbot_plugin_command_helper",
            module_path=module.__name__,
            star_cls=runtime.plugin,
        )
        star_map[Business.__module__].name = "example_business"
        star_map[Business.__module__].star_cls = runtime.business
        runtime.metadata = star_map[Business.__module__]
        runtime.handlers = {}
        for handler in star_handlers_registry:
            instance = (
                runtime.plugin
                if handler.handler_module_path == module.__name__
                else runtime.business
            )
            method = getattr(instance, handler.handler_name)
            if callable(method):
                handler.handler = method
            if instance is runtime.business:
                runtime.handlers[handler.handler_name] = handler
        runtime.handlers["chat"].enabled = False
        ctx = PipelineContext(
            astrbot_config=bot_cfg,
            plugin_manager=SimpleNamespace(context=context),
            astrbot_config_id="test-config",
        )
        runtime.waking = WakingCheckStage()
        await runtime.waking.initialize(ctx)
        star_stage = StarRequestSubStage()
        await star_stage.initialize(ctx)

        class RecordingAgent:
            async def process(self, item):
                runtime.ai_calls.append(item.get_message_str())
                if False:
                    yield

        runtime.process = ProcessStage()
        runtime.process.ctx = ctx
        runtime.process.star_request_sub_stage = star_stage
        runtime.process.agent_sub_stage = RecordingAgent()
        return runtime

    async def dispatch(item):
        await runtime.waking.process(item)
        if not item.is_stopped():
            async for _ in runtime.process.process(item):
                result = item.get_result()
                if result and result.chain and not item.is_stopped():
                    await item.send(result)
        return item

    runtime.setup = setup
    runtime.event = event
    runtime.dispatch = dispatch
    try:
        yield runtime
    finally:
        star_handlers_registry.clear()
        for handler in old_handlers:
            star_handlers_registry.append(handler)
        star_map.clear()
        star_map.update(old_stars)
        star_registry[:] = old_registry
        suspected = getattr(module, "SuspectedCommand", None)
        if suspected and getattr(suspected, "instance", None) is getattr(runtime, "plugin", None):
            suspected.instance = None
