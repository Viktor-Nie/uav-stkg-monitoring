"""Conservative pre-binding check of explicit text values against a frozen catalog.

The catalog remains authoritative. This module never replaces a stated value.
Unrecognized numeric syntax is refused rather than silently ignored.
"""
from __future__ import annotations
import math,re
NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
VALUE=re.compile(r'('+NUMBER+r')\s*(m/s|km/h|rad/s|rad|deg|ft|ms|m|s|米/秒|米每秒|公里/小时|弧度/秒|弧度|度|英尺|毫秒|米|秒)(?![A-Za-z/])')
UNITS={'m/s':('m/s',1.),'米/秒':('m/s',1.),'米每秒':('m/s',1.),'km/h':('m/s',1/3.6),'公里/小时':('m/s',1/3.6),'rad/s':('rad/s',1.),'弧度/秒':('rad/s',1.),'rad':('rad',1.),'弧度':('rad',1.),'deg':('rad',math.pi/180),'度':('rad',math.pi/180),'m':('m',1.),'米':('m',1.),'ft':('m',.3048),'英尺':('m',.3048),'s':('s',1.),'秒':('s',1.),'ms':('s',.001),'毫秒':('s',.001)}
ROLE_CUES={'upper_bound':('上界','上限','不得超过','不超过','不能高于','<=','≤','upper bound'),
 'trigger_upper':('触发阈值','trigger threshold'), 'recovery_upper':('恢复阈值','recovery threshold'),
 'deadline_seconds':('期限','时限','deadline'), 'dwell_seconds':('驻留','dwell'),
 'value_epsilon':('容差','tolerance')}

def check_explicit_numeric_text(text:str,bindings:list[dict])->dict:
 """Return admission plus parsed values; no mutation of text or bindings."""
 if re.search(r'\b(?:nan|inf(?:inity)?)\b',text,re.I): return {'accepted':False,'reason':'nonfinite_numeric_expression','checks':[]}
 if re.search(r'[零一二三四五六七八九十百千万两点]+\s*(米|秒|度|英尺|弧度|m/s|km/h|rad|ms|m\b|s\b)',text) or re.search(r'\b(?:one|two|three|four|five|six|seven|eight|nine|ten|hundred)\s+(?:metres?|meters?|seconds?|degrees?|feet|radians?)\b',text,re.I):
  return {'accepted':False,'reason':'unsupported_spelled_numeric_expression','checks':[]}
 if not re.search(r'\d',text): return {'accepted':True,'reason':'no_explicit_numeric_value','checks':[]}
 if re.search(r'约|大约|approximately|about|[~～]|\d\s*[-–—]\s*\d',text,re.I):
  return {'accepted':False,'reason':'unsupported_approximation_or_interval','checks':[]}
 hits=list(VALUE.finditer(text));remaining=VALUE.sub('',text)
 if not hits or re.search(r'\d',remaining): return {'accepted':False,'reason':'unsupported_number_or_unit','checks':[]}
 by_role={b['role']:b for b in bindings};checks=[];previous_end=0;seen=set()
 for hit in hits:
  prefix=text[previous_end:hit.start()];previous_end=hit.end()
  matches=[(prefix.lower().rfind(c.lower()),role) for role,cues in ROLE_CUES.items() for c in cues if c.lower() in prefix.lower()]
  if not matches:return {'accepted':False,'reason':'numeric_role_unresolved','checks':checks}
  nearest=max(i for i,_ in matches);roles={r for i,r in matches if i==nearest}
  if len(roles)!=1:return {'accepted':False,'reason':'numeric_role_ambiguous','checks':checks}
  role=next(iter(roles))
  if role not in by_role or role in seen:return {'accepted':False,'reason':'missing_or_repeated_numeric_role','checks':checks}
  seen.add(role);value=float(hit.group(1));unit,factor=UNITS[hit.group(2)];b=by_role[role]
  catalog_unit=str(b['unit']);catalog_unit='rad/s' if catalog_unit in ('rps','rad/s') else catalog_unit
  value*=factor
  match=unit==catalog_unit and math.isfinite(value) and math.isclose(value,float(b['value']),rel_tol=1e-10,abs_tol=1e-12)
  checks.append({'role':role,'text_value_canonical':value,'text_unit_canonical':unit,'catalog_value':float(b['value']),'catalog_unit':catalog_unit,'matches':match})
  if not match:return {'accepted':False,'reason':'explicit_value_or_unit_conflict','checks':checks}
 return {'accepted':True,'reason':'explicit_values_match_frozen_catalog','checks':checks}

def bind_if_text_consistent(text:str,bindings:list[dict])->dict:
 """Checked binding entry point: refuse conflicts, otherwise return unchanged values."""
 check=check_explicit_numeric_text(text,bindings)
 return {'check':check,'bound_values':{b['role']:b['value'] for b in bindings} if check['accepted'] else None}
