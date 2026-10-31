"""V8.1 research-only tests; the source is a PUBLIC regulatory table, not raw inflow telemetry."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2] if (HERE.parents[2] / 'server').exists() else HERE.parent
if (ROOT / 'server' / 'hydro_api').is_dir():
    sys.path.insert(0, str(ROOT / 'server'))
else:
    sys.path.insert(0, str(ROOT))
from hydro_api.hydro_reference_v81 import (public_reference_report, sanitary_release_screen,
                                            InvalidReference, SITES, validate)

REF_FILE = ROOT / 'data' / 'references' / 'V81_KOLYMA_2025_RULES.json'
if not REF_FILE.exists():
    REF_FILE = ROOT / 'reference.json'


class ReferenceV81Test(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads(REF_FILE.read_text(encoding='utf-8'))

    def test_official_reference_loads(self):
        self.assertEqual(set(validate(self.raw)), set(SITES))

    def test_88_year_period(self):
        out = public_reference_report(self.raw)
        self.assertEqual((out['period'], out['observed_years']), ('1934-2021', 88))

    def test_kolyma_historical_statistics(self):
        st = public_reference_report(self.raw)['stations']['KOLYMA_UPSTREAM']
        self.assertEqual((st['observed_min_km3'], st['mean_annual_km3'], st['observed_max_km3']),
                         ('6.51','15.1','25.5'))

    def test_downstream_historical_statistics(self):
        st = public_reference_report(self.raw)['stations']['UST_SREDNEKAN_DOWNSTREAM']
        self.assertEqual((st['observed_min_km3'], st['mean_annual_km3'], st['observed_max_km3']),
                         ('11.1','24.9','39.3'))

    def test_official_p95_p50_p05(self):
        out=public_reference_report(self.raw)['stations']
        self.assertEqual([out['KOLYMA_UPSTREAM'][x] for x in ('p95_low_runoff_km3','p50_median_exceedance_km3','p05_high_runoff_km3')], ['9.18','14.9','21.6'])
        self.assertEqual([out['UST_SREDNEKAN_DOWNSTREAM'][x] for x in ('p95_low_runoff_km3','p50_median_exceedance_km3','p05_high_runoff_km3')], ['15.5','24.6','35.1'])

    def test_fitted_downstream_p1_may_exceed_observed_max(self):
        x=self.raw['stations']['UST_SREDNEKAN_DOWNSTREAM']
        self.assertGreater(float(x['exceedance_km3']['1']), float(x['observed_max_km3']))
        self.assertEqual(public_reference_report(self.raw)['status'],'PUBLIC_REFERENCE_ONLY')

    def test_never_claims_future_forecast(self):
        result=public_reference_report(self.raw)
        self.assertIsNone(result['forecast_next_water_year_km3'])
        self.assertFalse(result['scenario_probabilities_are_next_year_predictions'])

    def test_nested_sections_never_added(self):
        self.assertIsNone(public_reference_report(self.raw)['cascade_summed_runoff_km3'])

    def test_no_dispatch_or_financial_authority(self):
        result=public_reference_report(self.raw)
        self.assertFalse(result['approved_for_dispatch'])
        self.assertFalse(result['approved_for_investment'])
        self.assertIsNone(result['hydropower_mwh_forecast'])
        self.assertIsNone(result['financial_savings_rub'])

    def test_annualized_flow_is_dimensional_not_dispatch(self):
        result=public_reference_report(self.raw)['stations']
        self.assertEqual(result['KOLYMA_UPSTREAM']['mean_annualized_flow_equivalent_cms'],'478.50')
        self.assertEqual(result['UST_SREDNEKAN_DOWNSTREAM']['mean_annualized_flow_equivalent_cms'],'789.05')

    def test_bad_document_id_rejected(self):
        self.raw['document_id']='UNKNOWN'
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_unregistered_scope_rejected(self):
        self.raw['scope']='OTHER_BASIN'
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_mismatched_period_rejected(self):
        self.raw['observation_window']='1934-2026'
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_wrong_units_rejected(self):
        self.raw['volume_unit']='cms'
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_unknown_station_rejected(self):
        self.raw['stations']['FAKE_STATION']=self.raw['stations']['KOLYMA_UPSTREAM']
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_inverted_exceedance_curve_rejected(self):
        self.raw['stations']['KOLYMA_UPSTREAM']['exceedance_km3']['95']='100'
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_plausible_numeric_tampering_also_rejected(self):
        self.raw['stations']['KOLYMA_UPSTREAM']['exceedance_km3']['5'] = '21.5'
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_missing_rare_probability_rejected(self):
        del self.raw['stations']['KOLYMA_UPSTREAM']['exceedance_km3']['99']
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_boolean_value_rejected(self):
        self.raw['stations']['KOLYMA_UPSTREAM']['mean_annual_km3']=True
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_nonfinite_value_rejected(self):
        self.raw['stations']['KOLYMA_UPSTREAM']['mean_annual_km3']='NaN'
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_negative_value_rejected(self):
        self.raw['stations']['UST_SREDNEKAN_DOWNSTREAM']['observed_min_km3']='-11.1'
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_fabricated_sanitary_threshold_rejected(self):
        self.raw['stations']['KOLYMA_UPSTREAM']['nominal_sanitary_release_cms']='10'
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_cannot_claim_independent_subbasins(self):
        self.raw['stations_are_independent']=True
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_raw_88_year_data_not_fabricated(self):
        self.raw['raw_88_year_daily_dataset_available']=True
        with self.assertRaises(InvalidReference):validate(self.raw)

    def test_screen_below_sanitary_release_not_dispatch(self):
        screen=sanitary_release_screen(self.raw,{'KOLYMA_UPSTREAM':'99.99','UST_SREDNEKAN_DOWNSTREAM':'69'})
        self.assertEqual(screen['screening']['KOLYMA_UPSTREAM']['screen'],'BELOW_NOMINAL_SANITARY_FLOW')
        self.assertEqual(screen['screening']['UST_SREDNEKAN_DOWNSTREAM']['screen'],'BELOW_NOMINAL_SANITARY_FLOW')
        self.assertFalse(screen['approved_for_dispatch'])

    def test_screen_nominal_above_not_full_compliance(self):
        screen=sanitary_release_screen(self.raw,{'KOLYMA_UPSTREAM':'110','UST_SREDNEKAN_DOWNSTREAM':'80'})
        self.assertEqual(screen['screening']['KOLYMA_UPSTREAM']['screen'],'NOT_BELOW_NOMINAL_SANITARY_FLOW')
        self.assertFalse(screen['water_balance_approved'])

    def test_zero_flow_is_valid_scenario_but_violation(self):
        screen=sanitary_release_screen(self.raw,{'KOLYMA_UPSTREAM':'0','UST_SREDNEKAN_DOWNSTREAM':0})
        self.assertTrue(all(x['screen']=='BELOW_NOMINAL_SANITARY_FLOW' for x in screen['screening'].values()))

    def test_negative_proposed_flow_rejected(self):
        with self.assertRaises(InvalidReference):
            sanitary_release_screen(self.raw,{'KOLYMA_UPSTREAM':'-1','UST_SREDNEKAN_DOWNSTREAM':'80'})

    def test_bool_proposed_flow_rejected(self):
        with self.assertRaises(InvalidReference):
            sanitary_release_screen(self.raw,{'KOLYMA_UPSTREAM':True,'UST_SREDNEKAN_DOWNSTREAM':'80'})

    def test_incomplete_two_node_proposal_rejected(self):
        with self.assertRaises(InvalidReference):sanitary_release_screen(self.raw,{'KOLYMA_UPSTREAM':'101'})


if __name__ == '__main__':unittest.main()
