from datetime import datetime

import pytest

from relay.events import Mapper
from conftest import domain, message


def test_messages_joins_and_contract(config):
    mapper = Mapper(config)
    items = mapper.map(message())
    assert [item["type"] for item in items] == ["user_message", "addressed", "addressed", "board"]
    assert {item["actor"] for item in items if item["type"] == "addressed"} == {"budget", "planner"}
    assert all(item["v"] == 1 and datetime.fromisoformat(item["ts"]).utcoffset().total_seconds() == 0 for item in items)
    joined = mapper.map(domain("room_join", member="@planner:example.invalid",
                               member_name="custom.planner.owner", timestamp=1804389129000, listening=False))
    assert joined[0]["type"] == "join" and joined[0]["actor"] == "planner"
    items = mapper.map(message(sender="@planner:example.invalid", sender_name="custom.planner.owner", body="x" * 90 + "\nsecond line"))
    assert items[0]["text"] == "x" * 80
    for i in range(10):
        items = mapper.map(message(body=f"line {i}"))
    assert items[-1]["lines"] == [f"you: line {i}" for i in range(4, 10)]
    assert all(len(line) <= 80 for line in items[-1]["lines"])


def test_no_invented_senders_or_targets(config):
    mapper = Mapper(config)
    assert mapper.map(message(sender="unknown", sender_name="unknown")) == []
    assert mapper.map(message(sender_kind="platform", on_behalf_of="Traveller")) == []
    for body in ["normal chatter", "@plan.extra", "someone@plan", "@budgeting"]:
        assert [item["type"] for item in mapper.map(message(body=body, addressed=True))] == ["user_message", "board"]
    items = mapper.map(message(body="@plan, @custom.planner.owner! @plan @reel"))
    assert [item["actor"] for item in items if item["type"] == "addressed"] == ["planner", "reel_adder"]
    assert mapper.map(domain("command", command="reset", args="", user_id="person", user_name="Traveller")) == []
    assert mapper.map(domain("room_join", member="unknown", member_name="unknown")) == []


def test_tasks_use_only_representable_states(config):
    mapper = Mapper(config)
    common = {"task_id": "task-example", "requester_agent_id": "planner-id", "performer_agent_id": "budget-id"}
    for kind, extra, state, summary in [
        ("task_delegate", {"summary": "Check budget", "description": "Food costs"}, "delegated", "Check budget"),
        ("task_accept", {}, "accepted", "Check budget"),
        ("task_finalise", {"outcome": "Fits budget"}, "finalised", "Fits budget"),
    ]:
        item, = mapper.map(domain(kind, **common, **extra))
        assert {k: v for k, v in item.items() if k not in {"v", "ts", "type"}} == {
            "from": "planner", "to": "budget", "state": state, "summary": summary}
    assert not mapper.tasks
    for kind in ("task_update", "task_cancel"):
        assert mapper.map(domain(kind, **common)) == []
    assert mapper.map(domain("task_delegate", **{**common, "performer_agent_id": "unknown"}, summary="x")) == []


@pytest.mark.parametrize("body", [None, [], {}, {"type": "join"},
    {"type": "reel", "step": "invented", "platform": "tiktok"},
    {"type": "reel", "step": "failed", "platform": "youtube"},
    {"type": "reel", "step": "failed", "platform": "instagram", "reason": 4}])
def test_reel_validation(config, body):
    with pytest.raises(ValueError):
        Mapper(config).reel(body)


def test_reel_adds_own_envelope_and_board(config):
    items = Mapper(config).reel({"type": "reel", "step": "identified", "platform": "tiktok",
                               "place": "Kushikatsu Daruma, Shinsekai", "v": 99, "ts": "fake"})
    assert items[0]["v"] == 1 and items[0]["ts"] != "fake"
    assert items[1]["type"] == "board" and "Kushikatsu Daruma" in items[1]["lines"][0]


@pytest.mark.parametrize("state", ["delegated", "accepted", "finalised"])
@pytest.mark.parametrize("source,target", [("planner", "you"), ("budget", "you"),
    ("reel_adder", "planner"), ("budget", "planner"), ("you", "reel_adder")])
def test_activity_contract_board_and_envelope(config, state, source, target):
    body = {"type": "task", "from": source, "to": target, "state": state, "summary": "x" * 80}
    mapper = Mapper(config)
    for _ in range(8):
        task, board = mapper.activity({**body, "v": 99, "ts": "fake", "extra": "ignored"})
    assert task == {**body, "v": 1, "ts": task["ts"]}
    assert datetime.fromisoformat(task["ts"]).utcoffset().total_seconds() == 0
    assert board["lines"] == [(f"{source} → {target}: " + "x" * 80)[:80]] * 6


@pytest.mark.parametrize("change", [{"type": "reel"}, {"from": "unknown"}, {"from": []},
    {"to": None}, {"to": {}}, {"state": "working"}, {"state": []}, {"summary": 1},
    {"summary": ""}, {"summary": " "}, {"summary": "x" * 81}, {"summary": "line\nbreak"},
    {"summary": "line\n"}, {"summary": "line\r"}, {"summary": "line\u2028"}])
def test_activity_validation(config, change):
    mapper = Mapper(config)
    with pytest.raises(ValueError):
        mapper.activity({"type": "task", "from": "planner", "to": "you", "state": "finalised",
                         "summary": "Day 2: Park", **change})
    assert not mapper.lines


@pytest.mark.parametrize("body", [None, [], {}, {"type": "task"}])
def test_activity_missing_fields(config, body):
    with pytest.raises(ValueError):
        Mapper(config).activity(body)
