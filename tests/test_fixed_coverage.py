from types import SimpleNamespace
import pandas as pd
import pytest
from oslo_quant.config import TICKER_MAP
from oslo_quant.pipeline import _resolve_currency, _convert_prices
from oslo_quant.fetchers.yfinance_fetcher import YFinanceFetcher

REQUIRED = {'VSAT','NOD.OL','PUBLI.OL','SCATC.OL','DOFG.OL','COSH.OL','NORBT.OL','MOWI.OL','CMBTO.OL','ODL.OL','KOG.OL','ORK.OL'}

def test_exact_market_identity():
    assert REQUIRED <= TICKER_MAP.keys()
    assert 'VSAT.OL' not in TICKER_MAP
    assert (TICKER_MAP['VSAT'].exchange,TICKER_MAP['VSAT'].price_currency) == ('NASDAQ','USD')
    assert all(c.exchange=='Euronext Oslo' and c.price_currency=='NOK' for t,c in TICKER_MAP.items() if t.endswith('.OL'))

@pytest.mark.parametrize('ticker,price,financial,status',[
    ('VSAT','USD','USD','screening-currency-consistent'),
    ('VSAT','NOK','USD','gated-unverified-currency'),
    ('VSAT','Unknown','USD','gated-unverified-currency'),
    ('NOD.OL','NOK','USD','screening-currency-consistent'),
])
def test_provider_and_market_currency_contract(ticker,price,financial,status):
    fetcher=SimpleNamespace(fetch_currency_info=lambda *a,**k:dict(price_currency=price,financial_currency=financial))
    assert _resolve_currency(fetcher,ticker,TICKER_MAP[ticker],True)['status']==status


def test_us_failed_currency_fetch_never_falls_back_to_nok(tmp_path):
    class FailedTicker:
        @property
        def info(self):
            raise RuntimeError('offline')
    result=YFinanceFetcher()._detect_and_cache_currency(FailedTicker(),'VSAT',tmp_path,True)
    assert result['price_currency']=='Unknown'


def test_us_prices_do_not_request_nok_fx():
    def unexpected(*a): raise AssertionError('USD to USD must not request FX')
    frame=pd.DataFrame({'Close':[42.]})
    out=_convert_prices({'prices':frame},'USD','USD',SimpleNamespace(fetch_fx_rate=unexpected),{})
    assert out['prices'].iloc[0,0]==42.


def test_expanded_roster_keeps_eighty_percent_refresh_gate(tmp_path):
    from oslo_quant.healthcheck import build_health
    health=build_health(results_dir=tmp_path)
    assert health['coverage']['expected']==22
    assert health['coverage']['minimum_refreshed']==18
