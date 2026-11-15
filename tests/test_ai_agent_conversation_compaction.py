"""Tests for the server-side conversation compaction (plan ola2 T3.1).

``compact_messages`` shrinks the ``role:tool`` observations of every
turn except the last two user turns down to their critical keys, strips
the UI screen-context line from older user messages and never breaks a
``tool_call`` <-> ``tool`` pair. The save path compacts before it caps,
so a long history keeps its oldest turns instead of dropping them.
"""
from __future__ import annotations

import copy
import json
from typing import Any

import api.ai_agent_conversations as agent_conversations
import api.database as db
from core.ai_v2.agent import loop as agent_loop

SESSION = "sess-compaction"
SUFFIX = "...[compacted]"
LIMIT = 600
SYSTEM = {"role": "system", "content": "sistema de prueba"}


def _user(text: str) -> dict[str, Any]:
    return {"role": "user", "content": text}


def _text(text: str) -> dict[str, Any]:
    return {"role": "assistant", "content": text}


def _call(
    call_id: str,
    name: str = "query_results",
    arguments: str = "{}",
) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        ],
    }


def _tool(
    call_id: str, content: str, name: str = "query_results"
) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "name": name,
        "content": content,
    }


def _big_json(marker: str, size: int = 4000) -> str:
    return json.dumps(
        {"ok": True, "blob": marker * size}, ensure_ascii=False
    )


def _turn(index: int) -> list[dict[str, Any]]:
    return [
        _user(f"pregunta {index}"),
        _call(f"call-{index}"),
        _tool(f"call-{index}", _big_json(str(index % 10))),
        _text(f"respuesta {index}"),
    ]


def _compact_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def test_max_conversation_chars_is_48000_and_prefix_is_exported() -> None:
    assert agent_conversations.MAX_CONVERSATION_CHARS == 48000
    assert agent_conversations.UI_CONTEXT_PREFIX == "[Contexto de pantalla: "
    assert "UI_CONTEXT_PREFIX" in agent_conversations.__all__
    assert "compact_messages" in agent_conversations.__all__


def test_ten_turns_survive_save_and_load_with_compacted_old_results(
    api_isolated_db,
) -> None:
    session_id = db.get_or_create_session(SESSION)
    messages = [SYSTEM] + [m for index in range(10) for m in _turn(index)]
    conversation_id = agent_conversations.new_conversation_id()

    agent_conversations.save_conversation(session_id, conversation_id, messages)
    loaded = agent_conversations.load_conversation(session_id, conversation_id)

    assert loaded is not None
    _, stored = loaded
    assert len(stored) == len(messages)
    assert [m["content"] for m in stored if m["role"] == "user"] == [
        f"pregunta {index}" for index in range(10)
    ]
    old_tools = [m for m in stored if m["role"] == "tool"][:8]
    for tool in old_tools:
        assert len(tool["content"]) <= LIMIT + len(SUFFIX)
        assert json.loads(tool["content"]) == {"ok": True}
    recent_tools = [m for m in stored if m["role"] == "tool"][8:]
    for tool in recent_tools:
        assert tool["content"] == _big_json(str(int(tool["tool_call_id"][5:]) % 10))


def test_last_two_user_turns_are_byte_identical() -> None:
    messages = [SYSTEM] + [m for index in range(4) for m in _turn(index)]
    compacted = agent_conversations.compact_messages(messages)

    protected_from = 1 + 2 * 4
    assert _compact_dumps(compacted[protected_from:]) == _compact_dumps(
        messages[protected_from:]
    )
    assert compacted[0] == SYSTEM
    assert json.loads(compacted[3]["content"]) == {"ok": True}


def test_tool_pairs_and_names_survive_compaction() -> None:
    messages = [SYSTEM]
    for index in range(6):
        messages.extend(_turn(index))
    compacted = agent_conversations.compact_messages(messages)

    assert len(compacted) == len(messages)
    for position, message in enumerate(compacted):
        source = messages[position]
        if message["role"] == "assistant" and message.get("tool_calls"):
            assert message == source
        if message["role"] != "tool":
            continue
        assert message["tool_call_id"] == source["tool_call_id"]
        assert message["name"] == source["name"]
        announced = {
            call["id"]
            for previous in compacted[:position]
            if previous["role"] == "assistant"
            for call in previous.get("tool_calls") or []
        }
        assert message["tool_call_id"] in announced


def test_compaction_is_idempotent() -> None:
    messages = [
        SYSTEM,
        _user(
            "[Contexto de pantalla: sección seleccionada «S-03» (section_id 2)]\n"
            "¿y la berma?"
        ),
        _call("a"),
        _tool("a", _big_json("m")),
        _text("respuesta a"),
        _user("sin contexto"),
        _call("b"),
        _tool("b", "texto libre " * 200),
        _text("respuesta b"),
        _user(
            "[Contexto de pantalla: sección seleccionada «S-05» (section_id 4)]\n"
            "¿y esta?"
        ),
        _call("c"),
        _tool("c", json.dumps({"ok": True, "error": "x", "rows": [1] * 900})),
        _text("respuesta c"),
        _user(
            "[Contexto de pantalla: sección seleccionada «S-07» (section_id 6)]\n"
            "última"
        ),
        _call("d"),
        _tool("d", _big_json("d")),
        _text("respuesta d"),
    ]
    once = agent_conversations.compact_messages(messages)
    twice = agent_conversations.compact_messages(once)
    thrice = agent_conversations.compact_messages(twice)

    assert twice == once
    assert thrice == once


def test_non_json_tool_content_is_cut_at_600_with_suffix() -> None:
    long_text = "a" * 5000
    edge_text = "b" * 601
    exact_text = "c" * 600
    messages = [
        SYSTEM,
        _user("u1"),
        _call("c1"),
        _tool("c1", long_text),
        _text("r1"),
        _user("u2"),
        _call("c2"),
        _tool("c2", edge_text),
        _text("r2"),
        _user("u3"),
        _call("c3"),
        _tool("c3", exact_text),
        _text("r3"),
        _user("u4"),
        _text("r4"),
        _user("u5"),
        _text("r5"),
    ]
    compacted = agent_conversations.compact_messages(messages)

    assert compacted[3]["content"] == "a" * LIMIT + SUFFIX
    assert compacted[7]["content"] == "b" * LIMIT + SUFFIX
    assert compacted[11]["content"] == exact_text


def test_denied_observation_keeps_ok_error_and_stays_detected() -> None:
    denied = json.dumps(
        {
            "ok": False,
            "error": "denied_by_user",
            "message": "denegado",
            "blob": "q" * 4000,
        },
        ensure_ascii=False,
    )
    call_args = json.dumps(
        {"start": [0, 0], "end": [100, 0], "n_sections": 5}
    )
    messages = [
        SYSTEM,
        _user("regenera secciones"),
        _call("d-1", "generate_sections_auto", call_args),
        _tool("d-1", denied, "generate_sections_auto"),
        _text("entendido"),
        _user("otra cosa"),
        _call("c-2"),
        _tool("c-2", _big_json("z")),
        _text("listo"),
        _user("ultima"),
        _text("final"),
    ]
    compacted = agent_conversations.compact_messages(messages)

    tool = compacted[3]
    assert json.loads(tool["content"]) == {
        "ok": False,
        "error": "denied_by_user",
    }
    assert agent_loop._observation_error(tool["content"]) == "denied_by_user"
    before = agent_loop._denied_call_keys(messages[1:5])
    after = agent_loop._denied_call_keys(compacted[1:5])
    assert len(before) == 1
    assert after == before


def test_preserved_keys_survive_and_other_keys_are_dropped() -> None:
    payload = {
        "ok": True,
        "weighted_score": {"global_score": 67.0},
        "rows": [{"id": index} for index in range(300)],
        "pct_by_parameter": {"berma": 80.0},
        "warnings": ["sección sin datos"],
        "tolerances": {"altura": {"neg": -1.0, "pos": 1.5}},
    }
    messages = [
        SYSTEM,
        _user("u1"),
        _call("p"),
        _tool("p", json.dumps(payload, ensure_ascii=False)),
        _text("r1"),
        _user("u2"),
        _text("r2"),
        _user("u3"),
        _text("r3"),
    ]
    compacted = agent_conversations.compact_messages(messages)

    content = compacted[3]["content"]
    assert content == _compact_dumps(
        {
            "ok": True,
            "weighted_score": {"global_score": 67.0},
            "pct_by_parameter": {"berma": 80.0},
            "warnings": ["sección sin datos"],
            "tolerances": {"altura": {"neg": -1.0, "pos": 1.5}},
        }
    )
    assert "sección" in content


def test_ui_context_line_is_stripped_from_older_user_messages_only() -> None:
    prefix = agent_conversations.UI_CONTEXT_PREFIX
    line = prefix + "sección seleccionada «S-03» (section_id 2)]\n"
    messages = [
        SYSTEM,
        _user(line + "¿y la berma?"),
        _text("respuesta uno"),
        _user(line + "¿y esta?"),
        _text("respuesta dos"),
        _user(line + "última"),
        _text("respuesta tres"),
        _user("sin línea"),
        _text("respuesta cuatro"),
        _user("menciona " + prefix + "x]\nen medio"),
        _text("respuesta cinco"),
        _user("última de verdad"),
    ]
    compacted = agent_conversations.compact_messages(messages)
    user_contents = [m["content"] for m in compacted if m["role"] == "user"]

    assert user_contents == [
        "¿y la berma?",
        "¿y esta?",
        "última",
        "sin línea",
        "menciona " + prefix + "x]\nen medio",
        "última de verdad",
    ]
    last_context = [
        _user(line + "última con contexto"),
        _text("respuesta"),
    ]
    kept = agent_conversations.compact_messages([SYSTEM, *last_context])
    assert kept[1]["content"] == line + "última con contexto"


def test_input_list_and_dicts_are_not_mutated() -> None:
    messages = [SYSTEM]
    for index in range(4):
        messages.extend(_turn(index))
    messages[1]["content"] = (
        agent_conversations.UI_CONTEXT_PREFIX + "S-01]\nhola"
    )
    messages.append(_tool("loose", "z" * 2000))
    snapshot = copy.deepcopy(messages)

    result = agent_conversations.compact_messages(messages)

    assert messages == snapshot
    assert result is not messages
    assert all(out is not src for out, src in zip(result, messages))
    assert result != messages
