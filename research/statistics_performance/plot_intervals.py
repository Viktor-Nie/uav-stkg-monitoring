"""Plot retained conditional contrasts; never rerun the resampling analysis."""
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--statistics',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('output must be new')
    with (args.statistics/'paired_differences.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    fig,axes=plt.subplots(2,1,figsize=(7.2,5.5),layout='constrained')
    groups=[([r for r in rows if r['task']=='english_215' and r['metric']=='fixed_three_class_f1'],
      '(a) English: LLM minus comparator, equal-family scope F1',
      {'char_tfidf_linear_svc':'Character SVM','keyword_scope_rule':'Keyword rule','word_tfidf_1nn':'Word 1-NN','word_tfidf_linear_svc':'Word SVM'}),
      ([r for r in rows if r['task']=='chinese_19_five_contexts' and r['metric']=='tuple_exact' and r['resampling']=='paired_source_family_and_context'],
       '(b) Chinese: full minus prompt ablation, tuple exact',
       {'without_role_mapping':'Without role map','without_skeleton':'Without skeleton','without_both':'Without both'})]
    for ax,(subset,title,names) in zip(axes,groups):
        for y,r in enumerate(subset):
            point=float(r['point']);lo=float(r['lower']);hi=float(r['upper'])
            ax.plot([lo,hi],[y,y],color='#27647b',lw=1.7)
            ax.plot(point,y,'s',color='#9e4d30',markersize=5)
        ax.set_yticks(range(len(subset)),[names[r['method'].split(' minus ')[1]] for r in subset])
        ax.axvline(0,color='#777777',ls='--',lw=.9);ax.grid(axis='x',alpha=.2)
        ax.set_title(title,loc='left',fontsize=10)
        ax.invert_yaxis();ax.set_xlabel('Observed score difference with 95% conditional resampling interval',fontsize=9)
        ax.tick_params(labelsize=9)
    args.output.mkdir(parents=True)
    fig.savefig(args.output/'conditional_language_contrasts.pdf',bbox_inches='tight')
    fig.savefig(args.output/'conditional_language_contrasts.png',dpi=220,bbox_inches='tight')
    plt.close(fig)
    (args.output/'receipt.json').write_text(json.dumps({'status':'passed','resampling_runs':0,
      'source':'paired_differences.csv','interpretation':'conditional empirical intervals; not population confidence intervals'},indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
