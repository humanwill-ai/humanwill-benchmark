"""Synthetic pack/history compatibility and invalid-provenance regression tests."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from humanwill import api, sources
from humanwill.contracts import HumanWillError, digest, encode, fingerprint


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();(self.root/'cases').mkdir()
        messages=[{'role':'system','content':'Harmless fixture only.\n'},{'role':'user','content':'Return the word blue.'}]
        self.row={'format':'humanwill.frozen-message-case/0.1.0','id':'V01','family':'V','messages':messages,
            'intended_behavior':'assist_within_supplied_scope','review_status':'existing_in_scope_benchmark',
            'provenance':{'source_set':'original100','source_id':'V01','source_bundle_sha256':'a'*64,
                'source_messages_sha256':fingerprint(messages),'original_request_sha256':None,
                'original_runtime_settings':{'fixture':'original-setting'},'authorship':'HumanWill; AI-assisted','license':'unselected'}}
        self.manifest={'format':'humanwill.frozen-message-pack/0.1.0','pack_id':'fixture','version':'0.1.0','domain':'cybersecurity',
            'status':'frozen_private_pilot','license':'unselected','total':1,'family_counts':{'V':1},'source_counts':{'original100':1},
            'source_family_counts':{'original100':{'V':1},'discovery324':{}},'cases':[]}
        self.write()

    def write(self):
        raw=encode(self.row);(self.root/'cases/V01.json').write_bytes(raw)
        self.manifest['cases']=[{'id':'V01','family':'V','source_set':'original100','path':'cases/V01.json','sha256':digest(raw),'messages_sha256':fingerprint(self.row['messages'])}]
        self.write_manifest()

    def write_manifest(self):
        raw=encode(self.manifest);(self.root/'manifest.json').write_bytes(raw);(self.root/'manifest.sha256').write_text(digest(raw)+'\n')

    def load(self): return sources.load(self.root/'manifest.json')

    def test_exact_provenance_and_original_schema_preserved(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        pack=self.load();self.assertEqual(pack['cases'][0],self.row);self.assertEqual(pack['manifest'],self.manifest)
        sources.validate(pack)
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_duplicate_path_id_and_population_fail(self):
        self.manifest['cases']*=2;self.write_manifest()
        with self.assertRaises(HumanWillError):self.load()
        self.write();self.manifest['total']=2;self.write_manifest()
        with self.assertRaises(HumanWillError):self.load()

    def test_source_and_license_claim_changes_fail(self):
        original=deepcopy(self.row)
        for key,value in [('source_id','V02'),('source_messages_sha256','b'*64),('license','CC-BY'),('authorship','Expert certified')]:
            self.row=deepcopy(original);self.row['provenance'][key]=value;self.write()
            with self.assertRaises(HumanWillError):self.load()

    def test_bad_paths_hashes_and_source_versions_fail(self):
        self.manifest['cases'][0]['path']='../outside.json';self.write_manifest()
        with self.assertRaises(HumanWillError):self.load()
        self.write();(self.root/'cases/V01.json').write_bytes(b'{}')
        with self.assertRaises(HumanWillError):self.load()
        self.write();self.row['format']='humanwill.frozen-message-case/9';self.write()
        with self.assertRaises(HumanWillError):self.load()

    def test_historical_capture_read_only_and_exact_body(self):
        body=b'private synthetic\n\x00response';(self.root/'response-001.body').write_bytes(body)
        metadata={'http_status':403,'http_version':'HTTP/1.1','response_headers':[['x-request-id','fixture'],['set-cookie','SECRET']],
            'body_file':'response-001.body','body_bytes':len(body),'body_sha256':digest(body),'representation':'HTTPX body bytes'}
        path=self.root/'response-001.json';path.write_bytes(encode(metadata))
        value=api.inspect_historical_capture(path)
        self.assertTrue(value['read_only']);self.assertNotIn('http_body_base64',value);self.assertNotIn('SECRET',encode(value).decode())
        self.assertEqual(value['body_sha256'],digest(body));self.assertIsNone(value['accounting'])
        self.assertEqual(path.read_bytes(),encode(metadata))
        import base64
        value=api.inspect_historical_capture(path,include_http=True)
        self.assertEqual(base64.b64decode(value['http_body_base64']),body)

    def test_historical_partial_and_tampering(self):
        body=b'partial';(self.root/'response-001.body').write_bytes(body)
        metadata={'http_status':200,'response_headers':[],'body_bytes':len(body),'body_sha256':digest(body),
                  'capture_error':'ReadTimeout','representation':'HTTPX SSE'}
        path=self.root/'response-001.json';path.write_bytes(encode(metadata))
        self.assertEqual(api.inspect_historical_capture(path)['capture_status'],'partial')
        (self.root/'response-001.body').write_bytes(b'changed')
        with self.assertRaises(HumanWillError):api.inspect_historical_capture(path)

    def test_history_unknown_schema_and_symlink_rejected(self):
        path=self.root/'response-001.json';path.write_bytes(encode({'format':'unknown'}))
        with self.assertRaises(HumanWillError):api.inspect_historical_capture(path)
        link=self.root/'link.json';link.symlink_to(path)
        with self.assertRaises(HumanWillError):api.inspect_historical_capture(link)


if __name__=='__main__':unittest.main()
