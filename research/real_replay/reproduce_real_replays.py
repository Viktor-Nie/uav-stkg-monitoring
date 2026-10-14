"""Optional raw-source regeneration and comparison; never downloads by default.

--input-root is an external directory holding the declared materials layout.
--expected-root is an explicit historical replay results directory. Neither
path is imported as code. All monitor code comes from this standalone bundle.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import zipfile
import numpy as np
import pandas as pd
from scipy.spatial.transform import Rotation
import flight_review
import idf_ds
import insane

PACKAGE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PACKAGE/'src'))
from uav_stkg.monitor.run_precision_regression import run_real
from uav_stkg.monitor.monitor_from_traceability_graph import instantiate_formula, monitor_formula_from_graph, node_properties
from uav_stkg.monitor.sampled_data_contract import SamplingContract, EventTimeObservationContract
from uav_stkg.monitor.sampled_monitor import InvariantSpecification

SOURCE_GROUPS={
 'RflyMAD':('multi_real_motor_replay/canonical_formula_replay_by_log.csv','multi_real_motor_replay/canonical_formula_monitor_events.csv'),
 'FlightReview':('traceability_graph/external_flight_review_event_time_graph_bound_replay.csv','traceability_graph/external_flight_review_event_time_graph_bound_events.csv'),
 'IDF_DS':('idf_ds_lap120_event_time/graph_bound_monitor_replay.csv','idf_ds_lap120_event_time/graph_bound_monitor_events.csv'),
 'INSANE':('insane_indoor1_px4_imu_event_time/graph_bound_monitor_replay.csv','insane_indoor1_px4_imu_event_time/graph_bound_monitor_events.csv'),
}

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def record_input(path,input_root,role):
    return {'path':path.relative_to(input_root).as_posix(),'sha256':sha(path),'bytes':path.stat().st_size,'role':role}

def asof(grid,source,columns):
    return pd.merge_asof(grid,source[['timestamp',*columns]].sort_values('timestamp'),on='timestamp',direction='backward')

def rfly_online(case_id,input_root):
    """Preserve the distinct historical 406 versus 407 adapter versions."""
    records=[]
    if case_id=='407_1':
        archive_path=input_root/'external_datasets/rflymad/Real-Motor-Raw-Official/Real-Motor.zip'
        with zipfile.ZipFile(archive_path) as archive:
            member=next(name for name in archive.namelist() if name.startswith('acce/407_1/log_') and name.endswith('_vehicle_local_position_0.csv'))
            prefix=member.removesuffix('vehicle_local_position_0.csv')
            frames=[pd.read_csv(archive.open(prefix+topic+'_0.csv')).sort_values('timestamp') for topic in ['vehicle_local_position','vehicle_attitude','vehicle_angular_velocity']]
        records.append(record_input(archive_path,input_root,'official_archive_407_1'))
        local,attitude,angular=frames
        start=int(max(frame.timestamp.min() for frame in frames));end=int(min(frame.timestamp.max() for frame in frames))
    else:
        case_dir=input_root/('external_datasets/rflymad/Real-Minimal-406_1' if case_id=='406_1' else 'external_datasets/rflymad/Real-Motor-Extension/406_2')
        log='log_26_2023-6-2-10-09-14' if case_id=='406_1' else 'log_27_2023-6-2-10-13-42'
        paths=[case_dir/f'{log}_{topic}_0.csv' for topic in ['estimator_local_position','vehicle_attitude','vehicle_angular_velocity']]
        local,attitude,angular=[pd.read_csv(path).sort_values('timestamp') for path in paths]
        # Historical acquisition defined stream intersection using control
        # timestamps as well. No control IDs/parameters are read by this path.
        control_path=case_dir/f'{log}_rfly_ctrl_lxl_0.csv'
        control=pd.read_csv(control_path,usecols=['timestamp']).sort_values('timestamp')
        start=int(max(frame.timestamp.min() for frame in [local,attitude,angular,control]))
        end=int(min(frame.timestamp.max() for frame in [local,attitude,angular,control]))
        records.extend(record_input(path,input_root,'native_topic_export') for path in paths)
        records.append(record_input(control_path,input_root,'timestamp_bounds_only_no_control_values'))
    grid=pd.DataFrame({'timestamp':np.arange(start,end+1,50000,dtype=np.int64)})
    state=asof(grid,local,['x','y','z','vx','vy','vz'])
    state=asof(state,attitude,['q[0]','q[1]','q[2]','q[3]'])
    state=asof(state,angular,['xyz[0]','xyz[1]','xyz[2]'])
    quaternion=state[['q[1]','q[2]','q[3]','q[0]']].to_numpy(float)
    if case_id=='407_1':
        x,y,z,w=quaternion.T
        state['roll']=np.arctan2(2*(w*x+y*z),1-2*(x*x+y*y))
        state['pitch']=np.arcsin(np.clip(2*(w*y-z*x),-1,1))
        state['yaw']=np.arctan2(2*(w*z+x*y),1-2*(y*y+z*z))
    else:state[['roll','pitch','yaw']]=Rotation.from_quat(quaternion).as_euler('xyz',degrees=False)
    state=state.rename(columns={'x':'pos_n','y':'pos_e','z':'pos_d','vx':'vel_n','vy':'vel_e','vz':'vel_d','xyz[0]':'ang_rate_x','xyz[1]':'ang_rate_y','xyz[2]':'ang_rate_z'})
    online=state[['pos_n','pos_e','pos_d','vel_n','vel_e','vel_d','roll','pitch','yaw','ang_rate_x','ang_rate_y','ang_rate_z']].copy()
    online['time_seconds']=(state.timestamp-start)/1e6
    return online,{'case_id':case_id,'grid_start_us':start,'grid_end_us':end,'grid_period_us':50000,
      'alignment':'causal zero-order hold latest source timestamp <= grid timestamp; sampled-point replay only',
      'input_records':records,'orientation_adapter':'direct_original_quaternion_formula' if case_id=='407_1' else 'scipy.Rotation.from_quat.as_euler_xyz'}

def observable(raw):
    return pd.DataFrame({'time_seconds':raw['time_seconds'],
      'speed_3d_mps':(raw['vel_n']**2+raw['vel_e']**2+raw['vel_d']**2)**.5,
      'height_m':raw['pos_d'].abs(),'abs_roll_rad':raw['roll'].abs(),'abs_pitch_rad':raw['pitch'].abs(),
      'ang_rate_norm_rps':(raw['ang_rate_x']**2+raw['ang_rate_y']**2+raw['ang_rate_z']**2)**.5})

def standalone_replay(v2,output):
    """Generate fresh outcomes even when external historical ledgers are absent."""
    graph=PACKAGE/'data/graph'
    formula_ids=sorted(key for key in node_properties(graph) if key.startswith('formula:'))
    canonical={}
    for formula_id in formula_ids:canonical.setdefault(tuple(vars(instantiate_formula(formula_id,graph)).items()),formula_id)
    streams=[]
    for case in ['406_1','406_2','407_1']:
        path=v2/f'multi_real_motor_replay/{case}_observable_trace.csv'
        frame=pd.read_csv(path,dtype={'time_seconds':str},keep_default_na=False)
        streams.append(('RflyMAD',case,frame,sorted(canonical.values()),SamplingContract(.05,.05,.10)))
    for source,path,gap in [('FlightReview','external_flight_review_event_time_signal_observations.csv',.10),('IDF_DS','idf_ds_lap120_event_time/native_signal_observations.csv',.11),('INSANE','insane_indoor1_px4_imu_event_time/native_signal_observations.csv',.06)]:
        long=pd.read_csv(v2/path,dtype={'time_seconds':str},keep_default_na=False)
        for signal in sorted(long['signal_id'].unique()):
            frame=long.loc[long['signal_id'].eq(signal),['time_seconds','value']].rename(columns={'value':signal}).reset_index(drop=True)
            ids=[formula_id for formula_id in formula_ids if instantiate_formula(formula_id,graph).signal==signal]
            streams.append((source,'',frame,ids,EventTimeObservationContract(gap)))
    outcomes=[];events=[]
    for source,case,frame,ids,contract in streams:
        for formula_id in ids:
            definition,result=monitor_formula_from_graph(frame,formula_id,graph_directory=graph,contract=contract)
            common={'source':source,'case_id':case,'formula_id':formula_id.removeprefix('formula:'),'signal_id':definition.signal}
            outcomes.append({**common,'verdict':result.verdict.value,'sample_count':result.sampling_audit.sample_count,
              'violating_sample_count':len(result.violating_sample_indices),'created_obligation_count':len(result.created_obligations),
              'recovered_obligation_count':len(result.recovered_obligation_ids),'expired_obligation_count':len(result.expired_obligation_ids),'pending_obligation_count':len(result.pending_obligation_ids)})
            for event in result.absolute_event_records:events.append({**common,**event})
    pd.DataFrame(outcomes).to_csv(output/'fresh_monitor_outcomes.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(events).to_csv(output/'fresh_monitor_events.csv',index=False,encoding='utf-8-sig')
    return {'configuration_count':len(outcomes),'event_count':len(events),
      'source_counts':{source:{'configurations':sum(row['source']==source for row in outcomes),'events':sum(row['source']==source for row in events)} for source in SOURCE_GROUPS}}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root',type=Path,required=True,help='External materials directory; see SOURCE_INPUTS.md')
    parser.add_argument('--expected-root',type=Path,help='Explicit historical specification/v2/results directory; optional, never used as code.')
    parser.add_argument('--idf-profile',choices=['verified_v34','historical_v33'],default='verified_v34',help='Complete official IDF members, or explicitly reconstructed historical truncated byte prefixes.')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.expected_root and args.idf_profile!='historical_v33':parser.error('historical --expected-root requires --idf-profile historical_v33; verified v34 has its own frozen fingerprints')
    if args.output.exists():raise FileExistsError(f'Refusing to overwrite {args.output}')
    args.output.mkdir(parents=True)
    started=time.perf_counter();input_root=args.input_root.resolve()
    reconstructed=args.output/'reconstructed';v2=reconstructed/'specification/v2/results'
    v2.mkdir(parents=True);sources={};derived=[]
    def save(frame,relative,source):
        path=v2/relative;path.parent.mkdir(parents=True,exist_ok=True)
        frame.to_csv(path,index=False,encoding='utf-8-sig')
        reference=args.expected_root/relative if args.expected_root else None
        row={'source':source,'file':relative,'rows':len(frame),'sha256':sha(path),'bytes':path.stat().st_size}
        if reference and reference.is_file():row.update({'reference_sha256':sha(reference),'byte_exact':sha(reference)==row['sha256']})
        derived.append(row);return path
    for case in ['406_1','406_2','407_1']:
        online,source=rfly_online(case,input_root)
        online_path=save(online,f'multi_real_motor_replay/{case}_online_input.csv','RflyMAD')
        # The original replay adapter read the online CSV, so preserve that
        # exact serialization boundary instead of silently changing precision.
        save(observable(pd.read_csv(online_path,encoding='utf-8-sig')),f'multi_real_motor_replay/{case}_observable_trace.csv','RflyMAD')
        sources[case]=source
    flight_path=input_root/'datasets/v2_px4_flight_review/0000c079-6820-409a-95da-e86358b6c20f.ulg'
    save(flight_review.extract_observations(flight_path),'external_flight_review_event_time_signal_observations.csv','FlightReview')
    sources['FlightReview']={'inputs':[record_input(flight_path,input_root,'original_ulog')],'version':'log UUID 0000c079-6820-409a-95da-e86358b6c20f'}
    idf_dir=PACKAGE/'data/external/idf_ds_lap120_verified_v34'
    if args.idf_profile=='historical_v33':
        retained=args.output/'historical_idf_truncated_profile';retained.mkdir()
        metadata=json.loads((idf_dir/'source_acquisition_manifest.json').read_text(encoding='utf-8'))
        for member in metadata['members']:
            payload=(idf_dir/member['local_file']).read_bytes()[:member['historical_retained_bytes']]
            if hashlib.sha256(payload).hexdigest()!=member['historical_retained_sha256']:raise ValueError('Historical IDF byte-prefix fingerprint mismatch')
            (retained/member['local_file']).write_bytes(payload)
        (retained/'source_acquisition_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False),encoding='utf-8')
        idf_dir=retained
    frame,source=idf_ds.extract_observations(idf_dir)
    save(frame,'idf_ds_lap120_event_time/native_signal_observations.csv','IDF_DS');sources['IDF_DS']=source
    frame,source=insane.extract_observations(input_root/'external_datasets/insane')
    save(frame,'insane_indoor1_px4_imu_event_time/native_signal_observations.csv','INSANE');sources['INSANE']=source
    regeneration_seconds=time.perf_counter()-started
    print(json.dumps({'raw_regeneration_completed':True,'elapsed_seconds':regeneration_seconds,'derived_byte_exact':[row.get('byte_exact') for row in derived if 'byte_exact' in row]}),flush=True)
    fresh=standalone_replay(v2,args.output)
    comparison=[]
    if args.expected_root:
        for source,(summary,event) in SOURCE_GROUPS.items():
            for relative in [summary,event]:
                destination=v2/relative;destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(args.expected_root/relative,destination)
        comparison=run_real(reconstructed,args.output)
    reference_name='verified_four_source_reference.json' if args.idf_profile=='verified_v34' else 'frozen_replay_fingerprints.json'
    baseline=json.loads(Path(__file__).with_name(reference_name).read_text(encoding='utf-8'))
    expected_derived=baseline.get('derived_sha256') or {row['file']:row['sha256'] for row in baseline['derived_outputs']}
    derived_match={row['file']:row['sha256']==expected_derived[row['file']] for row in derived}
    outputs_match={name:sha(args.output/name)==digest for name,digest in baseline['fresh_output_sha256'].items()}
    if not all(derived_match.values()) or not all(outputs_match.values()):raise ValueError('Reconstructed source/output fingerprint mismatch; inputs and baseline remain unchanged')
    receipt={'schema':'independent-four-source-raw-replay-v1','input_root_explicit':str(input_root),'expected_root_explicit':str(args.expected_root) if args.expected_root else None,
      'raw_regeneration_seconds':regeneration_seconds,'total_elapsed_seconds':time.perf_counter()-started,'derived_outputs':derived,'sources':sources,
      'fresh_replay':fresh,'historical_comparison':comparison,'idf_profile':args.idf_profile,
      'all_derived_observation_files_byte_exact':all(derived_match.values()),'derived_fingerprint_matches':derived_match,'fresh_output_fingerprint_matches':outputs_match,'status':'passed',
      'code_provenance':'Bundled pure adapters and bundled formal monitor only; external input/reference directories are never imported.',
      'redistribution_boundary':'Three complete verified IDF CSV members are supplied under CC BY 4.0 with attribution. Other raw sources, derived observations and ledgers remain at their upstream locations or local to the caller.'}
    (args.output/'reproduction_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'fresh_replay':fresh,'elapsed_seconds':receipt['total_elapsed_seconds'],'all_derived_observation_files_byte_exact':receipt['all_derived_observation_files_byte_exact']},ensure_ascii=False),flush=True)
    reference_path=Path(__file__).with_name('verified_idf_reference.json')
    expected_events=28210 if args.idf_profile=='historical_v33' else 28210-27250+json.loads(reference_path.read_text(encoding='utf-8'))['summaries']['verified']['events']
    if fresh['configuration_count']!=68 or fresh['event_count']!=expected_events:raise SystemExit(1)
    if args.expected_root and (not receipt['all_derived_observation_files_byte_exact'] or any(row['missing_events'] or row['extra_events'] or row['changed_event_rows'] or row['summary_mismatches'] for row in comparison)):raise SystemExit(1)

if __name__=='__main__':main()
