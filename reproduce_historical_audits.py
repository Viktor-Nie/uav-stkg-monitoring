"""Recompute frozen source-binding consistency and relational decision parity."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'research/historical_audits'))


def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as handle:return list(csv.DictReader(handle))


def write(path,data):
    with path.open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    if output==ROOT or any(output.is_relative_to(ROOT/d) for d in ('data','src','research')):parser.error('output must not overwrite supplied inputs or source')
    if output.exists():parser.error('output must be a new directory')
    output.mkdir(parents=True)
    import pandas as pd
    from uav_stkg.graph_constraints import graph_mutations,validate_variant
    from relational_verifier import project_tables,validate_relational
    from source_binding_verifier import run as source_audit

    bindings=ROOT/'data/graph/bindings.csv'
    binding_result=source_audit(bindings)
    assert binding_result['status']=='passed',binding_result
    assert binding_result['binding_count']==84
    (output/'source_binding_receipt.json').write_text(json.dumps(binding_result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    altered=rows(bindings)
    target=next(r for r in altered if r['source_type']=='derived_statistical_reference')
    target['value']=str(float(target['value'])+1)
    control_path=output/'deliberately_changed_binding.csv';write(control_path,altered)
    control=source_audit(control_path)
    assert control['status']=='failed' and any('value differs from threshold catalog' in e for e in control['errors'])
    (output/'negative_binding_control.json').write_text(json.dumps(control,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    nodes=pd.read_csv(ROOT/'data/graph/nodes.csv',encoding='utf-8-sig')
    edges=pd.read_csv(ROOT/'data/graph/relationships.csv',encoding='utf-8-sig')
    validate_variant(nodes,edges);validate_relational(project_tables(nodes,edges))
    decisions=[]
    for kind,target,changed_nodes,changed_edges in graph_mutations(nodes,edges):
        accepted=[]
        for verify in (lambda:validate_variant(changed_nodes,changed_edges),lambda:validate_relational(project_tables(changed_nodes,changed_edges))):
            try:verify();accepted.append(True)
            except (AssertionError,KeyError,TypeError,ValueError):accepted.append(False)
        decisions.append({'mutation_type':kind,'target':target,'graph_accepts':accepted[0],'relational_accepts':accepted[1]})
    expected=rows(ROOT/'research/historical_audits/expected_relational_parity_details.csv')
    normalized=[{k:str(v) for k,v in r.items()} for r in decisions]
    assert len(decisions)==354 and normalized==expected
    assert all(not r['graph_accepts'] and not r['relational_accepts'] for r in decisions)
    write(output/'relational_parity_details.csv',decisions)
    sources=[ROOT/'data/graph/nodes.csv',ROOT/'data/graph/relationships.csv',bindings,ROOT/'research/historical_audits/expected_relational_parity_details.csv']
    receipt={'status':'passed','source_bindings_checked':84,'source_binding_negative_control_rejected':True,'clean_graph_accepted':True,'clean_relational_projection_accepted':True,'historical_mutants':354,'graph_rejected':354,'relational_rejected':354,'decision_disagreements':0,'input_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'interpretation':'Frozen source-pointer/value consistency and information-equivalent relational predicates. No independent semantic correctness, physical calibration, graph superiority or change-impact benefit is inferred. Historical source code is read statically; no training or model call occurs.'}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='input_sha256'},indent=2))


if __name__=='__main__':main()
