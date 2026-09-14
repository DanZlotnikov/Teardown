"""Deterministic OpenAI-compatible provider used before any paid smoke test."""
from __future__ import annotations
import argparse,json,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import tiktoken
def tokens(v,model):
    try: enc=tiktoken.encoding_for_model(model)
    except KeyError: enc=tiktoken.get_encoding("o200k_base")
    return len(enc.encode(json.dumps(v,ensure_ascii=False,separators=(",",":"))))
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") in {"/v1/models","/models"}: return self.send_json(200,{"object":"list","data":[{"id":"gpt-4o-mini","object":"model"}]})
        self.send_json(404,{"error":{"message":"not found"}})
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers.get("content-length","0"))) or b"{}")
        model=payload.get("model","gpt-4o-mini"); inp=tokens(payload,model); text=self.content(payload); out=tokens(text,model)
        if self.path.endswith("/chat/completions"):
            return self.send_json(200,{"id":"chatcmpl-mock","object":"chat.completion","created":int(time.time()),"model":model,"choices":[{"index":0,"message":{"role":"assistant","content":text},"finish_reason":"stop"}],"usage":{"prompt_tokens":inp,"completion_tokens":out,"total_tokens":inp+out}})
        if self.path.endswith("/responses"):
            return self.send_json(200,{"id":"resp-mock","object":"response","model":model,"output":[{"type":"message","role":"assistant","content":[{"type":"output_text","text":text}]}],"usage":{"input_tokens":inp,"output_tokens":out,"total_tokens":inp+out}})
        self.send_json(404,{"error":{"message":"not found"}})
    @staticmethod
    def content(payload):
        s=json.dumps(payload).lower()
        if "pairwise_quality_judge" in s:return '{"winner":"tie","reason":"deterministic mock"}'
        if "title" in s:return '{"title":"Deterministic Test Title"}'
        if "tag" in s:return '{"tags":["test","cost"]}'
        if "quer" in s:return '{"query":"open webui cost optimization"}'
        return "Deterministic mock response."
    def send_json(self,status,body):
        raw=json.dumps(body,separators=(",",":")).encode(); self.send_response(status); self.send_header("content-type","application/json"); self.send_header("content-length",str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def log_message(self,*args): pass
def main():
    p=argparse.ArgumentParser();p.add_argument("--host",default="127.0.0.1");p.add_argument("--port",type=int,default=9001);a=p.parse_args();ThreadingHTTPServer((a.host,a.port),Handler).serve_forever()
if __name__=="__main__":main()
