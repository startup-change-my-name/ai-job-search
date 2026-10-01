import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tools.remote_gate import classify
from tools.remote_sources import parse, discover
from tools.create_private_workspace import create


class RemoteMarketTests(unittest.TestCase):
    def job(self):
        return {'remote': True, 'brazil_eligible': True, 'paid_in_usd': True,
                'overlap_compatible': True, 'contract_compatible': True,
                'salary': {'min': 60000, 'max': 72000, 'currency': 'USD', 'period': 'year', 'kind': 'listed'},
                'evidence': {k:'explicit posting evidence' for k in ['remote','brazil_eligible','paid_in_usd','salary','overlap_compatible','contract_compatible']},
                'source_url':'https://example.com/job', 'checked_date':'2026-01-01'}
    def test_confirmed_annual_pay(self):
        result=classify(self.job()); self.assertEqual(result['verdict'],'PASS')
        self.assertEqual(result['monthly_usd_range'],[5000,6000])
        self.assertEqual(result['floor_monthly_usd'],5000)
    def test_default_floor_boundaries(self):
        for lower, upper, verdict in ((4999, 4999, 'FAIL'),
                                      (4500, 6000, 'FLAG'),
                                      (4999, 5000, 'FLAG'),
                                      (5000, 5000, 'PASS'),
                                      (5000, 6000, 'PASS')):
            with self.subTest(lower=lower, upper=upper):
                job = self.job()
                job['salary'].update(min=lower, max=upper, period='month')
                result = classify(job)
                self.assertEqual(result['verdict'], verdict)
                self.assertEqual(result['floor_monthly_usd'], 5000)
                if verdict == 'FAIL':
                    self.assertIn('salary maximum below floor', result['failures'])
                elif verdict == 'FLAG':
                    self.assertIn('salary range overlaps floor', result['clarifications'])
    def test_custom_floor_preserves_explicit_policy(self):
        job = self.job()
        job['salary']['min'] = 54000
        self.assertEqual(classify(job)['verdict'], 'FLAG')
        result = classify(job, floor=4500)
        self.assertEqual(result['verdict'], 'PASS')
        self.assertEqual(result['floor_monthly_usd'], 4500)
        self.assertEqual(classify(job, 6500)['verdict'], 'FAIL')
    def test_us_remote_is_not_brazil(self):
        j=self.job();j['brazil_eligible']=False
        self.assertEqual(classify(j)['verdict'],'FAIL')
    def test_display_currency_not_payment(self):
        j=self.job();j['paid_in_usd']=None
        self.assertEqual(classify(j)['verdict'],'FLAG')
    def test_salary_overlap_and_estimate(self):
        j=self.job();j['salary']['min']=48000
        self.assertEqual(classify(j)['verdict'],'FLAG')
        j['salary']['max']=50000
        self.assertEqual(classify(j)['verdict'],'FAIL')
        j['salary']['kind']='estimated'
        self.assertEqual(classify(j)['verdict'],'FLAG')
    def test_hourly_needs_hours(self):
        j=self.job();j['salary'].update(min=40,max=50,period='hour')
        for invalid in (None, True, 0, -1, '125', float('nan'), float('inf')):
            with self.subTest(hours=invalid):
                j['salary']['paid_hours_per_month'] = invalid
                result = classify(j)
                self.assertEqual(result['verdict'], 'FLAG')
                self.assertIsNone(result['monthly_usd_range'])
                self.assertIn('hourly rate needs explicit paid hours per month', result['clarifications'])
        j['salary']['paid_hours_per_month']=120
        self.assertEqual(classify(j)['verdict'],'FLAG')
        j['salary']['paid_hours_per_month']=125
        self.assertEqual(classify(j)['verdict'],'PASS')
        self.assertEqual(classify(j)['monthly_usd_range'], [5000,6250])
    def test_invalid_pay_and_booleans(self):
        j=self.job();j['salary']['min']=float('nan')
        with self.assertRaises(ValueError):classify(j)
        j=self.job();j['remote']='true'
        with self.assertRaises(ValueError):classify(j)
    def test_evidence_requires_nonblank_text(self):
        for field in self.job()['evidence']:
            for invalid in (None, '', ' \t\n', True, 1, ['excerpt'], {'text': 'excerpt'}):
                with self.subTest(field=field, evidence=invalid):
                    job = self.job()
                    job['evidence'][field] = invalid
                    self.assertEqual(classify(job)['verdict'], 'FLAG')

    def test_working_hours_and_contract_must_be_confirmed(self):
        for field in ('overlap_compatible', 'contract_compatible'):
            with self.subTest(field=field):
                job = self.job()
                del job[field]
                self.assertEqual(classify(job)['verdict'], 'FLAG')
                job[field] = None
                self.assertEqual(classify(job)['verdict'], 'FLAG')
                job[field] = False
                self.assertEqual(classify(job)['failures'], [field])
                job[field] = 'true'
                with self.assertRaises(ValueError):
                    classify(job)

    def test_invalid_job_and_floor(self):
        for invalid in (None, [], 'posting', True, 42):
            with self.subTest(job=invalid), self.assertRaises(ValueError):
                classify(invalid)
        for invalid in (None, True, '5000', -1, float('nan'), float('inf'), -float('inf')):
            with self.subTest(floor=invalid), self.assertRaises(ValueError):
                classify(self.job(), invalid)
        self.assertEqual(classify(self.job(), 5500)['verdict'], 'FLAG')
        self.assertEqual(classify(self.job(), 0)['verdict'], 'PASS')

    def test_cli_floor_default_and_override(self):
        script = Path(__file__).resolve().parents[1] / 'tools' / 'remote_gate.py'
        with tempfile.TemporaryDirectory() as temp:
            job = self.job()
            job['salary']['min'] = 54000
            source = Path(temp) / 'job.json'
            source.write_text(json.dumps(job), encoding='utf-8')
            for options, floor, verdict in (([], 5000, 'FLAG'),
                                             (['--floor-monthly-usd', '4500'], 4500, 'PASS'),
                                             (['--floor-monthly-usd', '6500'], 6500, 'FAIL')):
                with self.subTest(options=options):
                    run = subprocess.run([sys.executable, str(script), str(source), *options],
                                         capture_output=True, text=True, check=True)
                    result = json.loads(run.stdout)
                    self.assertEqual(result['floor_monthly_usd'], floor)
                    self.assertEqual(result['verdict'], verdict)

    def test_cli_rejects_invalid_floor(self):
        script = Path(__file__).resolve().parents[1] / 'tools' / 'remote_gate.py'
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'job.json'
            source.write_text(json.dumps(self.job()), encoding='utf-8')
            for invalid in ('-1', 'nan', 'inf', '-inf', 'not-a-number'):
                with self.subTest(floor=invalid):
                    run = subprocess.run([sys.executable, str(script), str(source),
                                          '--floor-monthly-usd=' + invalid],
                                         capture_output=True, text=True)
                    self.assertNotEqual(run.returncode, 0)
                    self.assertEqual(run.stdout, '')
                    self.assertIn('floor', run.stderr)
                    self.assertNotIn('Traceback', run.stderr)

    def test_malformed_source_urls_are_flagged(self):
        for invalid in (None, [], '', 'http://example.com/job', 'https://',
                        'https://[broken', 'https://example.com:bad/job',
                        'https://example.com:99999/job', 'https://bad host/job'):
            with self.subTest(url=invalid):
                job = self.job()
                job['source_url'] = invalid
                result = classify(job)
                self.assertEqual(result['verdict'], 'FLAG')
                self.assertIn('source URL missing or invalid', result['clarifications'])

    def test_source_contract(self):
        rows=parse('wwr',b'<rss><channel><item><title>Acme: Data Engineer</title><link>https://example.com/job</link></item></channel></rss>')
        self.assertEqual(rows[0]['title'],'Data Engineer')
        self.assertEqual(rows[0]['eligibility'],'unverified')
        rows=parse('greenhouse',json.dumps({'jobs':[{'id':1,'title':'Data Engineer','absolute_url':'https://example.com/job','updated_at':'today'}]}).encode(),'acme')
        self.assertEqual(rows[0]['date'],'')
        with self.assertRaises(ValueError):discover('lever','../bad')
    def test_private_workspace_preserves_source_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);src=root/'source';src.mkdir()
            subprocess.run(['git','init',str(src)],check=True,capture_output=True)
            (src/'CLAUDE.md').write_text('template')
            subprocess.run(['git','-C',str(src),'add','.'],check=True)
            subprocess.run(['git','-C',str(src),'-c','user.name=Test','-c','user.email=test@example.com','commit','-m','fixture'],check=True,capture_output=True)
            (src/'secret.txt').write_text('untracked secret')
            dest=create(root/'private',src)
            self.assertFalse((dest/'.git').exists());self.assertFalse((dest/'secret.txt').exists())
            self.assertEqual((dest/'.gitignore').read_text(),'*\n')
            with self.assertRaises(ValueError):create(dest,src)
            with self.assertRaises(ValueError):create(src/'nested',src)
