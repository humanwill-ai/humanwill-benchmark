"""Versioned, conservative report labels derived from saved configuration facts.

Pins identify reference materials, not judge calibration or publication approval.
No questions, policy prose, customer paths or credentials belong in this module.
"""
import re
from .contracts import fields, require

REFERENCE_ID = 'humanwill-cybersecurity-initial424/0.1.0'
# Original frozen pack, reviewed rc2, and metadata-only accepted delivery.
REFERENCE_PACKS = {
    '2388a3698bb311ee1f4fb4015a057a5fc5ed40efeaa7a76efa54918247638413': (REFERENCE_ID, 424),
    '6325cd38d144ac952046f8d1e79d686499f01568b8f7b9b36b07202336c5840e': (REFERENCE_ID, 424),
    '6e3c4ee98ed358d31e51e8c670a7d713658ae8a43149eab335b4f9da739e0488': (REFERENCE_ID, 424),
}
# Exact bundled POLICY.md: a reference starting policy, not historical corrections.
REFERENCE_POLICY = 'ea5f2cb073c2f884335484455157101b7d9f379d883c716af40cb6c714227a0d'
LABELS = {'reference':'Reference configuration', 'customized':'Customized configuration',
          'simulation':'Simulation', 'unverified':'Unverified configuration'}
QUESTIONS = {'reference':'Reference questions', 'customized':'Customized / unrecognized question pack',
             'demonstration':'Demonstration questions', 'unverified':'Unverified question provenance'}
POLICIES = {'reference':'Reference policy', 'customized':'Custom policy',
            'simulation':'Simulation policy', 'unverified':'Unverified policy'}
NOTE = ('Reference configuration identifies the pinned question pack, full selected population and exact bundled policy. '
        'It does not certify judge calibration, reproduce historical results, or establish comparability across model/judge settings.')


def digest(value):
    require(isinstance(value,str) and re.fullmatch(r'[0-9a-f]{64}',value), message='Invalid result-context digest.')


def pack_context(pack_sha, available, selected, domain):
    digest(pack_sha)
    require(type(available) is int and type(selected) is int and 0 < selected <= available,
            message='Invalid result-context population.')
    ref = REFERENCE_PACKS.get(pack_sha)
    if ref:
        require(available==ref[1] and domain=='cybersecurity', message='Reference pack facts disagree with its pin.')
    return {'format':'humanwill.result-context/1','pack_snapshot_sha256':pack_sha,
            'available_questions':available,'reference_id':ref[0] if ref else None,
            'question_set':'reference' if ref else ('demonstration' if domain=='demonstration' else 'customized'),
            'population':'full' if selected==available else 'subset'}


def assessment(context, *, simulated, policy_sha):
    if simulated:
        policy='simulation'; kind='simulation'
        reasons=['Fixture scores; no model-performance claim.']
    elif context['question_set']=='unverified':
        policy='unverified'; kind='unverified'
        reasons=['Legacy report lacks the saved pack facts needed to verify reference status.']
    else:
        digest(policy_sha)
        policy='reference' if policy_sha==REFERENCE_POLICY else 'customized'
        reasons=[]
        if context['question_set']!='reference': reasons.append('Question pack does not match a pinned HumanWill reference snapshot.')
        if context['population']!='full': reasons.append('Selected questions are a subset of the saved pack.')
        if policy!='reference': reasons.append('Judging policy differs from the exact bundled reference policy.')
        kind='customized' if reasons else 'reference'
        if kind=='reference': reasons=['Pinned reference questions, full population and exact bundled reference policy.']
    return {'kind':kind,'label':LABELS[kind],'policy':policy,'reasons':reasons}


def context_for(data):
    return data.get('context', {'format':'humanwill.result-context/1',
        'pack_snapshot_sha256':None,'available_questions':None,'reference_id':None,
        'question_set':'unverified','population':'unknown'})


def assessment_for(data, model):
    return model.get('assessment') or assessment(context_for(data),simulated=model['simulated'],policy_sha=model['policy_sha256'])


def banner(data, models=None):
    kinds={assessment_for(data,m)['kind'] for m in (data['profiles'] if models is None else models)}
    return LABELS[next(iter(kinds))] if len(kinds)==1 else 'Mixed configurations'


def summary(data):
    c=context_for(data)
    population={'full':'Full saved-pack population','subset':'Selected subset','unknown':'Population provenance unverified'}[c['population']]
    return QUESTIONS[c['question_set']]+' | '+population


def profile_label(data, model):
    return assessment_for(data,model)['label']


def export_context(data):
    return {'format':'humanwill.report-context/1','report_sha256':data['report_sha256'],
            'label':banner(data),'questions':context_for(data),'note':NOTE,
            'profiles':[{'profile':m['profile'],'policy_sha256':m['policy_sha256'],
                         **assessment_for(data,m)} for m in data['profiles']]}


def validate(data):
    c=data['context']
    fields(c, {'format','pack_snapshot_sha256','available_questions','reference_id','question_set','population'})
    expected=pack_context(c['pack_snapshot_sha256'],c['available_questions'],
                          data['pack']['selected_questions'],data['pack']['domain'])
    require(c==expected, 'integrity_error','Report question classification changed.')
    for m in data['profiles']:
        expected=assessment(c,simulated=m['simulated'],policy_sha=m['policy_sha256'])
        require(m['assessment']==expected, 'integrity_error','Report profile classification changed.')
