"""Build figures, a source-review reference, and scores from retained evidence."""
from __future__ import annotations
import argparse,csv,hashlib,importlib.util,json,math,shutil
from pathlib import Path
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from numeric_text_guard import bind_if_text_consistent

HERE=Path(__file__).resolve().parent
# The release reads its supplied frozen inputs regardless of its parent folder.
ROOT=None
V33=None
OLD=None
INPUTS=HERE/'inputs'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'pdf.fonttype':42,'ps.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
MODULES=['topology_and_cardinality','exact_binding_identity','semantic_typing_and_policy','monitor_compatibility_and_profiles','provenance_context','formula_signal_alignment']
MODLABEL=['Topology / cardinality','Binding identity','Semantic typing / policy','Monitor / input profile','Provenance / context','Formula / signal alignment']
TYPES=['requirement_formula_link','template_implementation_link','role_completeness','binding_parameter_identity','signal_consistency','unit_compatibility','parameter_signal_scope','role_semantics','finite_numeric_value','monitor_compatibility','monitor_input_profiles','provenance_context','formula_signal_alignment']
TYPLABEL=['Requirement link','Template implementation','Required role','Parameter identity','Binding signal','Parameter unit','Parameter signal scope','Role policy','Finite value','Monitor compatibility','Input profile','Provenance / context','Formula signal']

def f1_score(truth,prediction,labels,average='macro',zero_division=0):
 assert average=='macro' and zero_division==0
 values=[]
 for label in labels:
  tp=sum(t==label and p==label for t,p in zip(truth,prediction));fp=sum(t!=label and p==label for t,p in zip(truth,prediction));fn=sum(t==label and p!=label for t,p in zip(truth,prediction))
  values.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.)
 return sum(values)/len(values)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name,obj):(HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def outcsv(name,rows):pd.DataFrame(rows).to_csv(HERE/name,index=False,encoding='utf-8')
def figure(fig,name):
 fig.savefig(HERE/f'{name}.pdf',bbox_inches='tight');fig.savefig(HERE/f'{name}.png',dpi=220,bbox_inches='tight');plt.close(fig)
 if V33 and (V33/'figures').is_dir():
  for ext in ['pdf','png']:shutil.copy2(HERE/f'{name}.{ext}',V33/'figures'/f'{name}.{ext}')

def graph_figures():
 d=pd.read_csv(INPUTS/'v4_graph_mutation_ablation_details.csv');assert len(d)==2832
 ratios=[];counts=[]
 for module in MODULES:
  x=d[(d.validator_variant=='without_'+module)&(d.mutation_module==module)]
  ratios.append(100*x.mutant_accepted.mean());counts.append((int(x.mutant_accepted.sum()),len(x)))
 variants=['full_validator']+['without_'+m for m in MODULES]+['schema_only_all_six_modules_removed']
 matrix=np.zeros((13,8));labels=np.empty((13,8),dtype=object)
 for i,t in enumerate(TYPES):
  for j,v in enumerate(variants):
   x=d[(d.mutation_type==t)&(d.validator_variant==v)];assert len(x)>0
   a=int(x.mutant_accepted.sum());matrix[i,j]=100*a/len(x);labels[i,j]=f'{a}/{len(x)}'
 fig=plt.figure(figsize=(7.1,8.1));ax=fig.add_axes([.35,.61,.62,.32]);hm=fig.add_axes([.35,.15,.62,.34])
 y=np.arange(6);ax.barh(y,ratios,color='#167b87',height=.62);ax.set_yticks(y,MODLABEL);ax.invert_yaxis();ax.set_xlim(0,121);ax.set_xticks([0,25,50,75,100]);ax.set_xlabel('Targeted mutant escape rate (%)')
 for i,(a,n) in enumerate(counts):ax.text(ratios[i]+1.5,i,f'{a}/{n}',va='center',fontsize=10)
 ax.axvline(0,color='#a84c37',lw=2);ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True);ax.set_title('(a) Removing one safeguard',loc='left',pad=12)
 im=hm.imshow(matrix,vmin=0,vmax=100,cmap='YlOrRd',aspect='auto');hm.set_yticks(np.arange(13),TYPLABEL);hm.tick_params(axis='y',length=0,labelsize=9.4)
 hm.set_xticks(np.arange(8),['Full','–C1','–C2','–C3','–C4','–C5','–C6','None'],rotation=45,ha='right');hm.set_title('(b) Mutation types and validator variants',loc='left',pad=12,fontsize=11)
 for i in range(13):
  for j in range(8):hm.text(j,i,labels[i,j],ha='center',va='center',fontsize=8.8,color='white' if matrix[i,j]>60 else '#26333c')
 cbax=fig.add_axes([.35,.04,.62,.018]);fig.colorbar(im,cax=cbax,orientation='horizontal',label='Escape rate within each mutation type (%)')
 figure(fig,'v33_structural_ablation')
 outcsv('structural_module_rates.csv',[{'module':m,'accepted_targeted_mutants':a,'targeted_mutants':n,'escape_rate':a/n} for m,(a,n) in zip(MODULES,counts)])
 outcsv('structural_mutation_heatmap.csv',[{'mutation_type':t,'validator_variant':v,'escape_rate':matrix[i,j]/100,'accepted_over_targeted':labels[i,j]} for i,t in enumerate(TYPES) for j,v in enumerate(variants)])
 a=pd.read_csv(INPUTS/'v4_binding_ambiguity_ablation.csv');assert len(a)==24
 fig,ax=plt.subplots(figsize=(7.1,4.2));x=np.arange(24);coarse=a.without_parameter_binding_candidate_configurations
 ax.vlines(x,1,coarse,color='#b8c6cc',lw=1.2);ax.scatter(x,np.ones(24),color='#167b87',marker='s',s=28,label='Explicit bindings');ax.scatter(x,coarse,color='#a84c37',s=35,label='Coarse adjacency')
 ax.set_yscale('log');ax.set_yticks([1,2,8,12,80],['1','2','8','12','80']);ax.set_xticks(x,a.formula_id,rotation=60);ax.set_ylabel('Candidate assignments per formula (log scale)');ax.grid(axis='y',alpha=.2);ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),frameon=False,ncols=2);ax.set_title('Coarse-adjacency stress test: 24 internal formula records',loc='left',y=1.17)
 fig.tight_layout();figure(fig,'v33_binding_ambiguity')
 for name in ['v4_graph_mutation_ablation_details.csv','v4_graph_mutation_ablation_summary.csv','v4_graph_mutation_ablation_by_type.csv','v4_binding_ambiguity_ablation.csv']:
  if OLD and (OLD/'results'/name).exists():shutil.copy2(OLD/'results'/name,HERE/name)

def source_review():
 old=pd.read_csv(ROOT/'specification/v2/data/independent_requirement_adjudicated_v2.csv').fillna('')
 reg=pd.read_csv(ROOT/'specification/v2/data/independent_requirement_source_registry_v2.csv').fillna('').set_index('source_item_id')
 paths={'ARDUPILOT_COPTER_DOCS':'ArduPilot_Copter_Fences_20260810.html','ARDUPILOT_BATTERY_FAILSAFE':'ArduPilot_Copter_Battery_Failsafe_20260810.html','ECFR_14_CFR_107_51':'eCFR_14_CFR_107_51_20260810.html','ICAROUS_MONITORING_2020':'Dutle2020_Monitoring_ICAROUS.pdf','PX4_SAFETY_V116':'PX4_Safety_v1_16_20260810.html','UK_CAA_DRONE_CODE':'UK_CAA_Drone_Code_20260810.html'}
 changes={
 'PX4_FAILURE_PITCH_01':('out_of_scope','Sustained pitch exceedance triggers detection; the source defines no recovery target or recovery deadline.'),
 'PX4_FAILURE_ROLL_01':('out_of_scope','Sustained roll exceedance triggers detection; the source defines no recovery target or recovery deadline.'),
 'ECFR_107_SPEED_01':('out_of_scope','The requirement concerns groundspeed; the only speed identifier is three-dimensional speed, which is not an equivalent observable.')}
 explanations={
 'ARDUPILOT_ALTITUDE_REF_01':'An explanatory definition of altitude reference frames, not an operational upper bound.',
 'ARDUPILOT_FENCE_ALT_MAX_01':'A configured maximum-altitude boundary is an upper-bound structure; enabled state, breach action, and chosen altitude frame remain external preconditions.',
 'ARDUPILOT_FENCE_ALT_MIN_01':'A minimum-altitude boundary requires a lower-bound pattern outside the evaluated fragment.',
 'ARDUPILOT_GCS_TIMEOUT_01':'Heartbeat-loss timeout and failsafe action require link state and action observables outside the five-signal fragment.',
 'ARDUPILOT_BATT_ACTION_01':'Secondary battery failsafe actions require action and battery-state observables outside the fragment.',
 'ARDUPILOT_BATT_CAPACITY_01':'Battery-capacity condition and failsafe action are outside the available scalar catalog.',
 'ARDUPILOT_BATT_VOLT_01':'Battery-voltage persistence and detection/action are not a supported recovery obligation.',
 'ECFR_107_ALT_01':'The curated sentence has an upper-bound structure, but omits the regulation\'s structure exception; AGL is not verified equivalent to replayed relative height.',
 'ECFR_107_VISUAL_01':'Visual line of sight is outside the scalar fragment; the historical locator wrongly pointed to visibility §107.51(c), corrected here to §107.31.',
 'ECFR_107_YIELD_01':'Right-of-way is outside the scalar fragment; the historical locator wrongly pointed to cloud separation §107.51(d), corrected here to §107.37.',
 'ICAROUS_ALT_01':'The paper describes an altitude ceiling as an example of parametric requirements, not an experimentally calibrated ceiling; an upper-bound skeleton is expressible.',
 'ICAROUS_SEPARATION_01':'The cited requirement involves horizontal/vertical intruder distances and flight mode, outside the scalar catalog.',
 'PX4_GEOFENCE_ALT_01':'Geofence cylinder height supplies a maximum-height structure; actual reference frame, enabled status and failsafe action are not established for replay.',
 'PX4_LINK_LOSS_01':'Data-link-loss timeout and failsafe action are outside the signal and temporal fragment.',
 'UKCAA_HEIGHT_01':'The closest-earth-surface height limit has an upper-bound shape; it is not verified equivalent to relative vertical height.',
 'UKCAA_PEOPLE_01':'Horizontal distance from people and applicability exceptions require unsupported observables.'}
 ledger=[];reference=[]
 for _,row in old.iterrows():
  r=reg.loc[row.source_item_id];file=paths[row.source_family_id]
  if row.source_item_id=='ARDUPILOT_ALTITUDE_REF_01':file='ArduPilot_Copter_Altitude_20260810.html'
  if row.source_item_id=='ARDUPILOT_GCS_TIMEOUT_01':file='ArduPilot_Copter_GCS_Failsafe_20260810.html'
  sp=ROOT/'materials/papers/v2_external_sources'/file;assert sp.exists()
  scope,why=changes.get(row.source_item_id,(row.adjudicated_scope,explanations.get(row.source_item_id,'')))
  locator=r.locator;url=r.url
  if row.source_item_id=='ECFR_107_VISUAL_01':locator='14 CFR §107.31';url=url.rsplit('/',1)[0]+'/section-107.31'
  if row.source_item_id=='ECFR_107_YIELD_01':locator='14 CFR §107.37';url='https://www.govinfo.gov/link/cfr/14/107?link-type=pdf&year=mostrecent'
  if row.source_item_id=='ICAROUS_ALT_01':locator='PDF page 5, Section 4, altitude-ceiling example'
  if row.source_item_id=='ICAROUS_SEPARATION_01':locator='PDF pages 2–4, Requirement 1 and distance example'
  height=scope=='in_scope' and row.reference_signal_id=='height_m'
  ledger.append({'source_item_id':row.source_item_id,'original_source_family':row.source_family_id,'source_statement_summary':r.source_requirement_summary,'curated_chinese_input':row.normalized_requirement,'historical_scope':row.adjudicated_scope,'source_reviewed_text_scope':scope,'scope_changed':scope!=row.adjudicated_scope,'original_locator':r.locator,'reviewed_locator':locator,'original_url':r.url,'reviewed_url':url,'frozen_source_snapshot':str(sp.relative_to(ROOT)),'source_sha256':sha(sp),'review_reason':why,'candidate_signal_applicability':'abstract height structure; coordinate adapter unresolved' if height else 'unsupported' if scope=='out_of_scope' else 'supported_structure','executable_source_binding_verified':False,'reviewer_type':'AI source review, not newly authenticated independent human gold'})
  reference.append({'source_item_id':row.source_item_id,'source_family_id':row.source_family_id,'normalized_requirement':row.normalized_requirement,'adjudicated_scope':scope,'reference_signal_id':row.reference_signal_id if scope=='in_scope' else 'none','reference_template_id':row.reference_template_id if scope=='in_scope' else 'none','reference_version':'v33_source_reviewed_text_fragment','independent_human_authentication':'not_established_by_this_computational_review','coordinate_compatibility': 'unresolved' if height else 'not_applicable'})
 outcsv('source_review_19.csv',ledger);outcsv('reference_19_v33_source_reviewed.csv',reference)
 save('source_review_receipt.json',{'input_items':19,'reviewed_items':19,'old_in_scope':8,'new_text_in_scope':5,'scope_changes':list(changes),'coordinate_unresolved_height_items':5,'historical_labels_unchanged':True,'review_kind':'AI source review with retained submitted annotation tables only; original recovery records and independent human workflow are unverified','pointer_corrections':['ECFR_107_VISUAL_01','ECFR_107_YIELD_01','ICAROUS_ALT_01','ICAROUS_SEPARATION_01'],'official_pointer_verification':['https://www.ecfr.gov/current/title-14/chapter-I/subchapter-F/part-107/subpart-B/section-107.31','https://www.govinfo.gov/link/cfr/14/107?link-type=pdf&year=mostrecent']})
 return pd.DataFrame(reference).set_index('source_item_id')

def load_scorer():
 import ablation_scoring
 return ablation_scoring

def metrics(rows):
 y=[r['reference_scope'] for r in rows];pred=[r['predicted_scope'] for r in rows];n=len(rows)
 ins=[r for r in rows if r['reference_scope']=='in_scope'];outs=[r for r in rows if r['reference_scope']=='out_of_scope']
 return {'item_opportunities':n,'reference_in_scope_count':len(ins),'reference_out_of_scope_count':len(outs),'scope_macro_f1':float(f1_score(y,pred,labels=['in_scope','out_of_scope'],average='macro',zero_division=0)),'scope_accuracy':sum(a==b for a,b in zip(y,pred))/n,'tuple_exact':sum(r['tuple_correct'] for r in rows)/n,'formula_structure_exact':sum(r['formula_correct'] for r in rows)/n,'signal_accuracy_in_scope':sum(r['signal_correct'] for r in ins)/len(ins) if ins else 0,'template_accuracy_in_scope':sum(r['template_correct'] for r in ins)/len(ins) if ins else 0,'role_exact_in_scope':sum(r['role_correct'] for r in ins)/len(ins) if ins else 0,'correct_rejection_rate':sum(r['predicted_scope']=='out_of_scope' for r in outs)/len(outs) if outs else 0,'raw_false_acceptance_count':sum(r['predicted_scope']=='in_scope' for r in outs),'graph_admitted_count':sum(r['graph_accepted'] for r in rows),'graph_admitted_false_count':sum(r['graph_accepted'] for r in outs),'failed_item_count':sum(r.get('failed_call',False) for r in rows)}

def score_row(m,sid,pred,ref,configuration,repetition=0,failed=False):
 r=ref.loc[sid];scope=pred.get('scope','parse_error');signal=pred.get('signal_id','') if scope=='in_scope' else '';template=pred.get('template_id','') if scope=='in_scope' else '';roles=m.normalize_roles(pred.get('parameter_roles',[])) if scope=='in_scope' else ();form=pred.get('formula_structure','')
 goldscope=r.adjudicated_scope;goldsig=r.reference_signal_id if goldscope=='in_scope' else '';goldtemplate=r.reference_template_id if goldscope=='in_scope' else '';goldroles=tuple(sorted(m.TEMPLATE_ROLES.get(goldtemplate,())))
 catalog=pd.read_csv(INPUTS/'v4_complete_formula_catalog.csv');admissible=set(zip(catalog.signal_id,catalog.template_id))
 admitted,reason=m.graph_validate(signal,template,roles,form,admissible) if scope=='in_scope' else (False,'model_refusal' if not failed else 'call_failed')
 goldformula=m.normalize_formula_serialization(m.canonical_formula(goldscope,goldsig,goldtemplate)) if goldscope=='in_scope' else 'OUT_OF_SCOPE'
 return {'source_item_id':sid,'condition':configuration,'repetition':repetition,'reference_scope':goldscope,'predicted_scope':scope,'signal_id':signal,'template_id':template,'roles':';'.join(roles),'formula_structure':form,'tuple_correct':scope==goldscope and signal==goldsig and template==goldtemplate,'formula_correct':m.provided_formula_key(scope,form)==goldformula,'signal_correct':signal==goldsig,'template_correct':template==goldtemplate,'role_correct':roles==goldroles,'graph_accepted':bool(admitted),'graph_reason':reason,'failed_call':failed}

def historical_scores(m,ref):
 frozen=pd.read_csv(INPUTS/'historical_language_predictions.csv').fillna('');allrows=[];metric=[]
 for condition,x in frozen.groupby('configuration'):
  rows=[]
  for _,p in x.iterrows():
   roles=[s.strip(" '()") for s in str(p.raw_roles).split(',') if s.strip(" '()")]
   pred={'scope':p.raw_scope,'signal_id':p.raw_signal_id,'template_id':p.raw_template_id,'parameter_roles':roles,'formula_structure':p.raw_formula_text}
   rows.append(score_row(m,p.source_item_id,pred,ref,'historical_'+condition))
  metric.append({'method':'historical_'+condition,'reference_version':'v33_source_reviewed',**metrics(rows)});allrows+=rows
  gated=[]
  for row in rows:
   pred={'scope':'in_scope' if row['graph_accepted'] else 'out_of_scope','signal_id':row['signal_id'] if row['graph_accepted'] else '','template_id':row['template_id'] if row['graph_accepted'] else '','parameter_roles':row['roles'].split(';') if row['graph_accepted'] else [],'formula_structure':row['formula_structure'] if row['graph_accepted'] else ''}
   gated.append(score_row(m,row['source_item_id'],pred,ref,row['condition']+'_plus_gate'))
  metric.append({'method':'historical_'+condition+'_plus_gate','reference_version':'v33_source_reviewed',**metrics(gated)});allrows+=gated
 baseline=pd.read_csv(INPUTS/'historical_baseline_predictions.csv').fillna('')
 for method,x in baseline.groupby('method'):
  rows=[]
  for _,p in x.iterrows():
   scope=p.predicted_scope;signal=p.predicted_signal_id if scope=='in_scope' else '';template=p.predicted_template_id if scope=='in_scope' else ''
   pred={'scope':scope,'signal_id':signal,'template_id':template,'parameter_roles':list(m.TEMPLATE_ROLES.get(template,())),'formula_structure':m.canonical_formula(scope,signal,template) if scope=='in_scope' else ''}
   rows.append(score_row(m,p.source_item_id,pred,ref,'historical_'+method))
  metric.append({'method':'historical_'+method,'reference_version':'v33_source_reviewed',**metrics(rows)});allrows+=rows
 outcsv('historical_methods_on_v33_reference.csv',metric);outcsv('historical_predictions_on_v33_reference.csv',allrows)
 shutil.copy2(INPUTS/'historical_metrics_original_reference.csv',HERE/'historical_metrics_original_reference.csv')
 return metric

def language_scores(m,ref):
 mappingpath=HERE/'anonymous_id_mapping_restricted.json' if (HERE/'anonymous_id_mapping_restricted.json').exists() else HERE/'scoring_id_mapping.json'
 mapping={r['anonymous_id']:r['source_item_id'] for r in json.loads(mappingpath.read_text(encoding='utf-8'))}
 allrows=[];results=[]
 conditions=['full','without_role_mapping','without_skeleton','without_both']
 for c in conditions:
  for rep in range(1,6):
   cd=HERE/'calls'/f'{c}_r{rep}'
   if (cd/'receipt.json').exists():
    receipt=json.loads((cd/'receipt.json').read_text(encoding='utf-8'));ok=receipt['status']=='completed';out=json.loads((cd/'output.json').read_text(encoding='utf-8')) if ok else {'records':[]}
   else:
    public=json.loads((HERE/'public_calls'/f'{c}_r{rep}.json').read_text(encoding='utf-8'));receipt=public['receipt'];ok=receipt['status']=='completed';out=public['output'] if ok else {'records':[]}
   index={p['id']:p for p in out['records']}
   rows=[score_row(m,sid,index.get(a,{}),ref,c,rep,not ok) for a,sid in mapping.items()]
   allrows+=rows;results.append({'condition':c,'repetition':rep,'call_status':receipt['status'],'elapsed_seconds':receipt['elapsed_seconds'],**metrics(rows)})
 outcsv('fair_language_predictions_v33_reference.csv',allrows);outcsv('fair_language_run_metrics.csv',results)
 aggregate=[]
 for c in conditions:
  rr=[r for r in allrows if r['condition']==c];run=[r for r in results if r['condition']==c]
  aggregate.append({'condition':c,'independent_contexts':5,'unique_items':19,'item_opportunities':95,'completed_calls':sum(r['call_status']=='completed' for r in run),'scope_macro_f1_mean':np.mean([r['scope_macro_f1'] for r in run]),'tuple_exact_mean':np.mean([r['tuple_exact'] for r in run]),'formula_exact_mean':np.mean([r['formula_structure_exact'] for r in run]),'raw_false_acceptance_count':sum(r['raw_false_acceptance_count'] for r in run),'graph_admitted_false_count':sum(r['graph_admitted_false_count'] for r in run),'graph_admitted_count':sum(r['graph_admitted_count'] for r in run),'failed_item_count':sum(r['failed_item_count'] for r in run)})
 outcsv('fair_language_condition_summary.csv',aggregate);d=pd.DataFrame(results)
 fig=plt.figure(figsize=(7.1,7.1));gs=fig.add_gridspec(2,2);a=fig.add_subplot(gs[0,:]);b=fig.add_subplot(gs[1,0]);coverage=fig.add_subplot(gs[1,1]);labels=['Full','–role\nmap','–skeleton','–both'];x=np.arange(4)
 for k,marker,col,offset,title in [('scope_macro_f1','o','#167b87',-.11,'Scope macro F1'),('tuple_exact','s','#a84c37',.11,'Tuple exact')]:
  means=[d[d.condition==c][k].mean() for c in conditions];a.plot(x+offset,means,marker=marker,label=title,color=col,ls='none',ms=7)
  for i,c in enumerate(conditions):a.scatter(i+offset+np.linspace(-.035,.035,5),d[d.condition==c][k],marker=marker,color=col,s=12,alpha=.6)
 a.set_xticks(x,labels);a.set_ylim(0,1.04);a.set_yticks(np.arange(0,1.1,.2));a.set_ylabel('Score on source-reviewed reference');a.set_title('(a) Five isolated contexts per condition',loc='left',fontsize=11);a.legend(frameon=False,fontsize=10,loc='lower left');a.grid(axis='y',alpha=.2)
 raw=[r['raw_false_acceptance_count'] for r in aggregate];gated=[r['graph_admitted_false_count'] for r in aggregate]
 b.bar(x-.15,raw,width=.3,color='#a84c37',label='Raw scope errors');b.bar(x+.15,gated,width=.3,color='#167b87',label='Errors admitted by gate');b.set_xticks(x,labels,rotation=30,ha='right');b.set_ylabel('False acceptances\n(70 negative opportunities)');b.set_ylim(0,max(raw+gated+[1])+2);b.set_title('(b) Semantic false acceptances',loc='left',fontsize=10.5);b.legend(frameon=False,fontsize=9);b.grid(axis='y',alpha=.2);b.set_axisbelow(True)
 for i,(r,g) in enumerate(zip(raw,gated)):b.text(i-.15,r+.08,str(r),ha='center',fontsize=9);b.text(i+.15,g+.08,str(g),ha='center',fontsize=9)
 correct=[r['graph_admitted_count']-r['graph_admitted_false_count'] for r in aggregate]
 coverage.bar(x,correct,color='#167b87',width=.55);coverage.set_xticks(x,labels,rotation=30,ha='right');coverage.set_ylim(0,28);coverage.set_ylabel('Admitted positive descriptors\n(25 positive opportunities)');coverage.set_title('(c) Positive gate coverage',loc='left',fontsize=10.5);coverage.grid(axis='y',alpha=.2);coverage.set_axisbelow(True)
 for i,n in enumerate(correct):coverage.text(i,n+.4,f'{n}/25',ha='center',fontsize=9)
 fig.subplots_adjust(left=.14,right=.97,bottom=.13,top=.95,hspace=.5,wspace=.55);figure(fig,'v33_fair_language_ablation')
 save('fair_language_scientific_receipt.json',{'planned_calls':20,'completed_calls':sum(r['call_status']=='completed' for r in results),'unique_items':19,'record_opportunities':380,'source_reviewed_in_scope_per_run':5,'source_reviewed_out_of_scope_per_run':14,'positive_templates':{'invariant_upper':5,'bounded_response':0},'model':'gpt-5.5 requested','serving_snapshot':'not returned by CLI','reasoning_effort':'low','output_schema_same_sha256':sha(HERE/'shared_output_schema.json'),'limits':['Repeated contexts do not create new independent source items.','No positive bounded-response item remains after correcting source semantics; response-role/skeleton effectiveness is not measured.','The task definition is more explicit than the historical experiment; new and historical scores do not isolate a model change.','Role names also occur in supplied skeletons, so removing the explicit role map leaves recoverable redundant information.','Five height positives concern abstract text structure; executable coordinate compatibility remains unresolved.'],'conditions':aggregate})
 return aggregate

def semantic_challenge(m,ref):
 rows=[]
 for sid,r in ref.iterrows():
  scope=r.adjudicated_scope
  if scope=='in_scope':
   for typ,signal,template,correct in [('matched_positive','height_m','invariant_upper',True),('wrong_signal_consistent','speed_3d_mps','invariant_upper',False),('wrong_signal_and_template_consistent','speed_3d_mps','bounded_response',False)]:
    p={'scope':'in_scope','signal_id':signal,'template_id':template,'parameter_roles':list(m.TEMPLATE_ROLES[template]),'formula_structure':m.canonical_formula('in_scope',signal,template)}
    x=score_row(m,sid,p,ref,typ);x['challenge_kind']=typ;x['semantic_match_by_construction']=correct;rows.append(x)
  else:
   p={'scope':'in_scope','signal_id':'speed_3d_mps','template_id':'invariant_upper','parameter_roles':['upper_bound'],'formula_structure':m.canonical_formula('in_scope','speed_3d_mps','invariant_upper')}
   x=score_row(m,sid,p,ref,'unsupported_to_legal_candidate');x['challenge_kind']='unsupported_to_legal_candidate';x['semantic_match_by_construction']=False;rows.append(x)
 outcsv('legal_catalog_semantic_challenge.csv',rows)
 good=[r for r in rows if r['semantic_match_by_construction']];bad=[r for r in rows if not r['semantic_match_by_construction']]
 save('legal_catalog_semantic_challenge_receipt.json',{'constructed_candidates':len(rows),'unique_source_texts':19,'positive_controls':len(good),'invalid_semantic_candidates':len(bad),'positive_controls_admitted':sum(r['graph_accepted'] for r in good),'semantically_invalid_admitted':sum(r['graph_accepted'] for r in bad),'gate_has_no_reference_label_input':True,'interpretation':'A well-formed catalog-consistent descriptor is not a semantic certificate. These manually constructed adversarial candidates are not model-generated independent samples.'})

def numeric_checks():
 catalog=pd.read_csv(INPUTS/'v4_complete_formula_catalog.csv').fillna('');rows=[]
 for _,r in catalog.iterrows():
  x=bind_if_text_consistent(r.source_requirement_text_zh,json.loads(r.parameter_bindings_json));rows.append({'formula_id':r.formula_id,'accepted':x['check']['accepted'],'reason':x['check']['reason'],'unchanged_values':x['bound_values']=={b['role']:b['value'] for b in json.loads(r.parameter_bindings_json)}})
 outcsv('numeric_guard_original_24.csv',rows);save('numeric_guard_receipt.json',{'original_catalog_rows':24,'original_rows_admitted':sum(r['accepted'] for r in rows),'original_bound_value_maps_unchanged':all(r['unchanged_values'] for r in rows),'catalog_sha256':sha(INPUTS/'v4_complete_formula_catalog.csv'),'grammar':'Explicit scalar quantities assigned by declared role cues; unit conversion only among supported equivalent dimensions; approximations/ranges/unknown units/role ambiguity refused.','physical_calibration_claimed':False})

def copy_research():
 if not V33:return
 dst=V33/'research'/'ablation';dst.mkdir(parents=True,exist_ok=True)
 if dst.resolve()==HERE.resolve():return
 for p in HERE.iterdir():
  if p.is_file() and p.suffix in ('.py','.csv','.json','.pdf','.png','.tex','.md','.txt') and p.name!='anonymous_id_mapping_restricted.json':shutil.copy2(p,dst/p.name)
 public=dst/'public_calls';public.mkdir(exist_ok=True)
 for c in (HERE/'calls').iterdir():
  if not c.is_dir():continue
  receipt=json.loads((c/'receipt.json').read_text(encoding='utf-8'))
  sanitized={k:v for k,v in receipt.items() if k not in ('failure_tail','error')}
  save_obj={'receipt':sanitized,'request':json.loads((c/'request.json').read_text(encoding='utf-8')),'output':json.loads((c/'output.json').read_text(encoding='utf-8')) if (c/'output.json').exists() else None}
  (public/f'{c.name}.json').write_text(json.dumps(save_obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 # Mapping contains only public source IDs, supplied after inference for reproducible scoring.
 shutil.copy2(HERE/'anonymous_id_mapping_restricted.json',dst/'scoring_id_mapping.json')
 shutil.copytree(INPUTS,dst/'inputs',dirs_exist_ok=True)

def bootstrap_inputs():
 if not ROOT:raise RuntimeError('Project bootstrap requires the original private workspace')
 INPUTS.mkdir(parents=True,exist_ok=True)
 for name in ['v4_graph_mutation_ablation_details.csv','v4_graph_mutation_ablation_summary.csv','v4_graph_mutation_ablation_by_type.csv','v4_binding_ambiguity_ablation.csv','v4_complete_formula_catalog.csv']:
  shutil.copy2(OLD/'results'/name,INPUTS/name)
 frozen=pd.read_csv(OLD/'results/v5_llm/formula_19_predictions_and_stkg_decisions.csv').fillna('')
 frozen[['source_item_id','configuration','raw_scope','raw_signal_id','raw_template_id','raw_roles','raw_formula_text']].to_csv(INPUTS/'historical_language_predictions.csv',index=False)
 baseline=pd.read_csv(ROOT/'specification/v2/results/independent_corpus/baseline_details.csv').fillna('')
 baseline[['source_item_id','method','predicted_scope','predicted_signal_id','predicted_template_id']].to_csv(INPUTS/'historical_baseline_predictions.csv',index=False)
 shutil.copy2(OLD/'results/v5_llm/formula_19_metrics_and_ablation.csv',INPUTS/'historical_metrics_original_reference.csv')
 source_review()

def main():
 global V33
 ap=argparse.ArgumentParser();ap.add_argument('--bootstrap-project',action='store_true');ap.add_argument('--sync-manuscript',action='store_true');a=ap.parse_args()
 if not a.sync_manuscript:V33=None
 if a.bootstrap_project:bootstrap_inputs()
 ref=pd.read_csv(HERE/'reference_19_v33_source_reviewed.csv').fillna('').set_index('source_item_id')
 graph_figures();m=load_scorer();historic=historical_scores(m,ref);new=language_scores(m,ref);semantic_challenge(m,ref);numeric_checks()
 save('ablation_artifacts_receipt.json',{'saved_inputs_sha256':{str(p.relative_to(HERE)):sha(p) for p in INPUTS.iterdir() if p.is_file()},'historical_methods_rescored':len(historic),'new_conditions':new,'plots':['v33_structural_ablation','v33_fair_language_ablation','v33_binding_ambiguity'],'default_mode':'offline_saved_output_recomputation_without_model_calls','no_old_source_or_results_changed':True});copy_research();print(json.dumps(new,ensure_ascii=False))
if __name__=='__main__':main()
