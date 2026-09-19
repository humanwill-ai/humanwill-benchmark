"""Verified result snapshots and aggregate-only exports. No provider calls.

Generalizes frozen publication/social arithmetic and presentation boundaries;
never imports their side-effectful, campaign-bound builders.
"""
import csv
from collections import Counter
from dataclasses import dataclass
import io
import math
import re
from pathlib import Path
from .contracts import decode, encode, fields, fingerprint, identifier, nonempty, require
from . import exports, runs, sources, result_context

METRICS = {'total', 'fr_classified', 'fr_unclassified', 'usefulness_scored',
           'usefulness_unscored', 'false_refusals', 'false_refusal_rate', 'mean_usefulness'}
CONFIG_FIELDS = {'id', 'provider', 'model', 'route', 'returned_models', 'returned_providers',
                 'settings', 'max_output_tokens', 'max_input_tokens', 'timeout_seconds'}


@dataclass(frozen=True)
class Report:
    serialized: bytes
    def to_dict(self):
        return decode(self.serialized)


def options(value, allowed):
    items = value.split(',') if isinstance(value, str) else list(value)
    require(items and all(isinstance(v, str) and v in allowed for v in items)
            and len(items) == len(set(items)), message='Unsupported or duplicate export option.')
    return items


def styles(value):
    require(value in ('clean', 'spotlight', 'both'), message='Use clean, spotlight or both.')
    return ['clean', 'spotlight'] if value == 'both' else [value]


def safe_spec(spec):
    return {key: spec[key] for key in sorted(CONFIG_FIELDS) if key in spec}


def summarize(run_id, *, workspace, selection='recovery', profiles=()):
    from . import api, engine
    require(not isinstance(profiles, str) and len(profiles) == len(set(profiles)), message='Expected unique profile IDs.')
    run_id = api.resolve_run(run_id, workspace=workspace)
    result = api.status(run_id, workspace=workspace, selection=selection)
    root = runs.root(workspace, run_id)
    if api._v2(run_id, workspace):
        before = engine.state_hash(root)
        root, plan, pack, _, _ = engine.load(run_id, workspace)
        # Re-read status within the same stable snapshot, not a potentially older query.
        result = api.status(run_id, workspace=workspace, selection=selection)
        require(engine.state_hash(root) == before, 'run_changed', 'Run changed while preparing the report.')
        population = plan['case_ids']
    else:
        root, plan, pack, _, _ = api._load_run(run_id, workspace)
        population = plan['pack']['case_ids']
    models = []
    for model in result['models']:
        if 'profile' in model:
            identity = model['profile']
            candidate, judge = model['model'], model['judge']
            votes = [r for r in result['records'] if r['profile'] == identity]
            policy = model['policy_sha256']
        else:
            candidate = next(m for m in plan['config']['models'] if m['id'] == model['model_id'])
            judge = plan['config']['judge']
            identity = fingerprint({'model': candidate, 'judge': judge, 'version': 1})
            votes = [r for r in result['records'] if r['model_id'] == model['model_id']]
            policy = 'mock-exact/1'
        require(model['overall'] == api._metrics(votes), 'integrity_error', 'Summary votes disagree with aggregates.')
        models.append({'profile': identity, 'model_id': model['model_id'],
                       'label': model['model_id'], 'candidate': safe_spec(candidate), 'judge': safe_spec(judge),
                       'policy_sha256': policy, 'simulated': candidate['provider'] == 'mock' or judge['provider'] == 'mock',
                       'overall': model['overall'], 'families': model['families'],
                       'coverage': {key: dict(Counter(r.get(field, 'unavailable') for r in votes))
                                    for key, field in (('candidate_states','candidate'), ('judge_states','judge'),
                                                       ('service_signals','candidate_signal'))}})
        if any('grading_method' in r for r in votes):
            models[-1]['coverage']['grading_methods']=dict(Counter(
                r.get('grading_method','semantic_judge' if r.get('judge')=='accepted' else 'unscored') for r in votes))
    require(set(profiles) <= {m['profile'] for m in models}, message='Unknown report profile.')
    if profiles:
        models = [m for m in models if m['profile'] in profiles]
    manifest = pack['manifest']
    context = result_context.pack_context(fingerprint(pack),len(pack['cases']),len(population),manifest['domain'])
    for model in models:
        model['assessment']=result_context.assessment(context,simulated=model['simulated'],policy_sha=model['policy_sha256'])
    value = {'format': 'humanwill.report-data/2', 'context':context, 'source': {'run_id': run_id,
             'plan_sha256': result['plan_sha256'], 'selection_sha256': result['selection_sha256'],
             'selection_policy': result['selection_policy'], 'result_sha256': fingerprint(result),
             'run_status': result['status']},
             'pack': {'id': sources.identity(pack), 'version': manifest['version'],
                      'domain': manifest['domain'], 'license': manifest['license'],
                      'review_status': manifest.get('review_status', manifest.get('status')),
                      'manifest_sha256': pack['manifest_sha256'], 'selected_questions': len(population),
                      'population_sha256': fingerprint(population)},
             'profiles': models, 'contains_simulation': any(m['simulated'] for m in models),
             'accounting': {'accounted_micro_usd': result['accounted_micro_usd'],
                            'unknown_hold_micro_usd': result.get('unknown_hold_micro_usd', 0)},
             'limitations': [
                 result_context.NOTE,
                 'False refusal and usefulness have independent denominators. Missing scores are excluded, never passes.',
                 'Judged usefulness is not verified task execution. Low refusal is not proof of correctness or safety.',
                 'Profiles retain distinct candidate, provider and judge settings; selection is chronological, never best-score.',
                 'Partial answers may receive valid scores. Selected transport states and service signals are listed per profile; signals are not semantic FR labels.',
                 'This assistance-focused population supplies no harmful-compliance denominator.',
                 'Semantic judge calibration and independent review are not established by schema validation.',
                 'Local export does not grant publication rights. Source question licensing is preserved.'
             ]}
    if manifest['domain'] == 'cybersecurity':
        value['limitations'].append('Selected cybersecurity challenge set; not a random sample or an everyday refusal-rate estimate.')
    if value['contains_simulation']:
        value['limitations'].insert(0, 'SIMULATION: fixture scores demonstrate the workflow, not model performance.')
    for model in models:
        count=model['coverage'].get('grading_methods',{}).get('native-block-fr-u/1',0)
        if count:
            value['limitations'].append(f"Profile {model['profile']}: {count} selected judgments use native-block-fr-u/1 locally (FR2/U0), not the configured LLM judge. This classification assumes the pack's assistance-eligibility labels are correct; candidate billing holds remain unchanged.")
    value['report_sha256'] = fingerprint(value)
    return load_report(Report(encode(value)))


def validate_metrics(value):
    fields(value, METRICS)
    for key in METRICS - {'false_refusal_rate', 'mean_usefulness'}:
        require(type(value[key]) is int and value[key] >= 0, message='Invalid metric count.')
    n, fr, u = value['total'], value['fr_classified'], value['usefulness_scored']
    require(fr + value['fr_unclassified'] == n and u + value['usefulness_unscored'] == n
            and value['false_refusals'] <= fr, message='Invalid metric denominators.')
    for key, denominator, high in (('false_refusal_rate', fr, 1), ('mean_usefulness', u, 4)):
        score = value[key]
        require(score is None if denominator == 0 else type(score) in (int, float) and math.isfinite(score) and 0 <= score <= high,
                message='Invalid metric value or empty denominator.')
    if fr:
        require(math.isclose(value['false_refusal_rate'], value['false_refusals'] / fr, abs_tol=1e-12), message='FR numerator/rate mismatch.')


def load_report(source):
    value = source.to_dict() if isinstance(source, Report) else runs.read(Path(source))
    require(isinstance(value,dict) and value.get('format') in ('humanwill.report-data/1','humanwill.report-data/2'),
            'unsupported_version', 'Unsupported report snapshot.')
    current=value['format']=='humanwill.report-data/2'
    fields(value, {'format', 'source', 'pack', 'profiles', 'contains_simulation', 'accounting', 'limitations', 'report_sha256'} | ({'context'} if current else set()))
    require(value['report_sha256'] == fingerprint({k: v for k, v in value.items() if k != 'report_sha256'}),
            'integrity_error', 'Report snapshot changed.')
    fields(value['source'], {'run_id','plan_sha256','selection_sha256','selection_policy','result_sha256','run_status'})
    fields(value['pack'], {'id','version','domain','license','review_status','manifest_sha256','selected_questions','population_sha256'})
    fields(value['accounting'], {'accounted_micro_usd','unknown_hold_micro_usd'})
    for amount in value['accounting'].values():
        require(type(amount) is int and amount >= 0, message='Invalid accounting summary.')
    for key in ('run_id','selection_policy','run_status'):
        nonempty(value['source'][key])
    for key in ('id','version','domain','license','review_status'):
        nonempty(value['pack'][key])
    for sha in [value['report_sha256'],value['pack']['manifest_sha256'],value['pack']['population_sha256'],
                *(value['source'][k] for k in ('plan_sha256','selection_sha256','result_sha256'))]:
        require(isinstance(sha,str) and re.fullmatch(r'[0-9a-f]{64}',sha), message='Invalid report digest.')
    count = value['pack']['selected_questions']
    require(type(count) is int and count > 0, message='Invalid selected population.')
    require(isinstance(value['profiles'], list) and value['profiles'], message='Report requires at least one profile.')
    ids = set()
    for model in value['profiles']:
        fields(model, {'profile','model_id','label','candidate','judge','policy_sha256','simulated','overall','families','coverage'} | ({'assessment'} if current else set()))
        nonempty(model['profile']); identifier(model['model_id']); nonempty(model['label'])
        require(model['profile'] not in ids and type(model['simulated']) is bool, message='Duplicate or invalid profile.')
        ids.add(model['profile'])
        for key in ('candidate','judge'):
            fields(model[key], {'id','provider','model'}, CONFIG_FIELDS - {'id','provider','model'})
            for text_key in ('id','provider','model'): nonempty(model[key][text_key])
            if 'settings' in model[key]:
                fields(model[key]['settings'],set(),{'reasoning_effort','temperature','thinking','effort'})
        validate_metrics(model['overall'])
        fields(model['coverage'], {'candidate_states','judge_states','service_signals'}, {'grading_methods'})
        for kind,counts in model['coverage'].items():
            require(isinstance(counts, dict) and counts, message='Invalid coverage summary.')
            for name, n in counts.items():
                if kind=='grading_methods':
                    require(name in ('native-block-fr-u/1','semantic_judge','unscored'), message='Unknown grading method.')
                else: identifier(name)
                require(type(n) is int and n >= 0, message='Invalid coverage count.')
            require(sum(counts.values()) == count, message='Coverage population changed.')
        require(model['overall']['total'] == count and isinstance(model['families'], dict) and model['families'], message='Profile population changed.')
        for name, metrics in model['families'].items():
            identifier(name); validate_metrics(metrics)
        for key in METRICS - {'false_refusal_rate','mean_usefulness'}:
            require(sum(f[key] for f in model['families'].values()) == model['overall'][key], message='Family denominators disagree.')
        total_u = sum((f['mean_usefulness'] or 0) * f['usefulness_scored'] for f in model['families'].values())
        require(math.isclose(total_u, (model['overall']['mean_usefulness'] or 0) * model['overall']['usefulness_scored'], abs_tol=1e-9), message='Family usefulness disagrees.')
    require(type(value['contains_simulation']) is bool and value['contains_simulation'] == any(m['simulated'] for m in value['profiles']), message='Invalid simulation label.')
    require(isinstance(value['limitations'], list) and all(isinstance(x, str) for x in value['limitations']), message='Invalid caveats.')
    if current: result_context.validate(value)
    return Report(encode(value))


def csv_bytes(data):
    stream = io.StringIO(newline='')
    keys = ['profile', 'model_id', 'scope', 'family', 'simulated', 'result_kind', 'result_label',
            'question_set','population','policy_kind','policy_sha256','pack_snapshot_sha256', *sorted(METRICS)]
    local=any('grading_methods' in m['coverage'] for m in data['profiles'])
    if local: keys.append('profile_grading_methods')
    writer = csv.DictWriter(stream, fieldnames=keys, lineterminator='\n')
    writer.writeheader()
    for model in data['profiles']:
        scopes = [('overall', '', model['overall'])] + [('family', family, metrics) for family, metrics in sorted(model['families'].items())]
        for scope, family, metrics in scopes:
            classification=result_context.assessment_for(data,model); context=result_context.context_for(data)
            row = {'profile': model['profile'], 'model_id': model['model_id'], 'scope': scope,
                   'family': family, 'simulated': model['simulated'], 'result_kind':classification['kind'],
                   'result_label':classification['label'],'question_set':context['question_set'],
                   'population':context['population'],'policy_kind':classification['policy'],
                   'policy_sha256':model['policy_sha256'],'pack_snapshot_sha256':context['pack_snapshot_sha256'], **metrics}
            if local: row['profile_grading_methods']=encode(model['coverage'].get('grading_methods',{})).decode().strip()
            # CSV cells are data even when opened in spreadsheet applications.
            row = {k: ("'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v) for k, v in row.items()}
            writer.writerow(row)
    return stream.getvalue().encode('utf-8')


def render_report(prepared, *, output, formats=('html','pdf'), style='clean', title='HumanWill evaluation report'):
    data = load_report(prepared).to_dict()
    kinds = options(formats, {'json','csv','html','pdf'})
    themes = styles(style); nonempty(title)
    path = exports.destination(output)
    context=result_context.export_context(data)
    files = {'results.json': encode(data), 'results.csv': csv_bytes(data), 'result-context.json':encode(context)}
    if {'html','pdf'} & set(kinds):
        from . import presentation
        for theme in themes:
            charts = presentation.charts(data, theme)
            if 'html' in kinds:
                files[f'report-{theme}.html'] = presentation.html_report(data, charts, theme, title).encode('utf-8')
            if 'pdf' in kinds:
                files[f'report-{theme}.pdf'] = presentation.pdf_report(data, charts, theme, title)
    return exports.publish(path, files, kind='report', metadata={
        'report_sha256': data['report_sha256'], 'selection_sha256': data['source']['selection_sha256'], 'styles': themes,
        'requested_formats': kinds, 'contains_simulation': data['contains_simulation'], 'result_context':context})


def render_images(prepared, *, output, formats=('png',), style='clean'):
    data = load_report(prepared).to_dict()
    kinds = options(formats, {'png','svg'})
    themes = styles(style); path = exports.destination(output)
    from . import presentation
    context=result_context.export_context(data)
    files = {'results.json': encode(data), 'result-context.json':encode(context)}
    audit = []
    for theme in themes:
        for chart in presentation.charts(data, theme, formats=kinds):
            for kind in kinds:
                files[f"{chart['slug']}-{theme}.{kind}"] = chart[kind]
            audit.append({k: chart[k] for k in ('slug','metric','families','profiles','values','result_label')} | {'style': theme})
    files['chart-data.json'] = encode({'format': 'humanwill.chart-data/2', 'report_sha256': data['report_sha256'], 'result_context':context,'charts': audit})
    return exports.publish(path, files, kind='images', metadata={
        'report_sha256': data['report_sha256'], 'selection_sha256': data['source']['selection_sha256'],
        'styles': themes, 'requested_formats': kinds, 'contains_simulation': data['contains_simulation'],'result_context':context})
