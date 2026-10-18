"""Persistent, account-scoped empire economy; independent of competitive match cash."""
import time, json, sqlite3
import storage
DISTRICTS=['CROWN PLAZA','GOLD BLOCK','DOWNTOWN','SNEAKER ROW','MIDTOWN','STUDIO DISTRICT','UPTOWN','MARKET STREET','THE HEIGHTS']
PROPERTY_TYPES=['Waterfront Hotel','Cookman Restaurant','Downtown Storefront','Sneaker Boutique','Main Street Garage','Recording Studio','Victorian Residence','Springwood Market','Prestige Townhouse']
BASE_COST=[180,125,100,90,80,135,95,70,155]
RATE=[9,7,6,6,5,8,5,5,8]
MAX_LEVEL=6
MISSION_TARGET=3

def init():
    with storage.db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS empires(user_id TEXT PRIMARY KEY,cash INTEGER NOT NULL DEFAULT 400,reputation INTEGER NOT NULL DEFAULT 0,last_accrual REAL NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS empire_properties(user_id TEXT NOT NULL,district INTEGER NOT NULL,level INTEGER NOT NULL DEFAULT 1,acquired REAL NOT NULL,PRIMARY KEY(user_id,district));
        CREATE TABLE IF NOT EXISTS empire_events(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,event TEXT NOT NULL,district INTEGER,detail TEXT NOT NULL,created REAL NOT NULL);''')

    with storage.db() as c:
        cols={r['name'] for r in c.execute('PRAGMA table_info(empires)')}
        if 'pending_income' not in cols:
            c.execute('ALTER TABLE empires ADD COLUMN pending_income INTEGER NOT NULL DEFAULT 0')
        if 'diamonds' not in cols:
            c.execute('ALTER TABLE empires ADD COLUMN diamonds INTEGER NOT NULL DEFAULT 0')
        c.execute('''CREATE TABLE IF NOT EXISTS empire_defenses(user_id TEXT NOT NULL, district INTEGER NOT NULL, level INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,district))''')

def ensure(c,uid,now):
    c.execute('INSERT OR IGNORE INTO empires(user_id,last_accrual,created) VALUES(?,?,?)',(uid,now,now))

def accrue(c,uid,now):
    e=c.execute('SELECT * FROM empires WHERE user_id=?',(uid,)).fetchone()
    # Whole-minute server-side accrual, capped at 12h per request to limit unattended farming.
    elapsed=max(0,min(720,int((now-e['last_accrual'])//60)))
    if elapsed:
        props=c.execute('SELECT district,level FROM empire_properties WHERE user_id=?',(uid,)).fetchall()
        earned=elapsed*sum(RATE[p['district']]*p['level'] for p in props)
        c.execute('UPDATE empires SET pending_income=pending_income+?,last_accrual=last_accrual+? WHERE user_id=?',(earned,elapsed*60,uid))
    return elapsed

def snapshot(uid):
    now=time.time()
    with storage.db() as c:
        c.execute('BEGIN IMMEDIATE');ensure(c,uid,now);accrue(c,uid,now)
        e=dict(c.execute('SELECT cash,reputation,last_accrual,pending_income,diamonds FROM empires WHERE user_id=?',(uid,)).fetchone())
        props=[dict(x) for x in c.execute('SELECT district,level,acquired FROM empire_properties WHERE user_id=? ORDER BY district',(uid,))]
        events=[dict(x) for x in c.execute('SELECT id,event,district,detail,created FROM empire_events WHERE user_id=? ORDER BY id DESC LIMIT 20',(uid,))]
        defense={r['district']:r['level'] for r in c.execute('SELECT district,level FROM empire_defenses WHERE user_id=?',(uid,))}
        owned={p['district'] for p in props}
        profile=c.execute('SELECT username,wins,losses FROM users WHERE id=?',(uid,)).fetchone()
    for prop in props: prop['defense']=defense.get(prop['district'],0)
    count=len(props);levels=sum(p['level'] for p in props)
    influence=[{'district':i,'owned':i in owned,'influence':(min(100,15+10*next((p['level'] for p in props if p['district']==i),0)+8*defense.get(i,0)) if i in owned else 0),'defense':defense.get(i,0)} for i in range(len(DISTRICTS))]
    rank='STREET ROOKIE' if count==0 else 'BLOCK OWNER' if count<3 else 'TURF BOSS' if count<6 else 'CITY KINGPIN' if count<9 else 'STREET KING'
    return {'player_id':uid,'cash':e['cash'],'reputation':e['reputation'],'income_per_minute':sum(RATE[p['district']]*p['level'] for p in props),'properties':props,'events':events,'districts':DISTRICTS,'property_types':PROPERTY_TYPES,'base_costs':BASE_COST,'rates':RATE,'mission':{'id':'first_three','title':'Own three properties','progress':min(count,3),'target':3,'completed':count>=3},'achievements':([{'id':'first_property','title':'First Deed'}] if count else [])+([{'id':'three_districts','title':'City Investor'}] if count>=3 else [])+([{'id':'nine_districts','title':'Citywide King'}] if count==9 else []),'total_levels':levels,'pending_income':e['pending_income'],'diamonds':e['diamonds'],'influence':influence,'rank':rank,'profile':dict(profile) if profile else {},'defense_cost':60,'maximum_level':MAX_LEVEL,'currency_note':'Empire credits and diamonds are virtual, separate from simulated Arena entry credits.'}

def action(uid,district,operation):
    if type(district) is not int or not 0<=district<9:raise ValueError('Invalid district')
    if operation not in ('acquire','upgrade','defend','collect'):raise ValueError('Invalid empire action')
    now=time.time()
    with storage.db() as c:
        c.execute('BEGIN IMMEDIATE');ensure(c,uid,now);accrue(c,uid,now)
        p=c.execute('SELECT level FROM empire_properties WHERE user_id=? AND district=?',(uid,district)).fetchone()
        if operation=='collect':
            collected=c.execute('SELECT pending_income FROM empires WHERE user_id=?',(uid,)).fetchone()['pending_income']
            if collected<=0:raise ValueError('No earnings available to collect yet')
            c.execute('UPDATE empires SET cash=cash+pending_income,pending_income=0 WHERE user_id=?',(uid,))
            c.execute('INSERT INTO empire_events(user_id,event,district,detail,created) VALUES(?,?,?,?,?)',(uid,'collect',None,json.dumps({'amount':collected}),now))
            c.commit()
            return snapshot(uid)
        if operation=='defend':
            if not p:raise ValueError('Acquire this property first')
            current=c.execute('SELECT level FROM empire_defenses WHERE user_id=? AND district=?',(uid,district)).fetchone()
            level=(current['level'] if current else 0)+1
            if level>5:raise ValueError('Maximum defense level reached')
            price=60*level
            updated=c.execute('UPDATE empires SET cash=cash-?,reputation=reputation+1 WHERE user_id=? AND cash>=?',(price,uid,price))
            if updated.rowcount!=1:raise ValueError('Not enough empire cash')
            c.execute('INSERT INTO empire_defenses(user_id,district,level) VALUES(?,?,?) ON CONFLICT(user_id,district) DO UPDATE SET level=excluded.level',(uid,district,level))
            c.execute('INSERT INTO empire_events(user_id,event,district,detail,created) VALUES(?,?,?,?,?)',(uid,'defend',district,json.dumps({'level':level,'cost':price}),now))
            c.commit()
            return snapshot(uid)
        if operation=='acquire':
            if p:raise ValueError('Property already owned')
            price=BASE_COST[district];level=1
        else:
            if not p:raise ValueError('Acquire this property first')
            if p['level']>=MAX_LEVEL:raise ValueError('Maximum property level reached')
            price=BASE_COST[district]*(p['level']+1);level=p['level']+1
        updated=c.execute('UPDATE empires SET cash=cash-?,reputation=reputation+? WHERE user_id=? AND cash>=?',(price,5 if operation=='acquire' else 2,uid,price))
        if updated.rowcount!=1:raise ValueError('Not enough empire cash')
        if operation=='acquire':c.execute('INSERT INTO empire_properties(user_id,district,level,acquired) VALUES(?,?,?,?)',(uid,district,level,now))
        else:c.execute('UPDATE empire_properties SET level=? WHERE user_id=? AND district=?',(level,uid,district))
        c.execute('INSERT INTO empire_events(user_id,event,district,detail,created) VALUES(?,?,?,?,?)',(uid,operation,district,json.dumps({'level':level,'cost':price}),now))
    return snapshot(uid)
