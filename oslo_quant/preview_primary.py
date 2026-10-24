"""Offline primary selection review; annual comparator is an issuer control, not provider data."""
import json
from pathlib import Path
import pandas as pd

from oslo_quant.primary_financials import load_primary
from oslo_quant.primary_adapter import apply_primary_current
from oslo_quant.frameworks import FRAMEWORK_REGISTRY
from oslo_quant import report


def build_preview():
    root=Path(__file__).resolve().parents[1]
    primary=load_primary('NOD.OL',root/'data/primary',download=False)
    statements={key:pd.DataFrame() for key in ('income_stmt','balance_sheet','cash_flow')}
    for fact in primary.get('records',[]):
        if fact['period_end']=='2025-12-31' and fact['scope'] in {'annual','instant'}:
            statements[fact['statement']].loc[fact['row'],'2025']=fact['value_units']
    statements['prices']=pd.DataFrame()
    selected,audit=apply_primary_current(statements,primary,'USD')
    # Explicit missing standardized fields mirror an existing provider frame's row vocabulary.
    # No fallback from undefined standardized EBIT/interest/share inputs is introduced here.
    for frame,rows in [('income_stmt',['EBIT']),('balance_sheet',['Long Term Debt','Share Issued'])]:
        for row in rows:
            if row not in selected[frame].index:selected[frame].loc[row]=float('nan')
    results={key:framework().compute(selected,'NOD.OL') for key,framework in FRAMEWORK_REGISTRY.items()}
    return {'baseline_commit':'ee2a65013f0acdfe073af4dfeb7112fed0e8c8fd',
            'fixture_kind':'Primary source actual records; annual comparator constructed from issuer comparative, not claimed frozen provider data',
            'selection':audit,'primary':primary,'framework_current_periods':{key:r.get('periods',{}).get('LTM 2026-09') for key,r in results.items()}}


if __name__=='__main__':
    print(json.dumps(build_preview(),indent=2))
