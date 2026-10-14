"""Recompute the historical train quantiles from explicit external inputs.

Raw mode reproduces only the seven window-end feature columns consumed by
the threshold catalogue, not the unrelated 84-feature ML experiment.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from case_metadata import read_test_info, infer_status, map_official_class
from split_allocation import allocate_counts

FIELDS = ['speed_3d__last','altitude_estimated__last','roll__last','pitch__last',
          'ang_rate_x__last','ang_rate_y__last','ang_rate_z__last']
RAW_FIELDS = ['index','PosNED[3]','VelNED[1]','VelNED[2]','VelNED[3]',
              'Eular[1]','Eular[2]','AngRate[1]','AngRate[2]','AngRate[3]']
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''): digest.update(block)
    return digest.hexdigest()

def read_selected_xlsx(path):
    """Read cached worksheet numbers without rounding or Excel date conversion.

    Reading only the required numeric columns avoids materialising all 41
    historical workbook columns. No third-party numerical reader is needed.
    """
    with zipfile.ZipFile(path) as archive:
        shared=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared=[''.join(element.itertext()) for element in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall(NS+'si')]
        workbook=ET.fromstring(archive.read('xl/workbook.xml'))
        first=workbook.find(NS+'sheets')[0]
        relationship=first.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        rels=ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target=next(item.attrib['Target'] for item in rels if item.attrib['Id']==relationship)
        member=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        data=ET.fromstring(archive.read(member)).find(NS+'sheetData')
        def cell_value(cell):
            kind=cell.attrib.get('t')
            if kind=='inlineStr':
                inline=cell.find(NS+'is')
                return ''.join(inline.itertext()) if inline is not None else None
            value=cell.find(NS+'v')
            if value is None or value.text is None:return None
            return shared[int(value.text)] if kind=='s' else value.text
        rows=list(data)
        header={''.join(c for c in cell.attrib['r'] if c.isalpha()):cell_value(cell) for cell in rows[0]}
        wanted={column:name for column,name in header.items() if name in RAW_FIELDS}
        missing=set(RAW_FIELDS)-set(wanted.values())
        if missing:raise ValueError(f'{path}: missing numeric fields {sorted(missing)}')
        records=[]
        for row in rows[1:]:
            values={name:np.nan for name in RAW_FIELDS}
            for cell in row:
                column=''.join(c for c in cell.attrib['r'] if c.isalpha())
                if column in wanted:
                    value=cell_value(cell)
                    try:values[wanted[column]]=float(value)
                    except (ValueError,TypeError): pass
            records.append(values)
        return pd.DataFrame(records,columns=RAW_FIELDS)

def endpoints_from_xlsx(path, hz):
    raw=read_selected_xlsx(path)
    # These are exactly the feature constructions in standardize_one().
    values=pd.DataFrame({
      'speed_3d__last':np.sqrt(raw['VelNED[1]']**2+raw['VelNED[2]']**2+raw['VelNED[3]']**2),
      'altitude_estimated__last':-raw['PosNED[3]'],
      'roll__last':raw['Eular[1]'],'pitch__last':raw['Eular[2]'],
      'ang_rate_x__last':raw['AngRate[1]'],'ang_rate_y__last':raw['AngRate[2]'],'ang_rate_z__last':raw['AngRate[3]']})
    width=max(2,int(round(hz)))
    step=max(1,int(round(hz)))
    records=[]
    for end in range(width-1,len(raw),step):
        row={'window_end_index':int(raw['index'].iloc[end]) if pd.notna(raw['index'].iloc[end]) else end}
        for name in FIELDS:
            block=values[name].iloc[end-width+1:end+1].to_numpy(float)
            finite=block[np.isfinite(block)]
            row[name]=float(finite[-1]) if finite.size else np.nan
        records.append(row)
    return pd.DataFrame(records)

def make_case_split(source_root):
    """Recreate the case split from raw TestInfo; no frozen assignments read."""
    rows=[]
    for path in sorted(source_root.rglob('TestInfo.csv')):
        case_root=path.parent.relative_to(source_root).as_posix()
        if not (path.parent/'TrueData/UAVState_data.xlsx').is_file() or not (path.parent/'TrueData/TrueState_data.xlsx').is_file():continue
        info=read_test_info(path)
        rows.append({'case_root':case_root,'flight_status':infer_status(case_root),
          'official_11_class':map_official_class(info['fault_id'],info['fault_mode_or_first_parameter']),
          'data_frequency':info['data_frequency']})
    index=pd.DataFrame(rows)
    rng=np.random.RandomState(20260727)
    pieces=[]
    for _,group in index.groupby(['official_11_class','flight_status'],sort=True):
        shuffled=group.sort_values('case_root').iloc[rng.permutation(len(group))].copy()
        train,validation,test=allocate_counts(len(shuffled),.15,.15)
        shuffled['split']=['train']*train+['validation']*validation+['test']*test
        pieces.append(shuffled)
    return pd.concat(pieces,ignore_index=True).sort_values('case_root').reset_index(drop=True)

def _case_worker(task):
    source_root,case=task
    path=Path(source_root)/case['case_root']/'TrueData/UAVState_data.xlsx'
    frame=endpoints_from_xlsx(path,float(case['data_frequency']))
    frame.insert(0,'split',case['split'])
    frame.insert(0,'case_root',case['case_root'])
    return frame,{'case_root':case['case_root'],'source_relative_path':path.relative_to(source_root).as_posix(),
      'source_sha256':sha256(path),'source_bytes':path.stat().st_size,'window_count':len(frame)}

def derive_quantiles(features):
    train=features[features['split'].eq('train')]
    derived=pd.DataFrame({'speed_3d_mps':train['speed_3d__last'].abs(),
      'height_m':train['altitude_estimated__last'].abs(),'abs_roll_rad':train['roll__last'].abs(),
      'abs_pitch_rad':train['pitch__last'].abs(),
      'ang_rate_norm_rps':(train['ang_rate_x__last']**2+train['ang_rate_y__last']**2+train['ang_rate_z__last']**2)**.5})
    units={'speed_3d_mps':'m/s','height_m':'m','abs_roll_rad':'rad','abs_pitch_rad':'rad','ang_rate_norm_rps':'rad/s'}
    rows=[]
    for signal in derived:
        stem=signal.removesuffix('_mps').removesuffix('_m').removesuffix('_rad').removesuffix('_rps')
        for percentile in (.95,.99):
            rows.append({'threshold_id':f'{stem}_p{int(percentile*100)}_train','signal_id':signal,
              'value':float(derived[signal].quantile(percentile)),'unit':units[signal],
              'policy':f'HIL_train_quantile_{int(percentile*100)}',
              'scope':'research_monitor_reference_not_engineering_safety_limit','train_windows':len(train)})
    return pd.DataFrame(rows)

def projection_hash(frame):
    ordered=frame.sort_values(['case_root','window_end_index']).reset_index(drop=True)
    digest=hashlib.sha256()
    for row in ordered[['case_root','split','window_end_index']].itertuples(index=False,name=None):
        digest.update(json.dumps(row,separators=(',',':')).encode()+b'\n')
    digest.update(ordered[FIELDS].to_numpy(dtype='<f8').tobytes())
    return digest.hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--raw-state-root',type=Path)
    group.add_argument('--feature-table',type=Path)
    parser.add_argument('--reference-features',type=Path)
    parser.add_argument('--reference-split',type=Path)
    parser.add_argument('--workers',type=int,default=1)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-cases',type=int,help='Smoke mode only; never claims complete population.')
    parser.add_argument('--catalogue',type=Path,default=Path(__file__).resolve().parents[2]/'data/provenance/research_monitor_thresholds.csv')
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(f'Refusing to overwrite {args.output}')
    args.output.mkdir(parents=True)
    started=time.perf_counter(); receipts=[]; split_comparison=None
    if args.raw_state_root:
        cases=make_case_split(args.raw_state_root.resolve())
        cases.to_csv(args.output/'reconstructed_case_split.csv',index=False,encoding='utf-8-sig')
        if args.reference_split:
            reference=pd.read_csv(args.reference_split)
            columns=['case_root','split','data_frequency','official_11_class','flight_status']
            split_comparison=cases[columns].equals(reference.sort_values('case_root').reset_index(drop=True)[columns])
        selected=cases.head(args.max_cases) if args.max_cases else cases
        tasks=[(str(args.raw_state_root.resolve()),row) for row in selected.to_dict('records')]
        pieces=[]
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            for index,(frame,receipt) in enumerate(executor.map(_case_worker,tasks),start=1):
                pieces.append(frame);receipts.append(receipt)
                if index%50==0 or index==len(tasks):
                    print(json.dumps({'raw_cases_completed':index,'total_cases':len(tasks),'elapsed_seconds':round(time.perf_counter()-started,2)}),flush=True)
        features=pd.concat(pieces,ignore_index=True)
        features.to_parquet(args.output/'reconstructed_threshold_window_endpoints.parquet',index=False)
    else:
        if args.feature_table.suffix=='.parquet':features=pd.read_parquet(args.feature_table)
        elif args.feature_table.suffix=='.pkl':raise ValueError('Use Parquet: loading untrusted pickle may execute code.')
        else:features=pd.read_csv(args.feature_table)
        receipts=[{'source_sha256':sha256(args.feature_table),'source_file':args.feature_table.name}]
    thresholds=derive_quantiles(features)
    thresholds.to_csv(args.output/'research_monitor_thresholds.csv',index=False,encoding='utf-8-sig')
    expected=pd.read_csv(args.catalogue,float_precision='round_trip')
    maximum=max(abs(float(a)-float(b)) for a,b in zip(thresholds['value'],expected['value']))
    projection=None
    if args.reference_features:
        reference=pd.read_parquet(args.reference_features)
        if args.max_cases:reference=reference[reference['case_root'].isin(features['case_root'])]
        left=features.sort_values(['case_root','window_end_index']).reset_index(drop=True)
        right=reference.sort_values(['case_root','window_end_index']).reset_index(drop=True)
        projection={'raw_sha256':projection_hash(left),'reference_sha256':projection_hash(right),
          'keys_exact':left[['case_root','split','window_end_index']].equals(right[['case_root','split','window_end_index']]),
          'numeric_array_exact':np.array_equal(left[FIELDS].to_numpy(float),right[FIELDS].to_numpy(float),equal_nan=True),
          'maximum_absolute_difference':float(np.nanmax(np.abs(left[FIELDS].to_numpy(float)-right[FIELDS].to_numpy(float))))}
    complete=(not args.max_cases and len(features)==201026 and features['split'].eq('train').sum()==141508 and features['case_root'].nunique()==2613)
    receipt={'schema':'hil-threshold-reproduction-v1','input_mode':'raw_excel' if args.raw_state_root else 'external_frozen_features',
      'complete_historical_population':bool(complete),'case_count':int(features['case_root'].nunique()),'window_count':len(features),
      'train_window_count':int(features['split'].eq('train').sum()),'case_split_reconstructed_exact':split_comparison,
      'endpoint_projection_comparison':projection,'threshold_maximum_absolute_difference':maximum,
      'threshold_csv_sha256':sha256(args.output/'research_monitor_thresholds.csv'),
      'catalogue_sha256':sha256(args.catalogue),'elapsed_seconds':time.perf_counter()-started,
      'quantile_method':'pandas.Series.quantile; linear interpolation, all train windows including fault-active periods',
      'boundary':'Seven causal 1-second endpoint columns only; not a reconstruction of 84 unrelated ML features or engineering calibration.',
      'inputs':receipts}
    (args.output/'reproduction_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in receipt.items() if key!='inputs'},ensure_ascii=False),flush=True)
    if not args.max_cases and (not complete or maximum>1e-12 or split_comparison is False or (projection and not projection['numeric_array_exact'])):raise SystemExit(1)

if __name__=='__main__':main()
