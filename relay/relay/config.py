from dataclasses import dataclass, field
from pathlib import Path
import json
import re
import tomllib
from urllib.parse import urlsplit

ACTORS = {"planner", "budget", "reel_adder", "you"}


@dataclass
class Config:
    base_url: str = "http://127.0.0.1:8000"
    agent_name: str = "custom.viewer.owner"
    agent_id: str = ""
    api_key_path: Path = Path(".local/viewer.json")
    ws_port: int = 8770
    reel_port: int = 8771
    actors: dict[str, str] = field(default_factory=dict)
    mentions: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Config":
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        switch = data.get("switch", {})
        server = data.get("server", {})
        result = cls(**switch, **server, actors=data.get("actors", {}),
                     mentions=data.get("mentions", {}))
        result.api_key_path = path.resolve().parent / result.api_key_path
        result.base_url = result.base_url.rstrip("/")
        url = urlsplit(result.base_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("switch.base_url must be an HTTP(S) bridge URL without credentials")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", result.agent_name):
            raise ValueError("Invalid Switch agent name")
        if any(not key or actor not in ACTORS for key, actor in result.actors.items()):
            raise ValueError("actors must map nonempty identities to contract actors")
        if any(not key or actor not in ACTORS - {"you"} for key, actor in result.mentions.items()):
            raise ValueError("mentions must map nonempty handles to agent actors")
        if any(type(port) is not int or not 1 <= port <= 65535 for port in (result.ws_port, result.reel_port)) or result.ws_port == result.reel_port:
            raise ValueError("server ports must be distinct integers from 1 to 65535")
        return result

    def credentials(self) -> tuple[str, str]:
        data = json.loads(self.api_key_path.read_text(encoding="utf-8"))
        if data.get("base_url") != self.base_url or data.get("agent_name") != self.agent_name:
            raise ValueError("Credentials belong to another bridge or Viewer name")
        if self.agent_id and self.agent_id != data["agent_id"]:
            raise ValueError("Configured agent_id disagrees with credentials")
        if not data.get("agent_id") or not data.get("api_key"):
            raise ValueError("Missing agent ID or API key; run register first")
        return data["agent_id"], data["api_key"]
