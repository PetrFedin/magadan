"""Regression tests for the published section III monthly Kolyma table."""
from __future__ import annotations
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server'/'hydro_api'))
from hydro_monthly_v83 import profile,validate,InvalidReference

REFERENCE=ROOT/'data'/'references'/'V83_official_monthly_characteristic_years.json'

class PublishedCharacteristicYearsTest(unittest.TestCase):
    def setUp(self):self.ref=json.loads(REFERENCE.read_text(encoding='utf-8'))
    def assert_invalid(self):
        with self.assertRaises(InvalidReference):validate(self.ref)
    def test_table_integrity(self):self.assertEqual(len(validate(self.ref)),2)
    def test_six_real_historical_profiles(self):
        x=profile(self.ref)
        self.assertEqual(sum(len(v) for v in x['observations'].values()),6)
    def test_wet_sums_match_regulation(self):
        x=profile(self.ref)['observations']
        self.assertEqual(x['KOLYMA_UPSTREAM']['wet']['annual_km3'],'23.00')
        self.assertEqual(x['UST_SREDNEKAN_DOWNSTREAM']['wet']['annual_km3'],'39.27')
    def test_average_year_sums(self):
        x=profile(self.ref)['observations']
        self.assertEqual(x['KOLYMA_UPSTREAM']['average']['annual_km3'],'14.77')
        self.assertEqual(x['UST_SREDNEKAN_DOWNSTREAM']['average']['annual_km3'],'24.07')
    def test_dry_year_sums(self):
        x=profile(self.ref)['observations']
        self.assertEqual(x['KOLYMA_UPSTREAM']['dry']['annual_km3'],'11.22')
        self.assertEqual(x['UST_SREDNEKAN_DOWNSTREAM']['dry']['annual_km3'],'18.45')
    def test_june_is_wettest_in_both_all_three_cases(self):
        x=profile(self.ref)['observations']
        self.assertTrue(all(v['peak_month']=='06' for row in x.values() for v in row.values()))
    def test_warm_share_upper_average(self):
        self.assertEqual(profile(self.ref)['observations']['KOLYMA_UPSTREAM']['average']['warm_may_sep_pct'],'97.02')
    def test_winter_share_downstream_wet(self):
        self.assertEqual(profile(self.ref)['observations']['UST_SREDNEKAN_DOWNSTREAM']['wet']['winter_oct_apr_pct'],'4.81')
    def test_nested_water_not_summed(self):
        self.assertIsNone(profile(self.ref)['nested_gauge_total_km3'])
    def test_no_forecast_and_no_power(self):
        x=profile(self.ref)
        self.assertIsNone(x['forecast_for_2027'])
        self.assertIsNone(x['forecast_distribution'])
        self.assertFalse(x['approved_for_hydroforecast'])
        self.assertFalse(x['approved_for_cascade'])
        self.assertFalse(x['approved_for_dispatch'])
        self.assertFalse(x['approved_for_investment'])
    def test_not_probability_sample(self):
        self.assertFalse(profile(self.ref)['monthly_cases_are_statistically_representative_sample'])
    def test_wrong_month_order(self):
        self.ref['water_year_months'][0]='01';self.assert_invalid()
    def test_wrong_units(self):
        self.ref['volume_unit']='m3_per_second';self.assert_invalid()
    def test_wrong_document(self):
        self.ref['document_id']='FAKE';self.assert_invalid()
    def test_source_url_change(self):
        self.ref['source_url']='https://example.com';self.assert_invalid()
    def test_fake_daily_archive(self):
        self.ref['raw_daily_archives_available']=True;self.assert_invalid()
    def test_claimed_next_year_forecast(self):
        self.ref['estimate_for_2027']='23.4';self.assert_invalid()
    def test_missing_month(self):
        self.ref['cases']['KOLYMA_UPSTREAM']['wet']['monthly_km3'].pop();self.assert_invalid()
    def test_plausible_tamper_preserving_annual(self):
        vals=self.ref['cases']['KOLYMA_UPSTREAM']['wet']['monthly_km3']
        vals[0]='1.9';vals[1]='9.8'
        self.assert_invalid()
    def test_no_negative_month(self):
        self.ref['cases']['UST_SREDNEKAN_DOWNSTREAM']['dry']['monthly_km3'][0]='-0.5'
        self.assert_invalid()
    def test_no_float_precision(self):
        self.ref['cases']['KOLYMA_UPSTREAM']['average']['monthly_km3'][0]=2.6
        self.assert_invalid()
    def test_zero_winter_volumes_in_source_allowed(self):
        self.assertEqual(profile(self.ref)['observations']['KOLYMA_UPSTREAM']['dry']['monthly_km3']['02'],'0')
    def test_observed_year_mismatch(self):
        self.ref['cases']['KOLYMA_UPSTREAM']['dry']['water_year']='2026/27';self.assert_invalid()

if __name__=='__main__':unittest.main()