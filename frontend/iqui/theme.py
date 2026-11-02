"""InterviewIQ design tokens + CSS. Dark blue/black palette (no light theme).
Native Streamlit widgets are themed best-effort through stable data-testid selectors; the base palette is also set in
.streamlit/config.toml so widgets stay dark even if a selector changes in a future Streamlit release."""

TOKENS = {
    "bg": "#080B12", "sidebar": "#0D1320", "panel": "#111827", "card": "#172033", "primary": "#1677FF",
    "primary_hover": "#4094FF", "border": "#26344B", "text": "#F5F7FB", "text2": "#AAB8CC", "muted": "#8290A5",
    "success": "#22C55E", "warning": "#F59E0B", "error": "#EF4444",
}

CSS = """
:root{--bg:#080B12;--sidebar:#0D1320;--panel:#111827;--card:#172033;--primary:#1677FF;--primary-hover:#4094FF;
--border:#26344B;--text:#F5F7FB;--text2:#AAB8CC;--muted:#8290A5;--success:#22C55E;--warning:#F59E0B;--error:#EF4444;
--radius:12px;--radius-sm:8px;}
html,body,[data-testid="stAppViewContainer"],.stApp{background:var(--bg)!important;color:var(--text);
font-family:"Inter","Segoe UI",system-ui,-apple-system,Roboto,sans-serif;}
[data-testid="stHeader"]{background:transparent!important;height:0;}
[data-testid="stToolbar"],[data-testid="stDecoration"],#MainMenu,footer{display:none!important;visibility:hidden;}
.block-container{padding:2rem 2.5rem 4rem!important;max-width:1280px;animation:iqfade .25s ease-out;}
@keyframes iqfade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media (max-width:900px){.block-container{padding:1.25rem 1rem 3rem!important}.iq-title{font-size:1.4rem!important}}
h1,h2,h3,h4{color:var(--text);letter-spacing:-.01em}
p,li,label,span{color:inherit}
a{color:var(--primary-hover)}
hr{border-color:var(--border)}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{background:var(--sidebar)!important;border-right:1px solid var(--border);}
[data-testid="stSidebar"] .block-container,[data-testid="stSidebarUserContent"]{padding-top:1.2rem!important}
.iq-brand{display:flex;align-items:center;gap:.65rem;margin:.2rem 0 1.1rem}
.iq-logo{width:34px;height:34px;border-radius:9px;background:var(--primary);display:flex;align-items:center;justify-content:center;
color:#fff;font-weight:700;font-size:15px;letter-spacing:-.02em}
.iq-brand-name{font-size:1.05rem;font-weight:650;color:var(--text);line-height:1.1}
.iq-brand-sub{font-size:.72rem;color:var(--muted)}
.iq-side-label{font-size:.68rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin:1.1rem 0 .4rem;font-weight:600}
[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"]{gap:2px}
[data-testid="stSidebar"] [data-testid="stRadio"] label{padding:.55rem .75rem;border-radius:var(--radius-sm);width:100%;
color:var(--text2);border:1px solid transparent;transition:background .15s,color .15s;cursor:pointer}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover{background:rgba(22,119,255,.08);color:var(--text)}
[data-testid="stSidebar"] [data-testid="stRadio"] label>div:first-child{display:none}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){background:rgba(22,119,255,.14);color:var(--text);
border-color:rgba(22,119,255,.45)}
[data-testid="stSidebar"] [data-testid="stRadio"] label p{font-size:.92rem;font-weight:500}
.iq-mode{border:1px solid var(--border);background:var(--panel);border-radius:var(--radius-sm);padding:.65rem .75rem;margin-top:.5rem;font-size:.78rem;color:var(--text2)}
.iq-mode b{color:var(--text)}

/* ---------- page header ---------- */
.iq-eyebrow{font-size:.72rem;letter-spacing:.09em;text-transform:uppercase;color:var(--primary-hover);font-weight:600;margin-bottom:.2rem}
.iq-title{font-size:1.75rem;font-weight:650;margin:0;color:var(--text);letter-spacing:-.02em}
.iq-subtitle{color:var(--text2);margin:.35rem 0 0;font-size:.95rem;max-width:760px;line-height:1.5}
.iq-header{margin-bottom:1.5rem;padding-bottom:1.1rem;border-bottom:1px solid var(--border)}
.iq-section{margin:1.6rem 0 .75rem}
.iq-section h3{font-size:1.02rem;margin:0;font-weight:600}
.iq-section p{margin:.2rem 0 0;color:var(--muted);font-size:.85rem}

/* ---------- cards / metrics ---------- */
.iq-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.9rem;margin:.25rem 0 .5rem}
.iq-metric{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1rem 1.1rem;
transition:border-color .15s}
.iq-metric:hover{border-color:#34476A}
.iq-metric .l{font-size:.78rem;color:var(--text2);font-weight:500}
.iq-metric .v{font-size:1.85rem;font-weight:650;margin:.25rem 0 .1rem;color:var(--text);letter-spacing:-.02em;line-height:1.1}
.iq-metric .h{font-size:.76rem;color:var(--muted)}
.iq-metric.tone-warning .v{color:var(--warning)}.iq-metric.tone-error .v{color:var(--error)}.iq-metric.tone-success .v{color:var(--success)}
.iq-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1.1rem 1.25rem;margin-bottom:.8rem}
.iq-card h4{margin:0 0 .4rem;font-size:.95rem;font-weight:600}
.iq-card p{margin:0;color:var(--text2);font-size:.88rem;line-height:1.55}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]){border-color:var(--border)}
div[data-testid="stVerticalBlockBorderWrapper"]{background:var(--panel);border-radius:var(--radius)}

/* ---------- badges ---------- */
.iq-badge{display:inline-flex;align-items:center;gap:.4rem;padding:.16rem .6rem;border-radius:999px;font-size:.74rem;font-weight:550;
border:1px solid var(--border);color:var(--text2);background:rgba(130,144,165,.1);white-space:nowrap}
.iq-badge i{width:6px;height:6px;border-radius:50%;background:currentColor;display:inline-block}
.iq-badge.info{color:#6CB0FF;background:rgba(22,119,255,.12);border-color:rgba(22,119,255,.35)}
.iq-badge.success{color:var(--success);background:rgba(34,197,94,.1);border-color:rgba(34,197,94,.3)}
.iq-badge.warning{color:var(--warning);background:rgba(245,158,11,.1);border-color:rgba(245,158,11,.3)}
.iq-badge.error{color:var(--error);background:rgba(239,68,68,.1);border-color:rgba(239,68,68,.3)}

/* ---------- callouts / empty ---------- */
.iq-callout{display:flex;gap:.8rem;border-radius:var(--radius);padding:.85rem 1rem;margin:.5rem 0 1rem;border:1px solid var(--border);
background:var(--panel);border-left-width:3px}
.iq-callout .t{font-weight:600;font-size:.9rem;color:var(--text)}.iq-callout .b{font-size:.86rem;color:var(--text2);margin-top:.15rem;line-height:1.5}
.iq-callout.info{border-left-color:var(--primary)}.iq-callout.success{border-left-color:var(--success)}
.iq-callout.warning{border-left-color:var(--warning)}.iq-callout.error{border-left-color:var(--error)}
.iq-empty{border:1px dashed var(--border);border-radius:var(--radius);padding:2rem 1.5rem;text-align:center;background:rgba(17,24,39,.5)}
.iq-empty .t{font-weight:600;color:var(--text)}.iq-empty .b{color:var(--muted);font-size:.88rem;margin-top:.3rem}

/* ---------- funnel / stepper / bars ---------- */
.iq-funnel{display:flex;flex-direction:column;gap:.55rem}
.iq-frow{display:grid;grid-template-columns:110px 1fr 44px;align-items:center;gap:.8rem;font-size:.85rem;color:var(--text2)}
.iq-ftrack{height:10px;background:#0E1626;border-radius:99px;overflow:hidden;border:1px solid var(--border)}
.iq-ffill{height:100%;background:var(--primary);border-radius:99px;transition:width .5s ease}
.iq-frow .n{text-align:right;color:var(--text);font-weight:600}
.iq-stepper{display:flex;gap:.4rem;flex-wrap:wrap;margin:.4rem 0 1rem}
.iq-step{flex:1;min-width:120px;padding:.6rem .75rem;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--panel);font-size:.8rem;color:var(--muted)}
.iq-step .n{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em}
.iq-step.done{color:var(--text2);border-color:rgba(34,197,94,.35)}.iq-step.done .n{color:var(--success)}
.iq-step.current{color:var(--text);border-color:var(--primary);background:rgba(22,119,255,.1)}.iq-step.current .n{color:var(--primary-hover)}
.iq-bar{display:flex;align-items:center;gap:.6rem;min-width:120px}
.iq-bar .track{flex:1;height:7px;background:#0E1626;border-radius:99px;overflow:hidden}
.iq-bar .fill{height:100%;border-radius:99px;background:var(--primary)}
.iq-bar .fill.success{background:var(--success)}.iq-bar .fill.warning{background:var(--warning)}.iq-bar .fill.error{background:var(--error)}
.iq-bar span{font-size:.8rem;color:var(--text);min-width:2.2rem;text-align:right;font-variant-numeric:tabular-nums}

/* ---------- table ---------- */
.iq-tablewrap{overflow-x:auto;border:1px solid var(--border);border-radius:var(--radius);background:var(--panel)}
table.iq-table{width:100%;border-collapse:collapse;font-size:.86rem}
.iq-table th{text-align:left;font-weight:600;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
padding:.7rem .9rem;background:#0F1626;border-bottom:1px solid var(--border);white-space:nowrap}
.iq-table td{padding:.7rem .9rem;border-bottom:1px solid #1C2940;color:var(--text2);vertical-align:middle}
.iq-table tr:last-child td{border-bottom:0}.iq-table tr:hover td{background:rgba(22,119,255,.04)}
.iq-table td.strong{color:var(--text);font-weight:550}.iq-table td.r,.iq-table th.r{text-align:right}

/* ---------- key/value, quotes, trace ---------- */
.iq-kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:.9rem 1.5rem}
.iq-kv .k{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}.iq-kv .v{color:var(--text);margin-top:.15rem;font-size:.92rem;word-break:break-word}
.iq-quote{border-left:2px solid var(--primary);padding:.35rem .9rem;margin:.4rem 0;color:var(--text2);font-size:.88rem;background:rgba(22,119,255,.05);border-radius:0 var(--radius-sm) var(--radius-sm) 0}
.iq-trace{border-left:2px solid var(--border);margin-left:.4rem;padding-left:1.1rem}
.iq-turn{position:relative;margin-bottom:1rem;padding:.8rem 1rem;background:var(--card);border:1px solid var(--border);border-radius:var(--radius)}
.iq-turn:before{content:"";position:absolute;left:-1.55rem;top:1.05rem;width:9px;height:9px;border-radius:50%;background:var(--primary);border:2px solid var(--bg)}
.iq-turn .top{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:.4rem;font-size:.8rem;color:var(--muted)}
.iq-turn .row{font-size:.86rem;color:var(--text2);margin-top:.3rem;line-height:1.5}.iq-turn .row b{color:var(--text);font-weight:550}
.iq-question{background:var(--card);border:1px solid rgba(22,119,255,.4);border-radius:var(--radius);padding:1.1rem 1.3rem;margin:.6rem 0 1rem}
.iq-question .l{font-size:.7rem;letter-spacing:.09em;text-transform:uppercase;color:var(--primary-hover);font-weight:600}
.iq-question .q{font-size:1.15rem;color:var(--text);margin-top:.35rem;line-height:1.5}

/* ---------- competency evidence presentation ---------- */
.iq-comp-box{border:1px solid var(--border);background:var(--panel);border-radius:var(--radius);padding:1.1rem 1.25rem;margin:.4rem 0 .9rem;transition:border-color .15s}
.iq-comp-box:hover{border-color:rgba(22,119,255,.35)}
.iq-comp-top{display:flex;justify-content:space-between;align-items:flex-start;gap:.8rem;margin-bottom:.5rem;flex-wrap:wrap}
.iq-comp-title{font-size:1.08rem;font-weight:650;color:var(--text);letter-spacing:-.01em;display:flex;align-items:center;gap:.6rem}
.iq-comp-desc{font-size:.84rem;color:var(--text2);margin-bottom:.85rem;line-height:1.45}
.iq-card-title{font-size:.75rem;font-weight:650;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:.85rem 0 .4rem;display:flex;align-items:center;gap:.45rem}
.iq-card-title.accent{color:var(--primary-hover)}
.iq-ev-card{background:var(--card);border:1px solid var(--border);border-left:3px solid var(--primary);border-radius:var(--radius-sm);padding:.75rem 1rem;margin-bottom:.5rem;font-size:.87rem;color:var(--text);line-height:1.55}
.iq-ev-empty{background:rgba(17,24,39,.6);border:1px dashed var(--border);border-left:3px solid var(--muted);border-radius:var(--radius-sm);padding:.85rem 1rem;color:var(--muted);font-size:.85rem;font-style:italic}
.iq-rationale-box{background:rgba(22,119,255,.05);border:1px solid rgba(22,119,255,.2);border-radius:var(--radius-sm);padding:.85rem 1.1rem;margin:.5rem 0 .8rem;font-size:.87rem;color:var(--text2);line-height:1.55}
.iq-gap-grid{display:grid;grid-template-columns:1fr 1fr;gap:.85rem;margin:.6rem 0 .9rem}
@media (max-width:768px){.iq-gap-grid{grid-template-columns:1fr}}
.iq-gap-col{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm);padding:.85rem 1rem}
.iq-gap-col.demonstrated{border-top:3px solid var(--success)}
.iq-gap-col.missing{border-top:3px solid var(--warning)}
.iq-gap-list{list-style:none;padding:0;margin:0}
.iq-gap-item{font-size:.83rem;color:var(--text2);margin-bottom:.4rem;display:flex;align-items:flex-start;gap:.45rem;line-height:1.45}
.iq-gap-item:last-child{margin-bottom:0}
.iq-gap-item i{font-style:normal;font-weight:700;flex-shrink:0}
.iq-gap-col.demonstrated .iq-gap-item i{color:var(--success)}
.iq-gap-col.missing .iq-gap-item i{color:var(--warning)}
.iq-probe-box{background:var(--card);border:1px solid rgba(22,119,255,.3);border-radius:var(--radius-sm);padding:.9rem 1.1rem;margin-top:.7rem}
.iq-probe-item{margin-bottom:.6rem}
.iq-probe-item:last-child{margin-bottom:0}
.iq-probe-tag{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:var(--primary-hover);font-weight:600;margin-bottom:.2rem}
.iq-probe-q{background:rgba(22,119,255,.08);border-left:2px solid var(--primary-hover);padding:.55rem .85rem;border-radius:0 6px 6px 0;font-size:.87rem;color:var(--text);font-weight:500;line-height:1.45}

/* ---------- shortlist candidate cards ---------- */
.iq-sl-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;flex-wrap:wrap;gap:.75rem}
.iq-sl-pill{display:inline-flex;align-items:center;gap:.45rem;background:#172238;border:1px solid #233554;border-radius:20px;padding:.35rem .85rem;font-size:.82rem;font-weight:600;color:var(--text)}
.iq-sl-pill i{width:8px;height:8px;border-radius:50%;background:var(--primary)}
.iq-cand-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1rem 1.2rem;margin-bottom:.85rem;transition:border-color .15s,box-shadow .15s;position:relative}
.iq-cand-card:hover{border-color:rgba(22,119,255,.4)}
.iq-cand-card.is-selected{border-color:var(--primary);border-left:4px solid var(--primary);background:linear-gradient(90deg,rgba(22,119,255,.06) 0%,rgba(17,24,39,1) 40%)}
.iq-cand-card.is-locked{border-color:var(--border);border-left:4px solid var(--muted);opacity:.85}
.iq-cand-top{display:flex;align-items:flex-start;justify-content:space-between;gap:.8rem;flex-wrap:wrap}
.iq-cand-meta{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap}
.iq-rank-badge{background:#172238;color:var(--primary-hover);border:1px solid rgba(22,119,255,.4);border-radius:6px;padding:.2rem .55rem;font-size:.78rem;font-weight:700;letter-spacing:.03em}
.iq-cand-name{font-size:1.05rem;font-weight:650;color:var(--text);letter-spacing:-.01em}
.iq-cand-role{font-size:.82rem;color:var(--muted);margin-top:.15rem}
.iq-cand-scorebox{display:flex;align-items:center;gap:.75rem}
.iq-cand-score{font-weight:700;font-size:1.1rem;color:var(--text)}
.iq-cand-score small{font-size:.75rem;color:var(--muted);font-weight:400}
.iq-sl-confirm-box{background:var(--card);border:1px solid rgba(22,119,255,.3);border-radius:var(--radius);padding:1.1rem 1.3rem;margin-top:1.2rem}

/* ---------- identity review styles ---------- */
.iq-id-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1.1rem 1.3rem;margin-bottom:1rem;transition:border-color .15s}
.iq-id-card:hover{border-color:rgba(22,119,255,.35)}
.iq-id-card.inconclusive{border-left:4px solid var(--warning)}
.iq-id-card.failed{border-left:4px solid var(--error)}
.iq-id-card.pending{border-left:4px solid var(--info)}
.iq-id-card.passed{border-left:4px solid var(--success)}
.iq-id-top{display:flex;align-items:flex-start;justify-content:space-between;gap:.8rem;flex-wrap:wrap;margin-bottom:.6rem}
.iq-id-evidence{background:rgba(22,119,255,.04);border:1px solid rgba(22,119,255,.18);border-radius:var(--radius-sm);padding:.75rem 1rem;margin:.6rem 0 .8rem}
.iq-id-evidence-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.6rem;font-size:.84rem}
.iq-id-evidence-item{display:flex;flex-direction:column}
.iq-id-evidence-label{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.iq-id-evidence-val{font-weight:600;color:var(--text);margin-top:.15rem}
.iq-id-notice{font-size:.78rem;color:var(--warning);margin-top:.4rem;display:flex;align-items:center;gap:.35rem}

/* ---------- native widgets ---------- */
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{border-radius:var(--radius-sm);border:1px solid var(--border);
background:var(--card);color:var(--text);font-weight:550;padding:.5rem 1rem;transition:background .15s,border-color .15s,transform .05s}
.stButton>button:hover{border-color:var(--primary-hover);color:#fff;background:#1B2842}
.stButton>button:active{transform:translateY(1px)}
.stButton>button:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid var(--primary-hover)!important;outline-offset:2px}
.stButton>button[kind="primary"],button[data-testid="stBaseButton-primary"],[data-testid="stFormSubmitButton"]>button[kind="primaryFormSubmit"]{
background:var(--primary)!important;border-color:var(--primary)!important;color:#fff!important}
.stButton>button[kind="primary"]:hover,button[data-testid="stBaseButton-primary"]:hover{background:var(--primary-hover)!important;border-color:var(--primary-hover)!important}
.stButton>button:disabled{opacity:.45;cursor:not-allowed}
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div,[data-testid="stNumberInput"] input{background:#0E1626!important;border-color:var(--border)!important;border-radius:var(--radius-sm)!important}
[data-baseweb="input"]:focus-within,[data-baseweb="textarea"]:focus-within,[data-baseweb="select"]>div:focus-within{border-color:var(--primary)!important;box-shadow:0 0 0 1px var(--primary)!important}
label[data-testid="stWidgetLabel"] p{color:var(--text2);font-size:.84rem;font-weight:500}
[data-baseweb="tab-list"]{gap:.25rem;border-bottom:1px solid var(--border)}
button[data-baseweb="tab"]{background:transparent!important;color:var(--text2);padding:.55rem .9rem}
button[data-baseweb="tab"][aria-selected="true"]{color:var(--text)!important}
[data-baseweb="tab-highlight"]{background:var(--primary)!important}
[data-baseweb="tab-border"]{background:transparent!important}
[data-testid="stExpander"]{border:1px solid var(--border)!important;border-radius:var(--radius)!important;background:var(--panel)}
[data-testid="stExpander"] summary:hover{color:var(--text)}
[data-testid="stAlert"]{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius)}
[data-testid="stFileUploader"] section{background:#0E1626;border:1px dashed #34476A;border-radius:var(--radius)}
[data-testid="stChatMessage"]{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:.7rem 1rem}
[data-testid="stProgress"] div[role="progressbar"]>div{background:var(--primary)}
[data-testid="stDataFrame"]{border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-thumb{background:#26344B;border-radius:8px}::-webkit-scrollbar-track{background:transparent}
"""


def css_block() -> str:
    return "<style>" + CSS.replace("\n", "") + "</style>"
