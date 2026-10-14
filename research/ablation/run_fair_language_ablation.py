"""Frozen, anonymous-ID, two-factor information ablation; no local gold is sent."""
from __future__ import annotations
import argparse, concurrent.futures, csv, hashlib, json, os, random, re, shutil, subprocess, tempfile, time, tomllib
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=next((p for p in HERE.parents if (p/'specification').is_dir()),None)
MODEL='gpt-5.5'
CONDITIONS=('full','without_role_mapping','without_skeleton','without_both')
FEATURES=('shell_tool','code_mode_host','browser_use','computer_use','in_app_browser','apps','plugins','multi_agent','goals','memories','workspace_dependencies','hooks','skill_search','auth_elicitation','image_generation','tool_suggest')
COMMON='''For each supplied Chinese requirement, decide whether it fits a deliberately narrow nonnumerical UAV STL fragment: an upper-bound invariant of one recorded scalar signal, or a triggered response that recovers below a bound within a deadline. Detection after a sustained exceedance is not a bounded recovery requirement. Reject requirements needing other quantities, actions, lower-bound operators, or unsupported temporal patterns. Do not invent numerical values. Do not use tools or files. Use only the legal vocabulary below, identically supplied in every condition. Infer from the sentence whether and how a template applies; the vocabulary by itself does not assign a template to a sentence. For an out-of-scope record, signal_id, template_id, formula_structure and parameter_roles must be empty. Return one records array preserving every supplied anonymous ID exactly once.
Legal signal identifiers: speed_3d_mps, height_m, abs_roll_rad, abs_pitch_rad, ang_rate_norm_rps.
Legal template identifiers: invariant_upper, bounded_response.
Global legal role names: upper_bound, trigger_upper, recovery_upper, deadline_seconds.
Legal syntax tokens include G, F, [0,T], <=, >, ->, parentheses, SIGNAL, and the listed role names. Numerical parameter values and source labels are not requested.
Return fields id, scope (in_scope or out_of_scope), signal_id, template_id, parameter_roles, formula_structure, refusal_reason.'''
MAPPING='''Template-to-role relations: invariant_upper requires exactly [upper_bound]. bounded_response requires exactly [trigger_upper,recovery_upper,deadline_seconds].'''
SKELETON='''Template-to-skeleton relations: invariant_upper has G[0,T](SIGNAL <= upper_bound). bounded_response has G[0,T]((SIGNAL > trigger_upper) -> F[0,deadline_seconds](SIGNAL <= recovery_upper)). Replace SIGNAL with one legal signal identifier.'''

def now(): return datetime.now(timezone.utc).isoformat()
def sha(b): return hashlib.sha256(b).hexdigest()
def save(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def schema():
 props={k:{'type':'string'} for k in ('id','scope','signal_id','template_id','formula_structure','refusal_reason')}
 props['scope']['enum']=['in_scope','out_of_scope'];props['parameter_roles']={'type':'array','items':{'type':'string'}}
 return {'type':'object','properties':{'records':{'type':'array','items':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}}},'required':['records'],'additionalProperties':False}
def capabilities():
 args=['-c','web_search="disabled"','-c','mcp_servers={}']
 for f in FEATURES: args+=['--disable',f]
 return args
def infer(call_id,payload,model,output_schema):
 out=HERE/'calls'/call_id;out.mkdir(parents=True,exist_ok=True)
 request=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
 save(out/'request.json',payload)
 result={'call_id':call_id,'requested_model':model,'serving_model':'not_returned_by_cli','cli_version':'0.145.0','reasoning_effort':'low','temperature':'not_exposed','request_sha256':sha(request.encode()),'started_utc':now(),'model_process_invocations':1,'backend_request_count':'not_observable','status':'started'}
 save(out/'receipt.json',result)
 command=[shutil.which('codex.cmd') or shutil.which('codex'),'exec','--ephemeral','--ignore-rules','--ignore-user-config','--skip-git-repo-check','--sandbox','read-only','-m',model,'-c','model_reasoning_effort="low"',*capabilities(),'--output-schema',str(output_schema),'--json','-']
 started=time.perf_counter()
 try:
  with tempfile.TemporaryDirectory(prefix='v33_public_requirement_only_') as wd:
   result['workdir_policy']='fresh_empty_temporary_directory_outside_project';r=subprocess.run(command,input=request,text=True,encoding='utf-8',errors='replace',capture_output=True,cwd=wd,timeout=900)
  result['exit_code']=r.returncode
  (out/'stdout.jsonl').write_text(r.stdout,encoding='utf-8');(out/'stderr.log').write_text(r.stderr,encoding='utf-8')
  events=[]
  for line in r.stdout.splitlines():
   try: events.append(json.loads(line))
   except json.JSONDecodeError: pass
  tool_events=[e for e in events if e.get('item',{}).get('type') in ('command_execution','mcp_tool_call','web_search')]
  messages=[e['item']['text'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
  result['unexpected_tool_events']=len(tool_events)
  result['usage']=[e.get('usage',{}) for e in events if e.get('type')=='turn.completed']
  if r.returncode==0 and messages and not tool_events:
   parsed=json.loads(messages[-1]);save(out/'output.json',parsed);result['status']='completed'
   if not call_id.startswith('availability'):
    expected={r['id'] for r in payload['records']};actual=[r['id'] for r in parsed.get('records',[])]
    if len(actual)!=len(expected) or set(actual)!=expected: result['status']='invalid_id_coverage'
   for event in events:
    if event.get('model'): result['serving_model']=event['model']
  else: result['status']='model_or_transport_failed';result['failure_tail']=(r.stderr+'\n'+r.stdout)[-1600:]
 except Exception as e: result['status']='exception';result['exception_type']=type(e).__name__;result['error']=str(e)
 result['elapsed_seconds']=time.perf_counter()-started;result['finished_utc']=now();save(out/'receipt.json',result)
 print(call_id,result['status'],round(result['elapsed_seconds'],2),flush=True)
 return result
def prepare(model):
 if ROOT:
  with (ROOT/'specification/v2/data/independent_requirement_adjudicated_v2.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
  rng=random.Random(202610130);rng.shuffle(rows)
  mapping=[{'anonymous_id':f'Q{i+1:03d}','source_item_id':r['source_item_id']} for i,r in enumerate(rows)]
  items=[{'id':m['anonymous_id'],'text':r['normalized_requirement']} for m,r in zip(mapping,rows)]
 else:
  mapping=json.loads((HERE/'scoring_id_mapping.json').read_text(encoding='utf-8'));items=json.loads((HERE/'public_input_records.json').read_text(encoding='utf-8'))
 save(HERE/'anonymous_id_mapping_restricted.json',mapping);save(HERE/'public_input_records.json',items);save(HERE/'shared_output_schema.json',schema())
 protocol={'frozen_utc':now(),'model':model,'reasoning_effort':'low','conditions':CONDITIONS,'repetitions_per_condition':5,'planned_calls':20,'unique_items':19,'model_record_opportunities':380,'global_vocabulary_and_json_equal':True,'shared_task_definition_equal':True,'source_identifiers_removed':True,'fixed_item_order':True,'no_gold_or_sources_in_requests':True,'source_review_and_score_reference_separate':True,'schema_does_not_conditionally_map_templates_to_roles':True,'failure_denominator_policy':'all 20 invocations and all 380 item opportunities retained; failure=incorrect for unconditional accuracy, separately reported'}
 save(HERE/'language_protocol_frozen.json',protocol)
 jobs=[]
 for rep in range(1,6):
  for c in CONDITIONS:
   prompt=COMMON
   if c in ('full','without_skeleton'): prompt+='\n'+MAPPING
   if c in ('full','without_role_mapping'): prompt+='\n'+SKELETON
   payload={'instruction':prompt,'records':items}
   jobs.append((f'{c}_r{rep}',payload))
 return jobs
def main():
 global HERE
 ap=argparse.ArgumentParser();ap.add_argument('--model',default=MODEL);ap.add_argument('--mode',choices=['availability','run'],required=True);ap.add_argument('--output-dir',type=Path);a=ap.parse_args()
 if a.mode=='run':
  if a.output_dir is None:ap.error('New model inference is opt-in and requires a fresh --output-dir; frozen evidence is never overwritten.')
  source_dir=HERE;destination=a.output_dir.resolve();destination.mkdir(parents=True,exist_ok=False)
  for name in ['public_input_records.json','scoring_id_mapping.json']:
   source=source_dir/name
   if name=='scoring_id_mapping.json' and not source.exists():source=source_dir/'anonymous_id_mapping_restricted.json'
   if source.exists():shutil.copy2(source,destination/name)
  HERE=destination
 if a.mode=='availability':
  sp=HERE/'availability_schema.json';save(sp,{'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False})
  i=1
  while (HERE/'calls'/f'availability_{i:02d}').exists(): i+=1
  infer(f'availability_{i:02d}',{'instruction':'Return {"ok":true}. Do not use tools.'},a.model,sp)
 else:
  jobs=prepare(a.model)
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
   receipts=list(pool.map(lambda j:infer(j[0],j[1],a.model,HERE/'shared_output_schema.json'),jobs))
  save(HERE/'language_call_summary.json',{'planned':20,'attempted':len(receipts),'completed':sum(r['status']=='completed' for r in receipts),'calls':receipts})
if __name__=='__main__':main()
