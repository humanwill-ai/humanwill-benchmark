"""Aggregate/reader contracts; all data is harmless and local, never model calls."""
import base64
from copy import deepcopy
import csv
from dataclasses import replace
from html.parser import HTMLParser
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from humanwill import api, config, engine, reporting, sources
from humanwill.contracts import HumanWillError, decode, digest, encode, fingerprint

REPO = Path(__file__).resolve().parents[1]
VISUAL = all(importlib.util.find_spec(x) for x in ('matplotlib','reportlab','PIL'))


class ReaderParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.case=None; self.role=None; self.messages={}; self.scripts=[]; self.ids=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.append(attrs['id'])
        if tag=='article':self.case=attrs['data-case-id'];self.messages[self.case]={}
        if tag=='pre':
            self.role=attrs.get('data-role')
            if self.role:self.messages[self.case][self.role]=''
        if tag=='script':self.scripts.append(attrs)
    def handle_data(self, data):
        if self.role:self.messages[self.case][self.role]+=data
    def handle_endtag(self, tag):
        if tag=='pre':self.role=None


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.cfg_path=Path(api.init(self.base/'demo')['config'])
        self.cfg=config.load(self.cfg_path);self.workspace=self.cfg.workspace
        self.report=None

    def prepare(self, cfg=None):
        api.execute(api.plan(cfg or self.cfg,run_id='test'))
        self.report=api.summarize('test',workspace=self.workspace)
        return self.report

    def output(self, name):return self.base/'exports'/name

    def test_native_scoring_counts_are_inspectable_in_exports(self):
        # Synthetic renderer input, not a new model-performance result.
        data=self.prepare().to_dict()
        counts={'native-block-fr-u/1':1,'semantic_judge':2}
        data['profiles'][0]['coverage']['grading_methods']=counts
        data['report_sha256']=fingerprint({k:v for k,v in data.items() if k!='report_sha256'})
        reporting.load_report(reporting.Report(encode(data)))
        rows=list(csv.DictReader(io.StringIO(reporting.csv_bytes(data).decode())))
        self.assertTrue(all(decode(row['profile_grading_methods'])==counts for row in rows))
        if VISUAL:
            from humanwill import presentation
            for style in ('clean','spotlight'):
                charts=presentation.charts(data,style,formats=('svg','png'))
                self.assertTrue(all(b'Includes local native-block-fr-u/1' in c['svg'] for c in charts))
                html=presentation.html_report(data,charts,style,'Synthetic scoring method check')
                self.assertIn('grading_methods',html)
                self.assertIn('native-block-fr-u/1',html)
        data['profiles'][0]['coverage']['grading_methods']['semantic_judge']=1
        data['report_sha256']=fingerprint({k:v for k,v in data.items() if k!='report_sha256'})
        with self.assertRaisesRegex(HumanWillError,'Coverage population changed'):
            reporting.load_report(reporting.Report(encode(data)))

    def test_snapshot_immutable_exact_denominators_and_no_payloads(self):
        report=self.prepare();value=report.to_dict();value['profiles'].clear()
        self.assertEqual(len(report.to_dict()['profiles']),1)
        data=report.to_dict();status=api.status('test',workspace=self.workspace)
        self.assertEqual(data['profiles'][0]['overall'],status['models'][0]['overall'])
        text=encode(data).decode()
        for banned in ('credential','workspace','messages','mock_behavior','fail_cases','abstain_fr_cases'):
            self.assertNotIn('"'+banned+'"',text)
        for row in sources.load(self.cfg.pack)['cases']:
            self.assertNotIn(row['messages'][1]['content'],text)
        self.assertTrue(data['contains_simulation'])

    def test_independent_abstentions_and_zero_scored_export(self):
        cfg=self.cfg.to_dict();cfg['judge']['abstain_fr_cases']=['D01']
        self.prepare(config.from_dict(cfg,base=self.base))
        metrics=self.report.to_dict()['profiles'][0]['overall']
        self.assertEqual(metrics['fr_classified'],2);self.assertEqual(metrics['usefulness_scored'],3)
        cfg['models'][0]['fail_cases']=['D01','D02','D03']
        cfg['workspace']=str(self.base/'failed')
        api.execute(api.plan(config.from_dict(cfg,base=self.base),run_id='empty'))
        data=api.summarize('empty',workspace=cfg['workspace']).to_dict()['profiles'][0]['overall']
        self.assertIsNone(data['false_refusal_rate']);self.assertIsNone(data['mean_usefulness'])

    def test_selected_partial_and_policy_evidence_remain_separate_from_scores(self):
        self.prepare()
        result=api.status('test',workspace=self.workspace)
        result['records'][0].update(candidate='partial',candidate_signal='incomplete')
        result['records'][1].update(candidate='blocked',candidate_signal='provider_safety_block')
        with patch.object(api,'status',return_value=result):
            model=api.summarize('test',workspace=self.workspace).to_dict()['profiles'][0]
        self.assertEqual(model['coverage']['candidate_states'],{'partial':1,'blocked':1,'accepted':1})
        self.assertEqual(model['coverage']['service_signals']['provider_safety_block'],1)
        self.assertEqual(model['overall'],self.report.to_dict()['profiles'][0]['overall'])

    def test_first_recovery_and_profile_selections_remain_separate(self):
        self.prepare();initial=self.report.to_dict()
        api.execute(api.plan_retry('test',workspace=self.workspace,stage='candidate',case_ids=['D01'],failed=False))
        first=api.summarize('test',workspace=self.workspace,selection='first').to_dict()
        recovered=api.summarize('test',workspace=self.workspace).to_dict()
        self.assertNotEqual(first['source']['selection_sha256'],recovered['source']['selection_sha256'])
        self.assertEqual(first['profiles'],recovered['profiles'])
        cfg=self.cfg.to_dict();cfg['judge']['id']='other-judge'
        api.execute(api.grade_saved('test',workspace=self.workspace,replacement=config.from_dict(cfg,base=self.base),case_ids=['D01']))
        all_profiles=api.summarize('test',workspace=self.workspace).to_dict()['profiles']
        self.assertEqual(len(all_profiles),2)
        self.assertEqual(sorted(p['overall']['usefulness_scored'] for p in all_profiles),[1,3])
        chosen=api.summarize('test',workspace=self.workspace,profiles=[initial['profiles'][0]['profile']]).to_dict()
        self.assertEqual(len(chosen['profiles']),1);self.assertEqual(chosen['pack']['selected_questions'],3)

    def test_json_csv_cli_parity_without_render_dependencies(self):
        prepared=self.prepare();api.render_report(prepared,output=self.output('api'),formats='json,csv')
        result=subprocess.run([sys.executable,'-m','humanwill','report','test','--workspace',self.workspace,'--output',str(self.output('cli')),'--format','json,csv','--json'],cwd=REPO,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        for name in ('results.json','results.csv'):
            self.assertEqual((self.output('api')/name).read_bytes(),(self.output('cli')/name).read_bytes())
        rows=list(csv.DictReader(io.StringIO((self.output('api')/'results.csv').read_text())))
        self.assertEqual(len(rows),4);self.assertEqual(rows[0]['fr_classified'],'3')

    def test_saved_snapshot_replay_without_source_run(self):
        prepared=self.prepare();api.render_report(prepared,output=self.output('source'),formats='json')
        import shutil
        shutil.rmtree(self.base/'demo')
        loaded=api.load_report(self.output('source')/'results.json')
        self.assertEqual(loaded,prepared)
        api.render_report(loaded,output=self.output('replay'),formats='csv')
        self.assertEqual((self.output('source')/'results.csv').read_bytes(),(self.output('replay')/'results.csv').read_bytes())

    def test_invalid_snapshots_scores_duplicates_denominators_and_html_digest(self):
        original=self.prepare().to_dict()
        mutations=[lambda d:d['profiles'][0]['overall'].update(fr_classified=4),
                   lambda d:d['profiles'][0]['overall'].update(false_refusal_rate=.5),
                   lambda d:d['profiles'][0]['overall'].update(mean_usefulness=True),
                   lambda d:d['profiles'].append(deepcopy(d['profiles'][0])),
                   lambda d:d['source'].update(selection_sha256='<script>alert(1)</script>'),
                   lambda d:d['profiles'][0]['candidate'].update(credential='SECRET'),
                   lambda d:d['profiles'][0]['coverage']['candidate_states'].update(accepted=4)]
        for mutate in mutations:
            data=deepcopy(original);mutate(data);data['report_sha256']=fingerprint({k:v for k,v in data.items() if k!='report_sha256'})
            with self.assertRaises(HumanWillError):reporting.load_report(reporting.Report(encode(data)))
        data=deepcopy(original);data['profiles'][0]['overall']['false_refusals']=2
        with self.assertRaises(HumanWillError):reporting.load_report(reporting.Report(encode(data)))

    def test_no_overwrite_symlink_or_export_inside_run(self):
        prepared=self.prepare();out=self.output('existing')
        api.render_report(prepared,output=out,formats='json')
        before={p:p.read_bytes() for p in out.iterdir()}
        with self.assertRaises(HumanWillError):api.render_report(prepared,output=out,formats='json')
        self.assertEqual(before,{p:p.read_bytes() for p in out.iterdir()})
        link=self.base/'link';link.symlink_to(self.base/'exports')
        with self.assertRaises(HumanWillError):api.render_report(prepared,output=link/'bad',formats='json')
        with self.assertRaises(HumanWillError):api.render_report(prepared,output=Path(self.workspace)/'test'/'export',formats='json')

    def test_unknown_formats_styles_and_missing_dependency_make_no_output(self):
        prepared=self.prepare()
        for kwargs in ({'formats':'html,exe'},{'style':'shiny-unknown'},{'formats':[]}):
            with self.assertRaises(HumanWillError):api.render_report(prepared,output=self.output('bad'),**kwargs)
        with patch('humanwill.presentation.dependencies',side_effect=HumanWillError('missing_dependency','missing')):
            with self.assertRaises(HumanWillError):api.render_images(prepared,output=self.output('missing'))
        self.assertFalse(self.output('bad').exists());self.assertFalse(self.output('missing').exists())

    def test_v1_runs_still_render(self):
        cfg=config.load(api.init(self.base/'legacy',version=1)['config'])
        api.execute(api.plan(cfg,run_id='old'))
        prepared=api.summarize('old',workspace=cfg.workspace)
        self.assertEqual(prepared.to_dict()['source']['selection_policy'],'first_attempt/1')
        api.render_report(prepared,output=self.output('legacy'),formats='json,csv')

    def test_question_roundtrip_unicode_crlf_html_and_structured_evidence(self):
        pack=Path(self.cfg.pack).parent;data=sources.load(self.cfg.pack)
        data['cases'][0]['id']='family-echo'
        text='\n\r\n<script>window.PWNED=true</script> café 🧪 & "exact"\r\n'
        data['cases'][0]['messages'][1]['content']=text
        data['cases'][0]['provenance']['source_id']='family-echo'
        data['cases'][0]['provenance']['messages_sha256']=fingerprint(data['cases'][0]['messages'])
        data['cases'][1]['messages'][1]['content']=json.dumps({'question':'Harmless <b>fixture</b>','evidence':[{'path':'sample.txt','content':'<script>no</script>'}],'native_artifacts':[]})
        data['cases'][1]['provenance']['messages_sha256']=fingerprint(data['cases'][1]['messages'])
        raw=b''.join(encode(r).replace(b'\n',b' ')+b'\n' for r in data['cases'])
        (pack/'cases.jsonl').write_bytes(raw);data['manifest']['cases_sha256']=digest(raw);(pack/'manifest.json').write_bytes(encode(data['manifest']))
        out=self.base/'.local'/'reader'
        api.export_questions(pack=self.cfg.pack,output=out,style='both')
        exported=decode((out/'questions.json').read_bytes())
        self.assertEqual(exported['cases'],data['cases'])
        for style in ('clean','spotlight'):
            html=(out/f'questions-{style}.html').read_text();parser=ReaderParser();parser.feed(html)
            self.assertEqual(len(parser.ids),len(set(parser.ids)))
            for row in data['cases']:
                self.assertEqual(parser.messages[row['id']],{m['role']:m['content'] for m in row['messages']})
            self.assertEqual(len(parser.scripts),1);self.assertNotIn('<script>window.PWNED',html)
            self.assertIn('connect-src &#x27;none&#x27;',html)

    def test_question_subset_run_snapshot_and_no_outcome_annotations(self):
        cfg=self.cfg.to_dict();cfg['case_ids']=['D01','D03']
        self.prepare(config.from_dict(cfg,base=self.base))
        import shutil
        shutil.rmtree(Path(self.cfg.pack).parent)
        out=self.base/'.local'/'subset'
        result=api.export_questions(run_id='test',workspace=self.workspace,output=out,families=['unicode'])
        self.assertEqual(result['questions'],1)
        raw=(out/'questions.json').read_text();self.assertIn('D03',raw)
        for name in ('false_refusal','judge','observed_block','candidate_attempt_id'):
            self.assertNotIn(name,raw)
        self.assertEqual(decode(raw)['cases'][0]['id'],'D03')

    def test_question_paths_empty_selection_and_conflicts(self):
        with self.assertRaises(HumanWillError):
            api.export_questions(pack=self.cfg.pack, output=self.base/'.local'/'..'/'public-questions')
        for kwargs in ({'pack':self.cfg.pack},{'pack':self.cfg.pack,'run_id':'other','workspace':self.workspace}):
            with self.assertRaises(HumanWillError):api.export_questions(output=self.output('public'),**kwargs)
        for kwargs in ({'case_ids':['unknown']},{'families':['wrong']},{'case_ids':['D01','D01']},{'case_ids':['D01'],'families':['unicode']}):
            with self.assertRaises(HumanWillError):api.export_questions(pack=self.cfg.pack,output=self.base/'.local'/'invalid',**kwargs)
        self.assertFalse((self.base/'.local'/'invalid').exists())

    def test_questions_cli_matches_api(self):
        out=self.base/'.local'
        api.export_questions(pack=self.cfg.pack,output=out/'api')
        result=subprocess.run([sys.executable,'-m','humanwill','questions','--pack',self.cfg.pack,'--output',str(out/'cli'),'--json'],cwd=REPO,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout)
        for name in ('questions.json','questions-clean.html'):
            self.assertEqual((out/'api'/name).read_bytes(),(out/'cli'/name).read_bytes())

    def test_same_snapshot_both_styles_have_identical_chart_values(self):
        prepared=self.prepare()
        # Numeric audit is independently checked by visual tests below; this ensures
        # JSON/CSV don't depend on a rendering dependency or presentation style.
        for style in ('clean','spotlight'):
            api.render_report(prepared,output=self.output(style),formats='json,csv',style=style)
        self.assertEqual((self.output('clean')/'results.json').read_bytes(),(self.output('spotlight')/'results.json').read_bytes())


@unittest.skipUnless(VISUAL,'Install reports extra for visual-format tests.')
class VisualTests(unittest.TestCase):
    setUp = ReportingTests.setUp
    prepare = ReportingTests.prepare
    output = ReportingTests.output
    def test_real_png_svg_pdf_html_and_hash_inventory(self):
        from PIL import Image
        prepared=self.prepare()
        images=api.render_images(prepared,output=self.output('images'),formats='png,svg',style='both')
        audit=decode((self.output('images')/'chart-data.json').read_bytes())['charts']
        clean=[{k:v for k,v in a.items() if k!='style'} for a in audit if a['style']=='clean']
        dark=[{k:v for k,v in a.items() if k!='style'} for a in audit if a['style']=='spotlight']
        self.assertEqual(clean,dark)
        manifest=decode((self.output('images')/'manifest.json').read_bytes())
        for name,entry in manifest['files'].items():self.assertEqual(digest((self.output('images')/name).read_bytes()),entry['sha256'])
        for name in images['files']:
            if name.endswith('.png'):
                with Image.open(name) as image:self.assertGreaterEqual(image.width,1500);self.assertGreaterEqual(image.height,900)
        result=api.render_report(prepared,output=self.output('report'),style='both',title='Escaped <script> title')
        html=(self.output('report')/'report-clean.html').read_text()
        self.assertIn('Escaped &lt;script&gt; title',html);self.assertNotIn('<script> title',html)
        self.assertNotIn('src="https:',html)
        if importlib.util.find_spec('pypdf'):
            from pypdf import PdfReader
            for style in ('clean','spotlight'):
                pdf=PdfReader(self.output('report')/f'report-{style}.pdf')
                self.assertGreaterEqual(len(pdf.pages),6)
                text=' '.join(p.extract_text() for p in pdf.pages)
                self.assertIn('SIMULATION',text);self.assertIn(prepared.to_dict()['report_sha256'],text)

    def test_many_profiles_long_labels_nulls_and_many_families_paginate(self):
        from humanwill import presentation
        data=self.prepare().to_dict();base=data['profiles'][0]
        data['profiles']=[]
        for i in range(9):
            m=deepcopy(base);m['profile']=fingerprint(i);m['model_id']='m'+str(i);m['label']='Long model configuration label '+str(i)+' '+'x'*45
            m['overall'].update(total=7,fr_classified=0,fr_unclassified=7,usefulness_scored=0,usefulness_unscored=7,false_refusals=0,false_refusal_rate=None,mean_usefulness=None)
            m['families']={f'family_{j}':{**m['overall'],'total':1,'fr_unclassified':1,'usefulness_unscored':1} for j in range(7)}
            m['coverage']={'candidate_states':{'error':7},'judge_states':{'unattempted':7},'service_signals':{'unknown':7}}
            data['profiles'].append(m)
        data['pack']['selected_questions']=7;data['context']['available_questions']=7
        data['report_sha256']=fingerprint({k:v for k,v in data.items() if k!='report_sha256'})
        prepared=reporting.load_report(reporting.Report(encode(data)))
        charts=presentation.charts(prepared.to_dict(),'spotlight',formats=('svg',))
        self.assertEqual(len(charts),12)
        self.assertTrue(all(len(c['profiles'])<=8 and len(c['families'])<=6 for c in charts))
        self.assertTrue(all(v['value'] is None for c in charts for v in c['values']))
        self.assertTrue(all(b'Not scored' in c['svg'] or b'N/A' in c['svg'] for c in charts))


if __name__=='__main__':unittest.main()
