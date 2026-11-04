import json

import pytest

from relay.config import Config


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "viewer.json"
    result = Config(api_key_path=path, actors={
        "@person:example.invalid": "you", "Traveller": "you",
        "@planner:example.invalid": "planner", "custom.planner.owner": "planner",
        "planner-id": "planner", "budget-id": "budget", "reel-id": "reel_adder",
    }, mentions={"plan": "planner", "budget": "budget", "reel": "reel_adder"})
    path.write_text(json.dumps({"agent_id": "viewer-id", "api_key": "fake-test-key",
                               "base_url": result.base_url, "agent_name": result.agent_name}))
    return result


def domain(kind="message", sequence=1, **payload):
    return {"type": kind, "room_id": "room-example", "bridge_id": "bridge-example",
            "channel_type": "channel_public", "payload": payload, "sequence": sequence}


def message(sequence=1, **overrides):
    payload = {"addressed": False, "sender": "@person:example.invalid",
               "sender_name": "Traveller", "message_id": f"message-{sequence}",
               "body": "@plan @budget Help plan Osaka", "timestamp": 1804389129000,
               "thread_id": None, "attachments": []}
    payload.update(overrides)
    return domain(sequence=sequence, **payload)


def sse(kind, data, sequence=None):
    prefix = f"id: {sequence}\n" if sequence is not None else ""
    return (prefix + f"event: {kind}\ndata: " + json.dumps(data) + "\n\n").encode()
