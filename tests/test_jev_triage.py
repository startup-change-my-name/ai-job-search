import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.jev_triage import build_request, evaluate, live_transport, main, parse_response, NoRedirect

SOURCE = {'posting_text': 'Public sample role: Python developer.',
          'candidate_summary': 'Professional skills: Python and SQL.'}
RESPONSE = {'model': 'jev-test-pinned', 'answers': {'priority': {
    'type': 'choice', 'choice': 'prioritize', 'confidence': .95,
    'probabilities': {'prioritize': .95, 'review': .04, 'low_priority': .01}}},
    'usage': {'input_tokens': 100, 'output_tokens': 10}}


class JevTests(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(evaluate(SOURCE, {'verdict': 'PASS'}, 'test')['status'], 'disabled')

    def test_fail_never_calls_model(self):
        def forbidden(body):
            self.fail('Provider called')
        r = evaluate(SOURCE, {'verdict': 'FAIL'}, 'test', forbidden)
        self.assertEqual(r['status'], 'gate_blocked')

    def test_flag_cannot_be_upgraded(self):
        gate = {'verdict': 'FLAG', 'clarifications': ['salary missing']}
        original = copy.deepcopy(gate)
        r = evaluate(SOURCE, gate, 'test', lambda _: RESPONSE)
        self.assertEqual(r['advisory_priority'], 'review')
        self.assertEqual(gate, original)

    def test_high_confidence_is_still_shadow(self):
        r = evaluate(SOURCE, {'verdict': 'PASS'}, 'test', lambda _: RESPONSE)
        self.assertEqual(r['advisory_priority'], 'prioritize')
        self.assertTrue(r['requires_review'])
        self.assertFalse(r['changes_application_state'])

    def test_low_confidence_review(self):
        x = copy.deepcopy(RESPONSE); x['answers']['priority']['confidence'] = .5
        self.assertEqual(evaluate(SOURCE, {'verdict': 'PASS'}, 'test', lambda _: x)
                         ['advisory_priority'], 'review')

    def test_high_confidence_with_uncertain_probabilities_stays_review(self):
        x = copy.deepcopy(RESPONSE)
        x['answers']['priority']['probabilities'] = {
            'prioritize': .4, 'review': .35, 'low_priority': .25}
        result = evaluate(SOURCE, {'verdict': 'PASS'}, 'test', lambda _: x)
        self.assertEqual(result['status'], 'evaluated')
        self.assertEqual(result['advisory_priority'], 'review')

    def test_low_priority_remains_advisory(self):
        x = copy.deepcopy(RESPONSE)
        x['answers']['priority'].update(choice='low_priority', probabilities={
            'prioritize': .01, 'review': .04, 'low_priority': .95})
        result = evaluate(SOURCE, {'verdict': 'PASS'}, 'test', lambda _: x)
        self.assertEqual(result['advisory_priority'], 'low_priority')
        self.assertEqual(result['gate_verdict'], 'PASS')
        self.assertTrue(result['requires_review'])
        self.assertFalse(result['changes_application_state'])

    def test_malformed_outputs_fail_closed(self):
        for bad in (None, {}, {'answers': {}}, {'model': []}):
            with self.subTest(bad=bad):
                self.assertEqual(evaluate(SOURCE, {'verdict': 'PASS'}, 'test', lambda _: bad)
                                 ['status'], 'provider_error')

    def test_probability_validation(self):
        for value in (float('nan'), float('inf'), -1, 2, True):
            x = copy.deepcopy(RESPONSE); x['answers']['priority']['confidence'] = value
            with self.assertRaises(ValueError): parse_response(x)

    def test_invalid_distribution_and_choice(self):
        for modification in ('sum', 'choice', 'keys'):
            x = copy.deepcopy(RESPONSE); a = x['answers']['priority']
            if modification == 'sum': a['probabilities']['review'] = .5
            if modification == 'choice': a['choice'] = 'low_priority'
            if modification == 'keys': a['probabilities']['unexpected'] = 0
            with self.assertRaises(ValueError): parse_response(x)

    def test_input_allowlist_and_size(self):
        with self.assertRaises(ValueError): build_request({**SOURCE, 'api_key': 'secret'}, 'test')
        with self.assertRaises(ValueError): build_request({**SOURCE, 'posting_text': 'a'*24000}, 'test')

    def test_exception_does_not_leak(self):
        def broken(body): raise RuntimeError('secret credential and candidate data')
        r = evaluate(SOURCE, {'verdict': 'PASS'}, 'test', broken)
        self.assertNotIn('secret', str(r))
        self.assertEqual(r['status'], 'provider_error')

    def test_live_requires_explicit_enable_and_key(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError): live_transport({})
        with patch.dict('os.environ', {'JEV_ENABLE_LIVE': '1'}, clear=True):
            with self.assertRaises(ValueError): live_transport({})

    def test_no_redirects(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.test'))

    def test_unicode_request_size_and_hash_match_actual_wire_bytes(self):
        source = {**SOURCE, 'posting_text': '\u00e9' * 7000}
        body = build_request(source, 'test')
        # The original default JSON escaping expanded this valid input past the cap.
        self.assertGreater(len(json.dumps(body).encode('utf-8')), 24000)
        with patch.dict('os.environ', {'JEV_ENABLE_LIVE': '1', 'TYPESAFE_API_KEY': 'synthetic-test'}, clear=True), \
                patch('tools.jev_triage.urllib.request.build_opener') as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = json.dumps(RESPONSE).encode('utf-8')
            result = evaluate(source, {'verdict': 'PASS'}, 'test', live_transport)
            opener.return_value.open.assert_called_once()
            request = opener.return_value.open.call_args.args[0]
            self.assertLessEqual(len(request.data), 24000)
            self.assertEqual(json.loads(request.data), body)
            self.assertEqual(result['input_hash'], hashlib.sha256(request.data).hexdigest())
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 20)
            self.assertEqual(result['status'], 'evaluated')

    def test_oversized_transport_payload_rejected_before_open(self):
        body = build_request(SOURCE.copy(), 'test')
        body['state']['posting_text'] = '\u00e9' * 12000
        with patch.dict('os.environ', {'JEV_ENABLE_LIVE': '1', 'TYPESAFE_API_KEY': 'synthetic-test'}, clear=True), \
                patch('tools.jev_triage.urllib.request.build_opener') as opener:
            with self.assertRaises(ValueError):
                live_transport(body)
            opener.assert_not_called()

    def test_oversized_response_leaves_review_without_retry(self):
        with patch.dict('os.environ', {'JEV_ENABLE_LIVE': '1', 'TYPESAFE_API_KEY': 'synthetic-test'}, clear=True), \
                patch('tools.jev_triage.urllib.request.build_opener') as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b'x' * 65537
            result = evaluate(SOURCE, {'verdict': 'PASS'}, 'test', live_transport)
            opener.return_value.open.assert_called_once()
            response.read.assert_called_once_with(65537)
            self.assertEqual(result['status'], 'provider_error')
            self.assertEqual(result['advisory_priority'], 'review')

    def test_cli_accepts_bom_and_never_activates_live_from_environment_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            source, gate, fixture = [Path(directory) / name for name in ('source.json', 'gate.json', 'fixture.json')]
            for path, value in ((source, SOURCE), (gate, {'verdict': 'PASS'}), (fixture, RESPONSE)):
                path.write_text(json.dumps(value), encoding='utf-8-sig')
            before = {path: path.read_bytes() for path in (source, gate, fixture)}
            for use_fixture in (False, True):
                argv = ['jev_triage.py', str(source), '--gate', str(gate), '--model', 'test']
                if use_fixture:
                    argv += ['--response-fixture', str(fixture)]
                output = io.StringIO()
                with self.subTest(use_fixture=use_fixture), \
                        patch('sys.argv', argv), redirect_stdout(output), \
                        patch.dict('os.environ', {'JEV_ENABLE_LIVE': '1', 'TYPESAFE_API_KEY': 'synthetic-test'}, clear=True), \
                        patch('tools.jev_triage.urllib.request.build_opener') as opener:
                    main()
                    opener.assert_not_called()
                    result = json.loads(output.getvalue())
                    self.assertEqual(result['status'], 'evaluated' if use_fixture else 'disabled')
            self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_hash_changes_with_profile_and_model(self):
        a = evaluate(SOURCE, {'verdict':'PASS'}, 'one')['input_hash']
        b = evaluate(SOURCE, {'verdict':'PASS'}, 'two')['input_hash']
        c = evaluate({**SOURCE, 'candidate_summary':'SQL only'}, {'verdict':'PASS'}, 'one')['input_hash']
        self.assertEqual(len({a,b,c}),3)

if __name__ == '__main__': unittest.main()
