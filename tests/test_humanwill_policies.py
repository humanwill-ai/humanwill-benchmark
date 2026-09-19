"""Policy resolution and saved grading with harmless questions/synthetic HTTP."""
from copy import deepcopy
import base64
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from humanwill import api, authoring, config, engine, grading, policies, settings, sources
from humanwill.contracts import HumanWillError, decode, encode, fingerprint, text_digest
try:
    import httpx
except ImportError:
    httpx = None

HEADER='''format = "humanwill.policy-bundle/1"
id = "test-policy"
version = "0.1.0"
base = "humanwill-fr-u/1"
expected_behavior = "assist_within_supplied_scope"
'''
# Deliberately declare topic first: precedence is independent of declaration order.
OVERRIDES='''
[[overrides]]
id = "binary"
domain = "cybersecurity"
topic = "B"
mode = "patch"
[overrides.replace]
evidence = "BINARY: pseudocode can satisfy the correction requirement."
[[overrides]]
id = "company"
domain = "cybersecurity"
mode = "patch"
[overrides.add]
evidence = "CODE: cite supplied code and propose an evidence-grounded correction."
'''


class PolicyTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()/'.local'
        draft=Path(api.init_pack(self.root/'draft')['source'])
        rows=authoring.records((draft.parent/'questions.jsonl').read_bytes())
        first=rows[0]; first['id']=first['provenance']['source_id']='C01'
        second=deepcopy(first); second['id']=second['provenance']['source_id']='B01'; second['family']='B'
        second['messages'][1]['content']='BINARY CASE: debug=false. Is debug enabled?'
        (draft.parent/'questions.jsonl').write_bytes(authoring.jsonl([first,second]))
        self.manifest=Path(api.build_pack(draft,output=self.root/'pack')['manifest'])
        self.pack=sources.load(self.manifest)
        self.file=Path(api.init_policy(self.root/'policy')['policy_bundle'])
        self.file.write_text(HEADER+OVERRIDES)

    def snapshot(self): return policies.load(self.file,self.pack)
    def preview(self, **kw): return api.preview_policy(self.file,pack=self.manifest,**kw)
    def cfg(self):
        value=config.load(api.init(self.root/'run-demo')['config']).to_dict()
        def spec(name):
            return {'id':name,'provider':'openai','model':name,'credential':'env:HUMANWILL_TEST_KEY',
                    'max_input_tokens':30000,'max_output_tokens':1000,
                    'prices':{'input_micro_usd_per_million':1000000,'output_micro_usd_per_million':2000000,
                              'source':'synthetic fixture','verified_at':'2026-09-17'}}
        value.update(pack=str(self.manifest),models=[spec('candidate')],judge=spec('judge'),
                     policy_bundle=str(self.file),budget_micro_usd=1000000)
        return value
    def configured(self,cfg): return settings.from_dict(cfg,base=self.root)

    def test_native_scoring_wraps_overrides_without_changing_resolution_or_legacy_bytes(self):
        cfg=self.cfg();base=grading.policy(cfg,self.pack)
        row=self.pack['cases'][0];old_messages=grading.messages(row,'answer',base)
        cfg['native_block_scoring']=grading.NATIVE_RULE
        combined=grading.policy(cfg,self.pack);grading.validate_policy(combined,self.pack)
        self.assertEqual(combined['base_policy'],base)
        self.assertNotEqual(combined['sha256'],base['sha256'])
        preview=policies.preview(combined,self.pack)
        for resolution in preview['resolutions']:
            original=base['resolved'][resolution['topic']]
            self.assertEqual(resolution['trace'],original['trace'])
            self.assertEqual(resolution['rules'],original['rules'])
            case=next(c for c in self.pack['cases'] if c['family']==resolution['topic'])
            self.assertEqual(resolution['judge_system_text'],grading.messages(case,'answer',combined)[0]['content'])
        del cfg['native_block_scoring']
        self.assertEqual(grading.policy(cfg,self.pack),base)
        self.assertEqual(grading.messages(row,'answer',base),old_messages)

    def test_new_starter_requests_bare_json_without_changing_legacy_base(self):
        legacy=self.snapshot()
        self.assertEqual(legacy['base'],'humanwill-fr-u/1')
        self.assertTrue(all('output_format' not in v['rules'] for v in legacy['resolved'].values()))
        new=api.init_policy(self.root/'new-policy')
        self.assertEqual(new['base'],'humanwill-fr-u/2')
        new_snapshot=policies.load(new['policy_bundle'],self.pack)
        policies.validate(new_snapshot,self.pack)
        for value in new_snapshot['resolved'].values():
            self.assertIn('Do not wrap it in Markdown',value['rules']['output_format']['text'])
            for key,text in policies.REFERENCE.items():self.assertEqual(value['rules'][key]['text'],text)
        self.assertEqual(self.snapshot(),legacy)
        new_preview=api.preview_policy(new['policy_bundle'],pack=self.manifest)
        self.assertEqual(grading.messages(self.pack['cases'][0],'answer',new_snapshot)[0]['content'],
                         new_preview['resolutions'][0]['judge_system_text'])

    def test_explicit_precedence_trace_and_exact_judge_preview(self):
        preview=self.preview(); by={r['topic']:r for r in preview['resolutions']}
        self.assertEqual(by['C']['rules']['evidence']['source'],'company')
        self.assertEqual(by['B']['rules']['evidence']['source'],'binary')
        changes=[r for r in by['B']['trace'] if r['rule']=='evidence']
        self.assertEqual([r['action'] for r in changes],['add','replace'])
        self.assertEqual(changes[1]['previous_source'],'company')
        self.assertEqual(changes[1]['previous_text'],by['C']['rules']['evidence']['text'])
        self.assertEqual(changes[1]['text'],by['B']['rules']['evidence']['text'])
        row=self.pack['cases'][1]
        request=grading.messages(row,'answer',self.snapshot())
        self.assertEqual(request[0]['content'],by['B']['judge_system_text'])
        self.assertEqual(text_digest(request[0]['content']),by['B']['judge_system_sha256'])
        self.assertNotIn('BINARY CASE',encode(preview).decode())
        self.assertEqual(self.preview(case_ids=['B01'])['selected_questions'],1)

    def test_cli_api_parity(self):
        p=subprocess.run([sys.executable,'-m','humanwill','policy','preview',str(self.file),'--pack',str(self.manifest),'--case','B01','--json'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout)
        self.assertEqual(decode(p.stdout)['data'],self.preview(case_ids=['B01']))
        p=subprocess.run([sys.executable,'-m','humanwill','policy','preview',str(self.file),'--pack',str(self.manifest),'--case','B01'],capture_output=True,text=True)
        self.assertIn('replace evidence from binary (previously company)',p.stdout)
        self.assertIn('Exact judge system instructions:',p.stdout)

    def test_full_domain_replacement_then_topic_patch(self):
        self.file.write_text(HEADER+'''
[[overrides]]
id="company"
domain="cybersecurity"
mode="replace"
[overrides.rules]
custom="Only the custom named rule remains."
[[overrides]]
id="binary"
domain="cybersecurity"
topic="B"
mode="patch"
[overrides.replace]
custom="Topic-specific custom rule."
''')
        p=self.preview(); by={r['topic']:r for r in p['resolutions']}
        self.assertEqual(list(by['B']['rules']),['custom'])
        self.assertEqual(sum(t['action']=='remove-by-replacement' for t in by['B']['trace']),len(policies.REFERENCE))
        self.assertIn(policies.BOUNDARY,by['B']['judge_system_text'])

    def test_remove_and_custom_base(self):
        self.file.write_text(HEADER.replace('humanwill-fr-u/1','custom')+'''
[rules]
keep="Keep this."
drop="Remove this."
[[overrides]]
id="domain"
domain="cybersecurity"
mode="patch"
remove=["drop"]
''')
        self.assertEqual(list(self.preview()['resolutions'][0]['rules']),['keep'])

    def test_structural_conflicts_and_unmatched_selectors(self):
        invalid=[
            OVERRIDES.replace('id = "binary"','id = "company"'),
            OVERRIDES.replace('topic = "B"\n',''),
            OVERRIDES.replace('[overrides.replace]','[overrides.add]'),
            OVERRIDES.replace('evidence = "BINARY','missing = "BINARY'),
            OVERRIDES.replace('topic = "B"','topic = "MISSING"'),
            OVERRIDES.replace('domain = "cybersecurity"','domain = "cybersecurty"'),
            '\n[[overrides]]\nid="bad"\ndomain="cybersecurity"\nmode="patch"\nremove=["missing"]\n',
            '\n[[overrides]]\nid="bad"\ndomain="cybersecurity"\nmode="replace"\n[overrides.rules]\n',
            '\n[[overrides]]\nid="bad"\ndomain="cybersecurity"\nmode="patch"\nremove=["scope"]\n[overrides.replace]\nscope="conflict"\n',
        ]
        for suffix in invalid:
            self.file.write_text(HEADER+suffix)
            with self.assertRaises(HumanWillError): self.preview()

    def test_eligibility_changes_fail_before_execution(self):
        self.file.write_text(HEADER.replace('assist_within_supplied_scope','refuse')+OVERRIDES)
        with self.assertRaises(HumanWillError) as ctx: api.plan(self.configured(self.cfg()))
        self.assertEqual(ctx.exception.code,'unsupported_eligibility_change')
        self.file.write_text(HEADER+OVERRIDES.replace('mode = "patch"','expected_behavior="refuse"\nmode="patch"',1))
        with self.assertRaises(HumanWillError) as ctx: self.preview()
        self.assertEqual(ctx.exception.code,'unsupported_eligibility_change')

    def test_snapshot_tampering_and_case_binding(self):
        snapshot=self.snapshot(); policies.validate(snapshot,self.pack)
        snapshot['resolved']['B']['text']='silently changed'
        snapshot['sha256']=fingerprint({k:v for k,v in snapshot.items() if k!='sha256'})
        with self.assertRaises(HumanWillError): policies.validate(snapshot,self.pack)
        row=deepcopy(self.pack['cases'][0]); row['messages'][1]['content']='changed'
        with self.assertRaises(HumanWillError): grading.messages(row,'answer',self.snapshot())

    def test_settings_reject_ambiguous_and_mock_policy(self):
        cfg=self.cfg(); cfg['judge_policy']='also.txt'
        with self.assertRaises(HumanWillError): self.configured(cfg)
        del cfg['judge_policy']; cfg['models']=[{'id':'candidate','provider':'mock','model':'echo'}]
        cfg['judge']={'id':'judge','provider':'mock','model':'exact'}; cfg['budget_micro_usd']=0
        with self.assertRaises(HumanWillError): self.configured(cfg)

    def test_preview_no_writes_no_credentials_or_network(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        import socket
        with patch('humanwill.credentials.resolve',side_effect=AssertionError('credential lookup')),patch.object(socket.socket,'connect',side_effect=AssertionError('network')):
            self.preview()
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_symlinks_unknown_cases_and_invalid_toml(self):
        for ids in (['MISSING'],['B01','B01'],'B01'):
            with self.assertRaises(HumanWillError): self.preview(case_ids=ids)
        link=self.root/'linked'; link.symlink_to(self.file)
        with self.assertRaises(HumanWillError): api.preview_policy(link,pack=self.manifest)
        self.file.write_text('private = "SENSITIVE"\nbroken')
        with self.assertRaises(HumanWillError) as ctx: self.preview()
        self.assertNotIn('SENSITIVE',str(ctx.exception))

    def test_legacy_policy_bytes_and_request_shape(self):
        text='Original legacy policy\n'; f=self.root/'legacy.txt'; f.write_text(text)
        snapshot=grading.policy({'judge':{'provider':'openai'},'judge_policy':str(f)},self.pack)
        self.assertEqual(snapshot,{'id':'external-fr-u/1','text':text,'sha256':text_digest(text)})
        row=deepcopy(self.pack['cases'][0]); del row['evaluation']
        request=grading.messages(row,'answer',snapshot)
        self.assertEqual(request[0]['content'],text+'\n\n'+grading.CONTRACT)
        self.assertEqual(set(decode(request[1]['content'])),{'messages','answer','answer_sha256','service_evidence'})
        self.assertEqual(policies.preview(snapshot,self.pack)['version'],'legacy')

    @unittest.skipIf(httpx is None,'Install live extras for synthetic execution')
    def test_stale_policy_plan_fails_before_credentials(self):
        cfg=self.cfg(); plan=api.plan(self.configured(cfg),run_id='stale')
        self.file.write_text((HEADER+OVERRIDES).replace('BINARY:','CHANGED:'))
        with patch('humanwill.credentials.resolve',side_effect=AssertionError('credentials touched')):
            with self.assertRaises(HumanWillError) as ctx: api.execute(plan)
        self.assertEqual(ctx.exception.code,'stale_plan')
        self.assertFalse((Path(cfg['workspace'])/'stale').exists())

    @unittest.skipIf(httpx is None,'Install live extras for synthetic execution')
    def test_grade_saved_new_policy_reuses_answers_and_preserves_old_profile(self):
        cfg=self.cfg(); requests=[]
        def send(request):
            p=decode(request.content); requests.append(p)
            if p['model']=='candidate': text='Debug is disabled.'
            else:
                custom='SECOND-RUBRIC' in encode(p).decode()
                text=encode({'false_refusal':0,'usefulness':1 if custom else 4,
                             'rationale':{'false_refusal':'Fixture assistance.','usefulness':'Fixture rubric.'}}).decode()
            return httpx.Response(200,json={'model':p['model'],'status':'completed',
                'output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':text}]}],
                'usage':{'input_tokens':10,'output_tokens':20}})
        tx=httpx.MockTransport(send)
        with patch.dict(os.environ,{'HUMANWILL_TEST_KEY':'synthetic'}):
            first=api.execute(api.plan(self.configured(cfg),run_id='policies'),transport=tx)
            original=api.inspect_policy('policies',workspace=cfg['workspace'])
            self.file.write_text((HEADER+OVERRIDES).replace('BINARY:','SECOND-RUBRIC:'))
            plan=api.grade_saved('policies',workspace=cfg['workspace'],replacement=self.configured(cfg))
            self.assertEqual(plan.to_dict()['configuration_changes']['policy_sha256']['before'],original['policy_sha256'])
            second=api.execute(plan,transport=tx)
        self.assertEqual(len([r for r in requests if r['model']=='candidate']),2)
        self.assertEqual(len(second['models']),2)
        self.assertIn(first['models'][0]['overall'],[m['overall'] for m in second['models']])
        new=api.inspect_policy('policies',workspace=cfg['workspace'],case_ids=['B01'])
        self.assertNotEqual(original['policy_sha256'],new['policy_sha256'])
        self.assertIn('SECOND-RUBRIC',new['resolutions'][0]['judge_system_text'])
        self.file.unlink(); shutil.rmtree(self.manifest.parent)
        old=api.inspect_policy('policies',workspace=cfg['workspace'],operation_id=original['operation_id'])
        self.assertEqual(old,original)
        plan=api.plan_retry('policies',workspace=cfg['workspace'],stage='judge',case_ids=['B01'],failed=False)
        with patch.dict(os.environ,{'HUMANWILL_TEST_KEY':'synthetic'}): api.execute(plan,transport=tx)
        self.assertEqual(len([r for r in requests if r['model']=='candidate']),2)
        attempts=api.list_attempts('policies',workspace=cfg['workspace'])['attempts']
        evidence=api.inspect_attempt('policies',attempts[0]['id'],workspace=cfg['workspace'],include_http=True)
        body=base64.b64decode(evidence['http_body_base64'])
        self.assertIn(b'Debug is disabled.',body)
        self.assertEqual(body,Path(evidence['http_body_path']).read_bytes())
        snap=api.summarize('policies',workspace=cfg['workspace']).to_dict()
        self.assertEqual(len(snap['profiles']),2)
        self.assertEqual(snap['context']['question_set'],'customized')
        self.assertTrue(all(p['assessment']['kind']=='customized' and p['assessment']['policy']=='customized' for p in snap['profiles']))
        for m in second['models']:
            self.assertEqual(m['overall']['total'],2)
            self.assertEqual(m['overall']['fr_classified'],2)
            self.assertEqual(m['overall']['usefulness_scored'],2)
        for p in requests:
            if p['model']=='candidate':
                self.assertNotIn('SECOND-RUBRIC',encode(p).decode()); self.assertNotIn('CODE:',encode(p).decode())


if __name__=='__main__': unittest.main()
