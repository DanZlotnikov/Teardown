"""Code-enforced API spend controls loaded from the pinned pricing snapshot."""
from __future__ import annotations
import json, os, time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar
import yaml
T = TypeVar("T")
class BudgetStop(RuntimeError): pass
@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
class BudgetGuard:
    def __init__(self, root: Path, config_path: Path|None=None):
        self.root=root.resolve(); self.config_path=config_path or self.root/"config.yaml"
        self.config=yaml.safe_load(self.config_path.read_text()); self.budget=self.config["budget"]
        self.models=self.config["pricing_snapshot"]["models"]; paths=self.config["paths"]
        self.log_path=self.root/paths["spend_log"]; self.total_path=self.root/paths["spend_total"]
        self.status_path=self.root/paths["budget_status"]; self.smoke_config=self.budget["smoke_test"]
        self.smoke_dir=self.root/self.smoke_config["marker_directory"]; self.log_path.parent.mkdir(parents=True,exist_ok=True); self.smoke_dir.mkdir(parents=True,exist_ok=True)
        if not self.log_path.exists(): self.log_path.touch()
        if not self.total_path.exists(): self._write_total(Decimal("0"))
    def _records(self): return [json.loads(x) for x in self.log_path.read_text().splitlines() if x.strip()]
    def running_total(self): return sum((Decimal(str(x["computed_cost_usd"])) for x in self._records() if x.get("computed_cost_usd") is not None),Decimal("0"))
    def unresolved_reservations(self): return sum((Decimal(str(x["reserved_worst_case_cost_usd"])) for x in self._records() if x.get("status")=="failed_unknown_usage" and x.get("reserved_worst_case_cost_usd") is not None),Decimal("0"))
    def effective_total(self): return self.running_total()+self.unresolved_reservations()
    def phase_total(self,phase): return sum((Decimal(str(x["computed_cost_usd"])) for x in self._records() if x.get("phase")==phase and x.get("computed_cost_usd") is not None),Decimal("0"))
    def compute_cost(self,model,usage):
        if model not in self.models: raise KeyError(f"No pinned pricing for model {model!r}")
        p=self.models[model]; uncached=usage.input_tokens-usage.cached_input_tokens
        if uncached<0: raise ValueError("cached input tokens cannot exceed input tokens")
        m=Decimal("1000000")
        return (Decimal(uncached)*Decimal(str(p["input"]))+Decimal(usage.cached_input_tokens)*Decimal(str(p["cached_input"]))+Decimal(usage.output_tokens)*Decimal(str(p["output"])))/m
    def preflight(self,*,phase,model,input_tokens,max_output_tokens):
        if (self.root/'results/PAID-CALLS-BLOCKED').exists():
            raise BudgetStop('Paid calls blocked: historical spend ledger was lost in workspace cleanup; see results/BUDGET-STATUS.md')
        if phase not in self.budget["phase_caps"]: raise KeyError(f"Unknown budget phase {phase!r}")
        self._enforce_smoke_gate(phase=phase,model=model,input_tokens=input_tokens,max_output_tokens=max_output_tokens)
        current=self.effective_total(); soft=Decimal(str(self.budget["soft_stop"])); hard=Decimal(str(self.budget["hard_stop"]))
        if current>=soft and os.getenv("TEARDOWN_ALLOW_POST_SOFT_STOP")!="1": self.write_status("Soft stop reached before request"); raise BudgetStop(f"Soft stop reached: ${current:.6f} >= ${soft}")
        worst=self.compute_cost(model,TokenUsage(input_tokens,max_output_tokens))
        if current+worst>hard: self.write_status("Request reservation could cross hard stop"); raise BudgetStop("Request could cross hard stop")
        cap=Decimal(str(self.budget["phase_caps"][phase])); mult=Decimal(str(self.budget["phase_overage_stop_multiplier"]))
        if self.phase_total(phase)+worst>cap*mult: self.write_status(f"{phase} request could exceed 150% phase stop"); raise BudgetStop(f"Phase stop would be crossed for {phase}")
        return worst
    def smoke_marker_path(self,phase): return self.smoke_dir/f"{phase}.passed.json"
    def smoke_passed(self,phase):
        try: data=json.loads(self.smoke_marker_path(phase).read_text())
        except (OSError,json.JSONDecodeError): return False
        required={"mock_dry_run_passed","paid_calls_persisted","token_usage_present","spend_log_reconciled","resume_check_passed","secrets_scan_passed"}
        return data.get("phase")==phase and all(data.get(k) is True for k in required)
    def write_smoke_marker(self,phase,checks:Mapping[str,bool]):
        required=["mock_dry_run_passed","paid_calls_persisted","token_usage_present","spend_log_reconciled","resume_check_passed","secrets_scan_passed"]
        missing=[k for k in required if checks.get(k) is not True]
        if missing: raise ValueError(f"Smoke test cannot pass; failed checks: {missing}")
        paid=[x for x in self._records() if x.get("phase")==phase and x.get("status")=="success"]
        if not paid: raise ValueError("Smoke test cannot pass without a successful paid call")
        if len(paid)>int(self.smoke_config["max_calls_per_phase"]): raise ValueError("Smoke test exceeded its call limit")
        if self.phase_total(phase)>Decimal(str(self.smoke_config["max_cost_per_phase"])): raise ValueError("Smoke test exceeded its spend limit")
        marker={"phase":phase,"validated_at":datetime.now(timezone.utc).isoformat(),"calls":len(paid),"cost_usd":float(self.phase_total(phase)),**{k:True for k in required}}
        target=self.smoke_marker_path(phase); target.write_text(json.dumps(marker,indent=2,sort_keys=True)+"\n"); return target
    def _enforce_smoke_gate(self,*,phase,model,input_tokens,max_output_tokens):
        if not self.smoke_config.get("required_before_batch",True) or self.smoke_passed(phase): return
        records=[x for x in self._records() if x.get("phase")==phase]
        if len(records)>=int(self.smoke_config["max_calls_per_phase"]): raise BudgetStop(f"Smoke gate blocks additional {phase} calls until validation passes")
        reservation=self.compute_cost(model,TokenUsage(input_tokens,max_output_tokens))
        if self.phase_total(phase)+reservation>Decimal(str(self.smoke_config["max_cost_per_phase"])): raise BudgetStop("Smoke request could exceed smoke cap")
    def record(self,*,phase,model,usage,status,attempt,error=None,reserved_worst_case_cost=None):
        cost=self.compute_cost(model,usage) if usage is not None else None; total=self.running_total()+(cost or Decimal("0"))
        record={"timestamp":datetime.now(timezone.utc).isoformat(),"phase":phase,"model":model,"input_tokens":usage.input_tokens if usage else None,"output_tokens":usage.output_tokens if usage else None,"cached_input_tokens":usage.cached_input_tokens if usage else None,"computed_cost_usd":float(cost) if cost is not None else None,"running_total_usd":float(total),"status":status,"attempt":attempt,"error":error,"reserved_worst_case_cost_usd":float(reserved_worst_case_cost) if reserved_worst_case_cost is not None else None}
        with self.log_path.open("a") as h: h.write(json.dumps(record,sort_keys=True)+"\n"); h.flush(); os.fsync(h.fileno())
        self._write_total(total)
        if total>=Decimal(str(self.budget["hard_stop"])): self.write_status("Hard stop reached"); raise BudgetStop("Hard stop reached")
        if total>=Decimal(str(self.budget["soft_stop"])): self.write_status("Soft stop reached")
        return record
    def call_with_retries(self,*,phase,model,input_tokens,max_output_tokens,call:Callable,sleep=time.sleep):
        for attempt in range(1,int(self.budget["max_retries"])+1):
            reserve=self.preflight(phase=phase,model=model,input_tokens=input_tokens,max_output_tokens=max_output_tokens)
            try: result,usage=call()
            except Exception as exc:
                self.record(phase=phase,model=model,usage=None,status="failed_unknown_usage",attempt=attempt,error=f"{type(exc).__name__}: {exc}",reserved_worst_case_cost=reserve)
                if attempt==int(self.budget["max_retries"]): raise
                sleep(2**(attempt-1)); continue
            self.record(phase=phase,model=model,usage=usage,status="success",attempt=attempt,reserved_worst_case_cost=reserve); return result
        raise AssertionError("unreachable")
    def progress(self,completed_calls,planned_calls=None):
        if planned_calls is not None and planned_calls>int(self.budget["long_run_threshold_calls"]) and completed_calls%int(self.budget["progress_every_calls"])==0:
            return f"calls={completed_calls}/{planned_calls} spend=${self.running_total():.6f} exposure=${self.effective_total():.6f}"
    def write_status(self,reason):
        total=self.running_total(); phases="\n".join(f"- `{p}`: ${self.phase_total(p):.6f} / ${c:.2f}" for p,c in self.budget["phase_caps"].items())
        self.status_path.write_text(f"# Budget status\n\n- Reason: {reason}\n- Running measured total: ${total:.6f}\n- Effective budget exposure: ${self.effective_total():.6f}\n- Soft stop: $23.00\n- Hard stop: $30.00\n\n## Phase totals\n\n{phases}\n\n## Work status\n\nPopulate this section from the run manifest before requesting approval.\n")
    def _write_total(self,total):
        temp=self.total_path.with_suffix(".tmp"); temp.write_text(f"{total:.9f}\n"); temp.replace(self.total_path)
