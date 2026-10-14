import copy,csv,json,math,unittest
from pathlib import Path
from numeric_text_guard import check_explicit_numeric_text,bind_if_text_consistent
from validate_candidate import validate_candidate
from ablation_scoring import canonical_formula,TEMPLATE_ROLES
HERE=Path(__file__).resolve().parent

class NumericGuardTests(unittest.TestCase):
 def test_value_conflict_is_refused_without_overwrite(self):
  b=[{'role':'upper_bound','unit':'m/s','value':6.62613257694774}];saved=copy.deepcopy(b)
  r=bind_if_text_consistent('速度不得超过 10 m/s',b)
  self.assertFalse(r['check']['accepted']);self.assertIsNone(r['bound_values']);self.assertEqual(b,saved)
 def test_exact_value_and_equivalent_units(self):
  for text,unit,value in [('速度上界 36 km/h','m/s',10),('高度上限 400 ft','m',121.92),('角度上限 180 deg','rad',math.pi),('期限 200 ms','s',.2),('角速度上界 2 rad/s','rad/s',2)]:
   with self.subTest(text=text):self.assertTrue(check_explicit_numeric_text(text,[{'role':'deadline_seconds' if '期限' in text else 'upper_bound','unit':unit,'value':value}])['accepted'])
 def test_unknown_numeric_expressions_are_refused(self):
  b=[{'role':'upper_bound','unit':'m/s','value':10}]
  for text in ['速度上界约 10 m/s','速度上界 5-10 m/s','速度上界 10 knots','速度上界 10','速度上界 NaN m/s','速度上界 inf m/s','速度 10 m/s','速度上界 10 m','速度上界 10 m/s 与 10 m/s','版本2，速度上界 10 m/s','速度上限十米每秒','deadline two seconds']:
   with self.subTest(text=text):self.assertFalse(check_explicit_numeric_text(text,b)['accepted'])
 def test_response_roles_cannot_be_swapped(self):
  b=[{'role':'trigger_upper','unit':'m/s','value':10},{'role':'recovery_upper','unit':'m/s','value':8},{'role':'deadline_seconds','unit':'s','value':2}]
  self.assertTrue(check_explicit_numeric_text('触发阈值 10 m/s；恢复阈值 8 m/s；期限 2 s',b)['accepted'])
  self.assertFalse(check_explicit_numeric_text('触发阈值 8 m/s；恢复阈值 10 m/s；期限 2 s',b)['accepted'])
 def test_all_24_original_configurations_unchanged(self):
  with (HERE/'inputs/v4_complete_formula_catalog.csv').open(encoding='utf-8-sig',newline='') as stream:
   rows=list(csv.DictReader(stream))
  self.assertEqual(len(rows),24)
  for r in rows:
   b=json.loads(r['parameter_bindings_json']);before=copy.deepcopy(b);v=bind_if_text_consistent(r['source_requirement_text_zh'],b)
   with self.subTest(formula=r['formula_id']):self.assertTrue(v['check']['accepted']);self.assertEqual(v['bound_values'],{p['role']:p['value'] for p in b});self.assertEqual(b,before)
 def test_guard_precedes_stkg_and_original_text_is_required(self):
  candidate={'scope':'in_scope','signal_id':'speed_3d_mps','template_id':'invariant_upper','parameter_roles':['upper_bound'],'formula_structure':canonical_formula('in_scope','speed_3d_mps','invariant_upper')};b=[{'role':'upper_bound','unit':'m/s','value':6.62613257694774}]
  x=validate_candidate('速度不得超过 10 m/s',candidate,b,{('speed_3d_mps','invariant_upper')})
  self.assertFalse(x['accepted']);self.assertFalse(x['stkg_checked']);self.assertIsNone(x['bound_values'])
  x=validate_candidate('速度不得超过 6.62613257694774 m/s',candidate,b,{('speed_3d_mps','invariant_upper')})
  self.assertTrue(x['accepted']);self.assertTrue(x['stkg_checked']);self.assertEqual(x['bound_values']['upper_bound'],b[0]['value'])
 def test_new_portable_entrypoint_accepts_24_unchanged_configurations(self):
  with (HERE/'inputs/v4_complete_formula_catalog.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
  pairs={(r['signal_id'],r['template_id']) for r in rows}
  for r in rows:
   b=json.loads(r['parameter_bindings_json']);candidate={'scope':'in_scope','signal_id':r['signal_id'],'template_id':r['template_id'],'parameter_roles':list(TEMPLATE_ROLES[r['template_id']]),'formula_structure':canonical_formula('in_scope',r['signal_id'],r['template_id'])}
   x=validate_candidate(r['source_requirement_text_zh'],candidate,b,pairs)
   with self.subTest(formula=r['formula_id']):self.assertTrue(x['accepted']);self.assertTrue(x['stkg_checked']);self.assertEqual(x['bound_values'],{p['role']:p['value'] for p in b})
if __name__=='__main__':unittest.main()
