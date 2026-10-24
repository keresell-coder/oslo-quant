from copy import deepcopy
from pathlib import Path
import json

import pandas as pd
from pandas.testing import assert_frame_equal
from oslo_quant.primary_financials import load_primary
from oslo_quant.primary_adapter import apply_primary_current
from oslo_quant import report,healthcheck
from oslo_quant.config import COMPANIES,ALL_FRAMEWORKS
from tests.test_healthcheck import _write_results


def source():
    return load_primary('NOD.OL',Path(__file__).parents[1]/'data/primary',download=False)


def provider():
    return {key:pd.DataFrame({'2025':{'Total Revenue':667619000,'Net Income':16385000,'Total Assets':983361000},'LTM 2026-06':{'Total Revenue':750000000,'Net Income':40000000,'Total Assets':1041349000}}) for key in ['income_stmt','balance_sheet','cash_flow']} | {'prices':pd.DataFrame({'Close':[16]})}


def test_primary_inputs_separate_provider_and_annual_controls():
    original=provider();before=deepcopy(original);primary=source()
    output,audit=apply_primary_current(original,primary,'USD')
    assert audit['status']=='applied-selected-primary'
    assert output['income_stmt'].loc['Total Revenue','LTM 2026-09']==815987000
    assert output['income_stmt'].loc['Reported EBITDA','LTM 2026-09']==108503000
    assert output['income_stmt'].loc['Net Income','LTM 2026-09']==58174000
    assert output['cash_flow'].loc['Operating Cash Flow','LTM 2026-09']==39938000
    assert output['balance_sheet'].loc['Retained Earnings','LTM 2026-09']==335403000
    assert 'EBIT' not in output['income_stmt'].index
    assert 'Diluted EPS' not in output['income_stmt'].index
    for key in ['income_stmt','balance_sheet','cash_flow']:
        assert output[key].loc['Total Assets','2025']==original[key].loc['Total Assets','2025']
        assert_frame_equal(original[key],before[key])
    assert audit['provider_virtual_current']['income_stmt']['LTM 2026-06']['Total Revenue']==750000000
    assert all(r['provider_value'] is None for r in audit['provider_comparisons'])


def test_incompatible_currency_and_incomplete_inputs_never_apply():
    original=provider();primary=source()
    out,audit=apply_primary_current(original,primary,'NOK')
    assert out is original and audit['status']=='blocked'
    primary['derived']=[r for r in primary['derived'] if r['row']!='Operating Cash Flow']
    out,audit=apply_primary_current(original,primary,'USD')
    assert out is original and audit['status']=='blocked'


def test_mowi_annual_controls_untouched():
    original=provider();out,audit=apply_primary_current(original,load_primary('MOWI.OL',Path(__file__).parents[1]/'data/primary',download=False),'EUR')
    assert out is original and audit['status']=='not-applied'


def test_health_keeps_provider_gap_but_qualifies_selected_primary_tables(tmp_path):
    _write_results(tmp_path,['fresh']*len(COMPANIES));primary=source();_,selection=apply_primary_current(provider(),primary,'USD');primary['selection']=selection
    for fw in ALL_FRAMEWORKS:
        path=tmp_path/'NOD.OL'/(fw+'.json');d=json.loads(path.read_text());src=d['source_metadata'];src['primary_inputs']=primary
        src['groups']['quarterly']['statement_period_ends']={k:['2026-06-30'] for k in ['income_stmt','balance_sheet','cash_flow']};path.write_text(json.dumps(d))
    row=next(r for r in healthcheck.build_health(results_dir=tmp_path)['companies'] if r['ticker']=='NOD.OL')
    assert row['status']!='blocked'
    assert row['filing_coverage']['input_source']=='selected-primary'
    assert all(r['status']=='behind-known-release' for r in row['filing_coverage']['provider_tables'].values())
    assert all(r['status']=='provider-covers-known-release' for r in row['filing_coverage']['tables'].values())
    assert row['effective_statement_period_end']=='2026-09-30'
    assert 'Reported EBITDA' in report._primary_inputs({'NOD.OL':{'primary':primary}})


def test_primary_never_replaces_newer_provider_observations():
    original=provider();primary=source()
    out,audit=apply_primary_current(original,primary,'USD',{'income_stmt':['2026-12-31']})
    assert out is original and audit['status']=='blocked'
    assert 'older' in audit['reason']
