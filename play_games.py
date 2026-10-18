"""Three STREET KINGS real-time skill arenas. All competition and accounting is free/virtual.
Server computes all scores and outcomes; no client-submitted scores. Single-instance SQLite persistence.
"""
import json, math, sqlite3, time, hashlib
from uuid import uuid4
import storage

DURATION=180
GAMES={
 'crossfire':{'name':'CROSSFIRE','tagline':'Bend the angle. Break the line.','instructions':'Aim your ricochet at rotating targets. Wall banks score a multiplier. Drag to aim; release to fire. Hit streaks build heat.'},
 'lockdown':{'name':'LOCKDOWN','tagline':'Read the grid. Crack the pattern.','instructions':'Trace connected numbered tiles whose values add to the target. Longer chains and speed score higher; wrong routes burn your combo.'},
 'clash':{'name':'CLASH CIRCUIT','tagline':'Read the tell. Strike the opening.','instructions':'Three lanes telegraph attack windows. Tap the correct lane at the right instant to parry and counter. Combos multiply points; mistimed taps break rhythm.'}
}
SCHEMA='''CREATE TABLE IF NOT EXISTS play_matches(
 id TEXT PRIMARY KEY,game TEXT NOT NULL,players TEXT NOT NULL,ready TEXT NOT NULL,status TEXT NOT NULL,
 state TEXT NOT NULL,created REAL NOT NULL,started REAL,ends REAL,completed REAL,
 winner TEXT,version INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS play_events(id INTEGER PRIMARY KEY AUTOINCREMENT,room_id TEXT NOT NULL,user_id TEXT NOT NULL,move_id TEXT NOT NULL,payload TEXT NOT NULL,points INTEGER NOT NULL,created REAL NOT NULL,UNIQUE(room_id,user_id,move_id));
 CREATE TABLE IF NOT EXISTS play_history(id INTEGER PRIMARY KEY AUTOINCREMENT,room_id TEXT NOT NULL,user_id TEXT NOT NULL,game TEXT NOT NULL,result TEXT NOT NULL,score INTEGER NOT NULL,created REAL NOT NULL,UNIQUE(room_id,user_id));
 CREATE TABLE IF NOT EXISTS play_virtual_prizes(room_id TEXT NOT NULL,user_id TEXT NOT NULL,delta INTEGER NOT NULL,reason TEXT NOT NULL,PRIMARY KEY(room_id,user_id));
 CREATE TABLE IF NOT EXISTS play_cash_ledger(id INTEGER PRIMARY KEY AUTOINCREMENT,ref TEXT UNIQUE NOT NULL,user_id TEXT NOT NULL,room_id TEXT,kind TEXT NOT NULL,amount_cents INTEGER NOT NULL,currency TEXT NOT NULL DEFAULT 'USD',status TEXT NOT NULL CHECK(status IN ('pending','confirmed','void')),created REAL NOT NULL);
 CREATE INDEX IF NOT EXISTS play_match_status ON play_matches(game,status,created);
 '''

def init():
 with storage.db() as c:c.executescript(SCHEMA)

def seed_for(room_id,game):return int(hashlib.sha256((room_id+':'+game).encode()).hexdigest()[:12],16)

def preset(game,round_no,seed):
 """Same deterministic challenge for both human players; independent lane progress."""
 v=(seed+round_no*2654435761)&0xffffffff
 if game=='crossfire':
  return {'target_x':14+(v%73),'target_y':19+((v//83)%47),'bank':1+((v//197)%3),'radius':9}
 if game=='lockdown':
  vals=[1+((v//(i%7+1)+i*17+i*i*9)%7) for i in range(25)]
  # Deterministic path with a guaranteed valid solution, both competitors get the same values.
  path=[(round_no+i*5)%25 for i in range(3)]
  # Pick a connected row triplet.
  row=(v//123)%5;col=(v//543)%3;path=[row*5+col+i for i in range(3)]
  return {'tiles':vals,'target':sum(vals[k] for k in path),'size':5}
 return {'lane':v%3,'beat':round_no,'width':0.34}

def new_state(game,room_id):
 seed=seed_for(room_id,game)
 return {'seed':seed,'lanes':[{'score':0,'combo':0,'round':0,'hits':0,'misses':0,'last_action':0,'last_round':-1} for _ in range(2)]}

def get(c,rid):
 r=c.execute('SELECT * FROM play_matches WHERE id=?',(rid,)).fetchone()
 if not r:raise ValueError('Match not found')
 return r

def as_state(r,uid=None):
 players=json.loads(r['players']);st=json.loads(r['state']);now=time.time(); left=max(0,math.ceil((r['ends'] or now)-now)) if r['status']=='running' else DURATION
 return {'room_id':r['id'],'game':r['game'],'status':r['status'],'players':players,'ready':json.loads(r['ready']),'scores':[x['score'] for x in st['lanes']],'remaining':left,'duration':DURATION,'winner':r['winner'],'version':r['version'],'your_seat':players.index(uid) if uid in players else None,'lanes':[{k:v for k,v in lane.items() if k not in ('last_action',)} for lane in st['lanes']], 'challenge':[preset(r['game'],lane['round'],st['seed']) for lane in st['lanes']],'started_at':r['started'],'server_time':now,'practice':len(players)==1 and r['status'] in ('running','finished'),'cash_enabled':False,'cash_reason':'Deposits, paid entries and real prizes are disabled; approval, KYC and geolocation are not connected.'}

def create(uid,game,queue=False):
 if game not in GAMES:raise ValueError('Unknown game')
 rid=uuid4().hex[:12];now=time.time()
 with storage.db() as c:
  c.execute('BEGIN IMMEDIATE')
  if queue:
   waiting=c.execute("SELECT * FROM play_matches WHERE game=? AND status='waiting' AND json_array_length(players)=1 AND created>? ORDER BY created LIMIT 1",(game,now-1800)).fetchone()
   if waiting and uid not in json.loads(waiting['players']):
    p=json.loads(waiting['players']);p.append(uid)
    c.execute('UPDATE play_matches SET players=?,version=version+1 WHERE id=?',(json.dumps(p),waiting['id']))
    return waiting['id']
  c.execute('INSERT INTO play_matches(id,game,players,ready,status,state,created) VALUES(?,?,?,?,?,?,?)',(rid,game,json.dumps([uid]),json.dumps([False,False]),'waiting',json.dumps(new_state(game,rid)),now))
 return rid

def practice(uid,game):
 if game not in GAMES:raise ValueError('Unknown game')
 rid=uuid4().hex[:12];now=time.time()
 with storage.db() as c:
  c.execute('INSERT INTO play_matches(id,game,players,ready,status,state,created,started,ends) VALUES(?,?,?,?,?,?,?,?,?)',(rid,game,json.dumps([uid]),json.dumps([True,False]),'running',json.dumps(new_state(game,rid)),now,now,now+DURATION))
 return status(rid,uid)

def join(uid,rid):
 with storage.db() as c:
  c.execute('BEGIN IMMEDIATE');r=get(c,rid);p=json.loads(r['players'])
  if uid not in p:
   if len(p)>1 or r['status']!='waiting':raise ValueError('Match is full or already started')
   p.append(uid);c.execute('UPDATE play_matches SET players=?,version=version+1 WHERE id=?',(json.dumps(p),rid))
 return status(rid,uid)

def ready(uid,rid):
 with storage.db() as c:
  c.execute('BEGIN IMMEDIATE');r=get(c,rid);players=json.loads(r['players'])
  if uid not in players:raise ValueError('Not a participant')
  if r['status']!='waiting':return as_state(r,uid)
  flags=json.loads(r['ready']);flags[players.index(uid)]=True
  start=len(players)==2 and all(flags);now=time.time()
  c.execute('UPDATE play_matches SET ready=?,status=?,started=?,ends=?,version=version+1 WHERE id=?',(json.dumps(flags),'running' if start else 'waiting',now if start else None,now+DURATION if start else None,rid))
 return status(rid,uid)

def _crossfire(st,move,elapsed):
 """Server-side ray tracing: shot from (50,96), reflects at vertical walls; target position fixed per round."""
 angle=move.get('angle');
 if not isinstance(angle,(int,float)) or not math.isfinite(angle) or not 8<=angle<=172:raise ValueError('Invalid shot angle')
 target=preset('crossfire',st['round'],st['_seed']);rad=math.radians(angle)
 vx=math.cos(rad);vy=-math.sin(rad)
 if vy>=-0.13:raise ValueError('Shot must aim upward')
 dy=96-target['target_y'];x=50+(vx/-vy)*dy
 banks=0
 while x<0 or x>100:
  if x<0:x=-x
  else:x=200-x
  banks+=1
  if banks>16:break
 hit=abs(x-target['target_x'])<=target['radius'] and banks<=4
 return (max(0,140+banks*55+min(8,st['combo'])*24) if hit else 0), hit, {'landing':round(x,1),'banks':banks}

def _lockdown(st,move,elapsed):
 p=move.get('path');cfg=preset('lockdown',st['round'],st['_seed']);vals=cfg['tiles']
 if not isinstance(p,list) or not 2<=len(p)<=12 or not all(type(i)==int and 0<=i<25 for i in p) or len(set(p))!=len(p):raise ValueError('Invalid tile route')
 for a,b in zip(p,p[1:]):
  if abs(a//5-b//5)+abs(a%5-b%5)!=1:raise ValueError('Tiles must be orthogonally adjacent')
 ok=sum(vals[i] for i in p)==cfg['target']
 return (len(p)*45+min(8,st['combo'])*30 if ok else 0),ok,{'sum':sum(vals[i] for i in p)}

def _clash(st,move,elapsed):
 lane=move.get('lane');cfg=preset('clash',st['round'],st['_seed'])
 if type(lane)!=int or not 0<=lane<3:raise ValueError('Invalid lane')
 # Beat is a server clock: 1.6s cycle, perfect middle window.
 phase=(elapsed%1.6)/1.6
 ok=lane==cfg['lane'] and .33<=phase<=.67
 return (105+min(9,st['combo'])*32 if ok else 0),ok,{'phase':round(phase,3)}

def move(uid,rid,move_id,payload):
 if not isinstance(move_id,str) or not 8<=len(move_id)<=64:raise ValueError('Invalid action identifier')
 if not isinstance(payload,dict):raise ValueError('Invalid move')
 now=time.time()
 with storage.db() as c:
  c.execute('BEGIN IMMEDIATE');r=get(c,rid);players=json.loads(r['players'])
  if uid not in players:raise ValueError('Not a participant')
  if r['status']!='running' or now>=r['ends']:raise ValueError('Match is not active')
  old=c.execute('SELECT points FROM play_events WHERE room_id=? AND user_id=? AND move_id=?',(rid,uid,move_id)).fetchone()
  if old:return as_state(r,uid)
  st=json.loads(r['state']);seat=players.index(uid);lane=st['lanes'][seat]
  # Avoid action spamming and limit the number of guesses per round.
  if now-lane['last_action']<.22:raise ValueError('Action rate limit')
  elapsed=now-r['started'];lane['_seed']=st['seed']
  if r['game']=='crossfire':pts,ok,_=_crossfire(lane,payload,elapsed)
  elif r['game']=='lockdown':pts,ok,_=_lockdown(lane,payload,elapsed)
  else:pts,ok,_=_clash(lane,payload,elapsed)
  del lane['_seed']
  lane['last_action']=now;lane['score']+=pts;lane['hits']+=int(ok);lane['misses']+=int(not ok)
  lane['combo']=min(12,lane['combo']+1) if ok else 0
  lane['round']+=1
  c.execute('UPDATE play_matches SET state=?,version=version+1 WHERE id=?',(json.dumps(st),rid))
  c.execute('INSERT INTO play_events(room_id,user_id,move_id,payload,points,created) VALUES(?,?,?,?,?,?)',(rid,uid,move_id,json.dumps(payload),pts,now))
 return status(rid,uid)

def finish_if_due(c,r,now):
 if r['status']!='running' or now<r['ends']:return r
 c.execute('BEGIN IMMEDIATE')
 fresh=get(c,r['id'])
 if fresh['status']!='running':return fresh
 p=json.loads(fresh['players']);lanes=json.loads(fresh['state'])['lanes'];scores=[x['score'] for x in lanes]
 if len(p)==1:
  c.execute('UPDATE play_matches SET status=?,completed=?,version=version+1 WHERE id=?',('finished',now,fresh['id']))
  return get(c,fresh['id'])
 winner=None if scores[0]==scores[1] else p[0 if scores[0]>scores[1] else 1]
 c.execute('UPDATE play_matches SET status=?,completed=?,winner=?,version=version+1 WHERE id=?',('finished',now,winner,fresh['id']))
 for i,uid in enumerate(p):
  outcome='draw' if winner is None else 'win' if uid==winner else 'loss'
  result=c.execute('INSERT OR IGNORE INTO play_history(room_id,user_id,game,result,score,created) VALUES(?,?,?,?,?,?)',(fresh['id'],uid,fresh['game'],outcome,scores[i],now))
  if result.rowcount and outcome!='draw':c.execute('UPDATE users SET '+('wins=wins+1' if outcome=='win' else 'losses=losses+1')+' WHERE id=?',(uid,))
 return get(c,r['id'])

def status(rid,uid=None):
 with storage.db() as c:
  r=get(c,rid)
  if r['status']=='running' and time.time()>=r['ends']:
   r=finish_if_due(c,r,time.time())
  return as_state(r,uid)

def rules():return {'games':GAMES,'duration_seconds':DURATION,'cash_active':False,'currency':'NO REAL MONEY','example_pricing':[{'entry_per_player_cents':100,'prize_pool_cents':140,'platform_cents':60},{'entry_per_player_cents':500,'prize_pool_cents':700,'platform_cents':300}], 'pricing_status':'ILLUSTRATIVE ONLY; NOT CHARGEABLE','requirements':['Approved payment processor','Regulatory review in each jurisdiction','Age, identity and location verification','Independent anti-fraud and game fairness validation','Withdrawals, disputes and payout ledger']}


def cash_status(uid):
    """Deliberately disabled. No real-money credits are created by skill games."""
    with storage.db() as c:
        entries=[dict(x) for x in c.execute('SELECT ref,room_id,kind,amount_cents,currency,status,created FROM play_cash_ledger WHERE user_id=? ORDER BY id DESC LIMIT 40',(uid,))]
    return {'enabled':False,'deposits':False,'paid_matches':False,'withdrawals':False,'kyc_connected':False,'geolocation_connected':False,'processor_approved':False,'balance_cents':0,'entries':entries,'money_mode':'DISABLED'}
