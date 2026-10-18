"""MY EMPIRE functionality, account isolation, transactions and persistence."""
import pytest
import storage, empire
from fastapi.testclient import TestClient

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DB_PATH',str(tmp_path/'players.db'))
    storage.init_db()
    empire.init()
    from main import app
    client=TestClient(app)
    creds1={'username':'empirealpha','password':'secretpass123'}
    creds2={'username':'empirebeta','password':'secretpass456'}
    for credentials in (creds1,creds2):
        assert client.post('/api/register',json=credentials).status_code==200
    tokens=[client.post('/api/login',json=c).json()['token'] for c in (creds1,creds2)]
    return client,[{'Authorization':'Bearer '+t} for t in tokens]

def test_starting_empires_isolated(setup):
    c,h=setup
    a=c.get('/api/empire/headquarters',headers=h[0]).json()
    b=c.get('/api/empire/headquarters',headers=h[1]).json()
    assert a['cash']==400 and b['cash']==400 and a['diamonds']==0
    assert a['properties']==[] and len(a['influence'])==9
    acquired=c.post('/api/empire/action',headers=h[0],json={'district':7,'operation':'acquire'})
    assert acquired.status_code==200
    assert len(acquired.json()['properties'])==1
    assert c.get('/api/empire/headquarters',headers=h[1]).json()['properties']==[]
    assert c.get('/api/empire/headquarters').status_code==401

def test_upgrades_fortify_collect_and_reload(setup,monkeypatch):
    c,h=setup
    assert c.post('/api/empire/action',headers=h[0],json={'district':7,'operation':'acquire'}).status_code==200
    assert c.post('/api/empire/action',headers=h[0],json={'district':7,'operation':'upgrade'}).status_code==200
    defended=c.post('/api/empire/action',headers=h[0],json={'district':7,'operation':'defend'})
    assert defended.status_code==200
    assert defended.json()['properties'][0]['defense']==1
    import time
    now=time.time()
    with storage.db() as db:db.execute('UPDATE empires SET last_accrual=? WHERE user_id=?',(now-180,defended.json()['player_id']))
    accrued=c.get('/api/empire/headquarters',headers=h[0]).json()
    assert accrued['pending_income']>=30
    collected=c.post('/api/empire/action',headers=h[0],json={'district':0,'operation':'collect'}).json()
    assert collected['pending_income']==0
    assert collected['cash']>=accrued['cash']+30
    assert c.get('/api/empire/headquarters',headers=h[0]).json()['properties'][0]['level']==2
    assert c.post('/api/empire/action',headers=h[1],json={'district':7,'operation':'upgrade'}).status_code==400
    assert c.post('/api/empire/action',headers=h[0],json={'district':22,'operation':'acquire'}).status_code==400
    assert c.post('/api/empire/action',headers=h[0],json={'district':7,'operation':'collect'}).status_code==400

def test_frontend_route(setup):
    c,h=setup
    page=c.get('/my-empire.html')
    assert page.status_code==200
    assert 'MY BUSINESSES' in page.text and '/api/empire/headquarters' in page.text
    homepage=c.get('/').text
    assert "'/my-empire.html'" in homepage
