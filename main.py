"""STREET KINGS v0.2; simulated credits ONLY. Single-instance architecture."""
import asyncio, os, time, logging, sqlite3
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Header
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from engine import Match,settle
from realtime import Arena
from ai_opponent import advance_ai
import storage, tournament, empire, divisions, play_games
empire.init()

app=FastAPI(title='STREET KINGS v0.2 — simulated credits only')
log=logging.getLogger('street_kings.auth')
storage.init_db()
divisions.init()
play_games.init()
legacy_games={}; arenas={}; spectators={}; locks={}; saved={}
for _arena in storage.load_matches():
    arenas[_arena.room_id]=_arena
    locks[_arena.room_id]=asyncio.Lock()
    if _arena.status=='finished':saved[_arena.room_id]=True
DURATION=max(15,min(600,int(os.environ.get('STREET_KINGS_MATCH_SECONDS','180'))))

def auth(authorization):
    uid=storage.authenticate((authorization or '').removeprefix('Bearer ').strip())
    if not uid:raise HTTPException(401,'Please log in')
    return uid

class Credentials(BaseModel):
    username:str
    password:str
class CreateRoom(BaseModel):
    duration:int|None=None
class Move(BaseModel):
    game_id:str
    block:int
    move:str
    kind:int=0
class HumanMove(BaseModel):
    block:int
    move:str
    kind:int=0
class TournamentConfig(BaseModel):
    capacity:int=5
    fee_cents:int=500

@app.get('/api/health/auth')
def auth_health():
    """Non-sensitive checks for registration/login infrastructure; no user enumeration."""
    try:
        with storage.db() as c:
            c.execute('SELECT 1 FROM users LIMIT 1').fetchone()
            c.execute('SELECT 1 FROM sessions LIMIT 1').fetchone()
        return {'status':'ok','database':'available','auth_routes':'available',
                'persistent_storage_configured':bool(os.environ.get('STREET_KINGS_DB')),
                'note':'A configured database path is not proof that the volume is persistent.'}
    except (sqlite3.Error,OSError) as exc:
        log.exception('Auth database health check failed')
        raise HTTPException(503,'Authentication database unavailable') from exc

@app.get('/api/auth/check')
def auth_check(authorization:str|None=Header(None)):
    """Validate the current session without returning tokens or private data."""
    uid=auth(authorization)
    return {'authenticated':True,'profile':storage.profile(uid)}

@app.post('/api/test-login')
def test_login():
    """Create a uniquely scoped test player on demand (never a shared password)."""
    if os.environ.get('STREET_KINGS_TEST_LOGIN', 'false').lower() not in ('1','true','yes'):
        raise HTTPException(403,'Test login is disabled on this service')
    username='tester_'+uuid4().hex[:12]
    temporary_password=uuid4().hex + uuid4().hex
    try:
        storage.register(username,temporary_password)
        token=storage.login(username,temporary_password)
    except (sqlite3.Error,OSError) as exc:
        log.exception('Test login database failure')
        raise HTTPException(503,'Test account could not be created') from exc
    return {'token':token,'username':username,'type':'temporary_test_account'}

@app.post('/api/admin-preview')
def admin_preview():
    """One-click demo account. No administrative access, no shared password.
    Each preview gets a distinct ordinary player account and standard session.
    """
    username='preview_'+uuid4().hex[:12]
    password=uuid4().hex+uuid4().hex
    try:
        storage.register(username,password)
        token=storage.login(username,password)
    except (sqlite3.Error,OSError,ValueError) as exc:
        log.exception('Preview login failed')
        raise HTTPException(503,'Preview account unavailable') from exc
    return {'token':token,'username':username,'preview':True}

@app.post('/api/register')
def register(d:Credentials):
    try:return {'user_id':storage.register(d.username,d.password)}
    except ValueError as e:
        log.info('Registration rejected: %s',str(e))
        raise HTTPException(400,str(e))
    except (sqlite3.Error,OSError) as exc:
        log.exception('Registration database failure')
        raise HTTPException(503,'Account storage unavailable; retry shortly') from exc
@app.post('/api/login')
def login(d:Credentials):
    try:return {'token':storage.login(d.username,d.password)}
    except ValueError:
        log.info('Login rejected: invalid username or password')
        raise HTTPException(401,'Invalid username or password. If your account was created before a Render redeploy, try REGISTER with the same username.')
    except (sqlite3.Error,OSError) as exc:
        log.exception('Login database failure')
        raise HTTPException(503,'Account storage unavailable; retry shortly') from exc
@app.get('/api/me')
def me(authorization:str|None=Header(None)):
    return storage.profile(auth(authorization))
class EmpireAction(BaseModel):
    district:int
    operation:str

@app.get('/api/empire')
def empire_state(authorization:str|None=Header(None)):
    return empire.snapshot(auth(authorization))

@app.post('/api/empire/action')
def empire_action(d:EmpireAction,authorization:str|None=Header(None)):
    try:return empire.action(auth(authorization),d.district,d.operation)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/empire/headquarters')
def empire_headquarters(authorization:str|None=Header(None)):
    return empire.snapshot(auth(authorization))

class DivisionChallenge(BaseModel):
    district:int

@app.get('/api/divisions')
def divisions_board():
    return divisions.board()

@app.get('/api/divisions/profile/{uid}')
def division_public_profile(uid:str):
    result=divisions.public_profile(uid)
    if result is None:raise HTTPException(404,'Player not found')
    return result

@app.post('/api/divisions/challenge')
def division_challenge(d:DivisionChallenge,authorization:str|None=Header(None)):
    uid=auth(authorization)
    a=Arena(duration=DURATION)
    # Registered-human competition; no AI accounts and no fabricated outcome.
    try:
        outcome=divisions.open_challenge(uid,d.district,a.room_id)
        a.join(uid)
        arenas[a.room_id]=a;locks[a.room_id]=asyncio.Lock();storage.save_match(a)
        return {**outcome,'seat':0,'duration':DURATION}
    except ValueError as exc:raise HTTPException(400,str(exc))

class PlayOpen(BaseModel):
    game:str
    matchmake:bool=False
class PlayAction(BaseModel):
    move_id:str
    payload:dict

@app.get('/api/play/games')
def play_games_list():
    return play_games.rules()

@app.post('/api/play/open')
def play_open(d:PlayOpen, authorization:str|None=Header(None)):
    uid=auth(authorization)
    try:
        rid=play_games.create(uid,d.game,queue=d.matchmake)
        return play_games.status(rid,uid)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/play/practice/{game}')
def play_practice(game:str,authorization:str|None=Header(None)):
    try:return play_games.practice(auth(authorization),game)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/play/{rid}/join')
def play_join(rid:str,authorization:str|None=Header(None)):
    try:return play_games.join(auth(authorization),rid)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/play/{rid}/ready')
def play_ready(rid:str,authorization:str|None=Header(None)):
    try:return play_games.ready(auth(authorization),rid)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/play/{rid}/move')
def play_move(rid:str,d:PlayAction,authorization:str|None=Header(None)):
    try:return play_games.move(auth(authorization),rid,d.move_id,d.payload)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/play/{rid}')
def play_state(rid:str,authorization:str|None=Header(None)):
    try:return play_games.status(rid,auth(authorization))
    except ValueError as exc:raise HTTPException(404,str(exc))

@app.get('/api/play/cash/status')
def play_cash_status(authorization:str|None=Header(None)):
    return play_games.cash_status(auth(authorization))

@app.get('/api/play/results/me')
def play_results(authorization:str|None=Header(None)):
    uid=auth(authorization)
    with storage.db() as c:
        return [dict(x) for x in c.execute('SELECT room_id,game,result,score,created FROM play_history WHERE user_id=? ORDER BY id DESC LIMIT 30',(uid,))]

@app.get('/api/leaderboard')
def leaderboard():return storage.ranking()
@app.get('/api/ledger')
def ledger(authorization:str|None=Header(None)):
    return storage.ledger(auth(authorization))
@app.get('/api/history')
def history(authorization:str|None=Header(None)):
    uid=auth(authorization)
    with storage.db() as c:return [dict(x) for x in c.execute('SELECT room_id,outcome,score,created FROM history WHERE user_id=? ORDER BY created DESC LIMIT 50',(uid,))]

# v0.1 compatibility: deprecated turn practice retained for existing API consumers; PLAY uses the realtime arena.
@app.post('/api/new')
def new():
    i=uuid4().hex;legacy_games[i]=Match();return {'game_id':i,'state':legacy_games[i].state()}
@app.post('/api/move')
def old_move(m:Move):
    g=legacy_games.get(m.game_id)
    if not g:raise HTTPException(404,'Game not found')
    try:
        state=g.action(0,m.block,m.move,m.kind)
        if not state['finished']:state=g.bot_move()
        return state
    except ValueError as e:raise HTTPException(400,str(e))
@app.get('/api/game/{game_id}')
def old_get(game_id:str):
    if game_id not in legacy_games:raise HTTPException(404,'Game not found')
    return legacy_games[game_id].state()

@app.post('/api/ai/start')
def start_ai(authorization:str|None=Header(None)):
    uid=auth(authorization)
    a=Arena(duration=DURATION)
    a.join(uid)
    a.join('AI_OPPONENT')
    a.set_ready(0)
    a.set_ready(1)
    arenas[a.room_id]=a
    locks[a.room_id]=asyncio.Lock()
    storage.save_match(a)
    return {'room_id':a.room_id,'seat':0,'state':a.state(),'opponent':'AI'}

@app.post('/api/rooms')
def create_room(d:CreateRoom,authorization:str|None=Header(None)):
    uid=auth(authorization);duration=DURATION if d.duration is None else d.duration
    if duration<15 or duration>600:raise HTTPException(400,'Duration 15-600 seconds')
    a=Arena(duration=duration);a.join(uid);arenas[a.room_id]=a;locks[a.room_id]=asyncio.Lock();storage.save_match(a)
    return {'room_id':a.room_id,'seat':0,'state':a.state()}
@app.post('/api/rooms/{rid}/join')
async def join_room(rid:str,authorization:str|None=Header(None)):
    uid=auth(authorization);a=room(rid)
    async with locks[rid]:
        try:
            if uid not in a.players: divisions.authorize_join(uid,rid)
            seat=a.join(uid)
        except ValueError as e:raise HTTPException(400,str(e))
        storage.save_match(a)
    await broadcast(rid)
    return {'seat':seat,'state':a.state()}
@app.post('/api/rooms/{rid}/ready')
async def ready(rid:str,authorization:str|None=Header(None)):
    uid=auth(authorization);a=room(rid)
    async with locks[rid]:
        try:a.set_ready(seat_for(a,uid))
        except ValueError as e:raise HTTPException(400,str(e))
        storage.save_match(a)
    await broadcast(rid)
    return a.state()
@app.post('/api/rooms/{rid}/action')
async def action(rid:str,d:HumanMove,authorization:str|None=Header(None)):
    uid=auth(authorization);a=room(rid)
    async with locks[rid]:
        try:a.action(seat_for(a,uid),d.block,d.move,d.kind)
        except ValueError as e:raise HTTPException(400,str(e))
        storage.save_match(a)
    await broadcast(rid)
    return a.state()
@app.get('/api/rooms/{rid}')
def room_state(rid:str):return room(rid).state()
@app.post('/api/rooms/{rid}/refresh')
async def refresh(rid:str):
    a=room(rid)
    async with locks[rid]:
        a.advance()
        if 'AI_OPPONENT' in a.players: advance_ai(a)
        if a.status=='finished' and rid not in saved:
            persist_finished(a);saved[rid]=True
        storage.save_match(a)
    await broadcast(rid)
    return a.state()

def room_for_fixture(uid_a,uid_b):
    a=Arena(duration=DURATION)
    a.join(uid_a);a.join(uid_b)
    arenas[a.room_id]=a;locks[a.room_id]=asyncio.Lock()
    storage.save_match(a)
    return a.room_id

def persist_finished(a):
    if 'AI_OPPONENT' in a.players: return
    storage.store_result(a)
    divisions.settle(a)
    for tid in fixture_tournaments(a.room_id):
        tournament.record_fixture(tid,a)

def fixture_tournaments(rid):
    import json
    with storage.db() as c:
        for row in c.execute("SELECT id,data FROM tournaments WHERE status='active'"):
            if any(f['room_id']==rid for f in json.loads(row['data']).get('fixtures',[])):
                yield row['id']

def room(rid):
    a=arenas.get(rid)
    if not a:raise HTTPException(404,'Room unavailable')
    return a
def seat_for(a,uid):
    if uid not in a.players:raise ValueError('Not a room participant')
    return a.players.index(uid)
async def broadcast(rid):
    if rid not in arenas:return
    s=arenas[rid].state()
    for ws in list(spectators.get(rid,())):
        try:await ws.send_json(s)
        except Exception:spectators[rid].discard(ws)
@app.websocket('/ws/rooms/{rid}')
async def ws_room(ws:WebSocket,rid:str):
    # read-only socket; all mutations through authenticated HTTP actions
    if rid not in arenas:
        await ws.close(code=1008);return
    await ws.accept();spectators.setdefault(rid,set()).add(ws)
    try:
        await ws.send_json(arenas[rid].state())
        while True:
            try:await asyncio.wait_for(ws.receive_text(),timeout=1)
            except asyncio.TimeoutError:
                async with locks[rid]:
                    a=arenas[rid];before=a.revision;a.advance()
                    if 'AI_OPPONENT' in a.players: advance_ai(a)
                    if a.status=='finished' and rid not in saved:
                        persist_finished(a);saved[rid]=True
                    if a.revision!=before:storage.save_match(a)
                await broadcast(rid)
    except WebSocketDisconnect:pass
    finally:spectators.get(rid,set()).discard(ws)

@app.get('/api/tournaments')
def tournaments():
    return [{'players':n,'entry_credits':fee,'settlement':settle([fee*100]*n,splits=['0.5','0.25','0.15','0.07','0.03'] if n>=5 else None)} for n,fee in [(2,5),(5,2),(10,5),(20,5),(50,10),(100,10)]]
@app.post('/api/tournaments/create')
def create_tour(d:TournamentConfig,authorization:str|None=Header(None)):
    auth(authorization)
    try:return tournament.info(tournament.create(d.capacity,d.fee_cents))
    except ValueError as e:raise HTTPException(400,str(e))
@app.post('/api/tournaments/{tid}/join')
def join_tour(tid:str,authorization:str|None=Header(None)):
    uid=auth(authorization)
    try:
        result=tournament.join(tid,uid)
        if result['status']=='active' and not result.get('fixtures'):
            tournament.assign_rooms(tid,room_for_fixture)
            result=tournament.info(tid)
        return result
    except ValueError as e:raise HTTPException(400,str(e))
@app.get('/api/tournaments/{tid}')
def tour(tid:str):
    try:return tournament.info(tid)
    except ValueError as e:raise HTTPException(404,str(e))

@app.middleware('http')
async def avoid_stale_game_ui(request, call_next):
    response=await call_next(request)
    if request.url.path in ('/','/index.html','/cover.jpg','/street-kings-live.html','/street-kings-live.js','/street-kings-launch.js','/street-kings-live.css','/play.html'):
        response.headers['Cache-Control']='no-store, max-age=0'
    return response

app.mount('/',StaticFiles(directory=str(Path(__file__).parent/'static'),html=True),name='static')
