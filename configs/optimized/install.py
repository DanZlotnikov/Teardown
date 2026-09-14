"""Install optimized task settings and the global context filter in Open WebUI."""
from __future__ import annotations
import argparse,json,urllib.error,urllib.request
from pathlib import Path
TITLE="""### Task:
Generate a concise 2-4 word title for this chat.
Return only JSON: { "title": "your concise title" }
### Truncated chat history:
<chat_history>
{{MESSAGES:END:2|start:800}}
</chat_history>"""
def req(method,url,token=None,payload=None):
    headers={};data=None
    if token:headers["Authorization"]=f"Bearer {token}"
    if payload is not None:data=json.dumps(payload).encode();headers["Content-Type"]="application/json"
    with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=headers,method=method),timeout=120) as r:
        raw=r.read();return json.loads(raw) if raw else {}
def signin(base):return req("POST",base+"/api/v1/auths/signin",payload={"email":"admin@localhost","password":"admin"})["token"]
def install(base,task_model,filter_path):
    token=signin(base);current=req("GET",base+"/api/v1/tasks/config",token);current.update({"TASK_MODEL":task_model,"TASK_MODEL_EXTERNAL":task_model,"TASK_MODEL_PARAMS":{"max_tokens":96},"TITLE_GENERATION_PROMPT_TEMPLATE":TITLE,"ENABLE_AUTOCOMPLETE_GENERATION":False});task=req("POST",base+"/api/v1/tasks/config/update",token,current)
    fid="token_budget_context_window";content=filter_path.read_text()
    try:function=req("GET",base+f"/api/v1/functions/id/{fid}",token)
    except urllib.error.HTTPError as e:
        if e.code not in {401,404}:raise
        function=req("POST",base+"/api/v1/functions/create",token,{"id":fid,"name":"Token-Budget Context Window","content":content,"meta":{"description":"Keep recent messages within an exact tokenizer budget."}})
    if not function.get("is_active"):function=req("POST",base+f"/api/v1/functions/id/{fid}/toggle",token)
    if not function.get("is_global"):function=req("POST",base+f"/api/v1/functions/id/{fid}/toggle/global",token)
    return {"task_model":task.get("TASK_MODEL_EXTERNAL"),"task_model_params":task.get("TASK_MODEL_PARAMS"),"autocomplete_enabled":task.get("ENABLE_AUTOCOMPLETE_GENERATION"),"title_template_has_truncation":"start:800" in task.get("TITLE_GENERATION_PROMPT_TEMPLATE",""),"filter_id":function.get("id"),"filter_active":function.get("is_active"),"filter_global":function.get("is_global")}
def main():
    p=argparse.ArgumentParser();p.add_argument("--base-url",default="http://127.0.0.1:8088");p.add_argument("--task-model",required=True);p.add_argument("--filter",type=Path,default=Path("configs/optimized/context_window_filter.py"));a=p.parse_args();print(json.dumps(install(a.base_url,a.task_model,a.filter),indent=2,sort_keys=True))
if __name__=="__main__":main()
