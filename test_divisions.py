import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

def test_crowns_and_match_integrity(monkeypatch):
    with tempfile.TemporaryDirectory() as temp:
        import main, storage, empire, divisions
        monkeypatch.setattr(storage,'DB_PATH',str(Path(temp)/'test.sqlite'))
        storage.init_db();empire.init();divisions.init()
        app=TestClient(main.app)
        assert app.get('/api/divisions').status_code==200
        board=app.get('/api/divisions').json()['divisions']
        assert len(board)==9 and all(d['king'] is None for d in board)
        people=[]
        for name in ('challenger','defender','outsider'):
            assert app.post('/api/register',json={'username':name,'password':'securepass123'}).status_code==200
            tk=app.post('/api/login',json={'username':name,'password':'securepass123'}).json()['token']
            people.append({'Authorization':'Bearer '+tk})
        room=app.post('/api/divisions/challenge',json={'district':2},headers=people[0]).json()['room_id']
        assert app.get('/api/divisions').json()['divisions'][2]['king'] is None
        assert app.post('/api/divisions/challenge',json={'district':2},headers=people[2]).status_code==400
        assert app.post(f'/api/rooms/{room}/join',headers=people[1]).status_code==200
        assert app.post(f'/api/rooms/{room}/ready',headers=people[0]).status_code==200
        assert app.post(f'/api/rooms/{room}/ready',headers=people[1]).status_code==200
        assert app.get('/api/divisions').json()['divisions'][2]['king'] is None
        a=main.arenas[room]
        a.cash[0]+=999
        a.finish(now=a.started_at+180)
        main.persist_finished(a)
        main.persist_finished(a)
        d=app.get('/api/divisions').json()['divisions'][2]
        assert d['king']['username']=='challenger' and d['version']==1
        assert len(d['history'])==1
        assert d['status']=='controlled'
        profile=app.get('/api/divisions/profile/'+a.players[0]).json()
        assert 'DOWNTOWN' in profile['crowns']
        room2=app.post('/api/divisions/challenge',json={'district':2},headers=people[1]).json()['room_id']
        assert app.post(f'/api/rooms/{room2}/join',headers=people[2]).status_code==400
        assert app.post(f'/api/rooms/{room2}/join',headers=people[0]).status_code==200
        b=main.arenas[room2]
        b.set_ready(0,now=2000);b.set_ready(1,now=2000)
        b.cash[0]+=1000;b.finish(now=2180)
        main.persist_finished(b)
        d=app.get('/api/divisions').json()['divisions'][2]
        assert d['king']['username']=='defender' and d['version']==2
        assert len(d['history'])==2
        assert app.get('/divisions.html').status_code==200
        assert 'CITY POWER MAP' in app.get('/divisions.html').text
        assert "window.location.assign('/divisions.html')" in app.get('/index.html').text
