"""Reusable clean/spotlight charts and reports from verified aggregate snapshots.

Visual lineage: reports/cybersecurity/social/v0.1.1/build_social.py. All counts,
labels, populations and dates now come from the selected report, never a campaign.
"""
import base64
from html import escape
from importlib.resources import files
import io
import json
import textwrap
import threading
from .contracts import HumanWillError
from . import result_context

THEMES = {
    'clean': dict(bg='#FAFBFA', fg='#102B38', muted='#506671', grid='#DEE7E8', panel='#F0F4F3', teal='#087F76', gold='#AA7100'),
    'spotlight': dict(bg='#091321', fg='#F3F7FC', muted='#BACADB', grid='#2A3C50', panel='#142338', teal='#54E6C8', gold='#F3BD50')}
METRICS = {'refusal': ('False-refusal rate', 'false_refusal_rate', 'fr_classified', 100, '%'),
           'usefulness': ('Judged usefulness', 'mean_usefulness', 'usefulness_scored', 4, '/4')}
LOCK = threading.RLock()


def dependencies(pdf=False):
    try:
        import matplotlib
        if pdf:
            import reportlab  # noqa: F401
        return matplotlib
    except ImportError:
        raise HumanWillError('missing_dependency', 'Install humanwill-evals[reports] for visual reports and images.') from None


def logo():
    return files('humanwill').joinpath('assets', 'humanwill-logo.png').read_bytes()


def label(model):
    return model['label'] + ' [' + model['profile'][:8] + ']' + (' *' if model['simulated'] else '')


def value_text(value, metric):
    if value is None:
        return 'Not scored'
    return f'{value:.1%}' if metric == 'refusal' else f'{value:.2f}/4'


def _chunks(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def charts(data, style, formats=('png',)):
    mpl = dependencies()
    from matplotlib.figure import Figure
    from matplotlib.colors import LinearSegmentedColormap, to_rgb
    import matplotlib.image as mpimg
    import numpy as np
    t = THEMES[style]
    output = []
    families = sorted({f for m in data['profiles'] for f in m['families']})
    with LOCK, mpl.rc_context({'font.family':'DejaVu Sans', 'font.size':11, 'text.parse_math':False,
                              'svg.fonttype':'none', 'svg.hashsalt':data['report_sha256']}):
        for metric, (title, field, denominator, maximum, suffix) in METRICS.items():
            # Stable profile order across metrics: no implicit score/rank selection.
            for page, models in enumerate(_chunks(data['profiles'], 8), 1):
                for group, family_group in enumerate([[]] + _chunks(families, 6)):
                    matrix = bool(family_group)
                    height = max(6.4, 3.8 + len(models) * .58)
                    fig = Figure(figsize=(12, height), dpi=150, facecolor=t['bg'])
                    if style == 'spotlight':
                        back = fig.add_axes([0, 0, 1, 1], zorder=-10)
                        y, x = np.mgrid[0:1:260j, 0:1:400j]
                        glow = np.exp(-((x-.95)**2/.2 + (y-.93)**2/.15))
                        rgb = np.array(to_rgb(t['bg'])) + glow[:, :, None] * np.array([.06,.10,.14])
                        back.imshow(np.clip(rgb, 0, 1), extent=[0,1,0,1], origin='lower', aspect='auto'); back.axis('off')
                    brand = fig.add_axes([.045, .916, .038, .06])
                    brand.imshow(mpimg.imread(io.BytesIO(logo()), format='png')); brand.axis('off')
                    fig.text(.095,.944,'humanwill.ai',color=t['fg'],fontsize=15,weight='bold',va='center')
                    fig.text(.955,.944,result_context.banner(data,models).upper(),
                             color=t['gold'],ha='right',fontsize=10,weight='bold',va='center')
                    fig.text(.045,.859,title + (' by family' if matrix else ''),color=t['fg'],fontsize=24,weight='bold')
                    subtitle = ('Lower is better' if metric=='refusal' else 'Higher is better; judged, not verified execution')
                    fig.text(.045,.816,subtitle + f"  |  {data['pack']['selected_questions']} selected questions per profile",color=t['muted'],fontsize=10)
                    fig.text(.045,.777,result_context.summary(data),color=t['gold'],fontsize=10)
                    ax = fig.add_axes([.36, .235, .55, .49], facecolor='none')
                    names = ['\n'.join(textwrap.wrap(label(m), 31))+'\n'+
                             result_context.assessment_for(data,m)['kind'].capitalize()+' / '+
                             result_context.POLICIES[result_context.assessment_for(data,m)['policy']]
                             for m in models]
                    cmap = LinearSegmentedColormap.from_list('metric', [t['teal'],t['gold'],'#EF6577']) if metric=='refusal' else LinearSegmentedColormap.from_list('metric',['#8CA0AB',t['teal']])
                    audit = []
                    if matrix:
                        array = np.full((len(models), len(family_group)), np.nan)
                        for i, m in enumerate(models):
                            for j, family in enumerate(family_group):
                                stats = m['families'].get(family)
                                v = stats[field] if stats else None
                                n = stats[denominator] if stats else 0
                                total = stats['total'] if stats else 0
                                if v is not None: array[i,j] = v * 100 if metric=='refusal' else v
                                audit.append({'profile':m['profile'],'family':family,'value':v,'n':n,'total':total,
                                              'result_kind':result_context.assessment_for(data,m)['kind']})
                        cmap = cmap.with_extremes(bad=t['panel'])
                        ax.imshow(np.ma.masked_invalid(array),cmap=cmap,vmin=0,vmax=maximum,aspect='auto')
                        ax.set_xticks(range(len(family_group)), ['\n'.join(textwrap.wrap(f, 14)) for f in family_group],fontsize=9)
                        ax.xaxis.tick_top()
                        for i, m in enumerate(models):
                            for j, family in enumerate(family_group):
                                cell = audit[i*len(family_group)+j]
                                txt = value_text(cell['value'],metric) if cell['value'] is not None else 'N/A'
                                ax.text(j,i,f"{txt}\nn={cell['n']}/{cell['total']}",ha='center',va='center',
                                        fontsize=9,color=t['fg'] if cell['value'] is None else '#102333',weight='bold')
                        ax.set_xticks(np.arange(-.5,len(family_group),1),minor=True)
                        ax.set_yticks(np.arange(-.5,len(models),1),minor=True)
                        ax.grid(which='minor',color=t['bg'],linewidth=3); ax.tick_params(which='minor',length=0)
                    else:
                        for i, m in enumerate(models):
                            stats = m['overall']; v = stats[field]; n = stats[denominator]
                            audit.append({'profile':m['profile'],'family':None,'value':v,'n':n,'total':stats['total'],
                                          'result_kind':result_context.assessment_for(data,m)['kind']})
                            ax.barh(i,maximum,height=.55,color=t['panel'],zorder=1)
                            if v is not None:
                                scaled = v*100 if metric=='refusal' else v
                                ax.barh(i,scaled,height=.55,color=cmap(scaled/maximum),hatch='///' if n < stats['total'] else None,
                                        edgecolor=t['fg'] if n < stats['total'] else 'none',linewidth=.6,zorder=3)
                                if scaled == 0: ax.plot(0,i,'|',color=t['teal'],ms=22,mew=3,zorder=4)
                            txt = value_text(v,metric) + f'   n={n}/{stats["total"]}'
                            ax.text(0,i-.37,txt,va='center',color=t['fg'],fontsize=9,weight='bold')
                        ax.set_xlim(0,maximum); ax.set_ylim(len(models)-.4,-.7)
                        ax.set_xticks(np.linspace(0,maximum,6 if metric=='refusal' else 5))
                        ax.xaxis.grid(True,color=t['grid']); ax.set_axisbelow(True)
                    ax.set_yticks(range(len(models)),names,fontsize=9)
                    ax.tick_params(colors=t['muted'],length=0,pad=12)
                    for spine in ax.spines.values(): spine.set_visible(False)
                    fig.text(.045,.148,'n = scored / selected. Missing values are excluded; FR and usefulness denominators remain separate.',color=t['muted'],fontsize=9)
                    fig.text(.045,.114,'* Simulated profile. No model-performance claim.' if data['contains_simulation'] else 'Configuration labels do not certify calibration or comparability with historical results.',color=t['muted'],fontsize=9)
                    if any(m['coverage'].get('grading_methods',{}).get('native-block-fr-u/1',0) for m in models):
                        fig.text(.045,.09,'Includes local native-block-fr-u/1 scores (FR2/U0); see per-profile grading counts in the report.',color=t['muted'],fontsize=8)
                    fig.text(.045,.064,'Selection: '+data['source']['selection_policy']+'  |  '+data['source']['selection_sha256'][:16],color=t['muted'],fontsize=8)
                    fig.text(.955,.064,f'Profiles page {page}  |  '+style,ha='right',color=t['muted'],fontsize=8)
                    slug = f'{metric}-'+('families-'+str(group) if matrix else 'overall')+f'-{page:02d}'
                    item = {'slug':slug,'metric':metric,'title':title + (' by family' if matrix else ''),
                            'families':family_group,'profiles':[m['profile'] for m in models],'values':audit,
                            'result_label':result_context.banner(data,models)}
                    for kind in formats:
                        buffer = io.BytesIO()
                        metadata = {'Description':result_context.banner(data,models)+' | '+result_context.summary(data)+' | '+data['report_sha256']}
                        fig.savefig(buffer,format=kind,dpi=150,facecolor=fig.get_facecolor(),metadata=metadata)
                        item[kind] = buffer.getvalue()
                    fig.clear(); output.append(item)
    return output


def css(style):
    t = THEMES[style]
    background = t['bg'] if style == 'clean' else 'radial-gradient(ellipse at top right,#1b354b,transparent 65%),'+t['bg']
    return f''':root{{color-scheme:{'light' if style=='clean' else 'dark'};--bg:{t['bg']};--fg:{t['fg']};--muted:{t['muted']};--panel:{t['panel']};--line:{t['grid']};--accent:{t['teal']};--gold:{t['gold']}}}
*{{box-sizing:border-box}}body{{margin:0;background:{background};color:var(--fg);font:16px/1.65 system-ui,sans-serif}}
.wrap{{max-width:1180px;margin:auto;padding:36px 30px}}.brand{{display:flex;align-items:center;gap:14px;font-size:23px;font-weight:750}}
.brand img{{width:48px;height:48px;background:white;border-radius:6px}}.kicker{{color:var(--gold);letter-spacing:.13em;font-size:12px;font-weight:750;text-transform:uppercase}}
h1{{font-size:clamp(30px,5vw,54px);line-height:1.12;letter-spacing:-.035em;margin:28px 0 18px}}h2{{font-size:28px;letter-spacing:-.02em}}
p{{max-width:85ch}}.muted,small{{color:var(--muted)}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin:30px 0}}
.card,figure,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:22px}}.card strong{{font-size:28px;display:block}}
nav{{display:flex;gap:25px;flex-wrap:wrap;margin:22px 0}}a{{color:var(--accent)}}a:focus-visible,button:focus-visible,input:focus-visible{{outline:3px solid var(--gold);outline-offset:4px}}
section{{margin:45px 0}}.table-scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:13px 12px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}th:first-child,td:first-child{{text-align:left;white-space:normal;min-width:190px}}th{{color:var(--muted)}}
figure{{margin:24px 0;padding:0;overflow:hidden}}figure img{{display:block;width:100%;height:auto}}figcaption{{padding:12px 22px;font-size:13px;color:var(--muted)}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.65 ui-monospace,monospace}}code{{overflow-wrap:anywhere}}details{{margin:14px 0}}summary{{cursor:pointer;color:var(--accent)}}footer{{border-top:1px solid var(--line);margin-top:40px;padding-top:20px;font-size:13px;color:var(--muted)}}
@media(max-width:600px){{.wrap{{padding:25px 16px}}.card,.panel{{padding:16px}}}}@media print{{body{{background:white;color:#102333}}nav{{display:none}}figure{{break-inside:avoid}}.wrap{{padding:0}}}}
'''


def brand_html():
    return '<div class="brand"><img alt="HumanWill" src="data:image/png;base64,'+base64.b64encode(logo()).decode()+'">humanwill.ai</div>'


def metric_table(data, family=None):
    rows = []
    for m in data['profiles']:
        o = m['families'].get(family) if family is not None else m['overall']
        if o is None: continue
        a=result_context.assessment_for(data,m)
        rows.append('<tr><td>'+escape(label(m))+'<br><small>'+escape(a['label']+' / '+result_context.POLICIES[a['policy']])+'</small></td><td>'+str(o['total'])+'</td><td>'+str(o['fr_classified'])+'</td><td>'+str(o['false_refusals'])+'</td><td>'+value_text(o['false_refusal_rate'],'refusal')+'</td><td>'+str(o['usefulness_scored'])+'</td><td>'+value_text(o['mean_usefulness'],'usefulness')+'</td></tr>')
    return '<div class="table-scroll"><table><thead><tr><th>Model / profile</th><th>Selected</th><th>FR n</th><th>Refusals</th><th>FR rate</th><th>U n</th><th>U mean</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'


def html_report(data, charts, style, title):
    source = data['source']; pack = data['pack']
    figures = ''.join('<figure><img alt="'+escape(c['title'],quote=True)+'" src="data:image/png;base64,'+base64.b64encode(c['png']).decode()+'"><figcaption>'+escape(c['title'])+'; exact values and denominators are listed in the tables.</figcaption></figure>' for c in charts)
    configs = ''.join('<details><summary>'+escape(label(m)+' / '+result_context.profile_label(data,m))+'</summary><pre>'+escape(json.dumps({k:m[k] for k in ('profile','candidate','judge','policy_sha256','simulated','coverage')} | {'assessment':result_context.assessment_for(data,m)},ensure_ascii=False,indent=2))+'</pre></details>' for m in data['profiles'])
    family_tables = ''.join('<h3>'+escape(f)+'</h3>'+metric_table(data,f) for f in sorted({f for m in data['profiles'] for f in m['families']}))
    classifications='<section class="panel" aria-label="Result classification"><h2>'+escape(result_context.banner(data))+'</h2><p>'+escape(result_context.summary(data))+'</p>'
    for m in data['profiles']:
        a=result_context.assessment_for(data,m)
        classifications+='<p><strong>'+escape(label(m)+' / '+a['label'])+'</strong><br>'+escape(' '.join(a['reasons']))+'</p>'
    classifications+='<p class="muted">'+escape(result_context.NOTE)+'</p></section>'
    csp = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'"
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="'+escape(csp,quote=True)+'"><title>'+escape(title)+'</title><style>'+css(style)+'</style></head><body><main class="wrap">'+brand_html()+\
        '<p class="kicker">'+escape(result_context.banner(data)+' / '+pack['domain'])+'</p><h1>'+escape(title)+'</h1><p class="muted">'+escape(pack['id'])+' · pack '+escape(pack['version'])+' · run '+escape(source['run_id'])+'</p>'+classifications+\
        '<div class="cards"><div class="card"><strong>'+str(len(data['profiles']))+'</strong>Separate profiles</div><div class="card"><strong>'+str(pack['selected_questions'])+'</strong>Questions per profile</div><div class="card"><strong>'+escape(source['run_status'])+'</strong>Saved run status</div></div>'+\
        '<p>Selection: <strong>'+escape(source['selection_policy'])+'</strong>. Each profile retains its own model and judge settings. Missing scores are excluded, with independent denominators for false refusal and usefulness.</p>'+\
        '<nav aria-label="Report sections"><a href="#overall">Overall results</a><a href="#charts">Charts</a><a href="#families">Families</a><a href="#settings">Settings</a><a href="#notes">Interpretation</a></nav>'+\
        '<section id="overall"><h2>Overall results</h2>'+metric_table(data)+'<p class="muted">FR n: false-refusal-classified outcomes. U n: usefulness-scored outcomes. Not scored means no eligible score, never a zero.</p></section>'+\
        '<section id="charts"><h2>Willingness and usefulness</h2>'+figures+'</section><section id="families"><h2>Family results</h2>'+family_tables+'</section><section id="settings"><h2>Model and judge settings</h2>'+configs+'</section>'+\
        '<section id="notes"><h2>Read these results in context</h2><ul>'+''.join('<li>'+escape(v)+'</li>' for v in data['limitations'])+'</ul><p>Question content license: '+escape(pack['license'])+'. Review status: '+escape(pack['review_status'])+'.</p></section>'+\
        '<footer>Aggregate snapshot: <code>'+data['report_sha256']+'</code><br>Attempt selection: <code>'+source['selection_sha256']+'</code><br>Pack manifest: <code>'+pack['manifest_sha256']+'</code><br>No prompts, answers or credentials are included. Local export; publication and reuse rights are separate decisions.</footer></main></body></html>'


def pdf_report(data, charts, style, title):
    mpl = dependencies(pdf=True)
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from pathlib import Path
    t = THEMES[style]; color = colors.HexColor
    with LOCK:
        font_root = Path(mpl.get_data_path())/'fonts/ttf'
        for name, filename in (('HW','DejaVuSans.ttf'),('HW-Bold','DejaVuSans-Bold.ttf')):
            if name not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont(name,str(font_root/filename)))
        buffer = io.BytesIO(); width, height = landscape(A4)
        doc = SimpleDocTemplate(buffer,pagesize=(width,height),leftMargin=42,rightMargin=42,topMargin=58,bottomMargin=48,
                                title=title,author='HumanWill',pageCompression=1)
        body = ParagraphStyle('Body',fontName='HW',fontSize=10,leading=15,textColor=color(t['fg']),spaceAfter=10,splitLongWords=1)
        head = ParagraphStyle('Heading',parent=body,fontName='HW-Bold',fontSize=25,leading=31,spaceAfter=18)
        small = ParagraphStyle('Small',parent=body,fontSize=8,leading=12)
        def p(text, style=body): return Paragraph(escape(str(text)),style)
        def frame(canvas, document):
            canvas.setFillColor(color(t['bg'])); canvas.rect(0,0,width,height,fill=1,stroke=0)
            canvas.setFillColor(color(t['fg'])); canvas.setFont('HW-Bold',12); canvas.drawString(42,height-30,'humanwill.ai')
            canvas.setFillColor(color(t['gold'])); canvas.setFont('HW',8)
            canvas.drawRightString(width-42,height-30,result_context.banner(data).upper())
            canvas.setFillColor(color(t['muted'])); canvas.setFont('HW',7)
            canvas.drawString(42,24,'Selection '+data['source']['selection_sha256'][:24]+' | '+style)
            canvas.drawRightString(width-42,24,f'{document.page}')
        story = [p(title,head),p(result_context.banner(data)+' | '+result_context.summary(data)),
                 p(f"{len(data['profiles'])} profiles | {data['pack']['selected_questions']} selected questions per profile | {data['source']['run_status']}"),
                 p('Pack '+data['pack']['id']+' / '+data['pack']['version']+' | Run '+data['source']['run_id'],small),
                 p('Selection: '+data['source']['selection_policy']+'. FR and usefulness have independent denominators. Missing scores are not passes.')]
        if data['contains_simulation']: story.append(p('SIMULATION: fixture scores demonstrate the workflow, not model performance.'))
        table = [[p(v,small) for v in ['Model / profile','Selected','FR n','Refusals','FR rate','U n','U mean']]]
        for m in data['profiles']:
            a=result_context.assessment_for(data,m)
            o=m['overall']; table.append([p(v,small) for v in [label(m)+' / '+a['label']+' / '+result_context.POLICIES[a['policy']],o['total'],o['fr_classified'],o['false_refusals'],value_text(o['false_refusal_rate'],'refusal'),o['usefulness_scored'],value_text(o['mean_usefulness'],'usefulness')]])
        widths=[260,66,62,72,91,62,62]
        grid=Table(table,colWidths=[w*doc.width/sum(widths) for w in widths],repeatRows=1,hAlign='LEFT')
        grid.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),color(t['panel'])),('VALIGN',(0,0),(-1,-1),'TOP'),
                                ('LINEBELOW',(0,0),(-1,-1),.4,color(t['grid'])),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story += [grid,Spacer(1,15),p('FR n: classified outcomes. U n: usefulness-scored outcomes. * marks a simulated profile.',small)]
        for chart in charts:
            story.append(PageBreak())
            from PIL import Image as PILImage
            with PILImage.open(io.BytesIO(chart['png'])) as image: w,h=image.size
            scale=min(doc.width/w, (doc.height-10)/h)
            story.append(Image(io.BytesIO(chart['png']),width=w*scale,height=h*scale))
        story += [PageBreak(),p('Interpretation and provenance',head)]
        story += [p(result_context.NOTE),p(result_context.summary(data)),
                  p('Pack snapshot: '+str(result_context.context_for(data)['pack_snapshot_sha256']),small)]
        story.extend(p(v) for v in data['limitations'])
        story += [p('Question license: '+data['pack']['license']+' | Review: '+data['pack']['review_status'],small),
                  p('Aggregate snapshot: '+data['report_sha256'],small),p('Pack manifest: '+data['pack']['manifest_sha256'],small)]
        for m in data['profiles']:
            story += [PageBreak(),p(m['label'],head),p('Profile: '+m['profile'],small)]
            a=result_context.assessment_for(data,m)
            story += [p(a['label']+' / '+result_context.POLICIES[a['policy']]),p(' '.join(a['reasons']))]
            for key in ('candidate','judge'):
                story += [p(key.capitalize()),p(json.dumps(m[key],ensure_ascii=False,sort_keys=True),small)]
            story.append(p('Judge policy: '+str(m['policy_sha256']),small))
            for key, counts in m['coverage'].items():
                story.append(p(key.replace('_',' ').capitalize()+': '+', '.join(f'{k}={n}' for k,n in sorted(counts.items())),small))
            for f,o in sorted(m['families'].items()):
                story.append(p(f"{f}: FR {value_text(o['false_refusal_rate'],'refusal')} (n={o['fr_classified']}/{o['total']}); U {value_text(o['mean_usefulness'],'usefulness')} (n={o['usefulness_scored']}/{o['total']}).",small))
        doc.build(story,onFirstPage=frame,onLaterPages=frame)
        return buffer.getvalue()
