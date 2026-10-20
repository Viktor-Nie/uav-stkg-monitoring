"""Offline conditional resampling of frozen language predictions; no inference.

Intervals describe sensitivity to reweighting the observed source families and,
separately, the five saved contexts. They are not population confidence intervals.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 2026101404
REPLICATES = 20000
CONDITIONS = ('full', 'without_role_mapping', 'without_skeleton', 'without_both')

def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def write_csv(path, rows):
    with path.open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def f1(y, p, labels):
    values = []
    for label in labels:
        tp = sum(a == label and b == label for a, b in zip(y, p))
        fp = sum(a != label and b == label for a, b in zip(y, p))
        fn = sum(a == label and b != label for a, b in zip(y, p))
        values.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)
    return sum(values)/len(labels)

def summary(task, method, metric, point, draws, resampling):
    lo, hi = np.quantile(draws, [0.025, 0.975], method='linear')
    return dict(task=task, method=method, metric=metric, point=float(point),
                lower=float(lo), upper=float(hi), resampling=resampling,
                interval='95% conditional percentile resampling interval',
                seed=SEED, replicates=REPLICATES)

def counts(rows):
    y = [r['reference_scope'] for r in rows]
    p = [r['predicted_scope'] for r in rows]
    values = [len(rows), sum(a == b for a,b in zip(y,p)),
              sum(r['tuple_correct'].lower() == 'true' for r in rows),
              sum(r['formula_correct'].lower() == 'true' for r in rows),
              sum(a == 'out_of_scope' for a in y),
              sum(a == 'out_of_scope' and b == 'out_of_scope' for a,b in zip(y,p))]
    for label in ('in_scope', 'out_of_scope'):
        values += [sum(a==label and b==label for a,b in zip(y,p)),
                   sum(a!=label and b==label for a,b in zip(y,p)),
                   sum(a==label and b!=label for a,b in zip(y,p))]
    return np.asarray(values, dtype=float)

def scores(array):
    """Vectorized metrics on sums of family count vectors, last dimension 12."""
    n = array[..., 0]
    parts = []
    for offset in (6,9):
        denominator = 2*array[...,offset]+array[...,offset+1]+array[...,offset+2]
        parts.append(np.divide(2*array[...,offset], denominator,
                               out=np.zeros_like(denominator), where=denominator!=0))
    return {'scope_macro_f1': (parts[0]+parts[1])/2,
            'scope_accuracy': array[...,1]/n, 'tuple_exact':array[...,2]/n,
            'formula_exact':array[...,3]/n,
            'correct_rejection':np.divide(array[...,5],array[...,4],
                   out=np.full_like(n,np.nan),where=array[...,4]!=0)}

def validate_saved_fair(reference, rows):
    """Re-score public raw output fields before using any stored correctness flag."""
    sys.path.insert(0, str(ROOT/'research/ablation'))
    import ablation_scoring as scorer
    mapping = {r['anonymous_id']:r['source_item_id'] for r in
               json.loads((ROOT/'research/ablation/scoring_id_mapping.json').read_text(encoding='utf-8'))}
    matched = 0
    for condition in CONDITIONS:
        for repetition in range(1,6):
            raw = json.loads((ROOT/f'research/ablation/public_calls/{condition}_r{repetition}.json').read_text(encoding='utf-8'))
            assert raw['receipt']['status'] == 'completed'
            predictions = {mapping[p['id']]:p for p in raw['output']['records']}
            for row in (r for r in rows if r['condition']==condition and int(r['repetition'])==repetition):
                pred = predictions[row['source_item_id']]; ref = reference[row['source_item_id']]
                scope = pred['scope']; gold_scope = ref['adjudicated_scope']
                signal = pred.get('signal_id','') if scope=='in_scope' else ''
                template = pred.get('template_id','') if scope=='in_scope' else ''
                gold_signal = ref['reference_signal_id'] if gold_scope=='in_scope' else ''
                gold_template = ref['reference_template_id'] if gold_scope=='in_scope' else ''
                assert (scope,signal,template)==(row['predicted_scope'],row['signal_id'],row['template_id'])
                exact = (scope,signal,template)==(gold_scope,gold_signal,gold_template)
                gold_formula = scorer.normalize_formula_serialization(scorer.canonical_formula(gold_scope,gold_signal,gold_template)) if gold_scope=='in_scope' else 'OUT_OF_SCOPE'
                formula_exact = scorer.provided_formula_key(scope,pred.get('formula_structure',''))==gold_formula
                assert exact == (row['tuple_correct'].lower()=='true')
                assert formula_exact == (row['formula_correct'].lower()=='true')
                matched += 1
    assert matched==380
    return matched

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    out=args.output.resolve()
    if out.exists(): parser.error('output must be new; previous evidence is preserved')
    out.mkdir(parents=True)
    input_paths=[ROOT/'data/language/english_predictions.csv',ROOT/'data/language/english_expected_families.csv',
                 ROOT/'research/ablation/reference_19_v33_source_reviewed.csv',
                 ROOT/'research/ablation/fair_language_predictions_v33_reference.csv',
                 ROOT/'research/ablation/historical_predictions_on_v33_reference.csv']
    input_paths += [ROOT/'research/ablation/scoring_id_mapping.json', ROOT/'research/ablation/ablation_scoring.py']
    input_paths += sorted((ROOT/'research/ablation/public_calls').glob('*_r[1-5].json'))
    before={p.relative_to(ROOT).as_posix():sha(p) for p in input_paths}
    protocol={'reference_version':'human_review_20261019','legacy_reference_filename':'reference_19_v33_source_reviewed.csv','legacy_filename_does_not_identify_active_version':True,'seed':SEED,'replicates':REPLICATES,'percentiles':[2.5,97.5],
      'frozen_before_resampling':True,'english_unit':'eight curated document families; equal family weight; same draws paired across methods',
      'chinese_source_unit':'six observed families; all items in each family retained; metrics recomputed at each reweighting',
      'chinese_context_unit':'five saved independent contexts per condition, resampled independently across conditions; repetition numbers are not paired random seeds',
      'chinese_paired_comparison':'same sampled families in each condition; contexts independent across conditions',
      'estimand':'English equal-family average; Chinese mean of five item-weighted run metrics, or historical item-weighted metric',
      'interpretation':'conditional empirical sensitivity intervals, not population confidence intervals; no iid text or flight assumption; no population superiority test',
      'limits':['only 8/6 curated families','publisher overlap and LOFO training overlap can induce further dependence','only 5 contexts, with unknown serving snapshot','reference uncertainty is not included','Chinese core reference human_review_20261019 is author-confirmed reviewed by A/B/C; original C physical-context fields are empty'],
      'input_sha256':before}
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n',encoding='utf-8')
    rng=np.random.default_rng(SEED)
    rows=read(input_paths[0]); families=sorted({r['family'] for r in rows}); methods=sorted({r['method'] for r in rows})
    assert len(families)==8
    family_draws=rng.integers(0,8,size=(REPLICATES,8))
    english=[]; reports=[]; english_distributions={}
    expected={(r['method'],r['family']):r for r in read(input_paths[1])}
    for method in methods:
        values=[]
        for family in families:
            group=[r for r in rows if r['method']==method and r['family']==family]
            y=[r['reference_scope'] for r in group]; p=[r['prediction'] for r in group]
            acc=sum(a==b for a,b in zip(y,p))/len(y); macro=f1(y,p,('in_scope','conditional','out_of_scope'))
            assert abs(acc-float(expected[(method,family)]['accuracy']))<1e-12
            assert abs(macro-float(expected[(method,family)]['fixed_three_class_f1']))<1e-12
            english.append(dict(method=method,family=family,n=len(group),accuracy=acc,fixed_three_class_f1=macro))
            values.append([acc,macro])
        assert sum(r['n'] for r in english if r['method']==method)==215
        a=np.asarray(values); draws=a[family_draws].mean(axis=1)
        for j,metric in enumerate(('accuracy','fixed_three_class_f1')):
            english_distributions[(method,metric)]=draws[:,j]
            reports.append(summary('english_215',method,metric,a[:,j].mean(),draws[:,j],'source_family'))
    comparisons=[]
    for method in methods:
        if method=='llm_zero_shot': continue
        for metric in ('accuracy','fixed_three_class_f1'):
            a=english_distributions[('llm_zero_shot',metric)]-english_distributions[(method,metric)]
            point=next(r['point'] for r in reports if r['task']=='english_215' and r['method']=='llm_zero_shot' and r['metric']==metric)-next(r['point'] for r in reports if r['task']=='english_215' and r['method']==method and r['metric']==metric)
            comparisons.append(summary('english_215','llm_zero_shot minus '+method,metric,point,a,'paired_source_family'))
    write_csv(out/'english_per_family.csv',english)
    reference={r['source_item_id']:r for r in read(input_paths[2])}
    chinese_families=sorted({r['source_family_id'] for r in reference.values()}); assert len(chinese_families)==6 and len(reference)==19
    fair=read(input_paths[3]); matched=validate_saved_fair(reference,fair)
    assert len(fair)==380 and len({r['source_item_id'] for r in fair})==19
    chinese_draws=rng.integers(0,6,size=(REPLICATES,6))
    # A family bootstrap reweights all rows in the family, never individual texts.
    raw_family=[]; distributions={}; point_by_condition={}; context_draw_records=[]
    for condition in CONDITIONS:
        cube=np.empty((5,6,12))
        for repetition in range(1,6):
            for j,family in enumerate(chinese_families):
                group=[r for r in fair if r['condition']==condition and int(r['repetition'])==repetition and reference[r['source_item_id']]['source_family_id']==family]
                cube[repetition-1,j]=counts(group)
                raw_family.append(dict(condition=condition,repetition=repetition,family=family,
                    **dict(zip(('n','scope_correct','tuple_correct','formula_correct','negatives','correct_rejection','positive_tp','positive_fp','positive_fn','negative_tp','negative_fp','negative_fn'),counts(group).astype(int)))))
        point_scores=scores(cube.sum(axis=1))
        family_scores=scores(cube[:,chinese_draws,:].sum(axis=2)) # contexts x draws
        contexts=rng.integers(0,5,size=(REPLICATES,5))
        context_draw_records += [{'condition':condition,'resample':i+1,'context_indices_0_based':';'.join(map(str,r))} for i,r in enumerate(contexts)]
        for metric,ps in point_scores.items():
            point=ps.mean(); point_by_condition[(condition,metric)]=point
            by_family=family_scores[metric].mean(axis=0)
            by_context=ps[contexts].mean(axis=1)
            crossed=family_scores[metric][contexts,np.arange(REPLICATES)[:,None]].mean(axis=1)
            for label,draws in (('source_family',by_family),('context_only',by_context),('source_family_and_context',crossed)):
                distributions[(condition,metric,label)]=draws
                reports.append(summary('chinese_19_five_contexts',condition,metric,point,draws,label))
    for condition in CONDITIONS[1:]:
        for metric in ('scope_macro_f1','tuple_exact','formula_exact','correct_rejection'):
            for label in ('source_family','context_only','source_family_and_context'):
                difference=distributions[('full',metric,label)]-distributions[(condition,metric,label)]
                comparisons.append(summary('chinese_19_five_contexts','full minus '+condition,metric,
                    point_by_condition[('full',metric)]-point_by_condition[(condition,metric)],difference,'paired_'+label if label!='context_only' else 'independent_contexts'))
    historical=read(input_paths[4]); historical_families=[]
    for condition in sorted({r['condition'] for r in historical}):
        matrix=[]
        for family in chinese_families:
            group=[r for r in historical if r['condition']==condition and reference[r['source_item_id']]['source_family_id']==family]
            value=counts(group); matrix.append(value)
            historical_families.append(dict(condition=condition,family=family,
                   **dict(zip(('n','scope_correct','tuple_correct','formula_correct','negatives','correct_rejection','positive_tp','positive_fp','positive_fn','negative_tp','negative_fp','negative_fn'),value.astype(int)))))
        a=np.asarray(matrix); point=scores(a.sum(axis=0)); draw=scores(a[chinese_draws].sum(axis=1))
        for metric in point:
            reports.append(summary('chinese_19_historical',condition,metric,point[metric],draw[metric],'source_family'))
    write_csv(out/'chinese_per_family_per_context.csv',raw_family)
    write_csv(out/'chinese_historical_per_family.csv',historical_families)
    write_csv(out/'conditional_intervals.csv',reports);write_csv(out/'paired_differences.csv',comparisons)
    write_csv(out/'family_draws_english.csv',[{'resample':i+1,'family_indices_0_based':';'.join(map(str,r))} for i,r in enumerate(family_draws)])
    write_csv(out/'family_draws_chinese.csv',[{'resample':i+1,'family_indices_0_based':';'.join(map(str,r))} for i,r in enumerate(chinese_draws)])
    write_csv(out/'context_draws_chinese.csv',context_draw_records)
    english_tex=[]
    for method in methods:
        rr={r['metric']:r for r in reports if r['task']=='english_215' and r['method']==method}
        english_tex.append(method.replace('_','\\_')+' & '+ ' & '.join(f"{rr[m]['point']:.3f} [{rr[m]['lower']:.3f}, {rr[m]['upper']:.3f}]" for m in ('accuracy','fixed_three_class_f1'))+r' \\')
    (out/'english_interval_rows.tex').write_text('\n'.join(english_tex)+'\n',encoding='utf-8')
    fair_tex=[]
    for condition in CONDITIONS:
        rr={r['metric']:r for r in reports if r['task']=='chinese_19_five_contexts' and r['method']==condition and r['resampling']=='source_family_and_context'}
        fair_tex.append(condition.replace('_','\\_')+' & '+' & '.join(f"{rr[m]['point']:.3f} [{rr[m]['lower']:.3f}, {rr[m]['upper']:.3f}]" for m in ('scope_macro_f1','tuple_exact','correct_rejection'))+r' \\')
    (out/'chinese_interval_rows.tex').write_text('\n'.join(fair_tex)+'\n',encoding='utf-8')
    after={p.relative_to(ROOT).as_posix():sha(p) for p in input_paths};assert before==after
    receipt={'status':'passed','seed':SEED,'replicates':REPLICATES,'english_items':215,'english_families':8,
      'chinese_unique_items':19,'chinese_families':6,'conditions':4,'contexts_per_condition':5,'opportunities':380,
      'rescored_public_output_rows':matched,'reference_version':'human_review_20261019','reference_positive':5,'reference_negative':14,'human_core_review_status':'completed_author_confirmed','original_C_physical_context_nonempty':0,
      'input_sha256':before,'source_unchanged':True,'population_inference':False,'reference_uncertainty_included':False,
      'model_calls':0,'training_runs':0,'network_requests':0,'numpy_version':np.__version__,'python':sys.version,
      'script_sha256':sha(Path(__file__))}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__': main()
