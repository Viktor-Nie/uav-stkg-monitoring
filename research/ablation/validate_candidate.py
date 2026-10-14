"""Portable opt-in candidate validation: original text -> numeric guard -> STKG.

This new entry point is not silently substituted into the frozen historical runner.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from ablation_scoring import normalize_roles,graph_validate
from numeric_text_guard import bind_if_text_consistent

def validate_candidate(original_text:str,candidate:dict,bindings:list[dict],admissible_pairs:set[tuple[str,str]])->dict:
 numeric=bind_if_text_consistent(original_text,bindings)
 if not numeric['check']['accepted']:
  return {'accepted':False,'stage':'explicit_numeric_text','reason':numeric['check']['reason'],'numeric_check':numeric['check'],'bound_values':None,'stkg_checked':False}
 if candidate.get('scope')!='in_scope':
  return {'accepted':False,'stage':'candidate_scope','reason':'model_refusal','numeric_check':numeric['check'],'bound_values':None,'stkg_checked':False}
 accepted,reason=graph_validate(candidate.get('signal_id',''),candidate.get('template_id',''),normalize_roles(candidate.get('parameter_roles',[])),candidate.get('formula_structure',''),admissible_pairs)
 return {'accepted':bool(accepted),'stage':'stkg','reason':reason,'numeric_check':numeric['check'],'bound_values':numeric['bound_values'] if accepted else None,'stkg_checked':True}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('input_json',type=Path,help='Object with original_text, candidate, bindings, and admissible_pairs');a=ap.parse_args();p=json.loads(a.input_json.read_text(encoding='utf-8'))
 result=validate_candidate(p['original_text'],p['candidate'],p['bindings'],{tuple(x) for x in p['admissible_pairs']})
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
