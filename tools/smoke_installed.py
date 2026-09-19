"""Run with python -I after wheel installation, from any working directory.

Only harmless mock data; exercises installed API, module CLI and console script.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import tomllib
from importlib.resources import files
from importlib.metadata import distribution


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports',action='store_true')
    args=parser.parse_args()
    import humanwill
    from humanwill import api
    from humanwill import settings
    from humanwill.contracts import HumanWillError
    installed=Path(humanwill.__file__).resolve()
    if not installed.is_relative_to(Path(sys.prefix).resolve()) or not sys.flags.isolated:
        raise RuntimeError('Use python -I with the installed wheel, not the source checkout')
    if not args.reports and any(importlib.util.find_spec(n) for n in ('httpx','matplotlib','reportlab')):
        raise RuntimeError('Base smoke requires a clean environment without optional dependencies')
    dist=distribution('humanwill-evals')
    assert dist.metadata['License-Expression']=='Apache-2.0 AND CC-BY-4.0'
    notices={'LICENSE','NOTICE','LICENSING.md','BRAND.md','LICENSES/CC-BY-4.0.txt'}
    assert set(dist.metadata.get_all('License-File'))==notices
    for name in notices:
        members=[p for p in dist.files if str(p).endswith('.dist-info/licenses/'+name)]
        assert len(members)==1 and dist.locate_file(members[0]).read_bytes()
    # The API portion may not open sockets. CLI commands select only mock tasks.
    def no_network(*args,**kwargs): raise AssertionError('Unexpected network use')
    socket.socket.connect=no_network
    socket.create_connection=no_network
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory).resolve()
        # Starter templates must ship in a wheel and require deliberate configuration.
        for name in ('openai','anthropic','openrouter','compare'):
            starter=tomllib.loads(files('humanwill').joinpath('data','examples',name+'.toml').read_text())
            try: settings.from_dict(starter,base=root)
            except HumanWillError: pass
            else: raise AssertionError('Unfilled live starter unexpectedly validated')
        def cli(*argv, expected=0):
            run=subprocess.run([sys.executable,'-I','-m','humanwill',*map(str,argv),'--json'],
                               cwd=root,capture_output=True,text=True,timeout=120)
            if run.returncode != expected:
                raise AssertionError('Unexpected CLI exit for '+str(argv[0])+': '+run.stdout+run.stderr)
            result=json.loads(run.stdout)
            assert result['ok'] is (expected in (0,3))
            return result.get('data') if result['ok'] else result['error']
        initialized=cli('init',root/'demo')
        assert initialized['license']=='CC-BY-4.0'
        assert (Path(initialized['pack']).parent/'LICENSE').is_file()
        cfg=initialized['config']
        authored=cli('pack','init',root/'.local'/'authored')
        verified=cli('pack','validate',authored['source'])
        assert verified==api.validate_pack(authored['source']) and verified['questions']==1
        built=cli('pack','build',authored['source'],'--output',root/'.local'/'compiled')
        extended=cli('pack','init',root/'.local'/'extension','--extends',built['manifest'])
        composed=cli('pack','build',extended['source'],'--output',root/'.local'/'composed')
        assert composed['questions']==2 and composed['inherited_questions']==1
        bundle=cli('policy','init',root/'.local'/'policy')['policy_bundle']
        preview=cli('policy','preview',bundle,'--pack',composed['manifest'])
        assert preview==api.preview_policy(bundle,pack=composed['manifest'])
        assert preview['selected_questions']==2 and preview['resolutions'][0]['trace']
        shutil.rmtree(Path(built['manifest']).parent)
        assert api.validate_pack(composed['manifest'])['questions']==2
        assert cli('check','--config',cfg)['valid']
        cli('run','--config',cfg,'--run-id','smoke','--save-plan',root/'plan.json')
        done=cli('run','--plan',root/'plan.json','--execute')
        workspace=done['workspace']
        assert done['status']=='complete' and done['accounted_micro_usd']==0
        assert api.status('smoke',workspace=workspace)==cli('status','smoke','--workspace',workspace)
        policy=cli('policy','inspect','smoke','--workspace',workspace)
        assert policy==api.inspect_policy('smoke',workspace=workspace)
        report=api.summarize('smoke',workspace=workspace)
        api.render_report(report,output=root/'api',formats='json,csv')
        cli('report','smoke','--workspace',workspace,'--output',root/'cli','--format','json,csv')
        for name in ('results.json','results.csv','result-context.json'):
            assert (root/'api'/name).read_bytes()==(root/'cli'/name).read_bytes()
        context=json.loads((root/'api'/'result-context.json').read_text())
        assert context['label']=='Simulation' and context['profiles'][0]['kind']=='simulation'
        assert report.to_dict()['format']=='humanwill.report-data/2'
        attempts=cli('attempts','smoke','--workspace',workspace,'--case','D01')
        evidence=cli('inspect','smoke','--workspace',workspace,'--attempt',attempts['attempts'][0]['id'])
        assert evidence
        retry=api.plan_retry('smoke',workspace=workspace,case_ids=['D01'],stage='candidate',failed=False)
        api.save_plan(retry,root/'retry.json')
        repaired=cli('run','--plan',root/'retry.json','--execute')
        assert repaired['attempt_count']==8 and repaired['status']=='complete'
        q=cli('questions','smoke','--workspace',workspace,'--output',root/'.local'/'questions','--style','both')
        assert q['questions']==3
        for style in ('clean','spotlight'):
            text=(root/'.local'/'questions'/('questions-'+style+'.html')).read_text()
            assert 'data:image/png;base64' in text and 'script-src' in text
        console=Path(sys.executable).parent/('humanwill.exe' if sys.platform=='win32' else 'humanwill')
        assert subprocess.check_output([str(console),'--version'],cwd=root,text=True).strip()==humanwill.__version__
        # Presentation must also work after the entire source run has disappeared.
        shutil.rmtree(Path(workspace))
        if args.reports:
            cli('report','--results',root/'api'/'results.json','--output',root/'rendered','--style','both')
            api.render_images(api.load_report(root/'api'/'results.json'),output=root/'images',style='both',formats='png,svg')
            charts=json.loads((root/'images'/'chart-data.json').read_text())['charts']
            values=lambda theme:[{k:v for k,v in c.items() if k!='style'} for c in charts if c['style']==theme]
            assert values('clean')==values('spotlight')
            for style in ('clean','spotlight'):
                assert (root/'rendered'/('report-'+style+'.pdf')).read_bytes().startswith(b'%PDF-')
                assert 'Simulation' in (root/'rendered'/('report-'+style+'.html')).read_text()
            assert all(c['result_label']=='Simulation' for c in charts)
        else:
            error=cli('images','--results',root/'api'/'results.json','--output',root/'unavailable',expected=2)
            assert error['code']=='missing_dependency' and not (root/'unavailable').exists()
    print(json.dumps({'version':humanwill.__version__,'python':sys.version.split()[0],
                      'platform':sys.platform,'installed':str(installed),'reports':args.reports,'passed':True}))


if __name__=='__main__': main()
