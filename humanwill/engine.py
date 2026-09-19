"""Version 2 execution and recovery operations shared by agents and the CLI.

A run owns immutable operation plans and attempts. One local writer spans an
operation; asynchronous requests reserve durably before yielding to transport.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import uuid

from . import config, credentials, grading, ledger, live, runs, settings, sources
from .contracts import HumanWillError, Plan, decode, digest, encode, fields, fingerprint, identifier, require, text_digest
from .providers import MockProvider, Request


def now(): return datetime.now(timezone.utc).isoformat()
def operation_id(): return 'op-' + uuid.uuid4().hex[:16]
def implementation():
    from .api import _implementation
    return _implementation()
def seal(value): return {**value, 'sha256': fingerprint(value)}
def verify(value):
    require(isinstance(value, dict) and value.get('sha256') == fingerprint({k:v for k,v in value.items() if k != 'sha256'}),
            'integrity_error', 'Record hash mismatch.')
    return value


def inputs(value):
    cfg = config.load(value).to_dict()
    require(cfg['version'] == 2, message='Recovery/live operations require configuration version 2.')
    pack = sources.load(cfg['pack']); sources.validate(pack)
    ids = [r['id'] for r in pack['cases']]
    selected = cfg['case_ids'] or ids
    require(set(selected) <= set(ids), message='Unknown selected question.')
    for spec in [*cfg['models'], cfg['judge']]:
        require(set(spec.get('fail_cases', [])) | set(spec.get('abstain_fr_cases', [])) <= set(ids), message='Unknown mock question.')
    require(pack['manifest']['domain'] == 'demonstration' or all(m['provider'] != 'mock' for m in [*cfg['models'], cfg['judge']]),
            message='Cybersecurity questions require real models and a semantic judge.')
    return cfg, pack, grading.policy(cfg,pack), selected


def check(value):
    cfg, pack, policy, selected = inputs(value)
    import importlib.util
    refs = {s['credential'] for s in [*cfg['models'], cfg['judge']] if s['provider'] != 'mock'}
    result = {'valid': True, 'simulated': not refs, 'pack_id': sources.identity(pack), 'questions': len(selected),
            'models': [s['id'] for s in cfg['models']], 'judge': cfg['judge']['id'], 'credentials_required': bool(refs),
            'credential_references': {r:credentials.available(r) for r in sorted(refs)},
            'live_dependency_available': importlib.util.find_spec('httpx') is not None,
            'budget_micro_usd': cfg['budget_micro_usd'], 'judge_policy_sha256': policy['sha256']}
    if policy['id']==grading.NATIVE_POLICY:
        result['native_block_scoring']={'rule':policy['rule'],'text':policy['rule_text'],
                                       'underlying_policy_sha256':policy['base_policy']['sha256']}
    return result


def profile(model, judge, policy_sha):
    return fingerprint({'model': model, 'judge': judge, 'policy_sha256': policy_sha})


def task(model, judge, policy_sha, case, stage='candidate', parent=None, candidate=None, reason='initial'):
    return {'model': model, 'judge': judge, 'policy_sha256': policy_sha, 'case_id': case, 'stage': stage,
            'parent_attempt_id': parent, 'candidate_attempt_id': candidate, 'reason': reason,
            'profile': profile(model, judge, policy_sha)}


def make_plan(cfg, pack, policy, selected, tasks, run_id, *, operation='run', base=None, changes=None, accounting_before=None):
    require(run_id!='latest', message='latest is reserved for workspace lookup.')
    by_id = {r['id']:r for r in pack['cases']}
    maximum = 0
    for job in tasks:
        if job['stage'] == 'candidate':
            maximum += live.reservation(job['model'], live.request(job['model'], by_id[job['case_id']]['messages']))
        judge = job['judge']
        if judge['provider'] != 'mock': maximum += live.priced(judge, judge['max_input_tokens'], judge['max_output_tokens'])
    value = {'format': 'humanwill.plan/2', 'run_id': identifier(run_id), 'operation_id': operation_id(),
             'operation': operation, 'created_at': now(), 'config': cfg, 'pack_sha256': fingerprint(pack),
             'case_ids': selected, 'policy_sha256': policy['sha256'], 'tasks': tasks, 'base_state_sha256': base,
             'implementation_sha256': implementation(), 'maximum_reservation_micro_usd': maximum,
             'configuration_changes': changes or {}, 'accounting_before': accounting_before or {'accounted_micro_usd':0,'unknown_hold_micro_usd':0},
             'simulated': all(s['provider']=='mock' for s in [*cfg['models'],cfg['judge']])}
    value['plan_sha256'] = fingerprint(value)
    return Plan(encode(value))


def plan(value, *, run_id=None):
    cfg, pack, policy, selected = inputs(value)
    jobs = [task(m, cfg['judge'], policy['sha256'], case) for m in cfg['models'] for case in selected]
    return make_plan(cfg, pack, policy, selected, jobs, 'run-'+uuid.uuid4().hex[:16] if run_id is None else run_id)


def validate_plan(value):
    fields(value, {'format','run_id','operation_id','operation','created_at','config','pack_sha256','case_ids',
        'policy_sha256','tasks','base_state_sha256','implementation_sha256','maximum_reservation_micro_usd','simulated','plan_sha256','configuration_changes','accounting_before'})
    require(value['format'] == 'humanwill.plan/2' and value['operation'] in ('run','retry','resume','grade'), message='Unsupported operation plan.')
    require(value['plan_sha256'] == fingerprint({k:v for k,v in value.items() if k!='plan_sha256'}), 'integrity_error','Plan hash mismatch.')
    identifier(value['run_id']); identifier(value['operation_id'])
    require(value['run_id']!='latest', message='latest is reserved for workspace lookup.')
    require(type(value['simulated']) is bool and type(value['maximum_reservation_micro_usd']) is int and value['maximum_reservation_micro_usd']>=0, message='Invalid operation limits.')
    fields(value['accounting_before'], {'accounted_micro_usd','unknown_hold_micro_usd'})
    require(all(type(v) is int and v>=0 for v in value['accounting_before'].values()), message='Invalid prior accounting.')
    require(isinstance(value['configuration_changes'], dict), message='Invalid configuration diff.')
    cfg = settings.from_dict(value['config'], base=Path.cwd()).to_dict()
    require(value['simulated']==all(s['provider']=='mock' for s in [*cfg['models'],cfg['judge']]), message='Simulation label changed.')
    require(cfg == value['config'], message='Unresolved operation configuration.')
    require(isinstance(value['tasks'], list) and isinstance(value['case_ids'], list) and value['case_ids'], message='Invalid task selection.')
    require(len(value['case_ids']) == len(set(value['case_ids'])), message='Duplicate question selection.')
    known, seen = {m['id']:m for m in cfg['models']}, set()
    for job in value['tasks']:
        fields(job, {'model','judge','policy_sha256','case_id','stage','parent_attempt_id','candidate_attempt_id','reason','profile'})
        require(job['model'] == known.get(job['model']['id']) and job['judge']==cfg['judge']
                and job['policy_sha256']==value['policy_sha256'] and job['case_id'] in value['case_ids']
                and job['stage'] in ('candidate','judge') and job['profile']==profile(job['model'],job['judge'],job['policy_sha256']),
                message='Invalid operation task.')
        key = (job['profile'],job['case_id'],job['stage'])
        require(key not in seen, message='Duplicate task.'); seen.add(key)
        if job['stage']=='candidate': require(job['candidate_attempt_id'] is None, message='Candidate cannot reuse an answer.')
        else: identifier(job['candidate_attempt_id'])
        if job['parent_attempt_id'] is not None: identifier(job['parent_attempt_id'])
    return cfg


def state_hash(root):
    files = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'unsafe_path', 'Symlinks are not supported in a run.')
        if path.is_file() and (path.suffix in ('.json', '.body')):
            files[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    return fingerprint(files)


def load(run_id, workspace):
    root = runs.root(workspace, run_id)
    before_hash=state_hash(root)  # Reject symlinks and bind a consistent read snapshot.
    initial = runs.read(root/'plan.json'); validate_plan(initial)
    require(initial['run_id']==run_id and initial['operation']=='run', message='Invalid run identity.')
    pack = runs.read(root/'inputs.json'); sources.validate(pack)
    require(fingerprint(pack)==initial['pack_sha256'], 'integrity_error','Input snapshot changed.')
    require(set(initial['case_ids']) <= {r['id'] for r in pack['cases']}, message='Invalid population.')
    operations = {}; policy_snapshots = {}
    for path in sorted((root/'operations').iterdir()):
        require(path.is_dir() and not path.is_symlink(), message='Invalid operation directory.')
        if not (path/'plan.json').exists(): continue  # interrupted before any paid work
        op = runs.read(path/'plan.json'); validate_plan(op)
        require(op['run_id']==run_id and op['operation_id']==path.name and op['pack_sha256']==initial['pack_sha256']
                and op['case_ids']==initial['case_ids'] and op['config']['budget_micro_usd']==initial['config']['budget_micro_usd'],
                'integrity_error','Operation lineage changed.')
        policy = runs.read(path/'policy.json')
        grading.validate_policy(policy,pack)
        require(policy['sha256']==op['policy_sha256'], message='Judge policy changed.')
        policy_snapshots[op['operation_id']] = policy
        if (path/'completion.json').exists():
            done = verify(runs.read(path/'completion.json'))
            for relative, sha in done['files'].items():
                target = root/relative
                require(not Path(relative).is_absolute() and '..' not in Path(relative).parts and not target.is_symlink()
                        and target.is_file() and digest(target.read_bytes())==sha, 'integrity_error','Completed artifacts changed.')
        operations[path.name] = op
    require(initial['operation_id'] in operations, 'incomplete_initialization', 'Run initialization was interrupted before any request.')
    records, seen = [], set()
    cases = {r['id']:r for r in pack['cases']}
    for path in sorted((root/'attempts').iterdir()):
        require(path.is_dir() and not path.is_symlink(), message='Invalid attempt directory.')
        if not (path/'intent.json').exists(): continue
        intent = verify(runs.read(path/'intent.json'))
        fields(intent, {'format','id','operation_id','task_sha256','stage','candidate_attempt_id','parent_attempt_id','request_sha256','reserved_micro_usd','created_at','sha256'}, {'local_rule'})
        local_rule=intent.get('local_rule')
        require('local_rule' not in intent or local_rule==grading.NATIVE_RULE and intent['stage']=='judge'
                and intent['reserved_micro_usd']==0, message='Invalid local scoring intent.')
        import re
        require(intent['format']=='humanwill.attempt/2' and re.fullmatch(r'a[0-9]{8}',intent['id']) and type(intent['reserved_micro_usd']) is int and intent['reserved_micro_usd']>=0, message='Invalid attempt intent.')
        require(intent['id']==path.name and intent['operation_id'] in operations, message='Unknown attempt identity.')
        op = operations[intent['operation_id']]
        jobs = {fingerprint(t):t for t in op['tasks']}
        job = jobs.get(intent['task_sha256'])
        require(job is not None and intent['stage'] in ('candidate','judge'), message='Unknown attempt task.')
        key = (intent['operation_id'], intent['task_sha256'], intent['stage'])
        require(key not in seen, message='Duplicate attempt.'); seen.add(key)
        require(intent['stage']==job['stage'] or job['stage']=='candidate' and intent['stage']=='judge', message='Stage mismatch.')
        request = runs.read(path/'request.json') if (path/'request.json').exists() else None
        require(request is None or fingerprint(request)==intent['request_sha256'], 'integrity_error','Request changed.')
        if request is not None and intent['stage']=='candidate':
            require(request==live.request(job['model'], cases[job['case_id']]['messages']), message='Candidate inputs changed.')
        outcome = verify(runs.read(path/'outcome.json')) if (path/'outcome.json').exists() else None
        if request is not None:
            spec=job['model'] if intent['stage']=='candidate' else job['judge']
            require(type(intent['reserved_micro_usd']) is int and intent['reserved_micro_usd']==(0 if local_rule else live.reservation(spec,request)), message='Reservation changed.')
        if outcome:
            fields(outcome, {'format','intent_sha256','response','verdict','capture_sha256','accounting','completed_at','sha256'})
            require(outcome['format']=='humanwill.outcome/2' and outcome['response']['status'] in ('accepted','partial','error','blocked'), message='Invalid outcome.')
            require(outcome['accounting']['kind'] in (('local_rule',) if local_rule else ('simulated','usage_upper_bound','unknown_hold')), message='Invalid accounting kind.')
            if local_rule:
                require(outcome['accounting']=={'kind':'local_rule','accounted_micro_usd':0}
                        and outcome['response']==grading.native_response(), message='Local scoring outcome changed.')
            if outcome['accounting']['kind']=='unknown_hold':
                require(outcome['accounting']['accounted_micro_usd']==intent['reserved_micro_usd'], message='Unknown hold changed.')
            require(outcome['intent_sha256']==fingerprint(intent) and request is not None, message='Outcome binding changed.')
            cost = outcome['accounting']['accounted_micro_usd']
            require(type(cost) is int and cost>=0, message='Invalid accounting.')
            if outcome.get('verdict'):
                v=outcome['verdict']
                grading.verdict(encode({k:v[k] for k in ('false_refusal','usefulness','rationale')}), '', v['policy_sha256'])
        capture = runs.read(path/'http.json') if (path/'http.json').exists() else None
        if capture:
            require(not local_rule, message='Local scoring cannot have a provider capture.')
            fields(capture, {'format','body_file','complete','status','headers','header_policy','error','representation','sha256','bytes'})
            require(capture['format']=='humanwill.http/1' and type(capture['complete']) is bool and capture['bytes']==(path/'response.body').stat().st_size, message='Invalid HTTP metadata.')
            require(capture['body_file']=='response.body' and not (path/'response.body').is_symlink()
                    and digest((path/'response.body').read_bytes())==capture['sha256'], message='HTTP capture changed.')
            require(outcome is None or outcome['capture_sha256']==fingerprint(capture), message='Capture binding changed.')
        if outcome:
            require((capture is None)==(outcome['capture_sha256'] is None), message='Missing HTTP evidence.')
        records.append({'intent':intent,'request':request,'outcome':outcome,'capture':capture,'task':job,'path':path})
    by_id={a['intent']['id']:a for a in records}
    for record in records:
        intent, job = record['intent'], record['task']
        parent_id=intent['parent_attempt_id']
        if parent_id is not None:
            prior=by_id.get(parent_id)
            require(prior is not None and prior['intent']['id']<intent['id'] and prior['intent']['stage']==intent['stage']
                    and prior['task']['case_id']==job['case_id'] and prior['task']['model']['id']==job['model']['id'], message='Invalid retry parent.')
        if intent['stage'] != 'judge':
            require(intent['candidate_attempt_id'] is None, message='Unexpected candidate reference.')
            continue
        parent = by_id.get(intent['candidate_attempt_id'])
        require(parent is not None and parent['intent']['stage']=='candidate' and parent['task']['case_id']==job['case_id']
                and parent['task']['model']==job['model'] and usable(parent), message='Invalid saved answer binding.')
        answer=parent['outcome']['response']['answer']
        if record['request'] is not None:
            policy = policy_snapshots[intent['operation_id']]
            if intent.get('local_rule'):
                expected=grading.native_request(cases[job['case_id']],policy,parent)
                require(expected is not None, message='Local scoring is not eligible.')
                if record['outcome']:
                    require(record['outcome']['verdict']==grading.native_verdict(answer,policy['sha256']),
                            message='Local verdict changed.')
            else:
                messages = cases[job['case_id']]['messages'] if job['judge']['provider']=='mock' else grading.messages(cases[job['case_id']], answer, policy, parent['outcome']['response'])
                expected=live.request(job['judge'], messages)
                if job['judge']['provider']=='mock': expected.update(answer=answer,answer_sha256=text_digest(answer),mock_behavior=parent['outcome']['response'].get('mock_behavior','answer'))
            require(record['request']==expected, message='Judge request changed.')
        if record['outcome'] and record['outcome'].get('verdict'):
            require(record['outcome']['verdict']['answer_sha256']==text_digest(answer)
                    and record['outcome']['verdict']['policy_sha256']==job['policy_sha256'], message='Judgment binding changed.')
    for opid in operations:
        completed=root/'operations'/opid/'completion.json'
        if completed.exists():
            owned=[root/'operations'/opid/'plan.json',root/'operations'/opid/'policy.json']
            for record in records:
                if record['intent']['operation_id']==opid:
                    owned.extend(p for p in record['path'].iterdir() if p.is_file() and p.suffix in ('.json','.body'))
            require(set(verify(runs.read(completed))['files'])=={p.relative_to(root).as_posix() for p in owned}, 'integrity_error','Completed operation inventory changed.')
    require(state_hash(root)==before_hash, 'run_changed', 'Run changed during inspection; read it again.')
    return root, initial, pack, operations, records


def usable(record):
    if not record or not record['outcome']: return False
    r=record['outcome']['response']
    return r['status'] in ('accepted','partial','blocked') and (bool(r.get('answer','').strip()) or r.get('signal') in ('structured_refusal','provider_safety_block'))


def response_status(record):
    return record['outcome']['response']['status'] if record and record['outcome'] else ('unresolved' if record else 'unattempted')


def views(initial, pack, operations, records, selection):
    require(selection in ('first','recovery'), message='Unknown selection policy.')
    profiles = {}
    for op in operations.values():
        for job in op['tasks']: profiles[job['profile']] = job
    rows=[]
    cases={r['id']:r for r in pack['cases']}
    for pid, job in sorted(profiles.items()):
        for case in initial['case_ids']:
            # New grading streams reuse exact candidate settings, never candidate scores.
            candidates=[a for a in records if a['intent']['stage']=='candidate' and a['task']['model']==job['model'] and a['task']['case_id']==case]
            candidate = (candidates[0] if candidates else None) if selection=='first' else next((a for a in reversed(candidates) if usable(a)), candidates[-1] if candidates else None)
            cid=candidate['intent']['id'] if candidate else None
            judges=[a for a in records if a['intent']['stage']=='judge' and a['task']['profile']==pid and a['task']['case_id']==case and a['intent']['candidate_attempt_id']==cid]
            judge=(judges[0] if judges else None) if selection=='first' else next((a for a in reversed(judges) if a['outcome'] and a['outcome'].get('verdict')), judges[-1] if judges else None)
            verdict=judge['outcome'].get('verdict') if judge and judge['outcome'] else None
            rows.append({'profile':pid,'model_id':job['model']['id'],'case_id':case,'family':cases[case]['family'],
                         'candidate_attempt_id':cid,'judge_attempt_id':judge['intent']['id'] if judge else None,
                         'candidate':response_status(candidate),'judge':response_status(judge),
                         'candidate_signal':candidate['outcome']['response'].get('signal','unknown') if candidate and candidate['outcome'] else 'unknown',
                         'latest_candidate_attempt_id':candidates[-1]['intent']['id'] if candidates else None,
                         'latest_judge_attempt_id':judges[-1]['intent']['id'] if judges else None,
                         'false_refusal':verdict['false_refusal'] if verdict else None,
                         'usefulness':verdict['usefulness'] if verdict else None})
            # Preserve historical selection hashes when no local rule was used.
            if verdict and judge['intent'].get('local_rule'):
                rows[-1]['grading_method']=judge['intent']['local_rule']
    return profiles,rows


def status(run_id, *, workspace, selection='recovery'):
    root, initial, pack, operations, records = load(run_id,workspace)
    profiles,rows=views(initial,pack,operations,records,selection)
    from .api import _metrics
    models=[]
    for pid,job in sorted(profiles.items()):
        chosen=[r for r in rows if r['profile']==pid]
        models.append({'profile':pid,'model_id':job['model']['id'],'model':job['model'],'judge':job['judge'],
                       'policy_sha256':job['policy_sha256'],'overall':_metrics(chosen),
                       'service_signals':{key:sum(r['candidate_signal']==key for r in chosen) for key in ('provider_safety_block','structured_refusal','incomplete','unknown')},
                       'families':{f:_metrics([r for r in chosen if r['family']==f]) for f in sorted({r['family'] for r in chosen})}})
    complete=all((root/'operations'/op/'completion.json').exists() for op in operations)
    cost=ledger.accounting(records)
    return {'format':'humanwill.results/2','run_id':run_id,'workspace':str(root.parent),
            'status':('complete' if all(r['judge']=='accepted' and r['candidate'] in ('accepted','blocked') for r in rows) else 'partial') if complete else 'incomplete',
            'simulated':all(op['simulated'] for op in operations.values()),'plan_sha256':initial['plan_sha256'],
            'selection_policy':selection+'/2','selection_sha256':fingerprint(rows),'attempt_count':len(records),
            'budget_micro_usd':initial['config']['budget_micro_usd'], **cost,'models':models,'records':rows}


async def execute_async(prepared, *, transport=None):
    value=prepared.to_dict(); cfg=validate_plan(value)
    require(value['implementation_sha256']==implementation(), 'stale_plan','Implementation changed; prepare a new plan.')
    root=runs.root(cfg['workspace'],value['run_id'])
    if value['operation']=='run':
        current, pack, policy, selected=inputs(settings.Settings(encode(cfg)))
        require(fingerprint(pack)==value['pack_sha256'] and policy['sha256']==value['policy_sha256'] and selected==value['case_ids'],
                'stale_plan','Inputs changed; prepare a new plan.')
        expected=[task(m,cfg['judge'],policy['sha256'],case) for m in cfg['models'] for case in selected]
        require(value['tasks']==expected, message='Initial population changed.')
    else:
        root, initial, pack, operations, records=load(value['run_id'],cfg['workspace'])
        policies=[runs.read(root/'operations'/op['operation_id']/'policy.json') for op in operations.values() if op['policy_sha256']==value['policy_sha256']]
        policy=policies[0] if policies else grading.policy(cfg,pack)
        require(policy['sha256']==value['policy_sha256'], 'stale_plan','Judge policy changed.')
    # Credential resolution/dependency errors cannot create paid intents.
    saved={r['intent']['id']:r for r in records} if value['operation']!='run' else {}
    case_lookup={r['id']:r for r in pack['cases']}
    local_jobs={fingerprint(job) for job in value['tasks'] if job['stage']=='judge'
                and grading.native_request(case_lookup[job['case_id']],policy,saved.get(job['candidate_attempt_id']))}
    specs={fingerprint(s):s for job in value['tasks'] if fingerprint(job) not in local_jobs
           for s in ((job['model'],job['judge']) if job['stage']=='candidate' else (job['judge'],)) if s['provider']!='mock'}
    secrets={key:credentials.resolve(s['credential']) for key,s in specs.items()}
    if specs:
        try: import httpx  # noqa: F401
        except ImportError: raise HumanWillError('missing_dependency','Install humanwill-evals[live].') from None
    if value['operation']=='run':
        root=runs.create(cfg['workspace'],value['run_id'])
        (root/'operations').mkdir(mode=0o700)
        runs.write(root/'plan.json',value); runs.write(root/'inputs.json',pack)
    with ledger.writer(root):
        if value['operation']!='run':
            require(state_hash(root)==value['base_state_sha256'], 'stale_plan','Run changed; prepare a new recovery plan.')
            existing={r['intent']['id']:r for r in records}
            for job in value['tasks']:
                parent=existing.get(job['parent_attempt_id'])
                if job['parent_attempt_id'] is not None:
                    require(parent is not None and parent['intent']['stage']==job['stage'] and parent['task']['case_id']==job['case_id'] and parent['task']['model']['id']==job['model']['id'], message='Retry parent mismatch.')
                    unknown=not parent['intent'].get('local_rule') and (not parent['outcome'] or parent['outcome']['accounting']['kind']=='unknown_hold')
                    require(not unknown or job['reason']=='unknown_billing_acknowledged', 'unknown_billing','Recovery plan must acknowledge unknown billing.')
            # Budget and populations cannot be changed by recovery.
            require(cfg['budget_micro_usd']==initial['config']['budget_micro_usd'] and value['case_ids']==initial['case_ids']
                    and value['pack_sha256']==initial['pack_sha256'], message='Recovery changed run contract.')
        opdir=root/'operations'/value['operation_id']; opdir.mkdir(mode=0o700)
        runs.write(opdir/'policy.json',policy); runs.write(opdir/'plan.json',value)
        _, initial, _, _, records=load(value['run_id'],cfg['workspace'])
        by_id={r['intent']['id']:r for r in records}; cases={r['id']:r for r in pack['cases']}
        cost=ledger.accounting(records)['accounted_micro_usd']
        sequence=max([int(p.name[1:]) for p in (root/'attempts').iterdir() if p.name.startswith('a') and p.name[1:].isdigit()]+[0])
        stopped=False; reasons=[]; pace=asyncio.Lock(); last=0.0
        semaphore=asyncio.Semaphore(cfg['concurrency'])

        async def call(job, stage, candidate=None):
            nonlocal cost,sequence,stopped,last
            spec=job['model'] if stage=='candidate' else job['judge']
            row=cases[job['case_id']]
            answer=candidate['outcome']['response']['answer'] if candidate else None
            local_payload=grading.native_request(row,policy,candidate) if stage=='judge' else None
            if local_payload:
                payload=local_payload
            else:
                messages=row['messages'] if stage=='candidate' or spec['provider']=='mock' else grading.messages(row,answer,policy,candidate['outcome']['response'])
                payload=decode(encode(live.request(spec,messages)))
            if stage=='judge' and spec['provider']=='mock':
                payload.update(answer=answer,answer_sha256=text_digest(answer),mock_behavior=candidate['outcome']['response'].get('mock_behavior','answer'))
            try: reserved=0 if local_payload else live.reservation(spec,payload)
            except HumanWillError:
                reasons.append('input_limit'); return None
            async with pace:
                if spec['provider']!='mock' and not local_payload:
                    loop=asyncio.get_running_loop()
                    await asyncio.sleep(max(0,cfg['minimum_interval_ms']/1000-(loop.time()-last)))
                    last=loop.time()
                if not local_payload and (stopped or cost+reserved>cfg['budget_micro_usd']):
                    reasons.append('budget_or_provider_stop'); return None
                sequence+=1; aid=f'a{sequence:08d}'; directory=root/'attempts'/aid; directory.mkdir(mode=0o700)
                intent=seal({'format':'humanwill.attempt/2','id':aid,'operation_id':value['operation_id'],
                    'task_sha256':fingerprint(job),'stage':stage,'candidate_attempt_id':candidate['intent']['id'] if candidate else None,
                    'parent_attempt_id':job['parent_attempt_id'] if stage==job['stage'] else None,
                    'request_sha256':fingerprint(payload),'reserved_micro_usd':reserved,'created_at':now(),
                    **({'local_rule':grading.NATIVE_RULE} if local_payload else {})})
                runs.write(directory/'intent.json',intent); cost+=reserved
                runs.write(directory/'request.json',payload)
            capture=None; verdict=None
            if local_payload:
                response=grading.native_response(); verdict=grading.native_verdict(answer,policy['sha256'])
                accounted=0; kind='local_rule'
            elif spec['provider']=='mock':
                mock_payload=decode(encode(payload))
                try:
                    response=await MockProvider().invoke(Request(row['id'],stage,spec['model'],mock_payload,row['id'] in spec.get('fail_cases',[]),row['id'] in spec.get('abstain_fr_cases',[])))
                except Exception: response={'status':'error','code':'provider_exception'}
                if stage=='judge' and response['status']=='accepted':
                    verdict={k:response[k] for k in ('false_refusal','usefulness','answer_sha256')}
                    verdict.update(policy_sha256=policy['sha256'],rationale={'false_refusal':'Synthetic fixture.','usefulness':'Exact fixture comparison.'})
                response.setdefault('answer','')
                response.update(complete=response['status']=='accepted',signal='structured_refusal' if response.get('mock_behavior')=='refusal' else 'simulated')
                accounted=0; kind='simulated'
            else:
                response,capture=await live.invoke(spec,payload,directory,secrets[fingerprint(spec)],transport=transport)
                observed=live.usage_bound(spec,response.get('usage')) if capture['complete'] and response.get('usage_final') else None
                accounted=reserved if observed is None else observed
                kind='unknown_hold' if observed is None else 'usage_upper_bound'
                if observed is not None and observed>reserved: stopped=True; reasons.append('price_bound_exceeded')
                if (capture['status'] in (401,402,403,429) or capture['status'] is not None and capture['status']>=500) and response['signal']!='provider_safety_block':
                    stopped=True; reasons.append('provider_stop')
                if stage=='judge':
                    if response['status']=='accepted' and response['signal']!='structured_refusal':
                        try: verdict=grading.verdict(response['answer'],answer,policy['sha256'])
                        except HumanWillError: pass
                    if verdict is None: response.update(status='error',code='invalid_judgment')
            outcome=seal({'format':'humanwill.outcome/2','intent_sha256':fingerprint(intent),'response':response,
                'verdict':verdict,'capture_sha256':fingerprint(capture) if capture else None,
                'accounting':{'kind':kind,'accounted_micro_usd':accounted},'completed_at':now()})
            runs.write(directory/'outcome.json',outcome); cost+=accounted-reserved
            record={'intent':intent,'outcome':outcome,'request':payload,'capture':capture,'task':job,'path':directory}
            by_id[aid]=record; records.append(record)
            return record

        async def one(job):
            async with semaphore:
                if job['stage']=='judge':
                    candidate=by_id.get(job['candidate_attempt_id'])
                    require(usable(candidate) and candidate['task']['model']==job['model'] and candidate['task']['case_id']==job['case_id'], message='Invalid recovery answer.')
                else:
                    candidate=await call(job,'candidate')
                if usable(candidate): await call(job,'judge',candidate)
        async with asyncio.TaskGroup() as group:
            for job in value['tasks']: group.create_task(one(job))
        paths=[opdir/'plan.json',opdir/'policy.json']
        for intent_path in (root/'attempts').glob('*/intent.json'):
            if runs.read(intent_path)['operation_id']==value['operation_id']:
                paths.extend(p for p in intent_path.parent.iterdir() if p.is_file() and p.suffix in ('.json','.body'))
        runs.write(opdir/'completion.json',seal({'format':'humanwill.completion/2','completed_at':now(),
                   'files':{p.relative_to(root).as_posix():digest(p.read_bytes()) for p in sorted(paths)},'stop_reasons':sorted(set(reasons))}))
    return status(value['run_id'],workspace=cfg['workspace'])


def recover(run_id, *, workspace, operation='retry', stage='judge', case_ids=(), model_id=None,
            failed=True, acknowledge_unknown=False, replacement=None, profile_id=None):
    """Materialize selection without writes/calls. execute_async binds its state hash."""
    require(operation in ('retry','resume','grade') and stage in ('candidate','judge'), message='Unsupported recovery operation.')
    require(type(failed) is bool and type(acknowledge_unknown) is bool, message='Expected boolean selection controls.')
    expected_state=state_hash(runs.root(workspace,run_id))
    root, initial, pack, operations, records=load(run_id,workspace)
    selected=initial['case_ids']
    require(not isinstance(case_ids,str) and len(set(case_ids))==len(case_ids) and set(case_ids)<=set(selected), message='Invalid question selection.')
    source_op=initial if operation=='resume' else max(operations.values(),key=lambda op:op['created_at'])
    if profile_id is not None:
        matches=[op for op in operations.values() if any(t['profile']==profile_id for t in op['tasks'])]
        require(matches, 'not_found', 'Unknown result profile.')
        source_op=max(matches,key=lambda op:op['created_at'])
    cfg=source_op['config'] if replacement is None else config.load(replacement).to_dict()
    require(cfg['version']==2 and cfg['workspace']==initial['config']['workspace'] and cfg['budget_micro_usd']==initial['config']['budget_micro_usd'], message='Recovery must retain workspace and total run budget.')
    require({m['id'] for m in cfg['models']}=={m['id'] for m in initial['config']['models']}, message='Recovery must retain model labels; settings changes create distinct profiles.')
    if replacement is not None:
        require(fingerprint(sources.load(cfg['pack']))==initial['pack_sha256'], message='Changed pack requires a new run.')
        require((cfg['case_ids'] or selected)==selected, message='Recovery cannot change denominators.')
        policy=grading.policy(cfg,pack)
    else:
        policy=runs.read(root/'operations'/source_op['operation_id']/'policy.json')
    if operation=='resume':
        require(replacement is None and initial['implementation_sha256']==implementation(), 'stale_plan','Resume requires the unchanged original configuration and implementation.')
    if operation=='grade':
        require(stage=='judge' and replacement is not None, message='A new grading stream requires a replacement judge configuration.')
        require(cfg['models']==source_op['config']['models'], message='Grading cannot change candidate settings.')
        require(profile(cfg['models'][0],cfg['judge'],policy['sha256']) != profile(source_op['config']['models'][0],source_op['config']['judge'],source_op['policy_sha256']), message='Grading requires a distinct judge/profile or policy; use retry for repair.')
    candidates={m['id']:m for m in cfg['models']}
    if model_id is not None: require(model_id in candidates, message='Unknown model ID.')
    profiles, rows=views(initial,pack,operations,records,'recovery')
    by_id={r['intent']['id']:r for r in records}
    jobs=[]; seen=set()
    # Resolve the latest operation to concrete source profiles; explicit profiles let
    # agents investigate/recover older configurations without a hidden global state.
    source_profiles={profile_id} if profile_id else {t['profile'] for t in source_op['tasks']}
    for row in rows:
        if row['profile'] not in source_profiles: continue
        if case_ids and row['case_id'] not in case_ids or model_id and row['model_id']!=model_id: continue
        candidate=by_id.get(row['candidate_attempt_id'])
        latest_candidate=by_id.get(row['latest_candidate_attempt_id'])
        latest_judge=by_id.get(row['latest_judge_attempt_id'])
        chosen_stage=stage
        if operation=='resume':
            if latest_candidate is None: chosen_stage='candidate'
            elif usable(candidate) and latest_judge is None: chosen_stage='judge'
            else: continue
        parent=latest_candidate if chosen_stage=='candidate' else latest_judge
        if operation=='retry' and failed:
            if parent and response_status(parent) not in ('error','partial','unresolved'): continue
            if chosen_stage=='candidate' and parent is None: continue
        if chosen_stage=='judge' and not usable(candidate): continue
        if operation=='retry' and not failed:
            require(bool(case_ids), message='Retrying completed outcomes requires explicit case IDs.')
        unknown=parent and not parent['intent'].get('local_rule') and (not parent['outcome'] or parent['outcome']['accounting']['kind']=='unknown_hold')
        require(not unknown or acknowledge_unknown or operation=='resume', 'unknown_billing',
                'Selected attempt has unknown billing. Retry with explicit acknowledgment to retain its hold and add a new reservation.')
        model=candidates[row['model_id']]
        if chosen_stage=='judge':
            require(model==candidate['task']['model'], message='Judge-only recovery cannot change candidate settings.')
        reason='unknown_billing_acknowledged' if unknown else ('unattempted' if parent is None else operation)
        job=task(model,cfg['judge'],policy['sha256'],row['case_id'],chosen_stage,parent['intent']['id'] if parent else None,
                 candidate['intent']['id'] if chosen_stage=='judge' else None,reason)
        key=(job['profile'],job['case_id'],job['stage'])
        if key not in seen: jobs.append(job); seen.add(key)
    require(jobs, 'empty_selection','No matching work. Completed refusals are excluded from failed-only selection.')
    changes={k:{'before':source_op['config'].get(k),'after':cfg.get(k)} for k in set(source_op['config'])|set(cfg) if source_op['config'].get(k)!=cfg.get(k)}
    if policy['sha256'] != source_op['policy_sha256']:
        changes['policy_sha256']={'before':source_op['policy_sha256'],'after':policy['sha256']}
    require(state_hash(root)==expected_state, 'run_changed', 'Run changed during planning; prepare again.')
    prepared=make_plan(cfg,pack,policy,selected,jobs,run_id,operation=operation,base=expected_state,changes=changes,accounting_before=ledger.accounting(records))
    return prepared


def list_attempts(run_id, *, workspace, case_id=None):
    _, initial, _, _, records=load(run_id,workspace)
    if case_id is not None: require(case_id in initial['case_ids'], message='Unknown selected case.')
    return {'run_id':run_id,'attempts':[{
        **a['intent'],'case_id':a['task']['case_id'],'model_id':a['task']['model']['id'],'profile':a['task']['profile'],
        'status':response_status(a),'capture_status':('complete' if a['capture']['complete'] else 'partial') if a['capture'] else ('not_applicable_local_rule' if a['intent'].get('local_rule') else 'not_applicable_mock' if a['task']['model' if a['intent']['stage']=='candidate' else 'judge']['provider']=='mock' else 'unavailable'),
        'accounting':a['outcome']['accounting'] if a['outcome'] else {'kind':'local_rule' if a['intent'].get('local_rule') else 'unknown_hold','accounted_micro_usd':a['intent']['reserved_micro_usd']}}
        for a in records if case_id is None or a['task']['case_id']==case_id]}


def inspect_attempt(run_id, attempt_id, *, workspace, include_payloads=False, include_http=False):
    require(type(include_payloads) is bool and type(include_http) is bool, message='Expected boolean inspection options.')
    _,_,_,_,records=load(run_id,workspace)
    record=next((a for a in records if a['intent']['id']==attempt_id),None)
    require(record is not None,'not_found','Unknown attempt ID.')
    capture=record['capture']; response=record['outcome']['response'] if record['outcome'] else {}
    result={'run_id':run_id,'intent':record['intent'],'task':record['task'],'status':response_status(record),
            'diagnosis':{'signal':response.get('signal','unknown'),'mechanism':response.get('mechanism')},
            'http_capture':capture,'http_body_path':str(record['path']/'response.body') if capture else None,
            'capture_status':('complete' if capture['complete'] else 'partial') if capture else ('not_applicable_local_rule' if record['intent'].get('local_rule') else 'unavailable')}
    if include_payloads: result.update(request=record['request'],outcome=record['outcome'])
    if include_http:
        import base64
        path=record['path']/'response.body'
        result['http_body_base64']=base64.b64encode(path.read_bytes()).decode('ascii') if path.exists() else None
        result['http_body_encoding']='base64'
    return result
