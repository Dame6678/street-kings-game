import pytest
from decimal import Decimal
from engine import Match,settle

def test_settlement():
    assert settle([500,500])=={'pool_cents':1000,'platform_cents':300,'prizes_cents':700,'payouts_cents':[700]}
    assert settle([1000]*100,splits=['0.5','0.25','0.15','0.07','0.03'])['payouts_cents']==[35000,17500,10500,4900,2100]
    for n in range(1,120):
        d=settle([101]*n,Decimal('0.16'));assert d['platform_cents']+sum(d['payouts_cents'])==d['pool_cents']
def test_game():
    g=Match();s=g.action(0,0,'claim');assert s['blocks'][0]['owner']==0
    with pytest.raises(ValueError):g.action(1,0,'claim')
    assert g.score(0)>0
    while not g.state()['finished']:
        g.pass_turn(0)
    assert g.state()['finished']
    with pytest.raises(ValueError):g.action(0,1,'claim')
def test_no_negative():
    g=Match(cash=[0,0]);
    with pytest.raises(ValueError):g.action(0,0,'claim')
