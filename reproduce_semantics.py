"""Reproduce bounded exact comparisons and explicitly expected counterexamples."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    if output==ROOT or any(output.is_relative_to(ROOT/d) for d in ('data','src','research')):parser.error('output must not overwrite inputs or sources')
    if output.exists():parser.error('output must be a new directory')
    output.mkdir(parents=True)
    script=ROOT/'research/semantics/verify_semantics.py'
    result=subprocess.run([sys.executable,'-B','-X','utf8',str(script),'--output',str(output/'checks.json')],capture_output=True,text=True,encoding='utf-8',cwd=ROOT)
    (output/'stdout.log').write_text(result.stdout,encoding='utf-8');(output/'stderr.log').write_text(result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError('Independent checks failed; see retained logs')
    checks=json.loads((output/'checks.json').read_text(encoding='utf-8'))
    assert checks['status']=='passed_with_explicit_characterized_float_counterexamples'
    assert checks['boundary_case_count']==19 and checks['non_equivalence_case_count']==3 and checks['float_counterexample_count']==2
    assert checks['exhaustive']['unique_case_count']==5760 and checks['exhaustive']['candidate_plus_v2_comparisons']==11520 and checks['exhaustive']['mismatch_count']==0
    receipt={'status':'passed','independent_checks_status':checks['status'],'boundary_cases':19,'nominal_STL_non_equivalence_examples':3,'characterized_float_disagreements':2,'dyadic_exact_cases':5760,'candidate_and_frozen_v2_comparisons':11520,'unexpected_dyadic_mismatches':0,'checks_sha256':hashlib.sha256((output/'checks.json').read_bytes()).hexdigest(),'interpretation':'Expected floating-point limitations reproduced and retained. Correctness proof assumes exact arithmetic or comparison fidelity. Finite checks do not replace the proof.','model_calls':0,'training_runs':0}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
