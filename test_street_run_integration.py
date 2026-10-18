from realtime import Arena,snapshot_arena,restore_arena
from street_run import EDGES
from fastapi.testclient import TestClient
from main import app

def test_two_players_route_scoring_and_finish():
    a=Arena(duration=180)
    a.join('p1');a.join('p2');a.set_ready(0,now=100);a.set_ready(1,now=100)
    assert a.state(now=100)['street_run']['positions']==[4,4]
    a.action(0,3,'drive',now=101)
    a.action(0,2,'drive',now=102)
    a.action(0,2,'pickup',now=103)
    assert a.street_run.packages[0]
    a.action(1,3,'drive',now=101)
    a.action(1,2,'drive',now=102)
    a.action(1,2,'intercept',now=104)
    assert not a.street_run.packages[0]
    assert a.street_run.run_points[1]>0
    clone=restore_arena(snapshot_arena(a))
    assert clone.street_run.snapshot()==a.street_run.snapshot()
    assert clone.score(1)==a.score(1)
    a.advance(281)
    assert a.status=='finished' and a.winner in (0,1,None)
    try:a.action(0,1,'drive',now=282)
    except ValueError:pass
    else:assert False,'accepted move after expiration'

def test_frontend_and_auth_endpoint():
    with TestClient(app) as c:
        page=c.get('/street-kings-live.html?mode=play')
        assert page.status_code==200 and 'canvas id="world"' in page.text
        assert c.get('/').status_code==200
        assert c.post('/api/rooms',json={}).status_code==401
