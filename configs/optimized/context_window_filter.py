"""Open WebUI global filter: retain system messages and the newest 6k tokens."""
from __future__ import annotations
from copy import deepcopy
from pydantic import BaseModel,Field
import tiktoken
class Filter:
    class Valves(BaseModel):
        max_non_system_tokens:int=Field(default=6000,ge=256)
        encoding_name:str="o200k_base"
    def __init__(self):self.valves=self.Valves()
    async def inlet(self,body:dict,__metadata__:dict|None=None):
        if (__metadata__ or {}).get("task"):return body
        messages=deepcopy(body.get("messages") or []);enc=tiktoken.get_encoding(self.valves.encoding_name);systems=[m for m in messages if m.get("role")=="system"];others=[m for m in messages if m.get("role")!="system"]
        kept=[];remaining=self.valves.max_non_system_tokens
        for message in reversed(others):
            content=message.get("content","")
            if not isinstance(content,str):
                cost=len(enc.encode(str(content)))
                if cost<=remaining:kept.append(message);remaining-=cost
                continue
            ids=enc.encode(content)
            if len(ids)<=remaining:kept.append(message);remaining-=len(ids)
            elif remaining>0:
                trimmed=dict(message);trimmed["content"]=enc.decode(ids[-remaining:]);kept.append(trimmed);remaining=0
            if remaining<=0:break
        body=dict(body);body["messages"]=[*systems,*reversed(kept)];return body
