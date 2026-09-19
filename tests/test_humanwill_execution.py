"""Synthetic transport tests; never authenticate or contact a provider."""
import asyncio
import base64
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from humanwill import api, config, engine, live, runs, settings, grading, ledger
from humanwill.contracts import HumanWillError, Plan, decode, encode, fingerprint
try:
    import httpx
except ImportError:
    httpx=None

REPO=Path(__file__).resolve().parents[1]


def model(provider='openai', name='candidate'):
    value={'id':name,'provider':provider,'model':name,'credential':'env:HUMANWILL_TEST_KEY',
           'max_output_tokens':1000,'max_input_tokens':30000,
           'prices':{'input_micro_usd_per_million':1000000,'output_micro_usd_per_million':2000000,
                     'source':'synthetic-price-fixture','verified_at':'2026-09-16'}}
    if provider=='openrouter': value.update(route='Fixture',returned_providers=['Fixture'])
    return value


def oa(text='answer', name='candidate', **changes):
    return {'model':name,'status':'completed','output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':text}]}],
            'usage':{'input_tokens':10,'output_tokens':20},**changes}


def judge_text(fr=0,u=4):
    return encode({'false_refusal':fr,'usefulness':u,'rationale':{'false_refusal':'Fixture willingness.','usefulness':'Fixture evidence.'}}).decode()


class JudgeFormattingTests(unittest.TestCase):
    def test_plain_and_single_fenced_json_have_identical_verdicts(self):
        raw=judge_text();expected=grading.verdict(raw,'answer','policy')
        for text in (raw,raw.encode(),' \n'+raw+'\t','```json\n'+raw+'```',
                     '```\n'+raw+'```',' \n```json\r\n'+raw.replace('\n','\r\n')+'```\n '):
            with self.subTest(text=repr(text)[:40]):
                self.assertEqual(grading.verdict(text,'answer','policy'),expected)
        self.assertIsNone(grading.verdict('```json\n'+judge_text(None,None)+'```','answer','policy')['false_refusal'])

    def test_fences_cannot_hide_commentary_multiple_objects_or_broken_json(self):
        raw=judge_text();fenced='```json\n'+raw+'```'
        bad=['Commentary\n'+fenced,fenced+'\nCommentary',fenced+'\n'+fenced,
             '```json\n'+raw,'```json '+raw+'```','```python\n'+raw+'```',
             '````json\n'+raw+'````','```json\n'+raw+raw+'```',
             '```json\n'+raw[:-2]+'\n```','```json\n\n```',
             '```json\n'+raw.replace('"false_refusal": 0','"false_refusal": 0, "false_refusal": 2',1)+'```',
             '```json\n'+raw.replace('"false_refusal": 0','"false_refusal": NaN',1)+'```']
        for text in bad:
            with self.subTest(text=text[:45]):
                with self.assertRaises(HumanWillError):grading.verdict(text,'answer','policy')

    def test_wrapped_values_still_require_exact_fields_score_types_and_rationales(self):
        valid=decode(judge_text());bad=[[],None,'prose']
        for key,value in [('false_refusal',True),('false_refusal',1.0),('false_refusal',3),
                          ('usefulness',-1),('usefulness','4'),('usefulness',5),
                          ('rationale',{'false_refusal':'','usefulness':'evidence'})]:
            item=deepcopy(valid);item[key]=value;bad.append(item)
        item=deepcopy(valid);item['extra']='unrequested';bad.append(item)
        item=deepcopy(valid);del item['usefulness'];bad.append(item)
        item=deepcopy(valid);item['rationale']['extra']='unrequested';bad.append(item)
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(HumanWillError):grading.verdict('```json\n'+encode(value).decode()+'```','answer','policy')


def sse(text='answer', done=True, model='candidate', provider='Fixture', finish='stop'):
    rows=[{'id':'gen-fixture','model':model,'provider':provider,'choices':[{'index':0,'delta':{'content':text},'finish_reason':finish}]}]
    if done: rows.append({'id':'gen-fixture','model':model,'provider':provider,'choices':[], 'usage':{'prompt_tokens':10,'completion_tokens':20}})
    return b''.join(b'data: '+encode(r).replace(b'\n',b' ')+b'\n\n' for r in rows)+(b'data: [DONE]\n\n' if done else b'')


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve(); self.path=Path(api.init(self.base,version=2)['config'])
        self.cfg=config.load(self.path).to_dict(); self.workspace=self.cfg['workspace']
        self.cases=[c['id'] for c in engine.inputs(self.path)[1]['cases']]

    def settings(self, value=None):
        return settings.from_dict(value or self.cfg,base=self.base)

    def run(self, result=None):
        # unittest.TestCase.run, not a benchmark helper.
        return super().run(result)

    def start(self, cfg=None, transport=None, run_id='test'):
        return api.execute(api.plan(self.settings(cfg),run_id=run_id),transport=transport)

    def attempts(self): return api.list_attempts('test',workspace=self.workspace)['attempts']
    def status(self, **kw): return api.status('test',workspace=self.workspace,**kw)


class RecoveryTests(Base):
    def test_v2_cli_api_parity(self):
        a=self.start()
        result=subprocess.run([sys.executable,'-m','humanwill','run','--config',str(self.path),'--run-id','cli','--execute','--json'],cwd=REPO,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout)
        b=decode(result.stdout)['data'];self.assertEqual(a['records'],b['records']);self.assertEqual(a['models'],b['models'])
        self.assertEqual(api.resolve_run('latest',workspace=self.workspace),'cli')

    def test_failed_candidate_selective_retry_and_no_refusal_retries(self):
        self.cfg['models'][0]['fail_cases']=[self.cases[0]]; self.start()
        p=api.plan_retry('test',workspace=self.workspace,stage='candidate')
        self.assertEqual([j['case_id'] for j in p.to_dict()['tasks']],[self.cases[0]])
        result=api.execute_retry(p)
        self.assertEqual(result['attempt_count'],6) # 5 initial, one failed retry
        self.assertEqual(self.status(selection='first')['records'][0]['candidate_attempt_id'],'a00000001')
        cfg=deepcopy(self.cfg);cfg['models'][0].update(model='refuse',fail_cases=[])
        self.start(cfg,run_id='refusals')
        with self.assertRaisesRegex(HumanWillError,'No matching work'):
            api.plan_retry('refusals',workspace=self.workspace,stage='candidate')

    def test_judge_only_retry_exact_binding(self):
        self.cfg['judge']['fail_cases']=[self.cases[0]];self.start()
        p=api.plan_retry('test',workspace=self.workspace)
        self.assertEqual(len(p.to_dict()['tasks']),1)
        job=p.to_dict()['tasks'][0];self.assertEqual(job['stage'],'judge')
        before=len([a for a in self.attempts() if a['stage']=='candidate'])
        api.execute(p)
        self.assertEqual(len([a for a in self.attempts() if a['stage']=='candidate']),before)
        self.assertEqual(self.attempts()[-1]['candidate_attempt_id'],job['candidate_attempt_id'])

    def test_changed_settings_and_grading_stream_do_not_pool(self):
        self.start()
        cfg=deepcopy(self.cfg);cfg['judge']['id']='new-judge'
        p=api.grade_saved('test',workspace=self.workspace,replacement=self.settings(cfg),case_ids=[self.cases[0]])
        result=api.execute(p)
        self.assertEqual(len(result['models']),2)
        self.assertEqual(sorted(m['overall']['usefulness_scored'] for m in result['models']),[1,3])
        self.assertTrue(all(m['overall']['total']==3 for m in result['models']))
        self.assertEqual(len([a for a in self.attempts() if a['stage']=='candidate']),3)
        cfg=deepcopy(self.cfg);cfg['models'][0]['model']='refuse'
        p=api.plan_retry('test',workspace=self.workspace,stage='candidate',case_ids=[self.cases[0]],failed=False,replacement=self.settings(cfg))
        result=api.execute(p)
        self.assertEqual(len(result['models']),3)

    def test_stale_selection_prevents_replay_and_plan_roundtrip(self):
        self.start();p=api.plan_retry('test',workspace=self.workspace,stage='candidate',case_ids=[self.cases[0]],failed=False)
        api.save_plan(p,self.base/'retry.json'); self.assertEqual(api.load_plan(self.base/'retry.json'),p)
        api.execute(p)
        with self.assertRaises(HumanWillError) as caught: api.execute(p)
        self.assertEqual(caught.exception.code,'stale_plan')

    def test_cancel_then_resume_skips_unresolved(self):
        async def scenario():
            async def cancel(request): raise asyncio.CancelledError
            with patch('humanwill.engine.MockProvider.invoke',side_effect=cancel):
                await api.execute_async(api.plan(self.settings(),run_id='test'))
        # Child cancellation leaves durable intents; no automatic resend.
        asyncio.run(scenario())
        with self.assertRaisesRegex(HumanWillError,'No matching work'): api.resume('test',workspace=self.workspace)
        with self.assertRaises(HumanWillError) as caught: api.plan_retry('test',workspace=self.workspace,stage='candidate')
        self.assertEqual(caught.exception.code,'unknown_billing')
        p=api.plan_retry('test',workspace=self.workspace,stage='candidate',acknowledge_unknown=True)
        result=api.execute(p); self.assertEqual(result['attempt_count'],9)

    def test_lock_excludes_another_process(self):
        self.start();root=Path(self.workspace)/'test'
        code='from humanwill.ledger import writer; from pathlib import Path;\nwith writer(Path(__import__("sys").argv[1])): pass'
        with ledger.writer(root):
            result=subprocess.run([sys.executable,'-c',code,str(root)],cwd=REPO,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('Another process',result.stderr)
        with ledger.writer(root): pass

    def test_independent_abstention_and_null_denominators(self):
        self.cfg['judge']['abstain_fr_cases']=[self.cases[0]]
        result=self.start()['models'][0]['overall']
        self.assertEqual(result['fr_classified'],2);self.assertEqual(result['usefulness_scored'],3)

    def test_private_records_and_completed_tamper_detection(self):
        self.start();root=Path(self.workspace)/'test'
        if os.name=='posix':
            for path in root.rglob('*'):
                self.assertEqual(path.stat().st_mode & 0o077,0,str(path))
        path=root/'attempts'/'a00000001'/'request.json';path.write_bytes(b'{}')
        with self.assertRaises(HumanWillError): self.status()

    def test_legacy_is_read_only_and_http_unavailable(self):
        legacy=api.init(self.base/'legacy',version=1)['config']
        cfg=config.load(legacy);api.execute(api.plan(cfg,run_id='old'))
        with self.assertRaises(HumanWillError) as caught: api.resume('old',workspace=cfg.workspace)
        self.assertEqual(caught.exception.code,'read_only_history')
        self.assertIsNone(api.inspect_attempt('old','a000001',workspace=cfg.workspace,include_http=True)['http_capture'])


    def test_latest_configuration_profile_is_used_for_next_retry(self):
        self.start();cfg=deepcopy(self.cfg)
        cfg['models'][0].update(model='refuse',fail_cases=[self.cases[0]])
        p=api.plan_retry('test',workspace=self.workspace,stage='candidate',case_ids=[self.cases[0]],failed=False,replacement=self.settings(cfg))
        original=self.status()['models'][0]['profile'];api.execute(p)
        next_plan=api.plan_retry('test',workspace=self.workspace,stage='candidate')
        self.assertEqual(len(next_plan.to_dict()['tasks']),1)
        self.assertEqual(next_plan.to_dict()['tasks'][0]['model']['model'],'refuse')
        self.assertEqual(next_plan.to_dict()['tasks'][0]['parent_attempt_id'],'a00000007')
        older=api.plan_retry('test',workspace=self.workspace,stage='candidate',case_ids=[self.cases[0]],failed=False,profile_id=original)
        self.assertEqual(older.to_dict()['tasks'][0]['model']['model'],'echo')

    def test_external_cancellation_and_resume_never_replays_intent(self):
        self.cfg["concurrency"]=1
        async def scenario():
            entered=asyncio.Event();wait=asyncio.Event()
            async def block(request): entered.set();await wait.wait()
            with patch('humanwill.engine.MockProvider.invoke',side_effect=block):
                work=asyncio.create_task(api.execute_async(api.plan(self.settings(),run_id='test')))
                await entered.wait();work.cancel()
                with self.assertRaises(asyncio.CancelledError):await work
        asyncio.run(scenario())
        self.assertEqual(len(self.attempts()),1)
        p=api.resume('test',workspace=self.workspace)
        self.assertEqual({j['case_id'] for j in p.to_dict()['tasks']},set(self.cases[1:]))
        api.execute(p)
        self.assertEqual(self.attempts()[0]['status'],'unresolved')
        self.assertEqual(len(self.attempts()),5)

    def test_saved_snapshot_recovery_without_original_demo(self):
        self.cfg['judge']['fail_cases']=[self.cases[0]];self.start()
        import shutil
        shutil.rmtree(self.base/'demo-pack');self.path.unlink()
        p=api.plan_retry('test',workspace=self.workspace)
        self.assertEqual(api.execute(p)['attempt_count'],7)

    def test_retry_cli_preview_has_no_effect_and_is_api_equivalent(self):
        self.cfg['judge']['fail_cases']=[self.cases[0]];self.start()
        before=engine.state_hash(Path(self.workspace)/'test')
        result=subprocess.run([sys.executable,'-m','humanwill','retry','latest','--workspace',self.workspace,'--failed','--stage','judge','--json'],cwd=REPO,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout)
        value=decode(result.stdout)['data']
        self.assertEqual(value['tasks'],api.plan_retry('test',workspace=self.workspace).to_dict()['tasks'])
        self.assertEqual(engine.state_hash(Path(self.workspace)/'test'),before)
        result=subprocess.run([sys.executable,'-m','humanwill','retry','test','--workspace',self.workspace,'--execute','--json'],cwd=REPO,capture_output=True,text=True)
        self.assertEqual(result.returncode,3,result.stdout);self.assertEqual(decode(result.stdout)['data']['attempt_count'],7)

    def test_empty_and_reserved_run_ids_rejected_before_write(self):
        for run_id in ('','latest','../escape'):
            with self.assertRaises(HumanWillError):
                api.execute(api.plan(self.settings(),run_id=run_id))
        self.assertFalse(Path(self.workspace).exists())


@unittest.skipUnless(httpx,'Install the live extra for synthetic HTTP tests.')
class LiveTests(Base):
    def setUp(self):
        super().setUp(); self.cfg['models']=[model()];self.cfg['judge']=model(name='judge')
        self.cfg['budget_micro_usd']=1000000
        self.cfg['judge_policy']=str(self.base/'judge.txt');Path(self.cfg['judge_policy']).write_text('Synthetic policy: score fixture evidence independently.')
        env=patch.dict(os.environ,{'HUMANWILL_TEST_KEY':'synthetic-not-a-real-key'});env.start();self.addCleanup(env.stop)

    def transport(self, candidate=None, judge=None):
        def handler(request):
            payload=decode(request.content)
            value=(judge or oa(judge_text(),name='judge')) if payload['model']=='judge' else (candidate or oa())
            return httpx.Response(200,content=encode(value),headers={'x-request-id':'fixture','set-cookie':'SECRET_COOKIE'})
        return httpx.MockTransport(handler)

    def native_setup(self):
        draft=api.init_pack(self.base/'.local'/'native-draft')['source']
        self.cfg['pack']=api.build_pack(draft,output=self.base/'.local'/'native-pack')['manifest']
        self.cfg['case_ids']=[]
        self.cfg['native_block_scoring']=grading.NATIVE_RULE
        self.cases=[r['id'] for r in engine.inputs(self.settings())[1]['cases']]

    def test_native_block_local_score_preserves_capture_budget_and_denominators(self):
        self.native_setup()
        _,pack,_,_=engine.inputs(self.settings())
        spec=settings.spec(self.cfg['models'][0])
        self.cfg['budget_micro_usd']=live.reservation(spec,live.request(spec,pack['cases'][0]['messages']))
        calls=[]
        def handler(request):
            calls.append(decode(request.content)['model'])
            return httpx.Response(403,json={'error':{'code':'cyber_policy'}})
        result=self.start(transport=httpx.MockTransport(handler))
        self.assertEqual(calls,['candidate']);self.assertEqual(result['status'],'complete')
        self.assertEqual(result['unknown_hold_micro_usd'],self.cfg['budget_micro_usd'])
        self.assertEqual(result['accounted_micro_usd'],self.cfg['budget_micro_usd'])
        self.assertEqual(result['records'][0]['grading_method'],grading.NATIVE_RULE)
        metrics=result['models'][0]['overall']
        self.assertEqual((metrics['total'],metrics['fr_classified'],metrics['usefulness_scored']),(1,1,1))
        self.assertEqual((metrics['false_refusal_rate'],metrics['mean_usefulness']),(1,0))
        local=api.inspect_attempt('test','a00000002',workspace=self.workspace,include_payloads=True,include_http=True)
        self.assertEqual(local['intent']['reserved_micro_usd'],0)
        self.assertEqual(local['capture_status'],'not_applicable_local_rule')
        self.assertIsNone(local['http_body_base64'])
        self.assertEqual(local['outcome']['accounting'],{'kind':'local_rule','accounted_micro_usd':0})
        self.assertEqual(local['request']['candidate_attempt_id'],'a00000001')
        raw=api.inspect_attempt('test','a00000001',workspace=self.workspace,include_http=True)
        self.assertEqual(decode(base64.b64decode(raw['http_body_base64'])),{'error':{'code':'cyber_policy'}})
        self.assertEqual(self.attempts()[1]['capture_status'],'not_applicable_local_rule')
        preview=api.inspect_policy('test',workspace=self.workspace)
        self.assertEqual(preview['native_block_scoring'],grading.NATIVE_RULE)
        self.assertIn(grading.NATIVE_TEXT,preview['resolutions'][0]['judge_system_text'])
        report=api.summarize('test',workspace=self.workspace).to_dict()
        self.assertEqual(report['profiles'][0]['coverage']['grading_methods'],{grading.NATIVE_RULE:1})
        self.assertTrue(any('locally (FR2/U0)' in s for s in report['limitations']))
        with self.assertRaisesRegex(HumanWillError,'No matching work'):
            api.plan_retry('test',workspace=self.workspace,stage='candidate')

    def test_native_rule_requires_explicit_eligibility_not_demo_or_error_prose(self):
        self.cfg['case_ids']=[self.cases[0]];self.cfg['native_block_scoring']=grading.NATIVE_RULE
        calls=[]
        def handler(request):
            name=decode(request.content)['model'];calls.append(name)
            return httpx.Response(200,json=oa(judge_text(),name='judge')) if name=='judge' else httpx.Response(403,json={'error':{'code':'cyber_policy'}})
        self.start(transport=httpx.MockTransport(handler))
        self.assertEqual(calls,['candidate','judge'])
        self.native_setup()
        for i,error in enumerate(({'code':'permission_denied','message':'cyber_policy refusal'}, {'message':'content_filter'})):
            result=self.start(run_id='generic'+str(i),transport=httpx.MockTransport(lambda r:httpx.Response(403,json={'error':error})))
            self.assertEqual(result['attempt_count'],1)
            self.assertIsNone(result['records'][0]['false_refusal'])

    def test_native_rule_leaves_text_and_partial_outputs_with_semantic_judge(self):
        self.native_setup()
        candidates=[oa('Some useful assistance',output=[{'type':'message','role':'assistant','content':[
            {'type':'output_text','text':'Some useful assistance'},{'type':'refusal','refusal':'Cannot continue.'}]}]),
            oa('Partial assistance',status='incomplete',incomplete_details={'reason':'content_filter'}),
            oa('I refuse because of cyber_policy')]
        for i,candidate in enumerate(candidates):
            result=self.start(run_id='text'+str(i),transport=self.transport(candidate=candidate,judge=oa(judge_text(fr=1,u=2),name='judge')))
            self.assertNotIn('grading_method',result['records'][0])
            self.assertEqual((result['records'][0]['false_refusal'],result['records'][0]['usefulness']),(1,2))

    def test_native_empty_structured_refusal_and_incomplete_capture(self):
        self.native_setup();self.cfg['models']=[model('anthropic')]
        body={'type':'message','role':'assistant','model':'candidate','content':[],
              'stop_reason':'refusal','usage':{'input_tokens':10,'output_tokens':0}}
        calls=[]
        def handler(request): calls.append(request);return httpx.Response(200,json=body)
        result=self.start(transport=httpx.MockTransport(handler))
        self.assertEqual(len(calls),1);self.assertEqual(result['records'][0]['false_refusal'],2)
        _,_,pack,ops,records=engine.load('test',self.workspace)
        policy=runs.read(records[0]['path'].parent.parent/'operations'/next(iter(ops))/'policy.json')
        candidate=deepcopy(records[0]);candidate['capture']['complete']=False
        self.assertIsNone(grading.native_request(pack['cases'][0],policy,candidate))
        for mutation in ({'complete':False},{'answer':'Useful text'},{'signal':'unknown'},{'status':'error'}):
            candidate=deepcopy(records[0]);candidate['outcome']['response'].update(mutation)
            self.assertIsNone(grading.native_request(pack['cases'][0],policy,candidate))

    def test_native_regrade_is_distinct_local_and_requires_no_credentials(self):
        self.native_setup();del self.cfg['native_block_scoring']
        def legacy(request):
            return httpx.Response(200,json=oa(judge_text(fr=1,u=1),name='judge')) if decode(request.content)['model']=='judge' else httpx.Response(403,json={'error':{'code':'cyber_policy'}})
        before=self.start(transport=httpx.MockTransport(legacy))
        old_profile=before['records'][0]['profile']
        root=Path(self.workspace)/'test'
        original={p:p.read_bytes() for p in root.rglob('*') if p.is_file() and p.suffix in ('.json','.body')}
        self.cfg['native_block_scoring']=grading.NATIVE_RULE
        plan=api.grade_saved('test',workspace=self.workspace,replacement=self.settings())
        with patch('humanwill.credentials.resolve',side_effect=AssertionError('No credential needed')):
            result=api.execute(plan,transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError('No HTTP'))))
        self.assertEqual(result['attempt_count'],3)
        rows={r['profile']:r for r in result['records']}
        self.assertEqual(rows[old_profile]['false_refusal'],1)
        other=next(r for p,r in rows.items() if p!=old_profile)
        self.assertEqual(other['false_refusal'],2);self.assertEqual(other['candidate_attempt_id'],'a00000001')
        for p,raw in original.items(): self.assertEqual(p.read_bytes(),raw)
        retry=api.plan_retry('test',workspace=self.workspace,stage='judge',failed=False,case_ids=self.cases)
        with patch('humanwill.credentials.resolve',side_effect=AssertionError):
            self.assertEqual(api.execute(retry)['attempt_count'],4)

    def test_native_policy_validation_and_tamper_rejection(self):
        self.native_setup()
        for bad in (True,'native-block-fr-u/2','off',None):
            cfg=deepcopy(self.cfg);cfg['native_block_scoring']=bad
            with self.assertRaises(HumanWillError): self.settings(cfg)
        _,pack,policy,_=engine.inputs(self.settings())
        grading.validate_policy(policy,pack)
        for key,value in (('rule','unknown'),('rule_text','changed'),('pack_sha256','0'*64)):
            altered=deepcopy(policy);altered[key]=value
            altered['sha256']=fingerprint({k:v for k,v in altered.items() if k!='sha256'})
            with self.assertRaises(HumanWillError): grading.validate_policy(altered,pack)
        self.start(transport=httpx.MockTransport(lambda r:httpx.Response(403,json={'error':{'code':'cyber_policy'}})))
        root=Path(self.workspace)/'test'
        # Remove completion seal to test semantic validation, not only inventory hashes.
        for p in (root/'operations').glob('*/completion.json'): p.unlink()
        out=root/'attempts'/'a00000002'/'outcome.json';value=runs.read(out)
        value['verdict']['false_refusal']=0
        out.write_bytes(encode(engine.seal({k:v for k,v in value.items() if k!='sha256'})))
        with self.assertRaisesRegex(HumanWillError,'Local verdict changed'): self.status()

    def test_interrupted_local_scoring_retries_without_billing_acknowledgment(self):
        self.native_setup()
        result=self.start(transport=httpx.MockTransport(lambda r:httpx.Response(403,json={'error':{'code':'cyber_policy'}})))
        root=Path(self.workspace)/'test'
        for p in (root/'operations').glob('*/completion.json'): p.unlink()
        (root/'attempts'/'a00000002'/'outcome.json').unlink()
        self.assertNotIn('grading_method',self.status()['records'][0])
        retry=api.plan_retry('test',workspace=self.workspace,stage='judge')
        with patch('humanwill.credentials.resolve',side_effect=AssertionError):
            recovered=api.execute(retry)
        self.assertEqual(recovered['records'][0]['false_refusal'],2)
        self.assertEqual(recovered['accounted_micro_usd'],result['accounted_micro_usd'])
        self.assertEqual(recovered['unknown_hold_micro_usd'],result['unknown_hold_micro_usd'])

    def test_offline_plan_no_credential_read_and_invalid_config(self):
        with patch('humanwill.credentials.resolve',side_effect=AssertionError):
            p=api.plan(self.settings());self.assertFalse(p.to_dict()['simulated'])
        self.assertFalse(Path(self.workspace).exists())
        for mutate in (lambda c:c['models'][0].update(api_key='SECRET'),lambda c:c.update(budget_micro_usd=0),
                       lambda c:c['models'][0].update(credential='SECRET'),lambda c:c['models'][0].update(provider='unknown'),
                       lambda c:c['models'][0]['prices'].update(input_micro_usd_per_million=True)):
            cfg=deepcopy(self.cfg);mutate(cfg)
            with self.assertRaises(HumanWillError):self.settings(cfg)

    def test_openai_exact_request_capture_and_usage(self):
        result=self.start(transport=self.transport());self.assertEqual(result['status'],'complete')
        self.assertEqual(result['accounted_micro_usd'],300)
        a=api.inspect_attempt('test','a00000001',workspace=self.workspace,include_payloads=True,include_http=True)
        self.assertEqual(decode(base64.b64decode(a['http_body_base64'])),oa())
        self.assertFalse(a['request']['store']);self.assertEqual(a['request']['input'],engine.inputs(self.settings())[1]['cases'][0]['messages'])
        self.assertNotIn('SECRET_COOKIE',encode(a['http_capture']).decode())
        for path in (Path(self.workspace)/'test').rglob('*.json'):
            self.assertNotIn('synthetic-not-a-real-key',path.read_text())
        self.assertEqual(result['models'][0]['overall']['mean_usefulness'],4)

    def test_anthropic_candidate_and_judge(self):
        self.cfg['models']=[model('anthropic')];self.cfg['judge']=model('anthropic','judge')
        def handler(request):
            payload=decode(request.content);name=payload['model']
            self.assertIn('system',payload);self.assertNotEqual(payload['messages'][0]['role'],'system')
            value={'model':name,'type':'message','role':'assistant','content':[{'type':'text','text':judge_text() if name=='judge' else 'answer'}],
                   'stop_reason':'end_turn','usage':{'input_tokens':10,'output_tokens':20,'cache_read_input_tokens':5}}
            return httpx.Response(200,content=encode(value))
        result=self.start(transport=httpx.MockTransport(handler));self.assertEqual(result['status'],'complete');self.assertEqual(result['accounted_micro_usd'],330)

    def test_fenced_judge_recovery_preserves_raw_capture_old_failure_and_candidate(self):
        self.cfg['models']=[model('anthropic')];self.cfg['judge']=model('anthropic','judge')
        self.cfg['case_ids']=[self.cases[0]]
        wrapped='```json\n'+judge_text()+'```';calls=[]
        def handler(request):
            payload=decode(request.content);name=payload['model'];calls.append(name)
            return httpx.Response(200,content=encode({'model':name,'type':'message','role':'assistant',
                'content':[{'type':'text','text':wrapped if name=='judge' else 'answer'}],
                'stop_reason':'end_turn','usage':{'input_tokens':10,'output_tokens':20}}))
        transport=httpx.MockTransport(handler);original=grading.verdict
        def old_parser(text,*args):
            if isinstance(text,str) and text.startswith('```'):raise HumanWillError('invalid_input','Invalid JSON document.')
            return original(text,*args)
        with patch('humanwill.grading.verdict',side_effect=old_parser):
            before=self.start(transport=transport)
        self.assertEqual(before['status'],'partial')
        root=Path(self.workspace)/'test'
        retained={p:p.read_bytes() for p in root.rglob('*') if p.is_file() and p.suffix in ('.json','.body')}
        prepared=api.plan_retry('test',workspace=self.workspace,stage='judge')
        self.assertEqual(prepared.to_dict()['tasks'][0]['candidate_attempt_id'],'a00000001')
        after=api.execute(prepared,transport=transport)
        self.assertEqual(calls,['candidate','judge','judge'])
        self.assertEqual(after['status'],'complete');self.assertEqual(after['attempt_count'],3)
        self.assertEqual(after['models'][0]['overall']['fr_classified'],1)
        self.assertEqual(after['models'][0]['overall']['usefulness_scored'],1)
        self.assertEqual(api.status('test',workspace=self.workspace,selection='first')['models'][0]['overall']['fr_classified'],0)
        for p,raw in retained.items():self.assertEqual(p.read_bytes(),raw)
        inspected=api.inspect_attempt('test','a00000003',workspace=self.workspace,include_payloads=True,include_http=True)
        self.assertEqual(inspected['outcome']['response']['answer'],wrapped)
        self.assertEqual(decode(base64.b64decode(inspected['http_body_base64']))['content'][0]['text'],wrapped)
        self.assertEqual(inspected['outcome']['verdict']['false_refusal'],0)

    def test_openrouter_strict_route_and_final_usage(self):
        self.cfg['models']=[model('openrouter')]
        def handler(request):
            payload=decode(request.content)
            if payload['model']=='judge': return httpx.Response(200,content=encode(oa(judge_text(),name='judge')))
            self.assertEqual(payload['provider'],{'only':['Fixture'],'order':['Fixture'],'allow_fallbacks':False,'require_parameters':True})
            return httpx.Response(200,content=sse())
        self.assertEqual(self.start(transport=httpx.MockTransport(handler))['status'],'complete')
        bad=live.normalize(settings.spec(model('openrouter')),200,sse(provider='Wrong'),True)
        self.assertEqual(bad['status'],'error');self.assertEqual(bad['answer'],'')

    def test_structured_policy_evidence_not_prose(self):
        spec=settings.spec(model())
        blocked=live.normalize(spec,403,encode({'error':{'code':'cyber_policy','message':'private'}}),True)
        self.assertEqual(blocked['mechanism'],'cyber_policy')
        generic=live.normalize(spec,403,encode({'error':{'message':'cyber_policy'}}),True)
        self.assertEqual(generic['signal'],'unknown')
        prose=live.normalize(spec,200,encode(oa('cyber_policy refusal timeout')),True)
        self.assertEqual(prose['signal'],'text_requires_review')

    def test_partial_stream_capture_survives_timeout_and_empty_retry(self):
        self.cfg['models']=[model('openrouter')];self.cfg['case_ids']=[self.cases[0]]
        class Broken(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield sse('usable partial',done=False,finish=None)
                raise httpx.ReadTimeout('SECRET_EXCEPTION')
        def partial(request):
            return httpx.Response(200,content=encode(oa(judge_text(),name='judge'))) if decode(request.content)['model']=='judge' else httpx.Response(200,stream=Broken())
        result=self.start(transport=httpx.MockTransport(partial));self.assertEqual(result['records'][0]['candidate'],'partial')
        kept=result['records'][0]['candidate_attempt_id'];hold=result['unknown_hold_micro_usd'];self.assertGreater(hold,0)
        p=api.plan_retry('test',workspace=self.workspace,stage='candidate',acknowledge_unknown=True)
        result=api.execute(p,transport=httpx.MockTransport(lambda req:httpx.Response(200,content=sse(''))))
        self.assertEqual(result['records'][0]['candidate_attempt_id'],kept)
        self.assertEqual(result['models'][0]['overall']['usefulness_scored'],1)
        self.assertGreaterEqual(result['unknown_hold_micro_usd'],hold)
        a=api.inspect_attempt('test',kept,workspace=self.workspace,include_http=True)
        self.assertEqual(a['capture_status'],'partial');self.assertEqual(base64.b64decode(a['http_body_base64']),sse('usable partial',done=False,finish=None))

    def test_generation_success_judge_failure_then_repair(self):
        self.cfg['case_ids']=[self.cases[0]]
        result=self.start(transport=self.transport(judge=oa('{invalid',name='judge')))
        self.assertEqual(result['records'][0]['candidate'],'accepted');self.assertEqual(result['records'][0]['judge'],'error')
        p=api.plan_retry('test',workspace=self.workspace)
        result=api.execute(p,transport=self.transport());self.assertEqual(result['attempt_count'],3);self.assertEqual(result['status'],'complete')

    def test_concurrency_reserves_before_dispatch_and_unknown_survives_restart(self):
        self.cfg['concurrency']=3
        spec=settings.spec(self.cfg['models'][0]);pack=engine.inputs(self.settings())[1]
        maximum=max(live.reservation(spec,live.request(spec,r['messages'])) for r in pack['cases'])
        self.cfg['budget_micro_usd']=maximum+100
        calls=[]
        async def timeout(request):
            calls.append(request);await asyncio.sleep(.01);raise httpx.ReadTimeout('SECRET_TIMEOUT')
        result=self.start(transport=httpx.MockTransport(timeout))
        self.assertEqual(len(calls),1);self.assertGreater(result['unknown_hold_micro_usd'],0)
        self.assertEqual(self.status()['accounted_micro_usd'],result['accounted_micro_usd'])
        p=api.resume('test',workspace=self.workspace)
        self.assertEqual(len(p.to_dict()['tasks']),2)
        api.execute(p,transport=httpx.MockTransport(timeout));self.assertEqual(len(calls),1)

    def test_usage_exceeding_bound_stops_future_work(self):
        self.cfg['case_ids']=[self.cases[0]]
        huge=oa(usage={'input_tokens':100000000,'output_tokens':10})
        result=self.start(transport=self.transport(candidate=huge))
        self.assertGreater(result['accounted_micro_usd'],result['budget_micro_usd']);self.assertEqual(result['attempt_count'],1)
        self.assertEqual(result['records'][0]['judge'],'unattempted')

    def test_cancel_writes_partial_http_and_keeps_intent(self):
        self.cfg['case_ids']=[self.cases[0]]
        class Cancelled(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'partial';raise asyncio.CancelledError
        async def go(): await api.execute_async(api.plan(self.settings(),run_id='test'),transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=Cancelled())))
        asyncio.run(go())
        a=api.inspect_attempt('test','a00000001',workspace=self.workspace,include_http=True)
        self.assertEqual(a['status'],'unresolved');self.assertEqual(a['capture_status'],'partial')
        self.assertGreater(self.status()['unknown_hold_micro_usd'],0)

    def test_unknown_usage_and_cached_reasoning_accounting(self):
        spec=settings.spec(model())
        self.assertEqual(live.usage_bound(spec,{'input_tokens':10,'output_tokens':20,'output_tokens_details':{'reasoning_tokens':15},'input_tokens_details':{'cached_tokens':8}}),50)
        self.assertIsNone(live.usage_bound(spec,{'input_tokens':True,'output_tokens':20}))
        self.assertIsNone(live.usage_bound(spec,{'input_tokens':10,'output_tokens':20,'input_tokens_details':{'cache_write_tokens':5}}))


    def test_stream_without_terminator_retains_accounting_hold(self):
        self.cfg['models']=[model('openrouter')];self.cfg['case_ids']=[self.cases[0]]
        raw=sse().replace(b'data: [DONE]\n\n',b'')
        def handler(request):
            return httpx.Response(200,content=encode(oa(judge_text(),name='judge'))) if decode(request.content)['model']=='judge' else httpx.Response(200,content=raw)
        result=self.start(transport=httpx.MockTransport(handler))
        self.assertGreater(result['unknown_hold_micro_usd'],0);self.assertEqual(result['records'][0]['candidate'],'partial')

    def test_judge_only_repair_does_not_read_candidate_credential(self):
        self.cfg['models'][0]['credential']='env:CANDIDATE_TEST_KEY'
        self.cfg['case_ids']=[self.cases[0]]
        with patch.dict(os.environ,{'CANDIDATE_TEST_KEY':'synthetic-candidate-key'}):
            self.start(transport=self.transport(judge=oa('invalid',name='judge')))
        p=api.plan_retry('test',workspace=self.workspace)
        with patch.dict(os.environ,{'CANDIDATE_TEST_KEY':''}):
            self.assertEqual(api.execute(p,transport=self.transport())['status'],'complete')

    def test_invalid_judgments_do_not_change_metric_denominators(self):
        self.cfg['case_ids']=[self.cases[0]]
        for text in (judge_text(fr=True),judge_text(u=9),judge_text().replace('"false_refusal": 0','"false_refusal": NaN'),'{"false_refusal":0,"false_refusal":1}'):
            with self.assertRaises(HumanWillError):grading.verdict(text,'answer','x')
        result=self.start(transport=self.transport(judge=oa(judge_text(fr=None),name='judge')))
        metrics=result['models'][0]['overall']
        self.assertIsNone(metrics['false_refusal_rate']);self.assertEqual(metrics['mean_usefulness'],4)

    def test_live_judge_policy_snapshot_survives_source_removal(self):
        self.cfg['case_ids']=[self.cases[0]];self.start(transport=self.transport(judge=oa('invalid',name='judge')))
        Path(self.cfg['judge_policy']).unlink()
        p=api.plan_retry('test',workspace=self.workspace)
        self.assertEqual(api.execute(p,transport=self.transport())['status'],'complete')

    def test_rate_pacing_spaces_durable_request_admissions(self):
        from types import SimpleNamespace
        self.cfg['minimum_interval_ms']=20;self.cfg['concurrency']=3
        ticks=[];clock=[100.0];write=runs.write
        async def paced_sleep(delay):
            self.assertGreaterEqual(delay,0)
            clock[0]+=delay
            await asyncio.sleep(0)
        def record_write(path,value):
            if path.name=='intent.json':ticks.append(clock[0])
            return write(path,value)
        # Pacing acts before durable intent/client setup, not at HTTP arrival.
        # Observe that boundary with a scheduler clock isolated from HTTPX's real
        # event loop. Disk/client startup jitter must not decide a 20ms assertion.
        scheduler=SimpleNamespace(**vars(asyncio))
        scheduler.get_running_loop=lambda:SimpleNamespace(time=lambda:clock[0])
        scheduler.sleep=paced_sleep
        with patch.object(engine,'asyncio',scheduler),patch.object(runs,'write',side_effect=record_write):
            result=self.start(transport=self.transport())
        self.assertEqual(result['status'],'complete')
        self.assertEqual(len(ticks),2*len(self.cases))
        for first,second in zip(ticks,ticks[1:]):self.assertAlmostEqual(second-first,.020)


    def test_policy_block_is_judged_with_evidence_and_not_automatically_retried(self):
        self.cfg['case_ids']=[self.cases[0]]
        def handler(request):
            payload=decode(request.content)
            if payload['model']=='judge':
                packet=decode(payload['input'][1]['content'])
                self.assertEqual(packet['service_evidence']['mechanism'],'cyber_policy')
                return httpx.Response(200,content=encode(oa(judge_text(fr=2,u=0),name='judge')))
            return httpx.Response(403,content=encode({'error':{'code':'cyber_policy'}}))
        result=self.start(transport=httpx.MockTransport(handler))
        self.assertEqual(result['status'],'complete');self.assertEqual(result['models'][0]['overall']['false_refusals'],1)
        self.assertEqual(result['models'][0]['service_signals']['provider_safety_block'],1)
        with self.assertRaisesRegex(HumanWillError,'No matching work'):api.plan_retry('test',workspace=self.workspace,stage='candidate')
        self.assertGreater(result['unknown_hold_micro_usd'],0)

    def test_total_deadline_preserves_received_bytes(self):
        self.cfg['case_ids']=[self.cases[0]];self.cfg['models'][0]['timeout_seconds']=1
        class Heartbeats(httpx.AsyncByteStream):
            async def __aiter__(self):
                while True:
                    yield b'heartbeat';await asyncio.sleep(.05)
        result=self.start(transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=Heartbeats())))
        self.assertEqual(result['attempt_count'],1)
        self.assertGreater(result['unknown_hold_micro_usd'],0)
        inspected=api.inspect_attempt('test','a00000001',workspace=self.workspace,include_http=True)
        self.assertEqual(inspected['capture_status'],'partial')
        self.assertIn(b'heartbeat',base64.b64decode(inspected['http_body_base64']))


if __name__=='__main__': unittest.main()
