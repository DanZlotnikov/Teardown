"""Open WebUI global filter: keep system messages plus the newest N user turns."""
from __future__ import annotations

from copy import deepcopy

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        turns: int = Field(default=6, ge=1, le=100)

    def __init__(self):
        self.valves = self.Valves()

    async def inlet(self, body: dict, __metadata__: dict | None = None):
        if (__metadata__ or {}).get("task"):
            return body
        messages = deepcopy(body.get("messages") or [])
        systems = [message for message in messages if message.get("role") == "system"]
        conversational = [message for message in messages if message.get("role") != "system"]
        user_indices = [index for index, message in enumerate(conversational) if message.get("role") == "user"]
        if len(user_indices) <= self.valves.turns:
            kept = conversational
        else:
            kept = conversational[user_indices[-self.valves.turns] :]
        result = dict(body)
        result["messages"] = [*systems, *kept]
        return result
