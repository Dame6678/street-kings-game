import os,sys,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
import storage

def test_two_browser_clients_websocket_and_auth():
    from main import app
    with TestClient(app) as client:
        p1='phase2_a_'+os.urandom(3).hex();p2='phase2_b_'+os.urandom(3).hex()
        for name in (p1,p2):
            r=client.post('/api/register',json={'username':name,'password':'super-secure-pass'})
            assert r.status_code==200,r.text
        t1=client.post('/api/login',json={'username':p1,'password':'super-secure-pass'}).json()['token']
        t2=client.post('/api/login',json={'username':p2,'password':'super-secure-pass'}).json()['token']
        h1={'Authorization':'Bearer '+t1};h2={'Authorization':'Bearer '+t2}
        r=client.post('/api/rooms',json={'duration':15},headers=h1);assert r.status_code==200,r.text
        rid=r.json()['room_id']
        assert client.post('/api/rooms/'+rid+'/join',headers=h2).json()['seat']==1
        with client.websocket_connect('/ws/rooms/'+rid) as ws:
            s=ws.receive_json();assert len(s['players'])==2
            assert client.post('/api/rooms/'+rid+'/ready',headers=h1).status_code==200
            assert client.post('/api/rooms/'+rid+'/ready',headers=h2).status_code==200
            assert client.post('/api/rooms/'+rid+'/action',headers=h1,json={'block':0,'move':'claim'}).status_code==200
            assert client.post('/api/rooms/'+rid+'/action',headers=h2,json={'block':1,'move':'claim'}).status_code==200
            s=client.get('/api/rooms/'+rid).json();assert s['blocks'][0]['owner']==0 and s['blocks'][1]['owner']==1
            assert client.post('/api/rooms/'+rid+'/action',headers=h2,json={'block':0,'move':'claim'}).status_code==400
            assert client.post('/api/rooms/'+rid+'/action',json={'block':2,'move':'claim'}).status_code==401
            assert client.get('/api/leaderboard').status_code==200
        assert client.get('/api/me',headers=h1).json()['username']==p1

def test_real_match_finishes_persists_and_tournament_api():
    import main
    from main import app
    with TestClient(app) as client:
        users=[];headers=[]
        for _ in range(2):
            name='fixture_'+os.urandom(4).hex()
            client.post('/api/register',json={'username':name,'password':'strong-pass-123'})
            t=client.post('/api/login',json={'username':name,'password':'strong-pass-123'}).json()['token']
            headers.append({'Authorization':'Bearer '+t})
        tid=client.post('/api/tournaments/create',headers=headers[0],json={'capacity':2,'fee_cents':500}).json()['id']
        client.post('/api/tournaments/'+tid+'/join',headers=headers[0]);t=client.post('/api/tournaments/'+tid+'/join',headers=headers[1]).json()
        assert len(t['fixtures'])==1
        rid=t['fixtures'][0]['room_id']
        for h in headers:assert client.post('/api/rooms/'+rid+'/ready',headers=h).status_code==200
        assert client.post('/api/rooms/'+rid+'/action',headers=headers[0],json={'block':0,'move':'claim'}).status_code==200
        a=main.arenas[rid]
        a.started_at-=200;a.last_income_at-=200
        result=client.post('/api/rooms/'+rid+'/refresh')
        assert result.status_code==200,result.text
        assert result.json()['status']=='finished'
        t=client.get('/api/tournaments/'+tid).json()
        assert t['status']=='finished' and t['platform_cents']==300
        assert sum(t['payouts'].values())==700
        for h in headers:
            assert len(client.get('/api/history',headers=h).json())>=1
            assert len(client.get('/api/ledger',headers=h).json())>=1
