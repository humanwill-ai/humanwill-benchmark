"""Result labels use pinned facts, never pack names or user-supplied badges."""
from copy import deepcopy
import csv
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

from humanwill import api, config, reporting, result_context as labels
from humanwill.contracts import HumanWillError, encode, decode, fingerprint

PIN=next(iter(labels.REFERENCE_PACKS))
VISUAL=all(importlib.util.find_spec(x) for x in ('matplotlib','reportlab','PIL','pypdf'))


def seal(data):
    data['report_sha256']=fingerprint({k:v for k,v in data.items() if k!='report_sha256'})
    return reporting.Report(encode(data))


def mixed_fixture(data):
    """Synthetic aggregate fixture; never a real model result."""
    data=deepcopy(data)
    data['source']['run_id']='synthetic-label-fixture'
    data['pack'].update(id=labels.REFERENCE_ID,domain='cybersecurity',selected_questions=424)
    data['context']=labels.pack_context(PIN,424,424,'cybersecurity')
    data['contains_simulation']=False
    base=data['profiles'][0]
    base.update(label='Synthetic reference fixture',simulated=False,policy_sha256=labels.REFERENCE_POLICY)
    base['candidate']['provider']=base['judge']['provider']='openai'
    base['overall'].update(total=424,fr_classified=424,fr_unclassified=0,usefulness_scored=424,
                          usefulness_unscored=0,false_refusals=0,false_refusal_rate=0,mean_usefulness=4)
    base['families']={'C':deepcopy(base['overall'])}
    base['coverage']={k:{'fixture':424} for k in base['coverage']}
    other=deepcopy(base);other.update(profile=fingerprint('custom-profile'),label='Synthetic custom-policy fixture',policy_sha256='a'*64)
    data['profiles']=[base,other]
    for m in data['profiles']:
        m['assessment']=labels.assessment(data['context'],simulated=False,policy_sha=m['policy_sha256'])
    return seal(data)


class LabelTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.cfg=config.load(api.init(self.root/'demo')['config'])
        api.execute(api.plan(self.cfg,run_id='test'))
        self.report=api.summarize('test',workspace=self.cfg.workspace)

    def test_reference_requires_pinned_pack_full_population_and_policy(self):
        for pin in labels.REFERENCE_PACKS:
            context=labels.pack_context(pin,424,424,'cybersecurity')
            self.assertEqual(labels.assessment(context,simulated=False,policy_sha=labels.REFERENCE_POLICY)['kind'],'reference')
            self.assertEqual(labels.assessment(context,simulated=False,policy_sha='0'*64)['kind'],'customized')
            subset=labels.pack_context(pin,424,423,'cybersecurity')
            self.assertEqual(labels.assessment(subset,simulated=False,policy_sha=labels.REFERENCE_POLICY)['kind'],'customized')
        for domain,n in [('fraud',424),('cybersecurity',425)]:
            with self.assertRaises(HumanWillError):labels.pack_context(PIN,n,n,domain)

    def test_extension_or_renamed_reference_is_customized(self):
        # Pack display names are not even inputs to classification.
        for count in (424,425):
            c=labels.pack_context('b'*64,count,count,'cybersecurity')
            a=labels.assessment(c,simulated=False,policy_sha=labels.REFERENCE_POLICY)
            self.assertEqual((c['question_set'],a['kind'],a['policy']),('customized','customized','reference'))

    def test_simulation_takes_precedence_and_subset_remains_visible(self):
        c=labels.pack_context(PIN,424,1,'cybersecurity')
        a=labels.assessment(c,simulated=True,policy_sha=labels.REFERENCE_POLICY)
        self.assertEqual(a['kind'],'simulation');self.assertEqual(c['population'],'subset')
        self.assertEqual(self.report.to_dict()['profiles'][0]['assessment']['kind'],'simulation')

    def test_custom_policy_hash_is_explicit_without_exposing_policy_text(self):
        data=mixed_fixture(self.report.to_dict()).to_dict()
        self.assertEqual(labels.banner(data),'Mixed configurations')
        self.assertEqual(data['profiles'][1]['assessment']['policy'],'customized')
        self.assertNotEqual(data['profiles'][0]['policy_sha256'],data['profiles'][1]['policy_sha256'])
        self.assertEqual(data['profiles'][0]['overall'],data['profiles'][1]['overall'])

    def test_rehashed_false_labels_and_invalid_context_reject(self):
        data=mixed_fixture(self.report.to_dict()).to_dict()
        mutations=[lambda d:d['profiles'][1]['assessment'].update(kind='reference'),
                   lambda d:d['profiles'][0]['assessment'].update(label='Official score'),
                   lambda d:d['context'].update(pack_snapshot_sha256='b'*64),
                   lambda d:d['context'].update(population='subset'),
                   lambda d:d['context'].update(available_questions=423),
                   lambda d:d['profiles'][0].update(policy_sha256='bad')]
        for mutate in mutations:
            value=deepcopy(data);mutate(value)
            with self.assertRaises(HumanWillError):reporting.load_report(seal(value))

    def test_all_machine_exports_carry_per_profile_labels_and_hashes(self):
        prepared=mixed_fixture(self.report.to_dict())
        result=api.render_report(prepared,output=self.root/'json',formats='json,csv')
        data=decode((self.root/'json/results.json').read_bytes())
        context=decode((self.root/'json/result-context.json').read_bytes())
        self.assertEqual(data['format'],'humanwill.report-data/2')
        self.assertEqual(result['result_context'],context)
        rows=list(csv.DictReader(io.StringIO((self.root/'json/results.csv').read_text())))
        self.assertEqual({r['result_kind'] for r in rows},{'reference','customized'})
        self.assertTrue(all(r['pack_snapshot_sha256']==PIN and r['population']=='full' for r in rows))
        self.assertTrue(all(r['policy_sha256'] for r in rows))
        self.assertEqual(data,prepared.to_dict())

    def test_legacy_snapshot_replay_is_unverified_and_preserves_bytes(self):
        data=mixed_fixture(self.report.to_dict()).to_dict()
        data['format']='humanwill.report-data/1';del data['context']
        for m in data['profiles']:del m['assessment']
        old=seal(data);reporting.load_report(old)
        self.assertEqual(labels.banner(old.to_dict()),'Unverified configuration')
        api.render_report(old,output=self.root/'legacy',formats='json,csv')
        self.assertEqual((self.root/'legacy/results.json').read_bytes(),old.serialized)
        sidecar=decode((self.root/'legacy/result-context.json').read_bytes())
        self.assertEqual(sidecar['label'],'Unverified configuration')
        self.assertTrue(all(r['kind']=='unverified' for r in sidecar['profiles']))

    @unittest.skipUnless(VISUAL,'Install reports extras and pypdf for rendering tests.')
    def test_labels_visible_in_both_styles_every_pdf_page_and_chart(self):
        from PIL import Image
        from pypdf import PdfReader
        prepared=mixed_fixture(self.report.to_dict())
        api.render_report(prepared,output=self.root/'report',style='both')
        api.render_images(prepared,output=self.root/'images',style='both',formats='png,svg')
        for style in ('clean','spotlight'):
            html=(self.root/'report'/f'report-{style}.html').read_text()
            for label in ('Mixed configurations','Reference configuration','Customized configuration','Custom policy'):
                self.assertIn(label,html)
            reader=PdfReader(self.root/'report'/f'report-{style}.pdf')
            self.assertTrue(all('MIXED CONFIGURATIONS' in p.extract_text() for p in reader.pages))
            text=' '.join(p.extract_text() for p in reader.pages)
            self.assertIn('Customized configuration',text);self.assertIn('Reference configuration',text)
            for svg in (self.root/'images').glob(f'*-{style}.svg'):
                text=svg.read_text();self.assertIn('MIXED CONFIGURATIONS',text)
                self.assertIn('Customized / Custom policy',text);self.assertIn('Reference / Reference policy',text)
            for png in (self.root/'images').glob(f'*-{style}.png'):
                with Image.open(png) as image:self.assertIn('Mixed configurations',image.info['Description'])
        charts=decode((self.root/'images/chart-data.json').read_bytes())['charts']
        clean=[{k:v for k,v in c.items() if k!='style'} for c in charts if c['style']=='clean']
        dark=[{k:v for k,v in c.items() if k!='style'} for c in charts if c['style']=='spotlight']
        self.assertEqual(clean,dark)
        self.assertTrue(all({v['result_kind'] for v in c['values']}=={'reference','customized'} for c in charts))


if __name__=='__main__':unittest.main()
