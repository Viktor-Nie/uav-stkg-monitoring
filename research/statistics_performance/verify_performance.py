"""Recalculate the retained complete workload records without rerunning timings."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import numpy as np

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reference',type=Path,default=HERE/'reference_performance')
    args=parser.parse_args();out=args.output.resolve();reference=args.reference.resolve()
    if out.exists():parser.error('output must be new; evidence is preserved')
    if not (reference/'receipt.json').exists():parser.error('complete reference records not present; do not substitute smoke/old partial records')
    receipt=json.loads((reference/'receipt.json').read_text(encoding='utf-8'))
    assert receipt['status']=='passed' and receipt['smoke'] is False and receipt['cells']==9 and receipt['complete_cells']==9
    manifest=json.loads((HERE/'frozen_configuration.json').read_text(encoding='utf-8'))
    assert receipt['configuration_sha256']==sha(HERE/'frozen_configuration.json')
    for path,digest in manifest['sha256'].items():assert sha(HERE/path)==digest,path
    for path,digest in manifest['old_result_sha256'].items():assert sha(HERE/path)==digest,path
    expected={r['workload_id']:r for r in read(reference/'workload_summary.csv')}
    recomputed=[]
    raw_hashes={}
    for index in range(1,10):
        cell=f'B{index:02d}';folder=reference/cell
        raw=read(folder/'iterations.csv')
        warm=[r for r in raw if r['phase']=='warmup'];timed=[r for r in raw if r['phase']=='timed']
        assert len(warm)==2 and len(timed)==5
        assert [int(r['repetition']) for r in timed]==list(range(1,6))
        assert all(int(r['formula_count'])==24 for r in raw)
        assert all(int(r['trace_samples'])==int(expected[cell]['samples']) for r in raw)
        counts=[tuple(int(r[k]) for k in ('trigger_count','recovery_count','expired_count','pending_count','invariant_violation_count')) for r in raw]
        assert len(set(counts))==1
        allocation=json.loads((folder/'allocation.json').read_text(encoding='utf-8'))
        assert allocation['excluded_from_timing_median'] and allocation['not_RSS']
        assert tuple(allocation['counts'][k] for k in ('trigger_count','recovery_count','expired_count','pending_count','invariant_violation_count'))==counts[0]
        values=[float(r['total_ms']) for r in timed]
        calculated={'median_ms':statistics.median(values),'q25_ms':float(np.quantile(values,.25)),
          'q75_ms':float(np.quantile(values,.75)),'min_ms':min(values),'max_ms':max(values),
          'python_allocation_peak_MiB':allocation['python_allocation_peak_bytes']/1024**2}
        for key,value in calculated.items():assert abs(value-float(expected[cell][key]))<1e-9,(cell,key)
        recomputed.append({'workload_id':cell,'samples':int(expected[cell]['samples']),'density':expected[cell]['density'],
          'warmups':2,'timed':5,**calculated})
        for path in folder.iterdir():
            if path.is_file():raw_hashes[path.relative_to(reference).as_posix()]=sha(path)
    out.mkdir(parents=True)
    with (out/'recomputed_summary.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(recomputed[0]));w.writeheader();w.writerows(recomputed)
    result={'status':'passed','timing_runs_performed':0,'cells':9,'warmups_verified':18,'timings_verified':45,
      'allocation_passes_verified':9,'all_count_signatures_consistent':True,'summary_recomputed':True,
      'source_inputs_unchanged':True,'historical_partial_records_unchanged':True,'model_calls':0,'training_runs':0,
      'configuration_sha256':receipt['configuration_sha256'],'raw_record_sha256':raw_hashes}
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='raw_record_sha256'},indent=2))

if __name__=='__main__':main()
