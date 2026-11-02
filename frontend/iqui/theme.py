"""InterviewIQ design tokens + CSS. Dark blue/black palette (no light theme).
Native Streamlit widgets are themed best-effort through stable data-testid selectors; the base palette is also set in
.streamlit/config.toml so widgets stay dark even if a selector changes in a future Streamlit release."""

TOKENS = {
    "bg": "#080B12", "sidebar": "#0D1320", "panel": "#111827", "card": "#172033", "primary": "#1677FF",
    "primary_hover": "#4094FF", "border": "#26344B", "text": "#F5F7FB", "text2": "#AAB8CC", "muted": "#8290A5",
    "success": "#22C55E", "warning": "#F59E0B", "error": "#EF4444",
}

CSS = """
:root{
  --bg:#090D16;--sidebar:#0C1220;--panel:#101728;--card:#151F33;--card-hover:#1A2842;
  --primary:#1677FF;--primary-hover:#4094FF;--primary-subtle:rgba(22,119,255,0.12);
  --border:#22324C;--border-light:#2D405E;--text:#F8FAFD;--text2:#A3B3CC;--muted:#71829C;
  --success:#22C55E;--success-subtle:rgba(34,197,94,0.12);
  --warning:#F59E0B;--warning-subtle:rgba(245,158,11,0.12);
  --error:#EF4444;--error-subtle:rgba(239,68,68,0.12);
  --radius:10px;--radius-sm:6px;
}
html,body,[data-testid="stAppViewContainer"],.stApp{
  background:var(--bg)!important;color:var(--text);
  font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;
}
[data-testid="stHeader"]{background:transparent!important;height:0;}
[data-testid="stToolbar"],[data-testid="stDecoration"],#MainMenu,footer{display:none!important;visibility:hidden;}
.block-container{padding:1.25rem 2rem 3rem!important;max-width:1300px;animation:iqfade .2s ease-out;}
@keyframes iqfade{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media (max-width:900px){.block-container{padding:.9rem 1rem 2.5rem!important}.iq-title{font-size:1.35rem!important}}

/* Spacing and gap tightness */
[data-testid="stVerticalBlock"]{gap:0.75rem!important;}
[data-testid="stHorizontalBlock"]{gap:0.75rem!important;align-items:center;}
div[data-testid="stVerticalBlock"] > div{margin-bottom:0!important;}
h1,h2,h3,h4{color:var(--text);letter-spacing:-.015em;margin:0 0 .3rem}
h1{font-size:1.6rem;font-weight:700}h2{font-size:1.3rem;font-weight:650}h3{font-size:1.05rem;font-weight:650}h4{font-size:.92rem;font-weight:600}
p,li,label,span{color:inherit}
a{color:var(--primary-hover);text-decoration:none}a:hover{text-decoration:underline}
hr{border-color:var(--border);margin:.8rem 0}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{background:var(--sidebar)!important;border-right:1px solid var(--border);}
[data-testid="stSidebar"] .block-container,[data-testid="stSidebarUserContent"]{padding:1rem .9rem!important}
.iq-brand{display:flex;align-items:center;gap:.65rem;margin:.1rem 0 1rem;padding-bottom:.75rem;border-bottom:1px solid rgba(34,50,76,.6)}
.iq-logo{width:32px;height:32px;border-radius:8px;background:linear-gradient(135deg,var(--primary) 0%,#0958d9 100%);display:flex;align-items:center;justify-content:center;
color:#fff;font-weight:750;font-size:14px;letter-spacing:-.02em;box-shadow:0 2px 6px rgba(22,119,255,.3)}
.iq-brand-name{font-size:1.02rem;font-weight:700;color:var(--text);line-height:1.15}
.iq-brand-sub{font-size:.7rem;color:var(--muted);font-weight:500}
.iq-side-label{font-size:.66rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin:1rem 0 .35rem;font-weight:650}
[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"]{gap:3px}
[data-testid="stSidebar"] [data-testid="stRadio"] label{padding:.5rem .75rem;border-radius:var(--radius-sm);width:100%;
color:var(--text2);border:1px solid transparent;transition:all .15s ease;cursor:pointer}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover{background:rgba(22,119,255,.08);color:var(--text)}
[data-testid="stSidebar"] [data-testid="stRadio"] label>div:first-child{display:none}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){background:rgba(22,119,255,.14);color:var(--text);
border-color:rgba(22,119,255,.4);box-shadow:inset 3px 0 0 var(--primary)}
[data-testid="stSidebar"] [data-testid="stRadio"] label p{font-size:.88rem;font-weight:550}
.iq-mode{border:1px solid var(--border);background:var(--panel);border-radius:var(--radius-sm);padding:.55rem .7rem;margin-top:.4rem;font-size:.75rem;color:var(--text2);line-height:1.45}
.iq-mode b{color:var(--text)}

/* ---------- page header ---------- */
.iq-eyebrow{font-size:.68rem;letter-spacing:.09em;text-transform:uppercase;color:var(--primary-hover);font-weight:650;margin-bottom:.15rem}
.iq-title{font-size:1.65rem;font-weight:700;margin:0;color:var(--text);letter-spacing:-.02em;line-height:1.2}
.iq-subtitle{color:var(--text2);margin:.25rem 0 0;font-size:.88rem;max-width:820px;line-height:1.45}
.iq-header{margin-bottom:1.1rem;padding-bottom:.85rem;border-bottom:1px solid var(--border)}
.iq-section{margin:1.2rem 0 .45rem}
.iq-section h3{font-size:1.02rem;margin:0;font-weight:650}
.iq-section p{margin:.15rem 0 0;color:var(--muted);font-size:.82rem}

/* ---------- cards / metrics ---------- */
.iq-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.75rem;margin:.2rem 0 .45rem}
@media (max-width:640px){.iq-grid{grid-template-columns:1fr 1fr}}
@media (max-width:440px){.iq-grid{grid-template-columns:1fr}}
.iq-metric{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:.85rem 1rem;
transition:border-color .15s,box-shadow .15s;position:relative;overflow:hidden}
.iq-metric:hover{border-color:var(--border-light);box-shadow:0 2px 8px rgba(0,0,0,.2)}
.iq-metric .l{font-size:.74rem;color:var(--text2);font-weight:550;text-transform:uppercase;letter-spacing:.04em}
.iq-metric .v{font-size:1.75rem;font-weight:700;margin:.2rem 0 .05rem;color:var(--text);letter-spacing:-.02em;line-height:1.1}
.iq-metric .h{font-size:.72rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.iq-metric.tone-warning .v{color:var(--warning)}.iq-metric.tone-error .v{color:var(--error)}.iq-metric.tone-success .v{color:var(--success)}
.iq-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1rem 1.15rem;margin-bottom:.7rem}
.iq-card h4{margin:0 0 .35rem;font-size:.92rem;font-weight:650}
.iq-card p{margin:0;color:var(--text2);font-size:.85rem;line-height:1.5}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]){border-color:var(--border)}
div[data-testid="stVerticalBlockBorderWrapper"]{background:var(--panel);border-radius:var(--radius)}

/* ---------- badges ---------- */
.iq-badge{display:inline-flex;align-items:center;gap:.35rem;padding:.15rem .55rem;border-radius:999px;font-size:.72rem;font-weight:600;
border:1px solid var(--border);color:var(--text2);background:rgba(130,144,165,.1);white-space:nowrap;line-height:1.3}
.iq-badge i{width:6px;height:6px;border-radius:50%;background:currentColor;display:inline-block;flex-shrink:0}
.iq-badge.info{color:#6CB0FF;background:rgba(22,119,255,.12);border-color:rgba(22,119,255,.35)}
.iq-badge.success{color:var(--success);background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.35)}
.iq-badge.warning{color:var(--warning);background:rgba(245,158,11,.12);border-color:rgba(245,158,11,.35)}
.iq-badge.error{color:var(--error);background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.35)}
.iq-badge.neutral{color:var(--text2);background:rgba(130,144,165,.08);border-color:var(--border)}

/* ---------- callouts / empty states ---------- */
.iq-callout{display:flex;gap:.75rem;border-radius:var(--radius);padding:.75rem .95rem;margin:.4rem 0 .85rem;border:1px solid var(--border);
background:var(--panel);border-left-width:3px}
.iq-callout .t{font-weight:650;font-size:.88rem;color:var(--text)}.iq-callout .b{font-size:.84rem;color:var(--text2);margin-top:.12rem;line-height:1.45}
.iq-callout.info{border-left-color:var(--primary);background:linear-gradient(90deg,rgba(22,119,255,.07) 0%,var(--panel) 100%)}
.iq-callout.success{border-left-color:var(--success);background:linear-gradient(90deg,rgba(34,197,94,.07) 0%,var(--panel) 100%)}
.iq-callout.warning{border-left-color:var(--warning);background:linear-gradient(90deg,rgba(245,158,11,.07) 0%,var(--panel) 100%)}
.iq-callout.error{border-left-color:var(--error);background:linear-gradient(90deg,rgba(239,68,68,.07) 0%,var(--panel) 100%)}
.iq-empty{border:1px dashed var(--border);border-radius:var(--radius);padding:1.8rem 1.4rem;text-align:center;background:rgba(16,23,40,.4)}
.iq-empty .icon{font-size:1.6rem;margin-bottom:.35rem;opacity:.7}
.iq-empty .t{font-weight:650;color:var(--text);font-size:.92rem}.iq-empty .b{color:var(--muted);font-size:.84rem;margin-top:.25rem;max-width:520px;margin-left:auto;margin-right:auto;line-height:1.45}

/* ---------- funnel / stepper / bars ---------- */
.iq-funnel{display:flex;flex-direction:column;gap:.5rem}
.iq-frow{display:grid;grid-template-columns:110px 1fr 44px;align-items:center;gap:.75rem;font-size:.84rem;color:var(--text2)}
.iq-ftrack{height:8px;background:#0D1422;border-radius:99px;overflow:hidden;border:1px solid var(--border)}
.iq-ffill{height:100%;background:var(--primary);border-radius:99px;transition:width .4s ease}
.iq-frow .n{text-align:right;color:var(--text);font-weight:650}
.iq-stepper{display:flex;gap:.35rem;flex-wrap:wrap;margin:.35rem 0 .85rem}
.iq-step{flex:1;min-width:115px;padding:.55rem .7rem;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--panel);font-size:.78rem;color:var(--muted)}
.iq-step .n{font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.iq-step.done{color:var(--text2);border-color:rgba(34,197,94,.35);background:rgba(34,197,94,.04)}.iq-step.done .n{color:var(--success)}
.iq-step.current{color:var(--text);border-color:var(--primary);background:rgba(22,119,255,.12);box-shadow:0 0 0 1px rgba(22,119,255,.3)}.iq-step.current .n{color:var(--primary-hover);font-weight:700}
.iq-bar{display:flex;align-items:center;gap:.55rem;min-width:110px}
.iq-bar .track{flex:1;height:6px;background:#0D1422;border-radius:99px;overflow:hidden}
.iq-bar .fill{height:100%;border-radius:99px;background:var(--primary)}
.iq-bar .fill.success{background:var(--success)}.iq-bar .fill.warning{background:var(--warning)}.iq-bar .fill.error{background:var(--error)}
.iq-bar span{font-size:.78rem;color:var(--text);min-width:2.2rem;text-align:right;font-variant-numeric:tabular-nums;font-weight:600}

/* ---------- table ---------- */
.iq-tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--border);border-radius:var(--radius);background:var(--panel);margin:.35rem 0 .75rem}
table.iq-table{width:100%;border-collapse:collapse;font-size:.84rem}
.iq-table th{text-align:left;font-weight:650;font-size:.7rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
padding:.65rem .85rem;background:#0D1422;border-bottom:1px solid var(--border);white-space:nowrap}
.iq-table td{padding:.65rem .85rem;border-bottom:1px solid #1A263B;color:var(--text2);vertical-align:middle;word-break:break-word;overflow-wrap:anywhere}
.iq-table tr:last-child td{border-bottom:0}.iq-table tr:hover td{background:rgba(22,119,255,.04)}
.iq-table td.strong{color:var(--text);font-weight:600}.iq-table td.r,.iq-table th.r{text-align:right}

/* ---------- key/value, quotes, trace ---------- */
.iq-kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.75rem 1.25rem}
.iq-kv .k{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-weight:600}.iq-kv .v{color:var(--text);margin-top:.12rem;font-size:.88rem;word-break:break-word}
.iq-quote{border-left:2px solid var(--primary);padding:.35rem .85rem;margin:.35rem 0;color:var(--text2);font-size:.85rem;background:rgba(22,119,255,.05);border-radius:0 var(--radius-sm) var(--radius-sm) 0;word-break:break-word}
.iq-trace{border-left:2px solid var(--border);margin-left:.35rem;padding-left:1rem}
.iq-turn{position:relative;margin-bottom:.85rem;padding:.75rem .95rem;background:var(--card);border:1px solid var(--border);border-radius:var(--radius)}
.iq-turn:before{content:"";position:absolute;left:-1.45rem;top:.95rem;width:8px;height:8px;border-radius:50%;background:var(--primary);border:2px solid var(--bg)}
.iq-turn .top{display:flex;gap:.45rem;align-items:center;flex-wrap:wrap;margin-bottom:.35rem;font-size:.78rem;color:var(--muted)}
.iq-turn .row{font-size:.84rem;color:var(--text2);margin-top:.25rem;line-height:1.45}.iq-turn .row b{color:var(--text);font-weight:600}
.iq-question{background:var(--card);border:1px solid rgba(22,119,255,.35);border-radius:var(--radius);padding:1rem 1.2rem;margin:.5rem 0 .85rem}
.iq-question .l{font-size:.68rem;letter-spacing:.09em;text-transform:uppercase;color:var(--primary-hover);font-weight:650}
.iq-question .q{font-size:1.1rem;color:var(--text);margin-top:.3rem;line-height:1.45;font-weight:550}

/* ---------- competency evidence presentation ---------- */
.iq-comp-box{border:1px solid var(--border);background:var(--panel);border-radius:var(--radius);padding:1rem 1.15rem;margin:.35rem 0 .75rem;transition:border-color .15s}
.iq-comp-box:hover{border-color:rgba(22,119,255,.35)}
.iq-comp-top{display:flex;justify-content:space-between;align-items:flex-start;gap:.75rem;margin-bottom:.45rem;flex-wrap:wrap}
.iq-comp-title{font-size:1.02rem;font-weight:650;color:var(--text);letter-spacing:-.01em;display:flex;align-items:center;gap:.55rem}
.iq-comp-desc{font-size:.82rem;color:var(--text2);margin-bottom:.75rem;line-height:1.4}
.iq-card-title{font-size:.72rem;font-weight:650;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:.75rem 0 .35rem;display:flex;align-items:center;gap:.4rem}
.iq-card-title.accent{color:var(--primary-hover)}
.iq-ev-card{background:var(--card);border:1px solid var(--border);border-left:3px solid var(--primary);border-radius:var(--radius-sm);padding:.65rem .85rem;margin-bottom:.45rem;font-size:.84rem;color:var(--text);line-height:1.5;word-break:break-word}
.iq-ev-empty{background:rgba(16,23,40,.6);border:1px dashed var(--border);border-left:3px solid var(--muted);border-radius:var(--radius-sm);padding:.75rem .95rem;color:var(--muted);font-size:.82rem;font-style:italic}
.iq-rationale-box{background:rgba(22,119,255,.05);border:1px solid rgba(22,119,255,.2);border-radius:var(--radius-sm);padding:.75rem .95rem;margin:.45rem 0 .7rem;font-size:.84rem;color:var(--text2);line-height:1.5;word-break:break-word}
.iq-gap-grid{display:grid;grid-template-columns:1fr 1fr;gap:.75rem;margin:.5rem 0 .75rem}
@media (max-width:768px){.iq-gap-grid{grid-template-columns:1fr}}
.iq-gap-col{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm);padding:.75rem .95rem}
.iq-gap-col.demonstrated{border-top:3px solid var(--success)}
.iq-gap-col.missing{border-top:3px solid var(--warning)}
.iq-gap-list{list-style:none;padding:0;margin:0}
.iq-gap-item{font-size:.81rem;color:var(--text2);margin-bottom:.35rem;display:flex;align-items:flex-start;gap:.4rem;line-height:1.4}
.iq-gap-item:last-child{margin-bottom:0}
.iq-gap-item i{font-style:normal;font-weight:700;flex-shrink:0}
.iq-gap-col.demonstrated .iq-gap-item i{color:var(--success)}
.iq-gap-col.missing .iq-gap-item i{color:var(--warning)}
.iq-probe-box{background:var(--card);border:1px solid rgba(22,119,255,.3);border-radius:var(--radius-sm);padding:.8rem 1rem;margin-top:.6rem}
.iq-probe-item{margin-bottom:.5rem}
.iq-probe-item:last-child{margin-bottom:0}
.iq-probe-tag{font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;color:var(--primary-hover);font-weight:650;margin-bottom:.15rem}
.iq-probe-q{background:rgba(22,119,255,.08);border-left:2px solid var(--primary-hover);padding:.5rem .75rem;border-radius:0 6px 6px 0;font-size:.84rem;color:var(--text);font-weight:500;line-height:1.4;word-break:break-word}

/* ---------- shortlist candidate cards ---------- */
.iq-sl-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:.85rem;flex-wrap:wrap;gap:.65rem}
.iq-sl-pill{display:inline-flex;align-items:center;gap:.4rem;background:#131C2E;border:1px solid #1E2D47;border-radius:20px;padding:.3rem .75rem;font-size:.78rem;font-weight:600;color:var(--text)}
.iq-sl-pill i{width:7px;height:7px;border-radius:50%;background:var(--primary)}
.iq-cand-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:.85rem 1.05rem;margin-bottom:.65rem;transition:border-color .15s,box-shadow .15s;position:relative}
.iq-cand-card:hover{border-color:rgba(22,119,255,.4)}
.iq-cand-card.is-selected{border-color:var(--primary);border-left:4px solid var(--primary);background:linear-gradient(90deg,rgba(22,119,255,.06) 0%,var(--card) 40%)}
.iq-cand-card.is-locked{border-color:var(--border);border-left:4px solid var(--muted);opacity:.85}
.iq-cand-top{display:flex;align-items:flex-start;justify-content:space-between;gap:.75rem;flex-wrap:wrap}
.iq-cand-meta{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;min-width:0}
.iq-rank-badge{background:#111A2C;color:var(--primary-hover);border:1px solid rgba(22,119,255,.4);border-radius:5px;padding:.15rem .45rem;font-size:.74rem;font-weight:700;letter-spacing:.02em}
.iq-cand-name{font-size:1rem;font-weight:650;color:var(--text);letter-spacing:-.01em;word-break:break-word}
.iq-cand-role{font-size:.78rem;color:var(--muted);margin-top:.15rem;word-break:break-word}
.iq-cand-scorebox{display:flex;align-items:center;gap:.65rem}
.iq-cand-score{font-weight:700;font-size:1.05rem;color:var(--text)}
.iq-cand-score small{font-size:.72rem;color:var(--muted);font-weight:400}
.iq-sl-confirm-box{background:var(--card);border:1px solid rgba(22,119,255,.3);border-radius:var(--radius);padding:1rem 1.15rem;margin-top:1rem}

/* ---------- identity review styles ---------- */
.iq-id-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1rem 1.15rem;margin-bottom:.85rem;transition:border-color .15s}
.iq-id-card:hover{border-color:rgba(22,119,255,.35)}
.iq-id-card.inconclusive{border-left:4px solid var(--warning)}
.iq-id-card.failed{border-left:4px solid var(--error)}
.iq-id-card.pending{border-left:4px solid var(--primary)}
.iq-id-card.passed{border-left:4px solid var(--success)}
.iq-id-top{display:flex;align-items:flex-start;justify-content:space-between;gap:.75rem;flex-wrap:wrap;margin-bottom:.5rem}
.iq-id-evidence{background:rgba(22,119,255,.04);border:1px solid rgba(22,119,255,.18);border-radius:var(--radius-sm);padding:.65rem .85rem;margin:.5rem 0 .7rem}
.iq-id-evidence-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.5rem;font-size:.82rem}
.iq-id-evidence-item{display:flex;flex-direction:column}
.iq-id-evidence-label{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.iq-id-evidence-val{font-weight:600;color:var(--text);margin-top:.12rem}
.iq-id-notice{font-size:.76rem;color:var(--warning);margin-top:.35rem;display:flex;align-items:center;gap:.3rem}

/* ---------- native widgets styling ---------- */
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{
  border-radius:var(--radius-sm);border:1px solid var(--border);
  background:var(--card);color:var(--text);font-weight:550;padding:.45rem .95rem;
  font-size:.86rem;transition:all .15s ease;min-height:36px;
}
.stButton>button:hover{border-color:var(--primary-hover);color:#fff;background:#1B2842}
.stButton>button:active{transform:translateY(1px)}
.stButton>button:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid var(--primary-hover)!important;outline-offset:2px}
.stButton>button[kind="primary"],button[data-testid="stBaseButton-primary"],[data-testid="stFormSubmitButton"]>button[kind="primaryFormSubmit"]{
  background:var(--primary)!important;border-color:var(--primary)!important;color:#fff!important;
  box-shadow:0 2px 6px rgba(22,119,255,.25);
}
.stButton>button[kind="primary"]:hover,button[data-testid="stBaseButton-primary"]:hover{
  background:var(--primary-hover)!important;border-color:var(--primary-hover)!important;
  box-shadow:0 3px 8px rgba(22,119,255,.35);
}
.stButton>button:disabled{opacity:.4;cursor:not-allowed}
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div,[data-testid="stNumberInput"] input{
  background:#0C1322!important;border:1px solid var(--border)!important;border-radius:var(--radius-sm)!important;color:var(--text)!important;
}
[data-baseweb="input"]:focus-within,[data-baseweb="textarea"]:focus-within,[data-baseweb="select"]>div:focus-within{
  border-color:var(--primary)!important;box-shadow:0 0 0 1px var(--primary)!important;
}
label[data-testid="stWidgetLabel"] p{color:var(--text2);font-size:.82rem;font-weight:550}
[data-baseweb="tab-list"]{gap:.35rem;border-bottom:1px solid var(--border);margin-bottom:.75rem}
button[data-baseweb="tab"]{background:transparent!important;color:var(--text2);padding:.5rem .85rem;font-size:.86rem;font-weight:550;border-radius:var(--radius-sm) var(--radius-sm) 0 0}
button[data-baseweb="tab"]:hover{color:var(--text)!important;background:rgba(22,119,255,.05)}
button[data-baseweb="tab"][aria-selected="true"]{color:var(--text)!important;font-weight:650}
[data-baseweb="tab-highlight"]{background:var(--primary)!important;height:2px!important}
[data-baseweb="tab-border"]{background:transparent!important}
[data-testid="stExpander"]{border:1px solid var(--border)!important;border-radius:var(--radius)!important;background:var(--panel);margin-bottom:.55rem}
[data-testid="stExpander"]:hover{border-color:rgba(22,119,255,.35)!important}
[data-testid="stExpander"] summary{font-weight:600;font-size:.86rem;padding:.55rem .85rem!important}
[data-testid="stExpander"] summary:hover{color:var(--text)}
[data-testid="stAlert"]{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:.75rem 1rem}
[data-testid="stFileUploader"] section{background:#0C1322;border:1px dashed #2E4161;border-radius:var(--radius);padding:1.25rem 1rem}
[data-testid="stChatMessage"]{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:.65rem .95rem}
[data-testid="stProgress"] div[role="progressbar"]>div{background:var(--primary)}
[data-testid="stDataFrame"]{border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:#23324C;border-radius:6px}::-webkit-scrollbar-thumb:hover{background:#344866}::-webkit-scrollbar-track{background:transparent}
"""


def css_block() -> str:
    return "<style>" + CSS.replace("\n", "") + "</style>"
