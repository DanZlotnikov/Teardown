"""Enable the one opt-in feature exercised by the baseline workload."""
from __future__ import annotations
import argparse,json
from configs.optimized.install import req,signin
def main():
    p=argparse.ArgumentParser();p.add_argument("--base-url",default="http://127.0.0.1:8088");a=p.parse_args();token=signin(a.base_url);current=req("GET",a.base_url+"/api/v1/tasks/config",token);current["ENABLE_AUTOCOMPLETE_GENERATION"]=True;updated=req("POST",a.base_url+"/api/v1/tasks/config/update",token,current);print(json.dumps({"autocomplete_enabled":updated["ENABLE_AUTOCOMPLETE_GENERATION"],"other_task_settings":"Open WebUI defaults"},sort_keys=True))
if __name__=="__main__":main()
