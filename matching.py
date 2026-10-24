"""Deterministic command matching, independent of AstrBot and business plugins."""

import inspect
import re
import types
import typing
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandSpec:
    key: str
    plugin: str
    handler_name: str
    names: tuple[str, ...]
    params: dict[str, Any] = field(default_factory=dict)
    usage: str = ""
    require_at: bool = False
    argument_pattern: str = ""
    hint_aliases: tuple[str, ...] = ()
    allow_plus: bool = False
    metadata: Any = field(default=None, repr=False)


@dataclass
class Hint:
    spec: CommandSpec
    command: str
    tail: str
    reason: str
    rank: int = 0
    issues: tuple[str, ...] = ()

    def example(self) -> str:
        return self.command + (" " + self.tail if self.tail else "")

    def usage(self) -> str:
        if self.spec.usage:
            return self.spec.usage.replace("{command}", self.command)
        parts = [self.command]
        for name, value in self.spec.params.items():
            required = (
                isinstance(value, (type, types.UnionType))
                or typing.get_origin(value) is typing.Union
                or value is inspect.Parameter.empty
            )
            parts.append(f"<{name}>" if required else f"[{name}]")
        return " ".join(parts)


def arguments_fit(spec: CommandSpec, tail: str, *, passive: bool = False) -> bool:
    """Reject uncertain argument boundaries without calling plugin converters."""
    if not tail:
        return True  # A usage hint may show required arguments still to be supplied.
    if spec.argument_pattern:
        return re.fullmatch(spec.argument_pattern, tail) is not None
    if not spec.params:
        return False
    words = tail.split()
    params = list(spec.params.values())
    greedy = getattr(params[-1], "__name__", "") == "GreedyStr"
    if len(words) > len(params) and not greedy:
        return False
    for index, word in enumerate(words):
        value = params[min(index, len(params) - 1)]
        kind = value if isinstance(value, type) else type(value)
        if kind in (int, float):
            try:
                kind(word)
            except ValueError:
                return False
        elif kind is bool:
            if word.lower() not in {"true", "false", "yes", "no", "1", "0"}:
                return False
        elif kind is str or value is None or getattr(kind, "__name__", "") == "GreedyStr":
            # Free-form natural language is too uncertain for unsolicited hints.
            if passive and not re.fullmatch(r"[A-Za-z0-9_./:@\[\]-]+", word):
                return False
        else:
            return False
    return True


def one_edit(left: str, right: str) -> bool:
    """Return whether strings differ by exactly one insertion/deletion/substitution."""
    if left == right or abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    short, long = (left, right) if len(left) < len(right) else (right, left)
    index = 0
    while index < len(short) and short[index] == long[index]:
        index += 1
    return short[index:] == long[index + 1 :]


def match_command(spec: CommandSpec, text: str, *, has_at: bool, woken: bool) -> list[Hint]:
    """Match only a command at the beginning, preserving the original argument tail."""
    results = []
    for name in spec.names:
        command = " ".join(name.split())
        head = re.match(r"\s*".join(re.escape(part) for part in command.split()), text)
        if head is None:
            continue
        remainder = text[head.end() :]
        attached = bool(remainder and not remainder[0].isspace())
        plus = attached and remainder.startswith("+") and spec.allow_plus
        tail = remainder[1:].lstrip() if plus else remainder.lstrip()
        if attached and not plus:
            # An ASCII identifier following a Chinese head is unambiguous; an
            # arbitrary word after an ASCII command (helpful/help) is not.
            explicit_pattern = bool(spec.argument_pattern)
            chinese_boundary = bool(
                re.search(r"[\u3400-\u9fff]$", command) and re.match(r"[A-Za-z0-9_]", tail)
            )
            if not (explicit_pattern or chinese_boundary):
                continue
        if not arguments_fit(spec, tail, passive=not has_at):
            continue
        normalized_head = " ".join(head.group().split())
        spacing = normalized_head != command or attached
        issues = []
        if plus:
            issues.append("separator")
        if normalized_head != command or (attached and not plus):
            issues.append("spacing")
        if spec.require_at and not has_at:
            issues.append("missing_at")
        elif not woken:
            issues.append("missing_wake")
        if spec.require_at and not has_at:
            reason = "missing_at"
        elif spacing:
            reason = "spacing"
        elif not woken:
            reason = "missing_wake"
        else:
            reason = "valid"
        results.append(Hint(spec, command, tail, reason, issues=tuple(issues)))

    if results or not has_at:
        return results
    # Short synonyms are explicit suggestions, never inferred from ordinary chat.
    for alias in spec.hint_aliases:
        if text == alias or text.startswith(alias + " "):
            tail = text[len(alias) :].lstrip()
            if arguments_fit(spec, tail):
                results.append(Hint(spec, spec.names[0], tail, "alias", 1, ("alias",)))
    if results:
        return results

    # Compare only the command head, never a user's ID/code or free-form argument.
    compact_text = "".join(char for char in text if not char.isspace())
    offsets = [index + 1 for index, char in enumerate(text) if not char.isspace()]
    for name in spec.names:
        compact = "".join(name.split())
        if len(compact) < 4:
            continue
        for length in (len(compact) - 1, len(compact), len(compact) + 1):
            if length > len(offsets):
                continue
            end = offsets[length - 1]
            if end < len(text) and not text[end].isspace():
                continue
            if not one_edit(compact_text[:length], compact):
                continue
            tail = text[end:].lstrip()
            if arguments_fit(spec, tail):
                results.append(Hint(spec, name, tail, "similar", 2, ("similar",)))
    return results


def select_hints(hints: list[Hint]) -> list[Hint]:
    """Prefer deterministic/longest command matches and merge a handler's aliases."""
    if not hints:
        return []
    rank = min(hint.rank for hint in hints)
    hints = [hint for hint in hints if hint.rank == rank]
    longest = max(len("".join(hint.command.split())) for hint in hints)
    hints = [hint for hint in hints if len("".join(hint.command.split())) == longest]
    distinct = {}
    for hint in hints:
        distinct.setdefault(hint.spec.key, hint)
    return list(distinct.values())[:3]
