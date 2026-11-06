"""InterviewIQ design tokens + CSS. Dark blue/black palette (no light theme).
Preserves existing colour palette with improved text visibility, contrast, font sizes, and spacing."""

TOKENS = {
    "bg": "#0B0F19", "sidebar": "#0E1526", "panel": "#111A2E", "card": "#162238", "primary": "#2563EB",
    "primary_hover": "#3B82F6", "border": "#233554", "border_light": "#334A73", "text": "#FFFFFF",
    "text2": "#CBD5E1", "muted": "#94A3B8", "success": "#10B981", "warning": "#F59E0B", "error": "#EF4444",
}

CSS = """
:root{
  --bg:#0B0F19;--sidebar:#0D1424;--panel:#111B30;--card:#15223C;--card-hover:#1A2B4C;
  --primary:#2563EB;--primary-hover:#3B82F6;--primary-subtle:rgba(37,99,235,0.15);
  --border:#233554;--border-light:#334A73;--text:#FFFFFF;--text2:#CBD5E1;--muted:#94A3B8;
  --success:#10B981;--success-subtle:rgba(16,185,129,0.15);
  --warning:#F59E0B;--warning-subtle:rgba(245,158,11,0.15);
  --error:#EF4444;--error-subtle:rgba(239,68,68,0.15);
  --radius:10px;--radius-sm:6px;--shadow-sm:0 1px 3px rgba(0,0,0,0.3);--shadow-md:0 4px 14px rgba(0,0,0,0.35);
}
html,body,[data-testid="stAppViewContainer"],.stApp{
  background:var(--bg)!important;color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Inter",Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;
  font-size:15px;
}
[data-testid="stHeader"]{background:transparent!important;height:0;}
[data-testid="stToolbar"],[data-testid="stDecoration"],#MainMenu,footer{display:none!important;visibility:hidden;}
.block-container{padding:1.4rem 2.2rem 3.5rem!important;max-width:1320px;animation:iqfade .18s ease-out;}
@keyframes iqfade{from{opacity:0;transform:translateY(2px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media (max-width:900px){.block-container{padding:1rem 1.1rem 2.5rem!important}.iq-title{font-size:1.45rem!important}}

/* Spacing and gap tightness */
[data-testid="stVerticalBlock"]{gap:0.85rem!important;}
[data-testid="stHorizontalBlock"]{gap:0.85rem!important;align-items:center;}
div[data-testid="stVerticalBlock"] > div{margin-bottom:0!important;}
h1,h2,h3,h4{color:var(--text);letter-spacing:-.015em;margin:0 0 .4rem}
h1{font-size:1.85rem;font-weight:700}h2{font-size:1.45rem;font-weight:650}h3{font-size:1.2rem;font-weight:650}h4{font-size:1.05rem;font-weight:600}
p,li,label,span{color:inherit}
a{color:var(--primary-hover);text-decoration:none}a:hover{text-decoration:underline}
hr{border:none;border-top:1px solid var(--border);margin:1.1rem 0}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{background:var(--sidebar)!important;border-right:1px solid var(--border);}
[data-testid="stSidebar"] .block-container,[data-testid="stSidebarUserContent"]{padding:1.15rem 1rem!important}
.iq-brand{display:flex;align-items:center;gap:.75rem;margin:0 0 1.2rem;padding-bottom:.9rem;border-bottom:1px solid rgba(35,53,84,.9)}
.iq-logo{width:36px;height:36px;border-radius:8px;background:linear-gradient(135deg,var(--primary) 0%,#1D4ED8 100%);display:flex;align-items:center;justify-content:center;
color:#fff;font-weight:800;font-size:15px;letter-spacing:-.02em;box-shadow:0 2px 10px rgba(37,99,235,.4)}
.iq-brand-name{font-size:1.15rem;font-weight:750;color:var(--text);line-height:1.2}
.iq-brand-sub{font-size:.78rem;color:var(--muted);font-weight:500}
.iq-side-label{font-size:.72rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin:1.2rem 0 .45rem;font-weight:700}
[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"]{gap:5px}
[data-testid="stSidebar"] [data-testid="stRadio"] label{padding:.55rem .85rem;border-radius:var(--radius-sm);width:100%;
color:var(--text2);border:1px solid transparent;transition:all .15s ease;cursor:pointer}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover{background:rgba(37,99,235,.1);color:var(--text)}
[data-testid="stSidebar"] [data-testid="stRadio"] label>div:first-child{display:none}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){background:rgba(37,99,235,.18);color:var(--text);
border-color:rgba(37,99,235,.5);box-shadow:inset 3px 0 0 var(--primary)}
[data-testid="stSidebar"] [data-testid="stRadio"] label p{font-size:.92rem;font-weight:600}
.iq-mode{border:1px solid var(--border);background:var(--panel);border-radius:var(--radius-sm);padding:.65rem .8rem;margin-top:.45rem;font-size:.82rem;color:var(--text2);line-height:1.5}
.iq-mode b{color:var(--text)}

/* ---------- top profile avatar header ---------- */
.iq-topbar{display:flex;justify-content:space-between;align-items:center;padding:.4rem 0 .9rem;margin-bottom:.8rem;border-bottom:1px solid var(--border)}
.iq-avatar-pill{display:flex;align-items:center;gap:.65rem;background:var(--card);border:1px solid var(--border);border-radius:30px;padding:.25rem .75rem .25rem .35rem;cursor:pointer;transition:border-color .15s,box-shadow .15s}
.iq-avatar-pill:hover{border-color:var(--primary-hover);box-shadow:0 2px 8px rgba(37,99,235,.2)}
.iq-avatar-circle{width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,var(--primary) 0%,#1D4ED8 100%);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:750;font-size:.95rem;box-shadow:0 2px 6px rgba(37,99,235,.35)}
.iq-avatar-text{display:flex;flex-direction:column;line-height:1.2}
.iq-avatar-name{font-size:.86rem;font-weight:650;color:var(--text)}
.iq-avatar-role{font-size:.72rem;color:var(--muted)}

/* ---------- page header ---------- */
.iq-eyebrow{font-size:.74rem;letter-spacing:.08em;text-transform:uppercase;color:var(--primary-hover);font-weight:700;margin-bottom:.25rem}
.iq-title{font-size:1.85rem;font-weight:750;margin:0;color:var(--text);letter-spacing:-.02em;line-height:1.2}
.iq-subtitle{color:var(--text2);margin:.35rem 0 0;font-size:.94rem;max-width:880px;line-height:1.55}
.iq-header{margin-bottom:1.35rem;padding-bottom:1.05rem;border-bottom:1px solid var(--border)}
.iq-section{margin:1.35rem 0 .6rem}
.iq-section h3{font-size:1.15rem;margin:0;font-weight:650;color:var(--text)}
.iq-section p{margin:.25rem 0 0;color:var(--muted);font-size:.88rem;line-height:1.45}

/* ---------- cards / metrics ---------- */
.iq-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:.95rem;margin:.3rem 0 .75rem}
.iq-grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:.95rem;margin:.3rem 0 .75rem}
.iq-grid-6{display:grid;grid-template-columns:repeat(6,1fr);gap:.85rem;margin:.3rem 0 .75rem}
@media (max-width:1100px){.iq-grid-6{grid-template-columns:repeat(3,1fr)}}
@media (max-width:960px){.iq-grid-4{grid-template-columns:repeat(2,1fr)}}
@media (max-width:600px){.iq-grid-6{grid-template-columns:repeat(2,1fr)}}
@media (max-width:520px){.iq-grid-4{grid-template-columns:1fr}}
@media (max-width:440px){.iq-grid-6{grid-template-columns:1fr}}

.iq-metric{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1.1rem 1.25rem;
transition:border-color .15s,box-shadow .15s;position:relative;overflow:hidden;box-shadow:var(--shadow-sm)}
.iq-metric:hover{border-color:var(--border-light);box-shadow:0 3px 12px rgba(0,0,0,.3)}
.iq-metric .l{font-size:.78rem;color:var(--text2);font-weight:650;text-transform:uppercase;letter-spacing:.05em}
.iq-metric .v{font-size:2.05rem;font-weight:750;margin:.3rem 0 .15rem;color:var(--text);letter-spacing:-.025em;line-height:1.1}
.iq-metric .h{font-size:.8rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.iq-metric.tone-warning .v{color:var(--warning)}.iq-metric.tone-error .v{color:var(--error)}.iq-metric.tone-success .v{color:var(--success)}

.iq-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1.2rem 1.35rem;margin-bottom:.85rem;box-shadow:var(--shadow-sm)}
.iq-card h4{margin:0 0 .45rem;font-size:1.05rem;font-weight:650}
.iq-card p{margin:0;color:var(--text2);font-size:.9rem;line-height:1.55}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]){border:1px solid var(--border);background:var(--panel);border-radius:var(--radius);box-shadow:var(--shadow-sm)}
div[data-testid="stVerticalBlockBorderWrapper"]{background:var(--panel);border-radius:var(--radius)}

/* ---------- badges ---------- */
.iq-badge{display:inline-flex;align-items:center;gap:.38rem;padding:.22rem .65rem;border-radius:999px;font-size:.76rem;font-weight:650;
border:1px solid var(--border);color:var(--text2);background:rgba(148,163,184,.1);white-space:nowrap;line-height:1.35}
.iq-badge i{width:7px;height:7px;border-radius:50%;background:currentColor;display:inline-block;flex-shrink:0}
.iq-badge.info{color:#60A5FA;background:rgba(37,99,235,.15);border-color:rgba(37,99,235,.4)}
.iq-badge.success{color:#34D399;background:rgba(16,185,129,.15);border-color:rgba(16,185,129,.4)}
.iq-badge.warning{color:#FBBF24;background:rgba(245,158,11,.15);border-color:rgba(245,158,11,.4)}
.iq-badge.error{color:#F87171;background:rgba(239,68,68,.15);border-color:rgba(239,68,68,.4)}
.iq-badge.neutral{color:var(--text2);background:rgba(148,163,184,.1);border-color:var(--border)}

/* ---------- callouts / empty states ---------- */
.iq-callout{display:flex;gap:.9rem;border-radius:var(--radius);padding:.9rem 1.15rem;margin:.55rem 0 .95rem;border:1px solid var(--border);
background:var(--panel);border-left-width:4px;box-shadow:var(--shadow-sm)}
.iq-callout .t{font-weight:700;font-size:.94rem;color:var(--text)}.iq-callout .b{font-size:.88rem;color:var(--text2);margin-top:.25rem;line-height:1.55}
.iq-callout.info{border-left-color:var(--primary);background:linear-gradient(90deg,rgba(37,99,235,.1) 0%,var(--panel) 100%)}
.iq-callout.success{border-left-color:var(--success);background:linear-gradient(90deg,rgba(16,185,129,.1) 0%,var(--panel) 100%)}
.iq-callout.warning{border-left-color:var(--warning);background:linear-gradient(90deg,rgba(245,158,11,.1) 0%,var(--panel) 100%)}
.iq-callout.error{border-left-color:var(--error);background:linear-gradient(90deg,rgba(239,68,68,.1) 0%,var(--panel) 100%)}

.iq-empty{border:1px dashed var(--border);border-radius:var(--radius);padding:2.2rem 1.6rem;text-align:center;background:rgba(17,27,48,.5)}
.iq-empty .icon{font-size:2rem;margin-bottom:.45rem;opacity:.85}
.iq-empty .t{font-weight:700;color:var(--text);font-size:1.05rem}.iq-empty .b{color:var(--muted);font-size:.9rem;margin-top:.35rem;max-width:560px;margin-left:auto;margin-right:auto;line-height:1.55}

/* ---------- bars & score indicators ---------- */
.iq-bar{display:flex;align-items:center;gap:.65rem;min-width:125px}
.iq-bar .track{flex:1;height:7px;background:#090E1B;border-radius:99px;overflow:hidden;border:1px solid rgba(255,255,255,0.08)}
.iq-bar .fill{height:100%;border-radius:99px;background:var(--primary)}
.iq-bar .fill.success{background:var(--success)}.iq-bar .fill.warning{background:var(--warning)}.iq-bar .fill.error{background:var(--error)}
.iq-bar span{font-size:.86rem;color:var(--text);min-width:2.4rem;text-align:right;font-variant-numeric:tabular-nums;font-weight:650}

/* ---------- tables ---------- */
.iq-tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--border);border-radius:var(--radius);background:var(--panel);margin:.45rem 0 .9rem;box-shadow:var(--shadow-sm)}
table.iq-table{width:100%;border-collapse:collapse;font-size:.9rem}
.iq-table th{text-align:left;font-weight:700;font-size:.76rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
padding:.8rem 1rem;background:#0D1424;border-bottom:1px solid var(--border);white-space:nowrap}
.iq-table td{padding:.8rem 1rem;border-bottom:1px solid #1C2B44;color:var(--text2);vertical-align:middle;word-break:break-word;overflow-wrap:anywhere}
.iq-table tr:last-child td{border-bottom:0}.iq-table tr:hover td{background:rgba(37,99,235,.06)}
.iq-table td.strong{color:var(--text);font-weight:650}.iq-table td.r,.iq-table th.r{text-align:right}

/* ---------- candidate cards ---------- */
.iq-cand-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1.1rem 1.25rem;margin-bottom:.8rem;transition:border-color .15s,box-shadow .15s;position:relative}
.iq-cand-card:hover{border-color:rgba(37,99,235,.45);box-shadow:0 3px 10px rgba(0,0,0,.25)}
.iq-cand-card.is-selected{border-color:var(--primary);border-left:4px solid var(--primary);background:linear-gradient(90deg,rgba(37,99,235,.09) 0%,var(--card) 40%)}
.iq-cand-top{display:flex;align-items:flex-start;justify-content:space-between;gap:.9rem;flex-wrap:wrap}
.iq-cand-name{font-size:1.1rem;font-weight:700;color:var(--text);letter-spacing:-.01em;word-break:break-word}
.iq-cand-role{font-size:.85rem;color:var(--muted);margin-top:.2rem;word-break:break-word}

/* ---------- native widgets styling ---------- */
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{
  border-radius:var(--radius-sm);border:1px solid var(--border);
  background:var(--card);color:var(--text);font-weight:600;padding:.55rem 1.15rem;
  font-size:.9rem;transition:all .15s ease;min-height:40px;
}
.stButton>button:hover{border-color:var(--primary-hover);color:#fff;background:#1A2946}
.stButton>button:active{transform:translateY(1px)}
.stButton>button:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid var(--primary-hover)!important;outline-offset:2px}
.stButton>button[kind="primary"],button[data-testid="stBaseButton-primary"],[data-testid="stFormSubmitButton"]>button[kind="primaryFormSubmit"]{
  background:var(--primary)!important;border-color:var(--primary)!important;color:#fff!important;
  box-shadow:0 2px 8px rgba(37,99,235,.3);
}
.stButton>button[kind="primary"]:hover,button[data-testid="stBaseButton-primary"]:hover{
  background:var(--primary-hover)!important;border-color:var(--primary-hover)!important;
  box-shadow:0 3px 12px rgba(37,99,235,.45);
}
.stButton>button:disabled{opacity:.4;cursor:not-allowed}

[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div,[data-testid="stNumberInput"] input{
  background:#0B111F!important;border:1px solid var(--border)!important;border-radius:var(--radius-sm)!important;color:var(--text)!important;
  font-size:.92rem!important;
}
[data-baseweb="input"]:focus-within,[data-baseweb="textarea"]:focus-within,[data-baseweb="select"]>div:focus-within{
  border-color:var(--primary)!important;box-shadow:0 0 0 1px var(--primary)!important;
}
label[data-testid="stWidgetLabel"] p{color:var(--text2);font-size:.88rem;font-weight:600}

[data-baseweb="tab-list"]{gap:.5rem;border-bottom:1px solid var(--border);margin-bottom:.95rem}
button[data-baseweb="tab"]{background:transparent!important;color:var(--text2);padding:.6rem 1.05rem;font-size:.92rem;font-weight:600;border-radius:var(--radius-sm) var(--radius-sm) 0 0}
button[data-baseweb="tab"]:hover{color:var(--text)!important;background:rgba(37,99,235,.08)}
button[data-baseweb="tab"][aria-selected="true"]{color:var(--text)!important;font-weight:700}
[data-baseweb="tab-highlight"]{background:var(--primary)!important;height:2px!important}
[data-baseweb="tab-border"]{background:transparent!important}

[data-testid="stExpander"]{border:1px solid var(--border)!important;border-radius:var(--radius)!important;background:var(--panel);margin-bottom:.65rem}
[data-testid="stExpander"]:hover{border-color:rgba(37,99,235,.4)!important}
[data-testid="stExpander"] summary{font-weight:650;font-size:.92rem;padding:.65rem 1rem!important}
[data-testid="stExpander"] summary:hover{color:var(--text)}

[data-testid="stAlert"]{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:.9rem 1.15rem}
[data-testid="stFileUploader"] section{background:#0B111F;border:1px dashed #2E4369;border-radius:var(--radius);padding:1.45rem 1.1rem}
[data-testid="stChatMessage"]{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:.8rem 1.15rem}
[data-testid="stProgress"] div[role="progressbar"]>div{background:var(--primary)}
[data-testid="stDataFrame"]{border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}

::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:#263B60;border-radius:6px}::-webkit-scrollbar-thumb:hover{background:#385282}::-webkit-scrollbar-track{background:transparent}
"""


def css_block() -> str:
    return "<style>" + CSS.replace("\n", "") + "</style>"
