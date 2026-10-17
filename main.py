"""STREET KINGS v0.2; simulated credits ONLY. Single-instance architecture."""
import asyncio, os, time
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
storage.init_db()
legacy_games={}; arenas={}; spectators={}; locks={}; saved={}
for _arena in storage.load_matches():
    arenas[_arena.room_id]=_arena
    locks[_arena.room_id]=asyncio.Lock()
    if _arena.status=='finished':saved[_arena.room_id]=True
DURATION=int(os.environ.get('STREET_KINGS_MATCH_SECONDS','180'))

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

@app.post('/api/register')
def register(d:Credentials):
    try:return {'user_id':storage.register(d.username,d.password)}
    except ValueError as e:raise HTTPException(400,str(e))
@app.post('/api/login')
def login(d:Credentials):
    try:return {'token':storage.login(d.username,d.password)}
    except ValueError as e:raise HTTPException(401,str(e))
@app.get('/api/me')
def me(authorization:str|None=Header(None)):
    return storage.profile(auth(authorization))
@app.get('/api/leaderboard')
def leaderboard():return storage.ranking()
@app.get('/api/ledger')
def ledger(authorization:str|None=Header(None)):
    return storage.ledger(auth(authorization))
@app.get('/api/history')
def history(authorization:str|None=Header(None)):
    uid=auth(authorization)
    with storage.db() as c:return [dict(x) for x in c.execute('SELECT room_id,outcome,score,created FROM history WHERE user_id=? ORDER BY created DESC LIMIT 50',(uid,))]

# v0.1 compatibility: legacy practice remains available
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

app.mount('/',StaticFiles(directory=str(Path(__file__).parent/'static'),html=True),name='static')
