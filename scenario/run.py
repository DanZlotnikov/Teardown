"""Run the deterministic workload through Open WebUI's real HTTP endpoints."""
from __future__ import annotations
import argparse,hashlib,json,os,re,time,urllib.error,urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from analysis.budget import BudgetGuard,BudgetStop
@dataclass(frozen=True)
class Action: conversation_id:str;call_type:str;endpoint:str;payload:dict[str,Any]
def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8",newline="\n") as h:h.write(json.dumps(value,ensure_ascii=False,sort_keys=True)+"\n");h.flush();os.fsync(h.fileno())
    tmp.replace(path)
def append(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8",newline="\n") as h:h.write(json.dumps(value,ensure_ascii=False,sort_keys=True)+"\n");h.flush();os.fsync(h.fileno())
def request_json(method,url,payload,token,timeout):
    headers={"Content-Type":"application/json"};
    if token:headers["Authorization"]=f"Bearer {token}"
    req=urllib.request.Request(url,data=json.dumps(payload,separators=(",",":")).encode() if payload is not None else None,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read())
def signin(base,timeout):
    token=request_json("POST",base+"/api/v1/auths/signin",{"email":"admin@localhost","password":"admin"},None,timeout).get("token")
    if not token:raise RuntimeError("Open WebUI sign-in did not return a token")
    return token
def prefixes(messages):return [messages[:i+1] for i,m in enumerate(messages) if m.get("role")=="user"]
def build_actions(data,model,profile):
    actions=[]
    for c in data["conversations"]:
        ps=prefixes(c["messages"])
        for turn,prefix in enumerate(ps):
            actions.append(Action(c["id"],"main","/api/chat/completions",{"model":model,"messages":prefix,"stream":False}))
            answered=[*prefix,{"role":"assistant","content":"Fixture answer used to keep baseline and optimized follow-up inputs identical."}]
            actions.append(Action(c["id"],"follow_up","/api/v1/tasks/follow_up/completions",{"model":model,"messages":answered,"stream":False}))
            if turn==0:
                for typ in ("title","tags"):actions.append(Action(c["id"],typ,f"/api/v1/tasks/{typ}/completions",{"model":model,"messages":answered,"stream":False}))
            if c["features"]["rag"]:actions.append(Action(c["id"],"retrieval_query","/api/v1/tasks/queries/completions",{"model":model,"messages":prefix,"type":"retrieval","stream":False}))
            if c["features"]["web_search"]:actions.append(Action(c["id"],"web_query","/api/v1/tasks/queries/completions",{"model":model,"messages":prefix,"type":"web_search","stream":False}))
        if c["features"]["autocomplete"] and profile=="baseline":
            for n in range(2):actions.append(Action(c["id"],"autocomplete","/api/v1/tasks/auto/completions",{"model":model,"messages":ps[-1],"prompt":ps[-1][-1]["content"],"type":"general","stream":False,"cursor_event":n+1}))
    return actions
def build_retrieval_actions(data,retrieval_k=None):
    actions=[]
    for case in data["queries"]:
        payload={"collection_names":[data["collection_id"]],"query":case["query"]}
        if retrieval_k is not None:payload["k"]=retrieval_k
        actions.append(Action(case["id"],"retrieval","/api/v1/retrieval/query/collection",payload))
    return actions
def cache_key(namespace,condition,scenario_sha256,profile,a):return hashlib.sha256(json.dumps({"namespace":namespace,"condition":condition,"scenario_sha256":scenario_sha256,"profile":profile,"conversation_id":a.conversation_id,"call_type":a.call_type,"endpoint":a.endpoint,"payload":a.payload},sort_keys=True,separators=(",",":")).encode()).hexdigest()
def valid_row(row,key):return isinstance(row,dict) and row.get("cache_key")==key and not row.get("error") and row.get("response") is not None
def call(base,token,a,timeout,attempts):
    for attempt in range(1,attempts+1):
        try:return request_json("POST",base+a.endpoint,a.payload,token,timeout),attempt,None
        except urllib.error.HTTPError as e:
            detail=e.read().decode(errors="replace")[:2000]
            if e.code not in {408,409,425,429} and e.code<500:return None,attempt,f"HTTPError: HTTP {e.code}: {detail}"
            if attempt==attempts:return None,attempt,f"HTTPError: HTTP {e.code}: {detail}"
        except (urllib.error.URLError,TimeoutError,json.JSONDecodeError) as e:
            if attempt==attempts:return None,attempt,f"{type(e).__name__}: {e}"
        time.sleep(2**(attempt-1))
def main():
    p=argparse.ArgumentParser();p.add_argument("--base-url",default="http://127.0.0.1:8088");p.add_argument("--scenario",type=Path,default=Path("scenario/cases.json"));p.add_argument("--retrieval-scenario",type=Path,default=Path("scenario/retrieval-cases.json"));p.add_argument("--retrieval-k",type=int,choices=(1,2,3));p.add_argument("--condition",required=True);p.add_argument("--profile",choices=("baseline","optimized"),required=True);p.add_argument("--phase",choices=("baseline","optimized"),required=True);p.add_argument("--model",default="gpt-4o-mini");p.add_argument("--mode",choices=("mock","paid-smoke","paid-batch"),required=True);p.add_argument("--max-actions",type=int);p.add_argument("--timeout",type=int,default=180);a=p.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*",a.condition):p.error("--condition must be a filesystem-safe lowercase identifier")
    root=Path(__file__).parents[1];guard=BudgetGuard(root);scenario_bytes=a.scenario.read_bytes();retrieval_bytes=a.retrieval_scenario.read_bytes();scenario_sha256=hashlib.sha256(scenario_bytes+b"\0"+retrieval_bytes).hexdigest();data=json.loads(scenario_bytes);retrieval_data=json.loads(retrieval_bytes);actions=build_actions(data,a.model,a.profile)+build_retrieval_actions(retrieval_data,a.retrieval_k)
    if a.max_actions is not None:actions=actions[:a.max_actions]
    if a.mode=="paid-smoke" and len(actions)>2:raise SystemExit("paid-smoke refuses more than two actions")
    if a.mode=="paid-batch" and not guard.smoke_passed(a.phase):raise BudgetStop(f"{a.phase} paid batch requires a passed smoke marker")
    token=signin(a.base_url,a.timeout);models=request_json("GET",a.base_url+"/api/models",None,token,a.timeout);ids={x.get("id") for x in models.get("data",[]) if isinstance(x,dict)}
    if a.model not in ids:raise RuntimeError(f"configured model {a.model!r} absent; available={sorted(x for x in ids if x)}")
    ns="mock" if a.mode=="mock" else "paid";cache=root/f"results/cache/{ns}/{a.condition}";cache.mkdir(parents=True,exist_ok=True);out=root/f"results/actions/{ns}/{a.condition}.jsonl"
    existing={}
    if out.exists():
        for line in out.read_text().splitlines():
            row=json.loads(line)
            if row.get("cache_key") and not row.get("error") and row.get("response") is not None:existing[row["cache_key"]]=row
    done=skipped=0
    for action in actions:
        key=cache_key(ns,a.condition,scenario_sha256,a.profile,action);cp=cache/f"{key}.json"
        cached=None
        if cp.exists():
            try:cached=json.loads(cp.read_text(encoding="utf-8"))
            except (OSError,json.JSONDecodeError):cached=None
        if valid_row(cached,key):
            if key not in existing:cached={**cached,"manifest_recovered_from_cache":True};append(out,cached);existing[key]=cached
            done+=1;skipped+=1
        elif key in existing and valid_row(existing[key],key):
            atomic(cp,existing[key]);done+=1;skipped+=1
        else:
            response,attempts,error=call(a.base_url,token,action,a.timeout,2 if a.mode=="paid-smoke" else int(guard.budget["max_retries"]));row={"cache_key":key,"namespace":ns,"condition":a.condition,"scenario_sha256":scenario_sha256,"profile":a.profile,"conversation_id":action.conversation_id,"call_type":action.call_type,"endpoint":action.endpoint,"payload_sha256":hashlib.sha256(json.dumps(action.payload,sort_keys=True,separators=(",",":")).encode()).hexdigest(),"response":response,"attempts":attempts,"error":error};atomic(cp,row);append(out,row)
            if error:raise RuntimeError(f"{action.conversation_id}/{action.call_type} failed after {attempts} attempts: {error}")
            existing[key]=row;done+=1
        msg=guard.progress(done,planned_calls=len(actions))
        if msg:print(f"{msg} cached={skipped}",flush=True)
    print(json.dumps({"condition":a.condition,"scenario_sha256":scenario_sha256,"profile":a.profile,"mode":a.mode,"planned_actions":len(actions),"completed_actions":done,"cached_actions":skipped,"measured_spend_usd":str(guard.running_total()),"effective_exposure_usd":str(guard.effective_total())},sort_keys=True))
if __name__=="__main__":main()
