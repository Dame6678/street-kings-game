import os, tempfile, importlib
from fastapi.testclient import TestClient

def test_empire_persistence_and_match_separation(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        monkeypatch.setenv('STREET_KINGS_DB',t+'/test.sqlite3')
        import storage, empire, main
        importlib.reload(storage);importlib.reload(empire);importlib.reload(main)
        with TestClient(main.app) as client:
            token=client.post('/api/test-login').json()['token'];h={'Authorization':'Bearer '+token}
            first=client.get('/api/empire',headers=h);assert first.status_code==200
            assert first.json()['cash']==400
            buy=client.post('/api/empire/action',headers=h,json={'district':7,'operation':'acquire'});assert buy.status_code==200
            assert buy.json()['cash']==330
            assert buy.json()['properties'][0]['district']==7
            upgrade=client.post('/api/empire/action',headers=h,json={'district':7,'operation':'upgrade'});assert upgrade.status_code==200
            assert upgrade.json()['properties'][0]['level']==2
            assert client.post('/api/empire/action',headers=h,json={'district':7,'operation':'acquire'}).status_code==400
            assert client.post('/api/empire/action',headers=h,json={'district':99,'operation':'acquire'}).status_code==400
            match=client.post('/api/ai/start',headers=h);assert match.status_code==200
            again=client.get('/api/empire',headers=h).json();assert again['properties'][0]['level']==2
            importlib.reload(empire);assert empire.snapshot(again['player_id'])['properties'][0]['level']==2
