"""Optional integration with actual PhCraft code, without initialization or API calls."""

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def phcraft_runtime(framework, monkeypatch):
    source = os.environ.get("PHCRAFT_SOURCE")
    if not source:
        pytest.skip("Set PHCRAFT_SOURCE to the actual PhCraft source directory")
    runtime = await framework.setup()
    # Avoid deliberately installing a second valid owner of 白名单申请 here.
    # The generic fixture tests that already matched commands always win.
    runtime.handlers["whitelist"].enabled = False
    from astrbot.core.star.star import StarMetadata, star_map

    name = "command_helper_phcraft_integration"
    spec = importlib.util.spec_from_file_location(name + ".main", Path(source) / "main.py")
    package_spec = importlib.util.spec_from_file_location(
        name, Path(source) / "__init__.py", submodule_search_locations=[source]
    )
    # PhCraft's repository is a namespace package (no __init__.py).
    package = importlib.util.module_from_spec(package_spec)
    monkeypatch.setitem(sys.modules, name, package)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name + ".main", module)
    spec.loader.exec_module(module)
    instance = module.Main.__new__(module.Main)
    instance.cfg = {"allowed_group_ids": ["77777"], "plugin_admin_ids": ["12345"]}
    monkeypatch.setattr(module.AllowedGroup, "groups", frozenset({"77777"}))
    monkeypatch.setattr(module.PluginAdmin, "admins", frozenset({"12345"}))
    metadata = StarMetadata(
        name="astrbot_plugin_phcraft", module_path=module.__name__, star_cls=instance
    )
    star_map[module.__name__] = metadata
    runtime.phcraft = SimpleNamespace(module=module, metadata=metadata)
    return runtime


@pytest.mark.parametrize(
    "text,expected",
    [
        ("mc绑定 THQHHK8T", "mc 绑定 THQHHK8T"),
        ("mc绑定THQHHK8T", "mc 绑定 THQHHK8T"),
        ("白名单申请legend_lio", "白名单申请 legend_lio"),
        ("白名单申请+Legend_lio", "白名单申请 Legend_lio"),
        ("@zar mc绑定S6SGBC93", "mc 绑定 S6SGBC93"),
    ],
)
async def test_screenshot_examples_use_actual_handlers(phcraft_runtime, text, expected):
    runtime = phcraft_runtime
    # Direct reminder execution ensures no business call can reach external APIs.
    item = runtime.event(text)
    await runtime.plugin.on_message(item)
    assert item.is_stopped() and len(item.sent) == 1
    assert expected in item.texts[0]


async def test_actual_whitelist_matched_without_at_still_gets_hint(phcraft_runtime):
    runtime = phcraft_runtime
    item = runtime.event("/白名单申请 Legend_lio")
    await runtime.waking.process(item)
    active = item.get_extra("activated_handlers", [])
    assert any(handler.handler_name == "cmd_whitelist_apply" for handler in active)
    await runtime.plugin.on_message(item)
    assert item.is_stopped() and len(item.sent) == 1
    assert "群成员列表" in item.texts[0]


async def test_actual_binding_allows_prefix_without_at(phcraft_runtime):
    runtime = phcraft_runtime
    item = runtime.event("/mc 绑定 S6SGBC93")
    await runtime.waking.process(item)
    await runtime.plugin.on_message(item)
    assert not item.is_stopped() and not item.sent


async def test_optional_plugin_disabled_and_uninstalled_leave_generic_hints(phcraft_runtime):
    runtime = phcraft_runtime
    from astrbot.core.star.star import star_map

    runtime.phcraft.metadata.activated = False
    assert not any(
        spec.plugin == "astrbot_plugin_phcraft"
        for spec in runtime.plugin.collect_commands(runtime.event("白名单申请Steve"))
    )
    runtime.phcraft.metadata.activated = True
    assert any(
        spec.plugin == "astrbot_plugin_phcraft"
        for spec in runtime.plugin.collect_commands(runtime.event("白名单申请Steve"))
    )
    star_map.pop(runtime.phcraft.module.__name__)
    item = runtime.event("mc绑定S6SGBC93")
    await runtime.plugin.on_message(item)
    assert item.is_stopped() and len(item.sent) == 1


async def test_actual_scope_and_exact_mc_query_are_respected(phcraft_runtime):
    runtime = phcraft_runtime
    commands = runtime.plugin.collect_commands(runtime.event("mc绑定S6SGBC93", group="88888"))
    assert not any(spec.plugin == "astrbot_plugin_phcraft" for spec in commands)
    hints = runtime.plugin.find_hints(runtime.event("mc绑定状态"))
    assert not any(hint.spec.handler_name == "cmd_client_status" for hint in hints)
    assert any(hint.spec.handler_name == "cmd_binding_status" for hint in hints)
