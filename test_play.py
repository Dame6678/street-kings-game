"""Integration, server validation, and persistence tests for three playable modes."""
import os,sys,json,time,importlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def app_client(tmp_path,monkeypatch):
 import storage
 monkeypatch.setattr(storage,'DB_PATH',str(tmp_path/'game.db'))
 import empire,divisions,play_games,main
 storage.init_db();empire.init();divisions.init();play_games.init()
 # keep existing test suite isolated
 return TestClient(main.app),storage,play_games

def players(client,storage):
 u1=storage.register('alpha_test','strong_password_A');u2=storage.register('beta_test','strong_password_B')
 t1=storage.login('alpha_test','strong_password_A');t2=storage.login('beta_test','strong_password_B')
 return u1,u2,{'Authorization':'Bearer '+t1},{'Authorization':'Bearer '+t2}

@pytest.mark.parametrize('game,payload', [('crossfire',{'angle':89.0}),('lockdown',{'path':[0,1]}),('clash',{'lane':0})])
def test_live_game_auth_scores_recovery(game,payload,app_client):
 client,storage,pg=app_client;a,b,ha,hb=players(client,storage)
 lobby=client.post('/api/play/open',json={'game':game,'matchmake':False},headers=ha);assert lobby.status_code==200,lobby.text
 rid=lobby.json()['room_id'];assert client.get('/api/play/'+rid,headers=hb).status_code==200
 assert client.post('/api/play/'+rid+'/join',headers=hb).status_code==200
 assert client.post('/api/play/'+rid+'/ready',headers=ha).json()['status']=='waiting'
 assert client.post('/api/play/'+rid+'/ready',headers=hb).json()['status']=='running'
 mid='action-'+game+'-1234';result=client.post('/api/play/'+rid+'/move',json={'move_id':mid,'payload':payload},headers=ha)
 assert result.status_code==200,result.text
 assert result.json()['scores'][0]>=0
 same=client.post('/api/play/'+rid+'/move',json={'move_id':mid,'payload':payload},headers=ha)
 assert same.status_code==200
 with storage.db() as c:assert c.execute('SELECT COUNT(*) FROM play_events WHERE room_id=?',(rid,)).fetchone()[0]==1
 assert client.post('/api/play/'+rid+'/move',json={'move_id':'other-player-123','payload':{'angle':3}},headers={'Authorization':'Bearer BAD'}).status_code==401
 with storage.db() as c:c.execute('UPDATE play_matches SET ends=? WHERE id=?',(time.time()-3,rid))
 done=client.get('/api/play/'+rid,headers=ha).json();assert done['status']=='finished'
 assert client.get('/api/play/'+rid,headers=ha).json()['status']=='finished'
 with storage.db() as c:assert c.execute('SELECT COUNT(*) FROM play_history WHERE room_id=?',(rid,)).fetchone()[0]==2


def test_matchmaking_two_real_players_and_no_phantom(app_client):
 client,storage,pg=app_client;a,b,ha,hb=players(client,storage)
 first=client.post('/api/play/open',json={'game':'clash','matchmake':True},headers=ha).json()
 assert first['players']==[a]
 second=client.post('/api/play/open',json={'game':'clash','matchmake':True},headers=hb).json()
 assert first['room_id']==second['room_id']
 assert second['players']==[a,b]
 assert client.post('/api/play/'+first['room_id']+'/join',headers=ha).status_code==200


def test_practice_and_cash_lock(app_client):
 client,storage,pg=app_client;a,b,ha,hb=players(client,storage)
 r=client.post('/api/play/practice/lockdown',headers=ha);assert r.status_code==200,r.text
 rid=r.json()['room_id'];assert r.json()['practice'] and r.json()['status']=='running'
 assert not client.get('/api/play/games').json()['cash_active']
 assert client.post('/api/play/'+rid+'/join',headers=hb).status_code==400
 with storage.db() as c:c.execute('UPDATE play_matches SET ends=? WHERE id=?',(time.time()-2,rid))
 assert client.get('/api/play/'+rid,headers=ha).json()['status']=='finished'
 with storage.db() as c:assert c.execute('SELECT count(*) FROM play_history').fetchone()[0]==0


def test_validation_and_idempotence(app_client):
 client,storage,pg=app_client;a,b,ha,hb=players(client,storage)
 rid=pg.create(a,'lockdown');pg.join(b,rid);pg.ready(a,rid);pg.ready(b,rid)
 impossible=client.post('/api/play/'+rid+'/move',headers=ha,json={'move_id':'invalid-path-00001','payload':{'path':[0,14]}})
 assert impossible.status_code==400
 assert pg.status(rid,a)['scores']==[0,0]
 assert client.post('/api/play/open',json={'game':'not-real'},headers=ha).status_code==400


def test_premium_play_page_and_home_link(app_client):
 client,*_=app_client
 r=client.get('/play.html');assert r.status_code==200
 assert 'PLAY FOR REAL MONEY.' in r.text and 'CROSSFIRE' in r.text
 assert "page==='play'" in client.get('/index.html').text


def test_exact_hit_and_cash_separation(app_client):
 client,storage,pg=app_client;a,b,ha,hb=players(client,storage)
 rid=pg.practice(a,'crossfire')['room_id'];st=pg.status(rid,a)
 cfg=st['challenge'][0];import math
 angle=math.degrees(math.atan2(96-cfg['target_y'],cfg['target_x']-50))
 shot=client.post('/api/play/'+rid+'/move',headers=ha,json={'move_id':'aimed-shot-123456','payload':{'angle':angle}})
 assert shot.status_code==200,shot.text
 assert shot.json()['scores'][0]>0,'A mathematically aimed shot should hit the target'
 cash=client.get('/api/play/cash/status',headers=ha)
 assert cash.status_code==200 and cash.json()['enabled'] is False
 assert cash.json()['balance_cents']==0 and cash.json()['entries']==[]


def test_guaranteed_tile_route_and_timing_math(app_client):
 client,storage,pg=app_client;a,b,ha,hb=players(client,storage)
 rid=pg.practice(a,'lockdown')['room_id'];cfg=pg.status(rid,a)['challenge'][0]
 found=None
 for row in range(5):
  for col in range(3):
   route=[row*5+col+i for i in range(3)]
   if sum(cfg['tiles'][i] for i in route)==cfg['target']:found=route;break
  if found:break
 assert found
 result=client.post('/api/play/'+rid+'/move',headers=ha,json={'move_id':'solved-grid-1234','payload':{'path':found}})
 assert result.status_code==200 and result.json()['scores'][0]>0
 st={'round':0,'combo':0,'_seed':1234}
 c=pg.preset('clash',0,1234)
 good,hit,_=pg._clash(st,{'lane':c['lane']},elapsed=.8)
 bad,miss,_=pg._clash(st,{'lane':c['lane']},elapsed=.05)
 assert hit and good>0 and not miss and bad==0
