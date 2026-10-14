"""Recalculate auxiliary historical rates from saved decision-only projections.

This does not reconstruct classifier features, train, score a model or access
raw telemetry. Original failures and development/final distinctions remain.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def rows(name):
    with (ROOT/name).open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))

def metrics(data,alarm):
    per=defaultdict(lambda:[0,0,0,0]);pooled=[0,0,0,0]
    for row in data:
        truth=int(row["installed_fault"]);pred=int(row[alarm]);assert truth in (0,1) and pred in (0,1)
        at=2*truth+pred;per[row["case_id"]][at]+=1;pooled[at]+=1
    normal=[];fault=[]
    for v in per.values():
        assert not (sum(v[:2]) and sum(v[2:])),"inconsistent installed condition within file"
        if sum(v[:2]):normal.append(v[1]/sum(v[:2]))
        if sum(v[2:]):fault.append(v[2]/sum(v[2:]))
    fpr=sum(normal)/len(normal);fnr=sum(fault)/len(fault)
    return dict(windows=len(data),files=len(per),pooled_tn_fp_fn_tp=pooled,
                fpr=fpr,fnr=fnr,balanced_accuracy=1-(fpr+fnr)/2)

def weighted_auc(data):
    sizes=defaultdict(int)
    for row in data:sizes[row["case_id"]]+=1
    groups=defaultdict(lambda:[0.,0.])
    for row in data:groups[float(row["score"])][int(row["installed_fault"])]+=1/sizes[row["case_id"]]
    pos=sum(v[1] for v in groups.values());neg=sum(v[0] for v in groups.values());lower=0.;auc=0.
    for _,(nw,pw) in sorted(groups.items()):auc+=pw*(lower+nw/2);lower+=nw
    return auc/(pos*neg)

def close(actual,expected):
    assert math.isclose(actual,expected,rel_tol=1e-10,abs_tol=1e-12),(actual,expected)

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError("Use a new output directory")
    before={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in ROOT.glob("*.csv")}
    results={}
    data=rows("uavfd_locked_decisions.csv")
    expected=json.loads((ROOT/"uavfd_locked_summary.json").read_text(encoding="utf8"))["results"]
    for row in expected:
        m=metrics(data,row["model"]+"__alarm")
        assert m["pooled_tn_fp_fn_tp"]==row["pooled_tn_fp_fn_tp"]
        close(m["fpr"],row["source_record_weighted_false_positive_rate"])
        close(m["fnr"],row["source_record_weighted_false_negative_rate"])
        results[row["model"]]=m
    for name,ref,method in [
        ("uavfd_vibration_selected_decisions.csv","uavfd_vibration_development_metrics.csv","validation_selected_vibration"),
        ("uavfd_conservative_selected_decisions.csv","uavfd_conservative_development_metrics.csv","round44_validation_selected")]:
        m=metrics(rows(name),"alarm");e=next(x for x in rows(ref) if x["method"]==method)
        assert m["pooled_tn_fp_fn_tp"]==json.loads(e["pooled_tn_fp_fn_tp"])
        for k in ("fpr","fnr","balanced_accuracy"):close(m[k],float(e[k]))
        results[method]=m
    data=rows("dronepropa_final_decisions.csv")
    expected=json.loads((ROOT/"dronepropa_final_summary.json").read_text(encoding="utf8"))["metrics"]
    for tag,col in [("old_vote","old_vote_alarm"),("selected","selected_alarm")]:
        m=metrics(data,col);e=expected[tag];assert m["pooled_tn_fp_fn_tp"]==e["pooled_tn_fp_fn_tp"]
        for k in ("fpr","fnr","balanced_accuracy"):close(m[k],e["equal_file_"+k])
        results["dronepropa_final_"+tag]=m
    allrows=rows("direction_validation_decisions.csv")
    expected=json.loads((ROOT/"direction_selection_before_new_final.json").read_text(encoding="utf8"))["candidate_decisions"]
    for e in expected:
        data=[x for x in allrows if x["candidate"]==e["candidate"]];m=metrics(data,"alarm");v=e["validation"]
        assert m["pooled_tn_fp_fn_tp"]==v["pooled_tn_fp_fn_tp"]
        for k in ("fpr","fnr","balanced_accuracy"):close(m[k],v[k])
        m["file_equal_auc"]=weighted_auc(data);close(m["file_equal_auc"],e["validation_file_equal_auc"])
        results[e["candidate"]]=m
    data=rows("historical_ground_benchmark_timings.csv")
    expected=json.loads((ROOT/"historical_ground_benchmark_summary.json").read_text(encoding="utf8"))
    assert len(data)==expected["measured_iterations"]==30
    def percentile(values,q):
        values=sorted(values);at=(len(values)-1)*q;lo=int(at);hi=min(lo+1,len(values)-1)
        return values[lo]+(values[hi]-values[lo])*(at-lo)
    latency=[float(x["end_to_end_ms"]) for x in data]
    measured={"p50":percentile(latency,.5),"p95":percentile(latency,.95),"p99":percentile(latency,.99),"max":max(latency),"mean":sum(latency)/len(latency)}
    for k,v in measured.items():close(v,expected["latency_ms"][k])
    alloc=[int(x["python_allocation_peak_bytes"]) for x in data]
    close(percentile(alloc,.5),expected["python_allocation_peak_bytes"]["p50"])
    close(max(alloc),expected["python_allocation_peak_bytes"]["max"])
    close(sum(int(x["trace_sample_count"])/(float(x["end_to_end_ms"])/1000) for x in data)/len(data),expected["throughput_trace_samples_per_second"])
    results["historical_ground_benchmark_record"]={"iterations":30,"latency_ms":measured,"timings_rerun":False}
    after={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in ROOT.glob("*.csv")};assert before==after
    a.output.mkdir(parents=True)
    receipt=dict(status="passed",result_series=len(results),results=results,input_sha256=before,
      scientific_boundary="Rescoring saved decisions only; no new fit/inference/raw-feature reconstruction, independent final data or causal explanation.",model_calls=0,training_runs=0,downloads=0)
    (a.output/"receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps(dict(status="passed",result_series=len(results))))
if __name__=="__main__":main()
