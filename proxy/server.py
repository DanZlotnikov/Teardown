"""OpenAI-compatible wire logger with mandatory paid-call budget controls."""
from __future__ import annotations
import argparse,json,re,time,urllib.error,urllib.parse,urllib.request
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import tiktoken
from analysis.budget import BudgetGuard,BudgetStop,TokenUsage
SECRET=re.compile(r"sk-[A-Za-z0-9_-]{12,}"); HOP={"connection","keep-alive","proxy-authenticate","proxy-authorization","te","trailers","transfer-encoding","upgrade"}
def scrub(v):
    if isinstance(v,dict): return {k:("[REDACTED]" if k.lower() in {"authorization","api-key","x-api-key"} else scrub(x)) for k,x in v.items()}
    if isinstance(v,list): return [scrub(x) for x in v]
    if isinstance(v,str): return SECRET.sub("[REDACTED]",v)
    return v
def enc(model):
    try:return tiktoken.encoding_for_model(model)
    except KeyError:return tiktoken.get_encoding("o200k_base")
def input_tokens(payload,model):return len(enc(model).encode(json.dumps(payload,ensure_ascii=False,separators=(",",":"))))+64
def output_limit(payload,path,safety):
    out=dict(payload); keys=["max_output_tokens"] if path.endswith("/responses") else ["max_completion_tokens","max_tokens"]
    for k in keys:
        if isinstance(payload.get(k),int) and payload[k]>0:return min(payload[k],safety),out,[]
    out[keys[0]]=safety;return safety,out,[f"injected {keys[0]}={safety} as budget safety ceiling"]
def parse_usage(body):
    try: candidates=[json.loads(body)]
    except Exception:candidates=[]
    for item in reversed(candidates):
        u=item.get("usage") if isinstance(item,dict) else None
        if not isinstance(u,dict):continue
        i=u.get("prompt_tokens",u.get("input_tokens"));o=u.get("completion_tokens",u.get("output_tokens"));d=u.get("prompt_tokens_details") or u.get("input_tokens_details") or {};c=d.get("cached_tokens",0) if isinstance(d,dict) else 0
        if isinstance(i,int) and isinstance(o,int):return TokenUsage(i,o,c if isinstance(c,int) else 0)
def response_log(body,headers):
    ct=next((v for k,v in headers.items() if k.lower()=="content-type"),"").lower()
    if "json" in ct:
        try:return scrub(json.loads(body))
        except Exception:return "[invalid-json-response]"
    return scrub(body.decode("utf-8","replace")) if "text/event-stream" in ct else "[binary-or-unrecognized-body]"
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):self.forward()
    def do_POST(self):self.forward()
    def forward(self):
        start=time.monotonic();raw=self.rfile.read(int(self.headers.get("content-length","0")));payload=None
        try:payload=json.loads(raw) if raw else None
        except Exception:pass
        model=None;reserve=None;estimated=None;maximum=None;mut=[];forwarded=raw
        if self.server.paid and self.command=="POST":
            if not isinstance(payload,dict):return self.send_error(400,"paid POST requires a JSON body")
            model=payload.get("model")
            if not isinstance(model,str):return self.send_error(400,"paid request requires a model")
            maximum,fp,mut=output_limit(payload,self.path,self.server.safety);estimated=input_tokens(fp,model)
            try:reserve=self.server.guard.preflight(phase=self.server.phase,model=model,input_tokens=estimated,max_output_tokens=maximum)
            except (BudgetStop,KeyError,ValueError) as e:return self.send_error(402,str(e))
            forwarded=json.dumps(fp,separators=(",",":")).encode()
        headers={k:v for k,v in self.headers.items() if k.lower() not in HOP|{"host","content-length"}}
        req=urllib.request.Request(self.server.upstream.rstrip("/")+self.path,data=forwarded if self.command=="POST" else None,headers=headers,method=self.command)
        status=502;rh={};body=b"";error=None
        try:
            with urllib.request.urlopen(req,timeout=self.server.timeout) as resp:status=resp.status;rh=dict(resp.headers.items());body=resp.read()
        except urllib.error.HTTPError as e:status=e.code;rh=dict(e.headers.items());body=e.read();error=f"HTTPError: {e}"
        except Exception as e:error=f"{type(e).__name__}: {e}";body=json.dumps({"error":{"message":error}}).encode()
        usage=parse_usage(body)
        if self.server.paid and self.command=="POST":
            try:self.server.guard.record(phase=self.server.phase,model=model,usage=usage,status="success" if status<400 and usage else "failed_unknown_usage",attempt=1,error=error if error else (None if usage else "provider response omitted usage"),reserved_worst_case_cost=reserve)
            except BudgetStop:pass
        self.server.write({"timestamp":datetime.now(timezone.utc).isoformat(),"phase":self.server.phase,"method":self.command,"path":self.path,"status":status,"elapsed_ms":round((time.monotonic()-start)*1000,3),"request_headers":scrub(dict(self.headers.items())),"request_body":scrub(payload),"response_headers":scrub(rh),"response_body":response_log(body,rh),"usage":usage.__dict__ if usage else None,"estimated_input_tokens_for_preflight":estimated,"max_output_tokens_for_preflight":maximum,"mutations":mut,"error":error})
        self.send_response(status)
        for k,v in rh.items():
            if k.lower() not in HOP|{"content-length","content-encoding"}:self.send_header(k,v)
        self.send_header("content-length",str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass
class Server(ThreadingHTTPServer):
    def __init__(self,address,root,upstream,log,paid,phase,safety,timeout):super().__init__(address,Handler);self.guard=BudgetGuard(root);self.upstream=upstream;self.log=log;self.paid=paid;self.phase=phase;self.safety=safety;self.timeout=timeout;log.parent.mkdir(parents=True,exist_ok=True)
    def write(self,row):
        with self.log.open("a") as h:h.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n");h.flush()
def main():
    p=argparse.ArgumentParser();p.add_argument("--host",default="127.0.0.1");p.add_argument("--port",type=int,default=8765);p.add_argument("--root",type=Path,default=Path.cwd());p.add_argument("--upstream",required=True);p.add_argument("--log",type=Path,required=True);p.add_argument("--paid",action="store_true");p.add_argument("--phase",default="contingency");p.add_argument("--safety-max-output",type=int,default=512);p.add_argument("--timeout",type=int,default=180);a=p.parse_args();log=a.log if a.log.is_absolute() else a.root/a.log;Server((a.host,a.port),a.root,a.upstream,log,a.paid,a.phase,a.safety_max_output,a.timeout).serve_forever()
if __name__=="__main__":main()
