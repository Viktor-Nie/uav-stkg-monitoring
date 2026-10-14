"""Redraw retained summary figures without models or flight telemetry.

The superseded language bars retain their original labels and union-class F1
for provenance; they are not the corrected fixed-three-class comparison.
"""
from pathlib import Path
import argparse,csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent

def read(name):
    with (ROOT/name).open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def save(fig,directory,name):
    fig.tight_layout();fig.savefig(directory/(name+".pdf"),bbox_inches="tight")
    fig.savefig(directory/(name+".png"),dpi=180,bbox_inches="tight");plt.close(fig)

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError("Use a new output directory")
    a.output.mkdir(parents=True)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":8,"pdf.fonttype":42,"axes.spines.top":False,"axes.spines.right":False})
    left={r["method"]:r for r in read("superseded_baseline_metrics.csv")};right={r["method"]:r for r in read("superseded_english_union_label_metrics.csv")}
    plans=[(left,[("development_only_retrieval","TF-IDF\nretrieval"),("frozen_embedding_retrieval","Frozen\nembedding"),("keyword_template","Keyword/\ntemplate"),("graph_constrained","Graph-\nconstrained")],"scope_macro_f1","Superseded 19-item internal comparison"),
           (right,[("keyword_scope_rule","Keyword\nrule"),("word_tfidf_1nn","Word TF-IDF\n1-NN"),("word_tfidf_linear_svc","Word TF-IDF\nSVM"),("char_tfidf_linear_svc","Char TF-IDF\nSVM")],"mean_macro_f1","Historical 215-item union-label fold F1")]
    fig,axes=plt.subplots(1,2,figsize=(7.4,3.0),sharey=True)
    for ax,(lookup,order,key,title) in zip(axes,plans):
        values=[float(lookup[k][key]) for k,_ in order];bars=ax.bar(range(len(values)),values,color=["#AAB7C4","#7895B2","#4F769C","#244E73"],width=.68)
        ax.set_xticks(range(len(values)),[label for _,label in order]);ax.set_ylim(0,1.03);ax.set_title(title,fontsize=8);ax.grid(axis="y",color="#D9DEE3",linewidth=.6);ax.set_axisbelow(True)
        for b,v in zip(bars,values):ax.text(b.get_x()+b.get_width()/2,v+.025,f"{v:.3f}",ha="center",fontsize=7)
    axes[0].set_ylabel("Historical macro F1");save(fig,a.output,"superseded_baseline_summary")
    data=read("rflymad_log_level_summary.csv");rec=[int(r["recovered_obligation_count"]) for r in data];exp=[int(r["expired_obligation_count"]) for r in data]
    fig,ax=plt.subplots(figsize=(4.8,2.9));x=range(len(data));ax.bar(x,rec,width=.58,color="#3C7894",label="Recovered");ax.bar(x,exp,bottom=rec,width=.58,color="#B4614D",label="Expired");ax.set_xticks(list(x),[r["case_id"] for r in data]);ax.set_ylabel("Obligation count");ax.legend(frameon=False);ax.grid(axis="y",color="#D9DEE3",linewidth=.6);ax.set_axisbelow(True)
    for i,(r,e) in enumerate(zip(rec,exp)):ax.text(i,r+e+max(2,.02*(r+e)),str(r+e),ha="center",fontsize=7)
    save(fig,a.output,"rflymad_obligations_summary")
    data=read("sampling_phase_detection.csv");lookup={(float(r["pulse_width_seconds"]),float(r["frequency_hz"])):float(r["sampled_point_detection_rate"]) for r in data};rates=[10.,20.,50.,100.]
    fig,ax=plt.subplots(figsize=(5.4,3.1))
    for width,marker in zip([.005,.01,.02,.05,.1],["o","s","^","D","P"]):ax.plot(rates,[lookup[(width,rate)] for rate in rates],marker=marker,linewidth=1.5,label=f"{int(width*1000)} ms")
    ax.set_xscale("log");ax.set_xticks(rates,["10","20","50","100"]);ax.set_ylim(-.02,1.04);ax.set_xlabel("Sampling rate (Hz)");ax.set_ylabel("Observed phase fraction");ax.legend(title="Pulse width",ncol=3,frameon=False,loc="lower right");ax.grid(color="#D9DEE3",linewidth=.6);save(fig,a.output,"sampling_visibility_summary")
    print("Redrew three summary figures from retained aggregate CSVs")
if __name__=="__main__":main()
