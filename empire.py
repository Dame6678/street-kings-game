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

def ensure(c,uid,now):
    c.execute('INSERT OR IGNORE INTO empires(user_id,last_accrual,created) VALUES(?,?,?)',(uid,now,now))

def accrue(c,uid,now):
    e=c.execute('SELECT * FROM empires WHERE user_id=?',(uid,)).fetchone()
    # Whole-minute server-side accrual, capped at 12h per request to limit unattended farming.
    elapsed=max(0,min(720,int((now-e['last_accrual'])//60)))
    if elapsed:
        props=c.execute('SELECT district,level FROM empire_properties WHERE user_id=?',(uid,)).fetchall()
        earned=elapsed*sum(RATE[p['district']]*p['level'] for p in props)
        c.execute('UPDATE empires SET cash=cash+?,last_accrual=last_accrual+? WHERE user_id=?',(earned,elapsed*60,uid))
    return elapsed

def snapshot(uid):
    now=time.time()
    with storage.db() as c:
        c.execute('BEGIN IMMEDIATE');ensure(c,uid,now);accrue(c,uid,now)
        e=dict(c.execute('SELECT cash,reputation,last_accrual FROM empires WHERE user_id=?',(uid,)).fetchone())
        props=[dict(x) for x in c.execute('SELECT district,level,acquired FROM empire_properties WHERE user_id=? ORDER BY district',(uid,))]
        events=[dict(x) for x in c.execute('SELECT id,event,district,detail,created FROM empire_events WHERE user_id=? ORDER BY id DESC LIMIT 20',(uid,))]
    count=len(props);levels=sum(p['level'] for p in props)
    return {'player_id':uid,'cash':e['cash'],'reputation':e['reputation'],'income_per_minute':sum(RATE[p['district']]*p['level'] for p in props),'properties':props,'events':events,'districts':DISTRICTS,'property_types':PROPERTY_TYPES,'base_costs':BASE_COST,'mission':{'id':'first_three','title':'Own three properties','progress':min(count,3),'target':3,'completed':count>=3},'achievements':([{'id':'first_property','title':'First Deed'}] if count else [])+([{'id':'three_districts','title':'City Investor'}] if count>=3 else [])+([{'id':'nine_districts','title':'Citywide King'}] if count==9 else []),'total_levels':levels}

def action(uid,district,operation):
    if type(district) is not int or not 0<=district<9:raise ValueError('Invalid district')
    if operation not in ('acquire','upgrade'):raise ValueError('Invalid empire action')
    now=time.time()
    with storage.db() as c:
        c.execute('BEGIN IMMEDIATE');ensure(c,uid,now);accrue(c,uid,now)
        p=c.execute('SELECT level FROM empire_properties WHERE user_id=? AND district=?',(uid,district)).fetchone()
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
