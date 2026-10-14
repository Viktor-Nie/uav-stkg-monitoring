"""Complete fixed desktop workloads with the frozen v34 production monitor.

Two warmups, five timings, and a separate tracemalloc pass are run per cell.
This script performs no model calls or training and never rewrites inputs.
"""
from __future__ import annotations
import argparse
import csv
import ctypes
from datetime import datetime, timezone
import gc
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time
import traceback
import tracemalloc

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'frozen_core'))
import numpy as np
import pandas as pd
from uav_stkg.monitor.monitor_from_traceability_graph import instantiate_formula,replay_trace

def now(): return datetime.now(timezone.utc).isoformat()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(path,value):
    with path.open('x',encoding='utf-8') as f: json.dump(value,f,indent=2,allow_nan=False);f.write('\n')

def check_manifest():
    manifest=json.loads((HERE/'frozen_configuration.json').read_text(encoding='utf-8'))
    for name,digest in manifest['sha256'].items():
        if sha(HERE/name)!=digest: raise ValueError('frozen input/source changed: '+name)
    return manifest

def system_cpu():
    if os.name!='nt': return None
    from ctypes import wintypes
    idle=wintypes.FILETIME();kernel=wintypes.FILETIME();user=wintypes.FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kernel),ctypes.byref(user)): return None
    number=lambda x:(x.dwHighDateTime<<32)+x.dwLowDateTime
    return number(idle),number(kernel)+number(user)

def process_memory():
    if os.name!='nt': return None
    from ctypes import wintypes
    class Memory(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),
          ('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),
          ('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),
          ('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),
          ('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]
    m=Memory();m.cb=ctypes.sizeof(m)
    handle=ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Memory),wintypes.DWORD]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(handle,ctypes.byref(m),m.cb): return None
    return {'working_set_bytes':m.WorkingSetSize,'process_peak_working_set_bytes':m.PeakWorkingSetSize}

class LoadRecorder:
    def __init__(self,out,memory_limit): self.out=out;self.memory_limit=memory_limit;self.stop=threading.Event();self.records=[]
    def loop(self):
        previous=system_cpu()
        while not self.stop.wait(.5):
            current=system_cpu();usage=None
            if current and previous and current[1]>previous[1]:
                usage=100*(1-(current[0]-previous[0])/(current[1]-previous[1]))
            memory=process_memory() or {}
            self.records.append({'utc':now(),'system_cpu_percent':usage,**memory})
            if memory.get('working_set_bytes',0)>self.memory_limit:
                self.save()
                dump(self.out.parent/'memory_limit.json',{'utc':now(),'status':'resource_terminated',
                     'working_set_limit_bytes':self.memory_limit,**memory})
                os._exit(86)
            previous=current
    def __enter__(self):
        self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start();return self
    def save(self):
        if self.records:
            with self.out.open('x',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(self.records[0]));w.writeheader();w.writerows(self.records)
    def __exit__(self,*_):
        self.stop.set();self.thread.join();self.save()

def iteration(path,ids):
    wall=time.perf_counter_ns();cpu=time.process_time_ns()
    frame=pd.read_csv(path,encoding='utf-8-sig');parsed=time.perf_counter_ns()
    replay=replay_trace(frame,ids,graph_directory=HERE/'inputs/graph');monitored=time.perf_counter_ns()
    buffer=io.StringIO();replay.to_csv(buffer,index=False,lineterminator='\n');finished=time.perf_counter_ns()
    counts={name:int(replay[column].sum()) for name,column in (
        ('trigger_count','created_obligation_count'),('recovery_count','recovered_obligation_count'),
        ('expired_count','expired_obligation_count'),('pending_count','pending_obligation_count'),
        ('invariant_violation_count','violating_sample_count'))}
    return {'parse_ms':(parsed-wall)/1e6,'monitor_ms':(monitored-parsed)/1e6,
        'summary_serialization_ms':(finished-monitored)/1e6,'total_ms':(finished-wall)/1e6,
        'process_cpu_ms':(time.process_time_ns()-cpu)/1e6,'trace_samples':len(frame),
        'formula_count':len(replay),'summary_bytes':len(buffer.getvalue().encode('utf-8')),**counts},replay

def worker(out,cell,smoke):
    configuration=check_manifest();ids=configuration['formula_ids'];path=HERE/cell['trace_path']
    out.mkdir(parents=True)
    dump(out/'started.json',{'utc':now(),'cell':cell,'pid':os.getpid(),'smoke':smoke,
        'frozen_configuration_sha256':sha(HERE/'frozen_configuration.json')})
    with LoadRecorder(out/'background_load.csv',configuration['worker_working_set_limit_bytes']) as load:
        with (out/'iterations.csv').open('x',encoding='utf-8-sig',newline='') as f:
            writer=None
            for phase,count in (('warmup',1 if smoke else 2),('timed',1 if smoke else 5)):
                for repetition in range(1,count+1):
                    assert not tracemalloc.is_tracing()
                    started=now();metrics,replay=iteration(path,ids)
                    row={'phase':phase,'repetition':repetition,'started_utc':started,'finished_utc':now(),**metrics}
                    if writer is None: writer=csv.DictWriter(f,fieldnames=list(row));writer.writeheader()
                    writer.writerow(row);f.flush()
                    if phase=='warmup' and repetition==1: replay.to_csv(out/'first_summary.csv',index=False,encoding='utf-8-sig')
                    del replay;gc.collect()
        if not smoke:
            gc.collect();tracemalloc.start();tracemalloc.reset_peak()
            started=now();metrics,replay=iteration(path,ids)
            _,peak=tracemalloc.get_traced_memory();tracemalloc.stop();del replay
            dump(out/'allocation.json',{'started_utc':started,'finished_utc':now(),
                 'python_allocation_peak_bytes':peak,'duration_ms':metrics['total_ms'],
                 'excluded_from_timing_median':True,'not_RSS':True,'counts':{k:v for k,v in metrics.items() if k.endswith('_count')}})
    dump(out/'completed.json',{'utc':now(),'status':'passed','smoke':smoke,
         'background_samples':len(load.records),'process_memory':process_memory()})

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--worker',choices=[f'B{i:02d}' for i in range(1,10)])
    args=parser.parse_args();out=args.output.resolve()
    if args.worker:
        try:
            cells=json.loads((HERE/'inputs/workloads.json').read_text(encoding='utf-8'))
            worker(out,next(c for c in cells if c['workload_id']==args.worker),args.smoke)
        except Exception:
            traceback.print_exc();raise
        return
    if out.exists(): parser.error('output must be new; previous attempts are retained')
    out.mkdir(parents=True);configuration=check_manifest()
    # Validate every bound numerical value against the frozen original workload.
    old=json.loads((HERE/'inputs/original_bound_specifications.json').read_text(encoding='utf-8'))
    specifications=[vars(instantiate_formula(fid,HERE/'inputs/graph')) for fid in configuration['formula_ids']]
    assert specifications==old['specifications']
    environment={'utc':now(),'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
        'processor':platform.processor(),'logical_cpus':os.cpu_count(),'pandas':pd.__version__,'numpy':np.__version__,
        'pid':os.getpid(),'cpu_environment':{k:os.environ.get(k,'not_set') for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS')},
        'device_role':'ground desktop offline batch; no airborne latency measurement'}
    if os.name=='nt':
        machine=subprocess.run(['powershell','-NoProfile','-Command',
          "Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json -Compress"],capture_output=True,text=True)
        environment['cpu_inventory']=machine.stdout.strip();environment['cpu_inventory_exit_code']=machine.returncode
    dump(out/'environment.json',environment)
    protocol={'frozen_utc':now(),'configuration_sha256':sha(HERE/'frozen_configuration.json'),
        'runner_sha256':sha(Path(__file__)),'warmups':1 if args.smoke else 2,'timed':1 if args.smoke else 5,
        'allocation_pass':not args.smoke,'smoke':args.smoke,'per_cell_budget_seconds':configuration['cell_budget_seconds'],
        'worker_working_set_limit_bytes':configuration['worker_working_set_limit_bytes'],
        'timing_scope':'CSV parsing + current frozen production graph replay of 24 formulas + summary CSV serialization',
        'exclusions':['full event-ledger serialization','telemetry','actuation','allocation tracing'],
        'order':'ascending samples then quiescent/sparse/dense; no best-run selection',
        'old_results':'Original 60-second-budget partial results retained separately; no old timings are substituted',
        'entry_version':'v34 precision-aware production graph replay; old v2 entry timings are not a speedup comparator',
        'memory':'separate tracemalloc Python allocation peak; process working set recorded separately',
        'background_policy':'root-coordinated CPU window; system CPU fraction sampled every 0.5s; ambient OS/app activity is not claimed absent'}
    dump(out/'protocol_before_runs.json',protocol)
    cells=json.loads((HERE/'inputs/workloads.json').read_text(encoding='utf-8'))
    if args.smoke: cells=cells[:1]
    receipts=[]
    for cell in cells:
        target=out/cell['workload_id'];started=now()
        command=[sys.executable,'-B','-X','utf8',str(Path(__file__)),'--worker',cell['workload_id'],'--output',str(target)]
        if args.smoke: command.append('--smoke')
        with (out/(cell['workload_id']+'.stdout.log')).open('x',encoding='utf-8') as stdout, (out/(cell['workload_id']+'.stderr.log')).open('x',encoding='utf-8') as stderr:
            process=subprocess.Popen(command,stdout=stdout,stderr=stderr)
            try: code=process.wait(timeout=configuration['cell_budget_seconds']);status='passed' if code==0 else 'resource_terminated' if code==86 else 'failed'
            except subprocess.TimeoutExpired:
                process.kill();code=process.wait();status='budget_terminated'
        receipt={**cell,'started_utc':started,'finished_utc':now(),'exit_code':code,'status':status}
        dump(out/(cell['workload_id']+'.receipt.json'),receipt);receipts.append(receipt)
        print(json.dumps(receipt),flush=True)
    rows=[]
    for receipt in receipts:
        target=out/receipt['workload_id'];raw=pd.read_csv(target/'iterations.csv') if (target/'iterations.csv').exists() else pd.DataFrame()
        measured=raw[raw.phase=='timed'] if len(raw) else raw
        complete=len(measured)==(1 if args.smoke else 5)
        allocation=json.loads((target/'allocation.json').read_text()) if (target/'allocation.json').exists() else {}
        values=measured.total_ms.tolist() if complete else []
        rows.append({'workload_id':receipt['workload_id'],'samples':receipt['samples'],'density':receipt['density'],
          'status':receipt['status'],'timed_completed':len(measured),'median_ms':statistics.median(values) if values else '',
          'q25_ms':float(np.quantile(values,.25)) if values else '','q75_ms':float(np.quantile(values,.75)) if values else '',
          'min_ms':min(values) if values else '','max_ms':max(values) if values else '',
          'python_allocation_peak_MiB':allocation.get('python_allocation_peak_bytes',0)/1024**2 if allocation else ''})
    with (out/'workload_summary.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    check_manifest()
    passed=all(r['status']=='passed' for r in receipts)
    dump(out/'receipt.json',{'status':'passed' if passed else 'incomplete','smoke':args.smoke,
         'cells':len(cells),'complete_cells':sum(r['status']=='passed' for r in receipts),
         'configuration_sha256':sha(HERE/'frozen_configuration.json'),'source_unchanged':True,
         'bound_specifications_match_original':True,'model_calls':0,'training_runs':0})

if __name__=='__main__':main()
