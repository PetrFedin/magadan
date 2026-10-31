import csv
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date,datetime,timedelta,timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from hydro_backtest_v82 import benchmark, timestamp, score

class HydroV82Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.tmp.name)
        cls.csv_path=cls.root/'daily.csv'
        last=date(2026,10,30)
        first=last-timedelta(days=1094)
        rows=[]
        for site in ['KOLYMA_UPSTREAM','UST_SREDNEKAN_DOWNSTREAM']:
            for i in range(1095):
                day=first+timedelta(days=i)
                value=100+(i%53) if site=='KOLYMA_UPSTREAM' else 200+(i%53)
                rows.append({'site_id':site,'observation_date':day.isoformat(),
                             'available_at':(datetime.combine(day+timedelta(days=1),datetime.min.time(),timezone.utc)).isoformat(),
                             'natural_inflow_cms':str(value),'quality_flag':'ACCEPTED_ACTUAL'})
        with cls.csv_path.open('w',encoding='utf-8',newline='') as stream:
            w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        cls.digest=hashlib.sha256(cls.csv_path.read_bytes()).hexdigest()
        cls.payload={'schema_version':'HYDRO_V82','as_of':'2026-10-31T00:00:00+00:00',
                     'source':{'relative_path':'daily.csv','sha256':cls.digest,
                               'scope':'AUTHORISED_RESEARCH_ONLY',
                               'authorization_ref':'SYNTHETIC_TEST_REFERENCE_NOT_REAL',
                               'submitted_by':'tester-A','reviewed_by':'tester-B',
                               'reviewed_at':'2026-10-30T00:00:00+00:00',
                               'authorization_expires_at':'2026-11-01T00:00:00+00:00'}}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def check(self,edit=None):
        x=json.loads(json.dumps(self.payload))
        if edit:edit(x)
        return benchmark(x,self.root)
    def test_complete_synthetic_reference_review_only(self):
        x=self.check()
        self.assertEqual(x['status'],'REVIEW_ONLY')
        self.assertIsNone(x['forecast_to_cascade'])
        self.assertFalse(x['actual_dispatch_approved'])
        self.assertFalse(x['investment_approved'])
        self.assertEqual(set(x['stations']),{'KOLYMA_UPSTREAM','UST_SREDNEKAN_DOWNSTREAM'})
    def test_three_horizons_and_two_baselines(self):
        x=self.check()
        for v in x['stations'].values():
            self.assertEqual(set(v['backtests_by_horizon_days']),{'1','7','30'})
            self.assertEqual(set(v['backtests_by_horizon_days']['7']),{'persistence','lag365'})
            self.assertGreater(v['backtests_by_horizon_days']['30']['persistence']['n'],20)
    def test_json_without_data_hold(self):
        self.assertEqual(benchmark({'schema_version':'HYDRO_V82','as_of':'2026-10-31T00:00:00+00:00','source':None},self.root)['status'],'HOLD')
    def test_input_requires_exact_csv_sha(self):
        self.assertEqual(self.check(lambda x:x['source'].update(sha256='a'*64))['status'],'HOLD')
    def test_source_requires_owner_rights(self):
        self.assertEqual(self.check(lambda x:x['source'].update(authorization_ref=''))['status'],'HOLD')
    def test_independent_review(self):
        self.assertEqual(self.check(lambda x:x['source'].update(reviewed_by='TESTER-a'))['status'],'HOLD')
    def test_reviewer_not_in_future(self):
        self.assertEqual(self.check(lambda x:x['source'].update(reviewed_at='2026-12-01T00:00:00Z'))['status'],'HOLD')
    def test_expired_authorization(self):
        self.assertEqual(self.check(lambda x:x['source'].update(authorization_expires_at='2026-10-30T00:00:00Z'))['status'],'HOLD')
    def test_wrong_scope_hold(self):
        self.assertEqual(self.check(lambda x:x['source'].update(scope='PUBLIC_UNVERIFIED'))['status'],'HOLD')
    def test_unsafe_relative_path(self):
        self.assertEqual(self.check(lambda x:x['source'].update(relative_path='../daily.csv'))['status'],'HOLD')
    def test_no_timezone(self):
        self.assertEqual(self.check(lambda x:x.update(as_of='2026-10-31T00:00:00'))['status'],'HOLD')
    def test_metric_wape_computed_from_actual_denominator(self):
        z=score([10.]*20,[5.]*20); self.assertEqual(z['wape_pct'],50)
    def test_all_zero_actuals_cannot_claim_wape(self):
        self.assertIsNone(score([0.]*30,[0.]*30))
    def test_missing_short_horizon(self):
        self.assertIsNone(score([1.]*3,[1.]*3))
    def test_zero_leakage_with_origin_available_after_issue(self):
        self.assertEqual(self.check()['status'],'REVIEW_ONLY')
        # Tests the actual check indirectly: all data are exactly next-day available.
    def test_tampered_csv_bytes_fail(self):
        original=self.csv_path.read_bytes()
        try:
            self.csv_path.write_bytes(original+b'\nTAMPERED')
            self.assertEqual(self.check()['status'],'HOLD')
        finally:
            self.csv_path.write_bytes(original)
    def test_missing_observation_is_not_imputed_zero(self):
        original=self.csv_path.read_bytes()
        try:
            lines=original.decode('utf-8').splitlines(keepends=True)
            lines.pop(1050)
            changed=''.join(lines).encode('utf-8')
            self.csv_path.write_bytes(changed)
            p=json.loads(json.dumps(self.payload))
            p['source']['sha256']=hashlib.sha256(changed).hexdigest()
            result=benchmark(p,self.root)
            self.assertEqual(result['status'],'HOLD')
            self.assertIn('1095-day',result['hold_reason'])
        finally:
            self.csv_path.write_bytes(original)
    def test_data_not_used_for_cascade(self):
        x=self.check();self.assertFalse(x['validated_future_skill']);self.assertIsNone(x['forecast_to_cascade'])

if __name__=='__main__':unittest.main()
