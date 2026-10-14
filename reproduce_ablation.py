"""Offline reproduction of the v33 ablation figures and saved language outputs.

No inference, account credential, network request, or training is performed.
"""
from __future__ import annotations
import argparse,hashlib,json,shutil,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'research'/'ablation'
EXPECTED=('fair_language_predictions_v33_reference.csv','fair_language_run_metrics.csv','fair_language_condition_summary.csv','historical_methods_on_v33_reference.csv','legal_catalog_semantic_challenge.csv','numeric_guard_original_24.csv','structural_module_rates.csv','structural_mutation_heatmap.csv')

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'outputs/ablation_reproduction');args=parser.parse_args();output=args.output.resolve()
 if output==ROOT or any(output.is_relative_to(ROOT/d) for d in ('data','src','research')):parser.error('Output must not overwrite release source or evidence.')
 before={str(p.relative_to(SOURCE)):digest(p) for p in SOURCE.rglob('*') if p.is_file()}
 with tempfile.TemporaryDirectory(prefix='uav_stkg_offline_ablation_') as temporary:
  run=Path(temporary)/'ablation';shutil.copytree(SOURCE,run)
  plotted=subprocess.run([sys.executable,'-B','build_ablation_artifacts.py'],cwd=run,capture_output=True,text=True,encoding='utf-8')
  if plotted.returncode:
   sys.stderr.write(plotted.stderr);raise SystemExit(plotted.returncode)
  tested=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','.','-p','test_numeric_text_guard.py','-v'],cwd=run,capture_output=True,text=True,encoding='utf-8')
  if tested.returncode:
   sys.stderr.write(tested.stderr);raise SystemExit(tested.returncode)
  equality={name:(run/name).read_bytes()==(SOURCE/name).read_bytes() for name in EXPECTED}
  if not all(equality.values()):raise AssertionError('Saved CSV reproduction disagrees: '+str(equality))
  for name in ('v33_structural_ablation','v33_fair_language_ablation','v33_binding_ambiguity'):
   assert (run/(name+'.pdf')).stat().st_size>1000
  output.mkdir(parents=True,exist_ok=True)
  for p in run.iterdir():
   if p.is_file() and p.suffix in ('.csv','.json','.pdf','.png'):shutil.copy2(p,output/p.name)
  scientific=json.loads((run/'fair_language_scientific_receipt.json').read_text(encoding='utf-8'))
  challenge=json.loads((run/'legal_catalog_semantic_challenge_receipt.json').read_text(encoding='utf-8'))
  guard=json.loads((run/'numeric_guard_receipt.json').read_text(encoding='utf-8'))
 after={str(p.relative_to(SOURCE)):digest(p) for p in SOURCE.rglob('*') if p.is_file()};assert before==after
 receipt={'status':'passed','model_calls':0,'network_requests':0,'training_runs':0,'source_evidence_unchanged':True,'saved_csv_byte_equal':equality,'language_unique_items':19,'language_calls_retained':20,'language_item_opportunities':380,'completed_original_inferences':scientific['completed_calls'],'constructed_semantic_challenges':challenge,'original_catalog_numeric_guard':guard,'numeric_guard_tests':{'test_count':7,'exit_code':tested.returncode},'input_sha256':before,'figures_regenerated':3}
 (output/'reproduction_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (output/'numeric_guard_tests.log').write_text(tested.stderr,encoding='utf-8')
 print(json.dumps({k:receipt[k] for k in ('status','model_calls','language_unique_items','language_calls_retained','language_item_opportunities','source_evidence_unchanged','figures_regenerated')},indent=2))
if __name__=='__main__':main()
