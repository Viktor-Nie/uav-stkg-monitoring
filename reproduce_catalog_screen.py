"""Check finite screening on 24 internal records and six targeted refusals."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'research/historical_audits'))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    if out==ROOT or any(out.is_relative_to(ROOT/d) for d in ('data','src','research')):p.error('output must not overwrite source inputs')
    if out.exists():p.error('output must be a new directory')
    out.mkdir(parents=True)
    import pandas as pd
    from uav_stkg.graph_constraints import properties,single_target
    from controlled_screen import controlled_conversion_audit,controlled_screen_negative_probe_audit
    nodes=pd.read_csv(ROOT/'data/graph/nodes.csv');edges=pd.read_csv(ROOT/'data/graph/relationships.csv');props=properties(nodes)
    catalog=[]
    for node in sorted(k for k in props if k.startswith('formula:')):
        catalog.append({'formula_id':node.removeprefix('formula:'),'signal_id':single_target(edges,node,'READS_SIGNAL').removeprefix('signal:'),'template_id':single_target(edges,node,'USES_TEMPLATE').removeprefix('template:'),'stored_parameterized_formula':props[node]['parameterized_formula']})
    pairs=pd.read_csv(ROOT/'data/graph/internal_requirement_pairs.csv')
    audit=controlled_conversion_audit(pairs,pd.DataFrame(catalog));ref=ROOT/'research/historical_audits'
    expected=pd.read_csv(ref/'v4_controlled_conversion_audit.csv').fillna('')
    assert len(audit)==24 and audit.fillna('').to_dict('records')==expected.to_dict('records')
    probes=controlled_screen_negative_probe_audit()
    assert len(probes)==6 and probes.fillna('').to_dict('records')==pd.read_csv(ref/'v4_controlled_screen_refusal_probes.csv').fillna('').to_dict('records')
    audit.to_csv(out/'controlled_conversion_audit.csv',index=False);probes.to_csv(out/'controlled_screen_refusal_probes.csv',index=False)
    receipt={'status':'passed','internal_records':24,'targeted_refusal_probes':6,'held_out_language_accuracy_estimated':False,'numeric_values_predicted':False,'graph_target_lookup_after_screening':True,'source_body_sha256':hashlib.sha256((ref/'controlled_screen.py').read_bytes()).hexdigest(),'model_calls':0,'training_runs':0}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
