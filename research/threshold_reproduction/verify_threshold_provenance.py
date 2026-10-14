"""Verify declared source composition; raw quantile computation is a separate path."""
import argparse,csv,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as h:return list(csv.DictReader(h))
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);a=parser.parse_args();out=a.output.resolve()
    if out==ROOT or any(out.is_relative_to(ROOT/d) for d in ('data','src','research')):parser.error('output must not overwrite inputs')
    if out.exists():parser.error('output must be new')
    source=json.loads((HERE/'raw_reproduction_receipt.json').read_text(encoding='utf-8'))
    assert source['complete_historical_population'] and source['threshold_maximum_absolute_difference']==0
    projection=source['endpoint_projection_comparison'];assert projection['keys_exact'] and projection['numeric_array_exact'] and projection['maximum_absolute_difference']==0
    assert source['threshold_csv_sha256']==hashlib.sha256((ROOT/'data/provenance/research_monitor_thresholds.csv').read_bytes()).hexdigest()
    cases=read(HERE/'frozen_case_split.csv');assert len(cases)==2613
    counts={r['case_root']:r['window_count'] for r in source['inputs']};assert len(counts)==2613 and sum(counts.values())==201026
    train=[r for r in cases if r['split']=='train'];assert len(train)==1841 and sum(counts[r['case_root']] for r in train)==141508
    actual=[{'case_class':k,'all_cases':sum(r['official_11_class']==k for r in cases),'training_cases':sum(r['official_11_class']==k for r in train),'training_windows':sum(counts[r['case_root']] for r in train if r['official_11_class']==k)} for k in sorted({r['official_11_class'] for r in cases})]
    assert [{k:str(v) for k,v in row.items()} for row in actual]==read(HERE/'composition.csv')
    out.mkdir(parents=True)
    with (out/'composition.csv').open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(actual[0]));w.writeheader();w.writerows(actual)
    receipt={'status':'passed','case_count':2613,'window_count':201026,'training_cases':1841,'training_windows':141508,'raw_quantiles_recomputed_this_command':False,'prior_actual_raw_reconstruction_receipt_verified':True,'raw_quantile_reproduction_entry':'research/threshold_reproduction/reproduce_thresholds.py --raw-state-root EXTERNAL_HIL_ROOT --output NEW_DIRECTORY','interpretation':'Source composition and previously computed raw evidence receipt, not a new computation from telemetry. Raw reconstruction requires explicit upstream inputs.','downloads':0,'model_calls':0,'training_runs':0}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
