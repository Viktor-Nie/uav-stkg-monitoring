"""Replay complete official IDF inputs and characterize the old truncated tails."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'research/real_replay'))
import pandas as pd
import idf_ds
from uav_stkg.monitor.monitor_from_traceability_graph import instantiate_formula,monitor_formula_from_graph,node_properties
from uav_stkg.monitor.sampled_data_contract import EventTimeObservationContract
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def replay(frame,output,prefix):
    graph=ROOT/'data/graph';ids=sorted(k for k in node_properties(graph) if k.startswith('formula:'))
    outcomes=[];events=[]
    for signal in sorted(frame['signal_id'].unique()):
        single=frame.loc[frame['signal_id'].eq(signal),['time_seconds','value']].rename(columns={'value':signal}).reset_index(drop=True)
        for formula in ids:
            definition=instantiate_formula(formula,graph)
            if definition.signal!=signal:continue
            definition,result=monitor_formula_from_graph(single,formula,graph_directory=graph,contract=EventTimeObservationContract(.11))
            common={'source':'IDF_DS','case_id':'','formula_id':formula.removeprefix('formula:'),'signal_id':signal}
            outcomes.append({**common,'verdict':result.verdict.value,'sample_count':result.sampling_audit.sample_count,'violating_sample_count':len(result.violating_sample_indices),'created_obligation_count':len(result.created_obligations),'recovered_obligation_count':len(result.recovered_obligation_ids),'expired_obligation_count':len(result.expired_obligation_ids),'pending_obligation_count':len(result.pending_obligation_ids)})
            events.extend({**common,**event} for event in result.absolute_event_records)
    a=pd.DataFrame(outcomes);b=pd.DataFrame(events)
    a.to_csv(output/(prefix+'_outcomes.csv'),index=False,encoding='utf-8-sig');b.to_csv(output/(prefix+'_events.csv'),index=False,encoding='utf-8-sig')
    return a,b
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    if output==ROOT or any(output.is_relative_to(ROOT/d) for d in ('data','src','research')):parser.error('output must not overwrite release inputs or code')
    if output.exists():parser.error('output must be a new directory')
    verified=ROOT/'data/external/idf_ds_lap120_verified_v34'
    manifest=json.loads((verified/'source_acquisition_manifest.json').read_text(encoding='utf-8'))
    for row in manifest['members']:assert sha(verified/row['local_file'])==row['sha256']
    output.mkdir(parents=True)
    historical=output/'historical_truncated_profile';historical.mkdir()
    for row in manifest['members']:
        payload=(verified/row['local_file']).read_bytes()[:row['historical_retained_bytes']]
        assert hashlib.sha256(payload).hexdigest()==row['historical_retained_sha256']
        (historical/row['local_file']).write_bytes(payload)
    (historical/'source_acquisition_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    summaries={};frames={}
    for name,directory in (('historical',historical),('verified',verified)):
        frame,source=idf_ds.extract_observations(directory)
        observed=output/(name+'_observations.csv');frame.to_csv(observed,index=False,encoding='utf-8-sig')
        # Retain the original CSV read boundary, including exact timestamp tokens.
        serialized=pd.read_csv(observed,dtype={'time_seconds':str},keep_default_na=False)
        a,b=replay(serialized,output,name);frames[name]=a
        summaries[name]={'observations':len(frame),'formula_trace_combinations':len(a),'events':len(b),'verdict_counts':a['verdict'].value_counts().to_dict(),'source_files':source.get('source_files_sha256',{}),'native_signal_sample_counts':frame['signal_id'].value_counts().to_dict()}
    assert summaries['historical']['observations']==25773 and summaries['historical']['events']==27250
    assert sha(output/'historical_observations.csv')=='631319f9519ab9cbab7e9318c2675c0e084e94c5bd148bbfec504b1de8be5add'
    before=frames['historical'].set_index('formula_id');after=frames['verified'].set_index('formula_id')
    columns=['sample_count','violating_sample_count','created_obligation_count','recovered_obligation_count','expired_obligation_count','pending_obligation_count']
    changes=[]
    for formula in before.index:
        a,b=before.loc[formula],after.loc[formula]
        changes.append({'formula_id':formula,'historical_verdict':a['verdict'],'verified_verdict':b['verdict'],'verdict_changed':a['verdict']!=b['verdict'],**{k+'_delta':int(b[k])-int(a[k]) for k in columns}})
    pd.DataFrame(changes).to_csv(output/'tail_correction_by_formula.csv',index=False,encoding='utf-8-sig')
    expected_path=ROOT/'research/real_replay/verified_idf_reference.json'
    deterministic=['historical_observations.csv','historical_outcomes.csv','historical_events.csv','verified_observations.csv','verified_outcomes.csv','verified_events.csv','tail_correction_by_formula.csv']
    digests={name:sha(output/name) for name in deterministic}
    if expected_path.is_file():
        expected=json.loads(expected_path.read_text(encoding='utf-8'));assert digests==expected['output_sha256'];assert summaries==expected['summaries']
    receipt={'status':'passed' if expected_path.is_file() else 'computed_reference_not_yet_frozen','summaries':summaries,'output_sha256':digests,'verdict_changes':sum(r['verdict_changed'] for r in changes),'all_comparisons_against_retained_truncation_explicit':True,'source':'https://zenodo.org/records/16992976','source_version':'v1.0','license':'CC-BY-4.0','historical_profile_is_not_full_official_input':True,'model_calls':0,'training_runs':0,'downloads':0}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
