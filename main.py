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
import storage, tournament

app=FastAPI(title='STREET KINGS v0.2 — simulated credits only')
log=logging.getLogger('street_kings.auth')
storage.init_db()
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
    if os.environ.get('STREET_KINGS_TEST_LOGIN', 'true').lower() not in ('1','true','yes'):
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
    return empire_snapshot(auth(authorization))

@app.post('/api/empire/action')
def empire_action(d:EmpireAction,authorization:str|None=Header(None)):
    try:return empire_action_execute(auth(authorization),d.district,d.operation)
    except ValueError as exc:raise HTTPException(400,str(exc))

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
        try:seat=a.join(uid)
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
    if request.url.path in ('/','/index.html','/cover.jpg'):
        response.headers['Cache-Control']='no-store, max-age=0'
    return response

app.mount('/',StaticFiles(directory=str(Path(__file__).parent/'static'),html=True),name='static')


# --- Integrated Phase 2 persistent empire (previously empire.py) ---
"""Persistent, account-scoped empire economy; independent of competitive match cash."""
import json
import storage
EMPIRE_DISTRICTS=['CROWN PLAZA','GOLD BLOCK','DOWNTOWN','SNEAKER ROW','MIDTOWN','STUDIO DISTRICT','UPTOWN','MARKET STREET','THE HEIGHTS']
EMPIRE_PROPERTY_TYPES=['Waterfront Hotel','Cookman Restaurant','Downtown Storefront','Sneaker Boutique','Main Street Garage','Recording Studio','Victorian Residence','Springwood Market','Prestige Townhouse']
EMPIRE_BASE_COST=[180,125,100,90,80,135,95,70,155]
EMPIRE_RATE=[9,7,6,6,5,8,5,5,8]
EMPIRE_MAX_LEVEL=6
EMPIRE_MISSION_TARGET=3

def empire_init():
    with storage.db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS empires(user_id TEXT PRIMARY KEY,cash INTEGER NOT NULL DEFAULT 400,reputation INTEGER NOT NULL DEFAULT 0,last_accrual REAL NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS empire_properties(user_id TEXT NOT NULL,district INTEGER NOT NULL,level INTEGER NOT NULL DEFAULT 1,acquired REAL NOT NULL,PRIMARY KEY(user_id,district));
        CREATE TABLE IF NOT EXISTS empire_events(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,event TEXT NOT NULL,district INTEGER,detail TEXT NOT NULL,created REAL NOT NULL);''')

def empire_ensure(c,uid,now):
    c.execute('INSERT OR IGNORE INTO empires(user_id,last_accrual,created) VALUES(?,?,?)',(uid,now,now))

def empire_accrue(c,uid,now):
    e=c.execute('SELECT * FROM empires WHERE user_id=?',(uid,)).fetchone()
    # Whole-minute server-side accrual, capped at 12h per request to limit unattended farming.
    elapsed=max(0,min(720,int((now-e['last_accrual'])//60)))
    if elapsed:
        props=c.execute('SELECT district,level FROM empire_properties WHERE user_id=?',(uid,)).fetchall()
        earned=elapsed*sum(EMPIRE_RATE[p['district']]*p['level'] for p in props)
        c.execute('UPDATE empires SET cash=cash+?,last_accrual=last_accrual+? WHERE user_id=?',(earned,elapsed*60,uid))
    return elapsed

def empire_snapshot(uid):
    now=time.time()
    with storage.db() as c:
        c.execute('BEGIN IMMEDIATE');empire_ensure(c,uid,now);empire_accrue(c,uid,now)
        e=dict(c.execute('SELECT cash,reputation,last_accrual FROM empires WHERE user_id=?',(uid,)).fetchone())
        props=[dict(x) for x in c.execute('SELECT district,level,acquired FROM empire_properties WHERE user_id=? ORDER BY district',(uid,))]
        events=[dict(x) for x in c.execute('SELECT id,event,district,detail,created FROM empire_events WHERE user_id=? ORDER BY id DESC LIMIT 20',(uid,))]
    count=len(props);levels=sum(p['level'] for p in props)
    return {'player_id':uid,'cash':e['cash'],'reputation':e['reputation'],'income_per_minute':sum(EMPIRE_RATE[p['district']]*p['level'] for p in props),'properties':props,'events':events,'districts':EMPIRE_DISTRICTS,'property_types':EMPIRE_PROPERTY_TYPES,'base_costs':EMPIRE_BASE_COST,'mission':{'id':'first_three','title':'Own three properties','progress':min(count,3),'target':3,'completed':count>=3},'achievements':([{'id':'first_property','title':'First Deed'}] if count else [])+([{'id':'three_districts','title':'City Investor'}] if count>=3 else [])+([{'id':'nine_districts','title':'Citywide King'}] if count==9 else []),'total_levels':levels}

def empire_action_execute(uid,district,operation):
    if type(district) is not int or not 0<=district<9:raise ValueError('Invalid district')
    if operation not in ('acquire','upgrade'):raise ValueError('Invalid empire action')
    now=time.time()
    with storage.db() as c:
        c.execute('BEGIN IMMEDIATE');empire_ensure(c,uid,now);empire_accrue(c,uid,now)
        p=c.execute('SELECT level FROM empire_properties WHERE user_id=? AND district=?',(uid,district)).fetchone()
        if operation=='acquire':
            if p:raise ValueError('Property already owned')
            price=EMPIRE_BASE_COST[district];level=1
        else:
            if not p:raise ValueError('Acquire this property first')
            if p['level']>=EMPIRE_MAX_LEVEL:raise ValueError('Maximum property level reached')
            price=EMPIRE_BASE_COST[district]*(p['level']+1);level=p['level']+1
        updated=c.execute('UPDATE empires SET cash=cash-?,reputation=reputation+? WHERE user_id=? AND cash>=?',(price,5 if operation=='acquire' else 2,uid,price))
        if updated.rowcount!=1:raise ValueError('Not enough empire cash')
        if operation=='acquire':c.execute('INSERT INTO empire_properties(user_id,district,level,acquired) VALUES(?,?,?,?)',(uid,district,level,now))
        else:c.execute('UPDATE empire_properties SET level=? WHERE user_id=? AND district=?',(level,uid,district))
        c.execute('INSERT INTO empire_events(user_id,event,district,detail,created) VALUES(?,?,?,?,?)',(uid,operation,district,json.dumps({'level':level,'cost':price}),now))
    return empire_snapshot(uid)

# Initialize empire tables after the main storage schema is initialized.
empire_init()
