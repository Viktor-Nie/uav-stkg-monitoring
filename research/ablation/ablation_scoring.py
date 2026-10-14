"""Small dependency-free candidate scorer, preserving the historical gate rules."""
import re
SIGNALS=('speed_3d_mps','height_m','abs_roll_rad','abs_pitch_rad','ang_rate_norm_rps')
TEMPLATE_ROLES={'invariant_upper':('upper_bound',),'bounded_response':('trigger_upper','recovery_upper','deadline_seconds')}
def normalize_roles(value):
 parts=value if isinstance(value,list) else re.split(r'[,;，；]',str(value or ''))
 return tuple(sorted({str(p).strip() for p in parts if str(p).strip()}))
def canonical_formula(scope,signal,template):
 if scope!='in_scope':return 'OUT_OF_SCOPE'
 if template=='invariant_upper':return f'G[0,T]({signal} <= upper_bound)'
 if template=='bounded_response':return f'G[0,T](({signal} > trigger_upper) -> F[0,deadline_seconds]({signal} <= recovery_upper))'
 return 'UNSUPPORTED'
def normalize_formula_serialization(formula):
 v=str(formula or '').strip().replace('≤','<=').replace('≥','>=').replace('→','->').replace('\\leq','<=').replace('\\le','<=').replace('\\rightarrow','->')
 return re.sub(r'\s+','',v)
def provided_formula_key(scope,formula):
 if scope!='in_scope':return 'OUT_OF_SCOPE' if not str(formula).strip() else 'INVALID_REFUSAL_WITH_FORMULA'
 return normalize_formula_serialization(formula)
def graph_validate(signal,template,roles,formula,admissible):
 reasons=[]
 if signal not in SIGNALS:reasons.append('unknown_signal')
 if template not in TEMPLATE_ROLES:reasons.append('unknown_template')
 if (signal,template) not in admissible:reasons.append('unlinked_signal_template')
 if roles!=tuple(sorted(TEMPLATE_ROLES.get(template,()))):reasons.append('parameter_role_mismatch')
 if normalize_formula_serialization(canonical_formula('in_scope',signal,template))!=normalize_formula_serialization(formula):reasons.append('formula_field_mismatch')
 return not reasons,'accepted' if not reasons else ';'.join(reasons)
