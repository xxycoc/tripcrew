from collections import deque
from datetime import UTC, datetime
import re

from .config import Config


def event(kind: str, **fields) -> dict:
    return {"v": 1, "type": kind, "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"), **fields}


def short(text: str) -> str:
    return (text.splitlines() or [""])[0][:80]


class Mapper:
    def __init__(self, config: Config):
        self.actors = config.actors
        self.handles = {**{k: v for k, v in self.actors.items() if v != "you"}, **config.mentions}
        self.lines: deque[str] = deque(maxlen=6)
        self.tasks: dict[str, str] = {}

    def actor(self, identity, name=None):
        return self.actors.get(identity) or self.actors.get(name)

    def board(self, line: str) -> dict:
        self.lines.append(short(line))
        return event("board", lines=list(self.lines))

    def map(self, frame: dict) -> list[dict]:
        kind, payload = frame.get("type"), frame.get("payload", {})
        if not isinstance(payload, dict):
            return []
        if kind == "room_join":
            actor = self.actor(payload.get("member"), payload.get("member_name"))
            return [event("join", actor=actor)] if actor else []
        if kind == "message":
            actor = self.actor(payload.get("sender"), payload.get("sender_name"))
            body = payload.get("body")
            if not actor or not isinstance(body, str) or payload.get("sender_kind") == "platform":
                return []
            out = [event("user_message", text=body)] if actor == "you" else [event("agent_message", actor=actor, text=short(body))]
            targets = set()
            for handle, target in self.handles.items():
                if re.search(r"(?<![\w@])@" + re.escape(handle.lstrip("@")) + r"(?![\w.-])", body, re.IGNORECASE):
                    targets.add(target)
            out.extend(event("addressed", actor=target, text=body) for target in sorted(targets))
            out.append(self.board(f"{actor}: {short(body)}"))
            return out
        states = {"task_delegate": "delegated", "task_accept": "accepted", "task_finalise": "finalised"}
        if kind in states:
            requester = self.actor(payload.get("requester_agent_id"))
            performer = self.actor(payload.get("performer_agent_id"))
            if not requester or not performer:
                return []
            task_id = payload.get("task_id", "")
            summary = payload.get("summary") or payload.get("outcome") or self.tasks.get(task_id, "")
            if not isinstance(summary, str):
                return []
            if kind == "task_delegate" and task_id:
                self.tasks[task_id] = short(summary)
            elif kind == "task_finalise":
                self.tasks.pop(task_id, None)
            return [event("task", **{"from": requester, "to": performer, "state": states[kind], "summary": short(summary)})]
        return []

    def activity(self, body: dict) -> list[dict]:
        if not isinstance(body, dict) or body.get("type") != "task":
            raise ValueError("Expected a task event body")
        for key in ("from", "to"):
            if not isinstance(body.get(key), str) or body[key] not in {"planner", "budget", "reel_adder", "you"}:
                raise ValueError(f"Unknown {key} actor")
        if not isinstance(body.get("state"), str) or body["state"] not in {"delegated", "accepted", "finalised"}:
            raise ValueError("Unknown task state")
        summary = body.get("summary")
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 80 or summary.splitlines() != [summary]:
            raise ValueError("Summary must be one nonblank line, at most 80 characters")
        fields = {key: body[key] for key in ("from", "to", "state", "summary")}
        return [event("task", **fields), self.board(f"{body['from']} → {body['to']}: {summary}")]

    def reel(self, body: dict) -> list[dict]:
        if not isinstance(body, dict) or body.get("type") != "reel":
            raise ValueError("Expected a reel event body")
        if body.get("step") not in {"fetch_start", "watching", "identified", "failed"}:
            raise ValueError("Unknown reel step")
        if body.get("platform") not in {"tiktok", "instagram"}:
            raise ValueError("Unknown reel platform")
        fields = {"step": body["step"], "platform": body["platform"]}
        for key in ("place", "reason"):
            if key in body:
                if not isinstance(body[key], str):
                    raise ValueError(f"{key} must be a string")
                fields[key] = body[key]
        platform = {"tiktok": "TikTok", "instagram": "Instagram"}[body["platform"]]
        # Fetch progress is shown by the animation; the board keeps only outcomes.
        if body["step"] == "identified":
            return [event("reel", **fields), self.board(f"reel_adder: {platform} reel is {fields.get('place', '?')}")]
        if body["step"] == "failed":
            return [event("reel", **fields), self.board(f"reel_adder: {platform} reel failed, {fields.get('reason', '?')}")]
        return [event("reel", **fields)]
