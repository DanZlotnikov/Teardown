"""Build a deterministic 30-conversation workload from pinned project material."""
from __future__ import annotations
import json,re
from pathlib import Path
import tiktoken
ROOT=Path(__file__).parents[1]; UP=ROOT.parent/"openwebui-upstream"
LINK=re.compile(r"\[(#\d+)\]\((https://github\.com/open-webui/open-webui/(?:issues|pull)/\d+)\)")
def clean(line):
    text=re.sub(r"\[[^]]+\]\([^)]+\)","",line.lstrip("- "));text=re.sub(r"[*`_]","",text);return " ".join(text.split())
def exact_tokens(text,n=10000):
    enc=tiktoken.get_encoding("o200k_base"); ids=enc.encode(text)
    if not ids:raise ValueError("empty source")
    return enc.decode((ids*((n//len(ids))+1))[:n])
def main():
    lines=(UP/"CHANGELOG.md").read_text(errors="replace").splitlines();items=[]
    for no,line in enumerate(lines,1):
        m=LINK.search(line)
        if m and line.lstrip().startswith("-"):
            items.append({"text":clean(line),"source":f"CHANGELOG.md:{no}","url":m.group(2)})
        if len(items)>=30:break
    if len(items)<30:raise RuntimeError("not enough issue-linked changelog items")
    conv=[]
    for i,item in enumerate(items):
        cid=("short" if i<8 else "long" if i<18 else "large-document" if i==18 else "case")+f"-{i+1:02d}"
        turns=2 if i<8 or i==18 else 10 if i<18 else 1
        msgs=[]
        for t in range(turns):
            body=f"I am using Open WebUI and ran into this behavior: {item['text']} What should I check, and how can I verify the fix?"
            if i==18 and t==0:
                material=(UP/"README.md").read_text(errors="replace")+"\n"+(UP/"CHANGELOG.md").read_text(errors="replace")
                body="Read this Open WebUI project material and identify the three operational changes most relevant to administrators.\n\n"+exact_tokens(material)
            if t:body=f"Follow-up {t}: {body}"
            msgs.append({"role":"user","content":body});msgs.append({"role":"assistant","content":"Fixture response retained so later turns have realistic alternating history."})
        features={"rag":19<=i<23,"web_search":23<=i<28,"autocomplete":i==28,"autocomplete_control":i==29}
        conv.append({"id":cid,"source":item["source"],"source_url":item["url"],"features":features,"messages":msgs})
    out={"schema_version":1,"conversations":conv}
    target=ROOT/"scenario/cases.json";target.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"conversations":len(conv),"output":str(target)}))
if __name__=="__main__":main()
