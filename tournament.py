"""Persisted simulated-credit tournaments. Each entrant runs one synchronized-seed score heat.
Heats are not knockout brackets; participants are ranked on identical challenge parameters.
"""
import json,time,secrets
from storage import db,move_credit
from engine import settle
SPLITS=['0.5','0.25','0.15','0.07','0.03']
def create(capacity=5,fee=500):
    if capacity not in (2,5,10,20,50,100) or fee not in (100,200,500,1000,2000,5000):raise ValueError('Unsupported tournament configuration')
    tid=secrets.token_hex(6)
    info={'seed':secrets.randbelow(999999),'standings':{},'payouts':{},'platform_cents':0,'prize_pool_cents':0}
    with db() as c:c.execute('INSERT INTO tournaments VALUES(?,?,?,?,?,?)',(tid,capacity,fee,'open',json.dumps(info),time.time()))
    return tid
def join(tid,uid):
    with db() as c:
        t=c.execute('SELECT * FROM tournaments WHERE id=?',(tid,)).fetchone()
        if not t or t['status']!='open':raise ValueError('Tournament unavailable')
        if c.execute('SELECT 1 FROM entrants WHERE tournament_id=? AND user_id=?',(tid,uid)).fetchone():raise ValueError('Already joined')
        n=c.execute('SELECT count(*) n FROM entrants WHERE tournament_id=?',(tid,)).fetchone()['n']
        if n>=t['capacity']:raise ValueError('Tournament filled')
        move_credit(c,uid,-t['fee'],'tournament_entry',f'entry:{tid}:{uid}')
        c.execute('INSERT INTO entrants VALUES(?,?,?)',(tid,uid,time.time()))
        if n+1==t['capacity']:c.execute("UPDATE tournaments SET status='active' WHERE id=?",(tid,))
    return info(tid)
def info(tid):
    with db() as c:
        t=c.execute('SELECT * FROM tournaments WHERE id=?',(tid,)).fetchone()
        if not t:raise ValueError('Tournament not found')
        entrants=[x['user_id'] for x in c.execute('SELECT user_id FROM entrants WHERE tournament_id=? ORDER BY joined,user_id',(tid,))]
        return {'id':tid,'capacity':t['capacity'],'fee_cents':t['fee'],'status':t['status'],'entrants':entrants,**json.loads(t['data'])}
def report(tid,uid,score,room_id):
    """Call only after server-verified completed match; scores are never accepted from client."""
    with db() as c:
        t=c.execute('SELECT * FROM tournaments WHERE id=?',(tid,)).fetchone()
        if not t or t['status']!='active':raise ValueError('Tournament not active')
        if not c.execute('SELECT 1 FROM entrants WHERE tournament_id=? AND user_id=?',(tid,uid)).fetchone():raise ValueError('Not entered')
        d=json.loads(t['data'])
        if uid in d['standings']:raise ValueError('Already scored')
        d['standings'][uid]={'score':score,'match_id':room_id}
        c.execute('UPDATE tournaments SET data=? WHERE id=?',(json.dumps(d),tid))
        return d
def finish(tid):
    with db() as c:
        t=c.execute('SELECT * FROM tournaments WHERE id=?',(tid,)).fetchone()
        if not t or t['status']!='active':raise ValueError('Tournament is not active')
        d=json.loads(t['data']); entrants=[x['user_id'] for x in c.execute('SELECT user_id FROM entrants WHERE tournament_id=?',(tid,))]
        if set(d['standings'])!=set(entrants):raise ValueError('Pending matches')
        ranked=sorted(entrants,key=lambda u:(-d['standings'][u]['score'],u))
        shares=SPLITS[:min(5,len(ranked))] if len(ranked)>2 else ['1']
        if len(ranked)==5:shares=SPLITS
        elif len(ranked)>2:shares=SPLITS
        result=settle([t['fee']]*len(entrants),splits=shares)
        for uid,cents in zip(ranked,result['payouts_cents']):
            if cents:move_credit(c,uid,cents,'tournament_prize',f'prize:{tid}:{uid}')
        d['payouts']={u:result['payouts_cents'][i] for i,u in enumerate(ranked[:len(result['payouts_cents'])])}
        d['platform_cents']=result['platform_cents'];d['prize_pool_cents']=result['prizes_cents'];d['ranking']=ranked
        c.execute("UPDATE tournaments SET status='finished',data=? WHERE id=?",(json.dumps(d),tid))
    return info(tid)

def assign_rooms(tid, create_room):
    """Create verified human-vs-human competition fixtures on reaching capacity.
    Even counts: one pairing/player. Five: circular fixtures give two games/player.
    All fixtures use identical match duration, starting assets and map.
    """
    t=info(tid)
    if t['status']!='active':raise ValueError('Tournament not full')
    if t.get('fixtures'):return t['fixtures']
    entrants=t['entrants']
    n=len(entrants)
    if n==5:pairs=[(entrants[i],entrants[(i+1)%5]) for i in range(5)]
    else:pairs=list(zip(entrants[::2],entrants[1::2]))
    fixtures=[]
    for a,b in pairs:
        rid=create_room(a,b)
        fixtures.append({'room_id':rid,'players':[a,b],'status':'waiting','scores':None})
    with db() as c:
        row=c.execute('SELECT data FROM tournaments WHERE id=?',(tid,)).fetchone()
        data=json.loads(row['data']);data['fixtures']=fixtures
        c.execute('UPDATE tournaments SET data=? WHERE id=?',(json.dumps(data),tid))
    return fixtures

def record_fixture(tid,arena):
    """Only called from trusted authoritative match completion, never client input."""
    if arena.status!='finished' or len(arena.players)!=2:raise ValueError('Match not settled')
    with db() as c:
        row=c.execute('SELECT status,data,fee,capacity FROM tournaments WHERE id=?',(tid,)).fetchone()
        if not row:raise ValueError('Tournament not found')
        if row['status']=='finished':return False
        if row['status']!='active':raise ValueError('Tournament not active')
        d=json.loads(row['data'])
        found=False
        for fixture in d.get('fixtures',[]):
            if fixture['room_id']==arena.room_id:
                if fixture['status']=='finished':return False
                if fixture['players']!=arena.players:raise ValueError('Participants mismatch')
                fixture['status']='finished';fixture['scores']=[arena.score(0),arena.score(1)]
                found=True;break
        if not found:raise ValueError('Not a tournament fixture')
        if all(f['status']=='finished' for f in d['fixtures']):
            totals={u:[] for f in d['fixtures'] for u in f['players']}
            for f in d['fixtures']:
                for u,score in zip(f['players'],f['scores']):totals[u].append(score)
            ranked=sorted(totals,key=lambda u:(-sum(totals[u])/len(totals[u]),-sum(totals[u]),u))
            splits=None if len(ranked)==2 else SPLITS
            settlement=settle([row['fee']]*len(ranked),splits=splits)
            d['standings']={u:{'score_total':sum(totals[u]),'matches':len(totals[u]),'average':sum(totals[u])/len(totals[u])} for u in ranked}
            d['ranking']=ranked;d['payouts']={u:amt for u,amt in zip(ranked,settlement['payouts_cents'])}
            d['platform_cents']=settlement['platform_cents'];d['prize_pool_cents']=settlement['prizes_cents']
            for u,amt in d['payouts'].items():
                if amt:move_credit(c,u,amt,'tournament_prize',f'prize:{tid}:{u}')
            c.execute("UPDATE tournaments SET status='finished',data=? WHERE id=?",(json.dumps(d),tid))
        else:c.execute('UPDATE tournaments SET data=? WHERE id=?',(json.dumps(d),tid))
    return True
