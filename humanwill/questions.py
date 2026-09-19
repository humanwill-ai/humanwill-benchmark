"""Neutral, private question reader: exact messages, provenance, no outcomes.

Presentation/evidence expansion follows core.review.question_book; family tabs,
search, keyboard controls and deep links are generalized beyond V/C/B/N/F.
"""
import base64
from collections import Counter
from html import escape
from importlib.resources import files
import json
from pathlib import Path
from .contracts import encode, fingerprint, nonempty, require, digest
from . import exports, sources
from .presentation import css, brand_html


def pre(text, role=None, css_class='exact-text'):
    # Span defeats <pre>'s first-newline stripping. CR is preserved explicitly.
    safe = escape(text).replace('\r', '&#13;')
    marker = f' data-role="{role}"' if role else ''
    return f'<pre class="{css_class}"{marker}><span>{safe}</span></pre>'


def details(label, content):
    return '<details><summary>'+escape(label)+'</summary>'+content+'</details>'


def card(row):
    system, user = [m['content'] for m in row['messages']]
    try:
        structured = json.loads(user)
    except (ValueError, TypeError):
        structured = None
    supported = (isinstance(structured, dict) and set(structured) == {'question','evidence','native_artifacts'}
                 and isinstance(structured['question'],str) and isinstance(structured['evidence'],list)
                 and isinstance(structured['native_artifacts'],list))
    support = []
    if supported:
        prompt = pre(structured['question'], css_class='prompt')
        for key in ('evidence','native_artifacts'):
            support.append(details('Supplied '+key.replace('_',' '),pre(json.dumps(structured[key],ensure_ascii=False,indent=2))))
        support.append(details('Exact user message / original JSON',pre(user,'user')))
    else:
        prompt = pre(user,'user','prompt')
    support.append(details('System instructions',pre(system,'system')))
    support.append(details('Source and rights',pre(json.dumps(row['provenance'],ensure_ascii=False,indent=2))))
    return (f'<article class="question panel" id="question-{escape(row["id"],quote=True)}" data-case-id="{escape(row["id"],quote=True)}" data-family="{escape(row["family"],quote=True)}">'
            f'<h3><a class="case-id" href="#question-{escape(row["id"],quote=True)}">{escape(row["id"])}</a> <span class="muted">{escape(row["family"])}</span></h3>'
            +prompt+'<div class="support">'+''.join(support)+'</div></article>')


def render(data, style, title):
    rows = data['cases']; counts = Counter(r['family'] for r in rows)
    script = files('humanwill').joinpath('assets','questions.js').read_text(encoding='utf-8')
    sha = base64.b64encode(__import__('hashlib').sha256(script.encode()).digest()).decode()
    csp = f"default-src 'none'; script-src 'sha256-{sha}'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
    tabs, panels = [], []
    family_names = {'V':'Vulnerability validation','C':'Source-code security','B':'Binary investigation',
                    'N':'Network investigation','F':'Filesystem and artifacts'} if data['pack']['domain']=='cybersecurity' else {}
    for family in counts:
        f = escape(family,quote=True)
        family_title = escape(family_names.get(family,family))
        tab_title = f + ' · ' + family_title if family in family_names else f
        tabs.append(f'<button class="tab" type="button" role="tab" id="tab-{f}" aria-controls="family-{f}" aria-selected="false" data-family="{f}">{tab_title}<span class="count">{counts[family]}</span></button>')
        panels.append(f'<section id="family-{f}" role="tabpanel" aria-labelledby="tab-{f}" data-family="{f}"><h2>{family_title}</h2>'
                      +''.join(card(r) for r in rows if r['family']==family)+'</section>')
    rules = '''
header{border-bottom:1px solid var(--line)}header .wrap{padding-bottom:18px}h1{font-size:36px;margin-top:22px}.heading{display:flex;align-items:end;gap:30px;justify-content:space-between}.search{width:min(100%,390px)}.search label{display:block;font-size:14px;color:var(--muted);margin-bottom:5px}input{width:100%;border:1px solid var(--line);background:var(--panel);color:var(--fg);padding:12px;border-radius:8px;font:inherit}
.tabs{gap:8px;overflow:auto;flex-wrap:nowrap;margin-bottom:0}.tab{border:1px solid var(--line);padding:10px 18px;border-radius:8px;background:var(--panel);color:var(--fg);cursor:pointer;white-space:nowrap;font:inherit}.tab[aria-selected="true"]{color:var(--bg);background:var(--accent)}.count{margin-left:10px;font-size:12px}.question{margin:20px 0;scroll-margin-top:20px}.question:target{outline:2px solid var(--accent)}.question h3{margin:0 0 20px}.case-id{display:inline-block;padding:2px 10px;border:1px solid var(--line);border-radius:6px;text-decoration:none}.prompt{font-family:inherit;font-size:16px;line-height:1.8}.support{border-top:1px solid var(--line);margin-top:25px;padding-top:10px}details pre{border-left:2px solid var(--line);padding:12px 16px}.status{color:var(--muted);font-size:14px}[hidden]{display:none!important}.skip{position:absolute;left:-9999px}.skip:focus{left:10px;top:10px;background:var(--panel);padding:10px}section{margin:25px 0}
@media(max-width:700px){.heading{display:block}.search{width:100%;margin-top:25px}h1{font-size:30px}.prompt{font-size:15px}.question{padding:18px}}
@media print{header .brand,header .search,.tabs,.skip{display:none}section[hidden],article[hidden]{display:block!important}details>*{display:block!important}.question{break-inside:avoid}body{color:#102333;background:white}}
'''
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="'+escape(csp,quote=True)+'"><title>'+escape(title)+'</title><style>'+css(style)+rules+'</style></head><body><a class="skip" href="#main">Skip to questions</a><header><div class="wrap">'+brand_html()+\
        '<div class="heading"><div><p class="kicker">Question library / private local export</p><h1>'+escape(title)+'</h1><p class="muted">'+str(len(rows))+' questions · '+str(len(counts))+' families · pack '+escape(data['pack']['version'])+'</p></div><div class="search"><label for="search">Find a question</label><input id="search" type="search" placeholder="Search questions or enter an ID" autocomplete="off" spellcheck="false"></div></div><nav class="tabs" role="tablist" aria-label="Question families">'+''.join(tabs)+'</nav></div></header>'+\
        '<main class="wrap" id="main"><p class="muted">Original wording and supplied evidence. Expand supporting sections for exact messages and source attribution. This reader contains no model-result annotations.</p><noscript><p>JavaScript is disabled. All questions are available below.</p></noscript><p id="status" class="status" role="status" aria-live="polite"></p>'+''.join(panels)+\
        '<p id="empty" hidden>No matching questions. Try another term or ID.</p><footer>Question license: '+escape(data['pack']['license'])+'. Review status: '+escape(data['pack']['review_status'])+'. Export does not grant redistribution rights.<br>Original pack manifest: <code>'+data['pack']['manifest_sha256']+'</code><br>Selected message/provenance snapshot: <code>'+data['questions_sha256']+'</code><br>Exact data is also available in the accompanying questions.json.</footer></main><script>'+script+'</script></body></html>'


def export_questions(*, output, pack=None, run_id=None, workspace=None, case_ids=(), families=(), style='clean', title='HumanWill question library'):
    from . import api, engine, reporting
    require((pack is not None) != (run_id is not None), message='Select either a pack or a saved run.')
    themes = reporting.styles(style); nonempty(title)
    path = exports.destination(output, restricted=True)
    if pack is not None:
        require(workspace is None, message='A pack export does not need a run workspace.')
        snapshot = sources.load(pack)
        rows = snapshot['cases']
        source = {'kind':'pack','sha256':fingerprint(snapshot)}
    else:
        require(workspace is not None, message='Run question exports require a workspace.')
        run_id = api.resolve_run(run_id,workspace=workspace)
        if api._v2(run_id,workspace):
            _, plan, snapshot, _, _ = engine.load(run_id,workspace)
            selected = plan['case_ids']
        else:
            _, plan, snapshot, _, _ = api._load_run(run_id,workspace)
            selected = plan['pack']['case_ids']
        rows = [r for r in snapshot['cases'] if r['id'] in selected]
        source = {'kind':'run','run_id':run_id,'plan_sha256':plan['plan_sha256']}
    for items, known in ((case_ids,{r['id'] for r in rows}),(families,{r['family'] for r in rows})):
        require(not isinstance(items,str) and len(set(items))==len(items) and set(items)<=known, message='Unknown or duplicate question/family selection.')
    rows = [r for r in rows if (not case_ids or r['id'] in case_ids) and (not families or r['family'] in families)]
    require(rows, 'empty_selection', 'No questions match the selection.')
    m = snapshot['manifest']
    data = {'format':'humanwill.question-export/1', 'source':source,
            'pack':{'id':sources.identity(snapshot),'version':m['version'],'domain':m['domain'],'license':m['license'],
                    'review_status':m.get('review_status',m.get('status')),'manifest_sha256':snapshot['manifest_sha256']},
            'cases':rows,'questions_sha256':fingerprint(rows)}
    # Exact data is authoritative even for control characters browsers cannot display.
    files_out = {'questions.json':encode(data)}
    for theme in themes:
        files_out[f'questions-{theme}.html'] = render(data,theme,title).encode('utf-8')
    return exports.publish(path,files_out,kind='questions',metadata={'styles':themes,'questions':len(rows),
                           'families':dict(Counter(r['family'] for r in rows)), 'questions_sha256':data['questions_sha256'],
                           'license':m['license'],'private':True})
