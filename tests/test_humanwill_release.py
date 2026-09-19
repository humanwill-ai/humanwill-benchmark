"""Release boundaries use synthetic files, never historical/private prompts."""
from pathlib import Path
import tempfile
import tarfile
import io
import json
import hashlib
import unittest
from unittest.mock import patch
import zipfile
from importlib.resources import files
import socket
import tomllib
from tools import release_check as release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        (self.root/'release').mkdir();(self.root/'humanwill').mkdir()
        (self.root/'humanwill/__init__.py').write_text('# harmless fixture\n')
        (self.root/'release/README.md').write_text('Standalone fixture\n')
        (self.root/'release/files.txt').write_text('humanwill/__init__.py\nrelease/README.md\nrelease/files.txt\n')

    def test_stage_selects_only_listed_sources_and_never_overwrites(self):
        (self.root/'private-secret.txt').write_text('Not selected')
        target=self.root/'.local'/'candidate'
        result=release.stage(target,self.root)
        self.assertFalse(result['publication_authorized'])
        self.assertFalse((target/'private-secret.txt').exists())
        self.assertEqual((target/'README.md').read_bytes(),(self.root/'release/README.md').read_bytes())
        with self.assertRaises(ValueError):release.stage(target,self.root)
        with self.assertRaises(ValueError):release.stage(self.root/'.local'/'..'/'public',self.root)

    def test_invalid_inventory_and_symlink_sources_fail(self):
        listing=self.root/'release/files.txt'
        original=listing.read_text()
        for text in ('../private\n','/absolute\n','humanwill/__init__.py\nhumanwill/__init__.py\n'):
            listing.write_text(text)
            with self.assertRaises(ValueError):release.inventory(self.root)
        listing.write_text(original)
        source=self.root/'humanwill/__init__.py';source.unlink();source.symlink_to(self.root/'release/README.md')
        with self.assertRaises(ValueError):release.selected(self.root)

    def test_potential_credential_detection_does_not_echo_secret(self):
        key=b'sk-'+b'A'*50
        with self.assertRaises(ValueError) as exc:release.content_check('fixture.py',key)
        self.assertNotIn(key.decode(),str(exc.exception))

    def wheel(self, extra=None, source=b'# harmless fixture\n'):
        path=self.root/'fixture.whl'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('humanwill/__init__.py',source)
            if extra:z.writestr(extra,b'harmless unwanted fixture')
        return path

    def test_distribution_inventory_and_source_equality(self):
        self.assertTrue(release.archive(self.wheel(),self.root)['source_matches'])
        for name in ('core/private.py','humanwill/extra.py','../../escape'):
            with self.assertRaises(ValueError):release.archive(self.wheel(name),self.root)
        with self.assertRaises(ValueError):release.archive(self.wheel(source=b'changed'),self.root)

    def test_full_test_gate_cannot_silently_skip_dependencies(self):
        with patch.object(release.importlib.util,'find_spec',return_value=None):
            with self.assertRaises(ValueError):release.suite(require_extras=True,root=self.root)

    def test_sdist_links_unknown_members_and_source_drift_fail(self):
        (self.root/'README.md').write_text('Standalone fixture\n')
        path=self.root/'source.tar.gz'
        files={n:(self.root/n).read_bytes() for n in release.inventory(self.root)}
        files.update({'README.md':b'Standalone fixture\n','PKG-INFO':b'Name: fixture\n'})
        def make(extra=None, link=False):
            with tarfile.open(path,'w:gz') as bundle:
                for name, raw in files.items():
                    member=tarfile.TarInfo('fixture/'+name);member.size=len(raw)
                    bundle.addfile(member,io.BytesIO(raw))
                if extra:
                    member=tarfile.TarInfo('fixture/'+extra)
                    if link:member.type=tarfile.SYMTYPE;member.linkname='../../outside'
                    bundle.addfile(member)
        make();self.assertTrue(release.archive(path,self.root)['source_matches'])
        for name, link in (('private/answer.json',False),('link',True)):
            make(name,link)
            with self.assertRaises(ValueError):release.archive(path,self.root)
        files['release/README.md']=b'Changed source';make()
        with self.assertRaises(ValueError):release.archive(path,self.root)

    def licensed_fixture(self):
        (self.root/'LICENSE').write_text('Synthetic license fixture\n')
        (self.root/'NOTICE').write_text('Synthetic attribution fixture\n')
        (self.root/'pyproject.toml').write_text('[project]\nlicense = "Apache-2.0 AND CC-BY-4.0"\nlicense-files = ["LICENSE", "NOTICE"]\n')
        listing=self.root/'release/files.txt'
        listing.write_text(listing.read_text()+'LICENSE\nNOTICE\npyproject.toml\n')
        return b'License-Expression: Apache-2.0 AND CC-BY-4.0\nLicense-File: LICENSE\nLicense-File: NOTICE\n\n'

    def test_license_decision_is_scoped_and_does_not_authorize_publication(self):
        self.licensed_fixture()
        target=self.root/'.local'/'licensed'
        release.stage(target,self.root)
        manifest=json.loads((target/'release-candidate.json').read_text())
        self.assertEqual(manifest['license_decision'],'selected')
        self.assertEqual(manifest['license_expression'],'Apache-2.0 AND CC-BY-4.0')
        self.assertFalse(manifest['publication_authorized'])
        project=self.root/'pyproject.toml';text=project.read_text()
        for wrong in ('../LICENSE','unselected.txt','LICENSE*'):
            project.write_text(text.replace('"NOTICE"','"'+wrong+'"'))
            with self.assertRaises(ValueError):release.license_config(self.root)

    def test_wheel_licenses_and_metadata_cannot_be_omitted_or_changed(self):
        meta=self.licensed_fixture()
        prefix='humanwill_evals-0.0.0.dist-info/'
        contents={'humanwill/__init__.py':(self.root/'humanwill/__init__.py').read_bytes(),
                  prefix+'METADATA':meta,
                  prefix+'licenses/LICENSE':(self.root/'LICENSE').read_bytes(),
                  prefix+'licenses/NOTICE':(self.root/'NOTICE').read_bytes()}
        path=self.root/'licensed.whl'
        def check(payloads):
            with zipfile.ZipFile(path,'w') as z:
                for name,raw in payloads.items():z.writestr(name,raw)
            return release.archive(path,self.root)
        self.assertTrue(check(contents)['source_matches'])
        for name in contents:
            changed=dict(contents);del changed[name]
            with self.assertRaises(ValueError):check(changed)
        for name in ('licenses/LICENSE','licenses/NOTICE','METADATA'):
            changed=dict(contents);changed[prefix+name]=b'Changed or missing license\n'
            with self.assertRaises(ValueError):check(changed)
        changed=dict(contents);changed[prefix+'licenses/unselected.txt']=b'Not selected'
        with self.assertRaises(ValueError):check(changed)
        for bad in (meta.replace(b'Apache-2.0 AND CC-BY-4.0',b'MIT'),
                    meta.replace(b'License-File: NOTICE\n',b'')):
            changed=dict(contents);changed[prefix+'METADATA']=bad
            with self.assertRaises(ValueError):check(changed)

    def test_sdist_license_metadata_and_notices_match_the_selection(self):
        meta=self.licensed_fixture()
        (self.root/'README.md').write_bytes((self.root/'release/README.md').read_bytes())
        contents={n:(self.root/n).read_bytes() for n in release.inventory(self.root)}
        contents.update({'README.md':(self.root/'README.md').read_bytes(),'PKG-INFO':meta})
        path=self.root/'licensed.tar.gz'
        def check(payloads):
            with tarfile.open(path,'w:gz') as z:
                for name,raw in payloads.items():
                    item=tarfile.TarInfo('fixture/'+name);item.size=len(raw)
                    z.addfile(item,io.BytesIO(raw))
            return release.archive(path,self.root)
        self.assertTrue(check(contents)['source_matches'])
        for name in ('LICENSE','NOTICE','PKG-INFO'):
            changed=dict(contents);del changed[name]
            with self.assertRaises(ValueError):check(changed)
            changed=dict(contents);changed[name]=b'Changed\n'
            with self.assertRaises(ValueError):check(changed)


class OnboardingTests(unittest.TestCase):
    """Validate shipped starter data against real configuration/planning contracts."""
    def test_licensed_demo_keeps_original_messages_and_copies_its_notices(self):
        from humanwill import api,packs
        with tempfile.TemporaryDirectory() as temporary:
            result=api.init(Path(temporary)/'demo')
            self.assertEqual(result['license'],'CC-BY-4.0')
            snapshot=packs.load(result['pack'])
            self.assertEqual(snapshot['manifest']['version'],'2')
            self.assertEqual(snapshot['manifest']['license'],'CC-BY-4.0')
            expected={'D01':'f820db21ee79a8c1e016bd88e14c6dd1ddd9e7964e5fe50714f324db562640f4',
                      'D02':'86b24b435d720c00f80a8d9fa66819c2101744bd4fd8c168e1d9dc61bde05a0d',
                      'D03':'3742757428b0c71d2b99a36894b84525869fbb300868d432cd465faebc101291'}
            for row in snapshot['cases']:
                self.assertEqual(row['provenance']['messages_sha256'],expected[row['id']])
                self.assertEqual(row['provenance']['source_id'],row['id'])
                self.assertEqual(row['provenance']['source'],'HumanWill local demonstration 1')
                self.assertEqual(row['provenance']['license'],'CC-BY-4.0')
            demo=Path(result['pack']).parent
            self.assertIn('https://humanwill.ai',(demo/'README.md').read_text())
            self.assertEqual(hashlib.sha256((demo/'LICENSE').read_bytes()).hexdigest(),
                             '9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411')

    def test_unfilled_provider_templates_cannot_plan_or_resolve_credentials(self):
        from humanwill import api, settings
        from humanwill.contracts import HumanWillError
        for name in ('openai','anthropic','openrouter','compare'):
            with self.subTest(template=name):
                raw=files('humanwill').joinpath('data','examples',name+'.toml').read_text()
                cfg=tomllib.loads(raw)
                with patch('humanwill.credentials.resolve',side_effect=AssertionError('secret read')):
                    with self.assertRaises(HumanWillError):api.plan(settings.from_dict(cfg,base=Path.cwd()))

    def test_filled_starters_plan_one_question_and_comparison_without_network(self):
        from humanwill import api, settings, engine, live
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()/'.local'
            source=api.init_pack(root/'my-pack')['source']
            api.build_pack(source,output=root/'my-pack-built')
            api.init_policy(root/'my-policy')
            for name in ('openai','anthropic','openrouter','compare'):
                with self.subTest(template=name):
                    cfg=tomllib.loads(files('humanwill').joinpath('data','examples',name+'.toml').read_text())
                    cfg['budget_micro_usd']=1_000_000
                    for spec in [*cfg['models'],cfg['judge']]:
                        spec['model']='synthetic-'+spec['id']
                        spec['credential']='env:HUMANWILL_ONBOARDING_TEST'
                        spec['prices'].update(input_micro_usd_per_million=1_000_000,
                            output_micro_usd_per_million=2_000_000,source='Synthetic fixture; not a quotation',verified_at='2026-09-17')
                        if spec['provider']=='openrouter':spec.update(route='SyntheticRoute',returned_providers=['SyntheticRoute'])
                    configured=settings.from_dict(cfg,base=root)
                    with (patch.object(socket.socket,'connect',side_effect=AssertionError('network')),
                          patch('humanwill.credentials.resolve',side_effect=AssertionError('secret read'))):
                        plan=api.plan(configured,run_id='first-live').to_dict()
                        parsed,pack,_,_=engine.inputs(configured)
                        for spec in [*parsed['models'],parsed['judge']]:live.request(spec,pack['cases'][0]['messages'])
                    self.assertEqual(plan['case_ids'],['CUSTOM01'])
                    self.assertEqual(len(plan['tasks']),2 if name=='compare' else 1)
                    self.assertEqual(plan['config']['workspace'],str(root/'runs'))
                    self.assertFalse((root/'runs').exists())


if __name__=='__main__':unittest.main()
