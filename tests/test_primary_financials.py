import copy
from datetime import datetime, timezone
import hashlib
import json

import pytest
from oslo_quant.primary_financials import validate, derive_ttm, load_primary, PrimaryInputError

NOW = datetime(2026, 10, 24, 22, tzinfo=timezone.utc)
ARTIFACT = b'%PDF-synthetic-regression-artifact-not-an-issuer-report'


def document():
    source = {"id": "nod-q3", "ticker": "NOD.OL", "title": "Synthetic test only", "url": "https://www.nordicsemi.com/test.pdf",
        "sha256": hashlib.sha256(ARTIFACT).hexdigest(), "published_on": "2026-10-22", "retrieved_at": "2026-10-24T21:00:00Z"}
    records = []
    for key, scope, start, end, value in [('fy','annual','2025-01-01','2025-12-31',600),('current','year_to_date','2026-01-01','2026-09-30',550),('prior','year_to_date','2025-01-01','2025-09-30',450)]:
        records.append({"id":key,"source_id":"nod-q3","statement":"income_stmt","row":"Total Revenue","source_label":"Revenue",
            "table":"Consolidated income statement","page":14,"scope":scope,"period_start":start,"period_end":end,
            "currency":"USD","scale":"thousands","accounting_basis":"IFRS-consolidated","consolidation_basis":"group",
            "review_status":"reviewed-transcription","value":value,"aggregation":"flow"})
    return {"schema_version":1,"ticker":"NOD.OL","currency":"USD","sources":[source],"records":records,
        "ttm_recipes":[{"id":"ttm-revenue","records":["fy","current","prior"]}]}


def test_audited_ttm_units_and_lineage():
    doc = document();_,records=validate(doc,NOW)
    row=derive_ttm(records,doc['ttm_recipes'][0])
    assert row['value_units']==700000
    assert row['source_records']==['fy','current','prior']
    assert row['period_end']=='2026-09-30'
    assert row['scope']=='ttm'
    assert records['current']['source']['sha256']==doc['sources'][0]['sha256']


@pytest.mark.parametrize('case',['issuer','currency','scale','quarter','basis','page','future','duplicate','missing_table'])
def test_reject_incompatible_primary_records(case):
    doc=document();r=doc['records'][1]
    if case=='issuer':doc['sources'][0]['ticker']='DOFG.OL'
    elif case=='currency':r['currency']='NOK'
    elif case=='scale':r['scale']='USD thousands'
    elif case=='quarter':r['scope']='quarter'
    elif case=='basis':r['consolidation_basis']='unallocated'
    elif case=='page':r['page']=0
    elif case=='future':doc['sources'][0]['retrieved_at']='2026-10-25T00:00:00Z'
    elif case=='duplicate':doc['records'].append({**r,'id':'duplicate'})
    elif case=='missing_table':r.pop('table')
    with pytest.raises((PrimaryInputError,ValueError)):validate(doc,NOW)


@pytest.mark.parametrize('case',['quarter','comparative_date','owners','unreviewed','eps'])
def test_reject_bad_ttm_bridge(case):
    doc=document()
    if case=='quarter':doc['records'][1].update(scope='quarter',period_start='2026-07-01')
    elif case=='comparative_date':doc['records'][2]['period_end']='2025-06-30'
    elif case=='owners':doc['records'][2]['consolidation_basis']='owners-of-parent'
    elif case=='unreviewed':doc['records'][2]['review_status']='unreviewed'
    elif case=='eps':
        for r in doc['records']:r['row']='Diluted EPS'
    _,records=validate(doc,NOW)
    with pytest.raises(PrimaryInputError):derive_ttm(records,doc['ttm_recipes'][0])


def test_hash_failure_never_releases_primary_inputs(tmp_path):
    doc=document();(tmp_path/'NOD.OL.json').write_text(json.dumps(doc));cache=tmp_path/'cache';cache.mkdir();path=cache/(doc['sources'][0]['sha256']+'.pdf');path.write_bytes(ARTIFACT)
    result=load_primary('NOD.OL',tmp_path,NOW,False)
    assert result['status']=='reviewed-line-items'
    assert result['input_policy']=='audit-only'
    assert result['artifacts'][0]['artifact_cache_used'] is True
    path.write_bytes(b'changed')
    failed=load_primary('NOD.OL',tmp_path,NOW,False)
    assert failed['status']=='blocked' and failed['records']==[] and failed['derived']==[]


def test_unavailable_source_does_not_become_verified(tmp_path):
    (tmp_path/'NOD.OL.json').write_text(json.dumps(document()))
    assert load_primary('NOD.OL',tmp_path,NOW,False)['status']=='blocked'
    assert load_primary('OTHER',tmp_path,NOW,False)['status']=='not-configured'


def test_official_nordic_ingestion_and_safe_unavailable_fields():
    from pathlib import Path
    result=load_primary('NOD.OL',Path(__file__).parents[1]/'data/primary',download=False)
    assert result['status']=='reviewed-line-items'
    ttm={r['row']:r['value_units'] for r in result['derived']}
    assert ttm['Total Revenue']==815987000
    assert ttm['Reported EBITDA']==108503000
    assert ttm['Net Income']==58174000
    assert ttm['Operating Cash Flow']==39938000
    assert not {'EBIT','Diluted EPS','Free Cash Flow'} & ttm.keys()
    instant={r['row']:r['value_units'] for r in result['records'] if r['scope']=='instant' and r['period_end']=='2026-09-30'}
    assert instant['Retained Earnings']==335403000
    assert instant['Stockholders Equity']==734346000
    assert instant['Retained Earnings']!=395126000


@pytest.mark.parametrize('row,aggregation',[('Weighted Average Shares','non-additive'),('Cash at end','stock')])
def test_nonadditive_bridge_rejected(row,aggregation):
    doc=document()
    for r in doc['records']:r.update(row=row,aggregation=aggregation)
    _,records=validate(doc,NOW)
    with pytest.raises(PrimaryInputError):derive_ttm(records,doc['ttm_recipes'][0])
