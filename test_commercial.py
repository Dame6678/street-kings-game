"""Commercial presentation and competition integrity regression checks."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def isolated(tmp_path, monkeypatch):
    import storage,empire,divisions,play_games,main
    monkeypatch.setattr(storage,'DB_PATH',str(tmp_path/'commercial.sqlite3'))
    storage.init_db();empire.init();divisions.init();play_games.init()
    return TestClient(main.app),storage,play_games


def test_play_has_no_practice_or_internal_revenue_banners(isolated):
    client,_,_=isolated
    html=client.get('/play.html').text.upper()
    for phrase in ('FREE SOLO PRACTICE','SOLO PRACTICE','FREE PRACTICE','HUMAN MATCHES','FIND REAL OPPONENT','FUTURE PRIZE DESIGN','PLATFORM SHARE','USE ADMIN PREVIEW','CASH COMPETITIONS ARE NOT YET ACTIVE'):
        assert phrase not in html,phrase
    assert 'PLAY FOR REAL MONEY.' in html
    assert 'CASH PRIZE SHOWDOWNS · COMING SOON' in html
    assert 'FIND MATCH' in html
    assert html.count('<SVG')>=3


def test_competition_catalog_persistent_and_unchargeable(isolated):
    client,db,play_games=isolated
    with db.db() as c:
        c.execute('INSERT INTO play_competitions(id,title,entry_fee_cents,prize_cents,enabled) VALUES(?,?,?,?,0)',('seasonal','CROWN SHOWDOWN',1200,1680))
    catalog=client.get('/api/play/games').json()
    assert catalog['cash_active'] is False
    assert catalog['competitions'][0]['entry_fee_cents']==0
    assert any(v['id']=='seasonal' and v['entry_fee_cents']==1200 and v['enabled']==0 for v in catalog['competitions'])
    with pytest.raises(Exception):
        with db.db() as c:
            c.execute("UPDATE play_competitions SET enabled=1 WHERE id='seasonal'")
    with db.db() as c:
        assert c.execute("SELECT enabled FROM play_competitions WHERE id='seasonal'").fetchone()[0]==0


def test_two_real_accounts_can_compete_without_payout(isolated):
    client,storage,_=isolated
    storage.register('commercialA','long-password-A1');storage.register('commercialB','long-password-B1')
    ha={'Authorization':'Bearer '+storage.login('commercialA','long-password-A1')}
    hb={'Authorization':'Bearer '+storage.login('commercialB','long-password-B1')}
    room=client.post('/api/play/open',headers=ha,json={'game':'crossfire','matchmake':True}).json()['room_id']
    joined=client.post('/api/play/open',headers=hb,json={'game':'crossfire','matchmake':True}).json()
    assert joined['room_id']==room and len(joined['players'])==2
    assert client.post(f'/api/play/{room}/ready',headers=ha).status_code==200
    assert client.post(f'/api/play/{room}/ready',headers=hb).json()['status']=='running'
    assert client.get('/api/play/cash/status',headers=ha).json()['enabled'] is False
