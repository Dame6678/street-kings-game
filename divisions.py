"""Durable nine-crown league. Only completed, authenticated Arena results transfer crowns."""
import time, sqlite3
import storage
from empire import DISTRICTS, PROPERTY_TYPES


def init():
    with storage.db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS division_crowns(district INTEGER PRIMARY KEY,king_id TEXT, since REAL NOT NULL DEFAULT 0, defenses INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS division_challenges(id TEXT PRIMARY KEY,district INTEGER NOT NULL,challenger TEXT NOT NULL,defender TEXT,room_id TEXT UNIQUE NOT NULL,status TEXT NOT NULL DEFAULT 'pending',winner TEXT,created REAL NOT NULL,completed REAL);
        CREATE INDEX IF NOT EXISTS idx_division_challenge_district ON division_challenges(district,created DESC);
        CREATE TABLE IF NOT EXISTS division_events(id INTEGER PRIMARY KEY AUTOINCREMENT,district INTEGER NOT NULL,old_king TEXT,new_king TEXT,room_id TEXT UNIQUE NOT NULL,created REAL NOT NULL);
        ''')
        for i in range(9):c.execute('INSERT OR IGNORE INTO division_crowns(district) VALUES(?)',(i,))

def public_profile(uid):
    with storage.db() as c:
        p=c.execute('SELECT id,username,wins,losses,created FROM users WHERE id=?',(uid,)).fetchone()
        if not p:return None
        crowns=c.execute('SELECT district FROM division_crowns WHERE king_id=? ORDER BY district',(uid,)).fetchall()
        return {**dict(p),'crowns':[DISTRICTS[r['district']] for r in crowns]}

def board():
    with storage.db() as c:
        rows=[]
        for i,name in enumerate(DISTRICTS):
            crown=c.execute('SELECT * FROM division_crowns WHERE district=?',(i,)).fetchone()
            king=c.execute('SELECT id,username,wins,losses FROM users WHERE id=?',(crown['king_id'],)).fetchone() if crown['king_id'] else None
            pending=[dict(r) for r in c.execute('''SELECT ch.id,ch.challenger,u.username AS challenger_name,ch.room_id,ch.created,ch.status FROM division_challenges ch JOIN users u ON u.id=ch.challenger WHERE ch.district=? AND ch.status IN ('pending','active') ORDER BY ch.created DESC LIMIT 8''',(i,))]
            history=[dict(r) for r in c.execute('''SELECT ev.created,ev.room_id,old.username AS old_king_name,new.username AS new_king_name FROM division_events ev LEFT JOIN users old ON old.id=ev.old_king LEFT JOIN users new ON new.id=ev.new_king WHERE ev.district=? ORDER BY ev.id DESC LIMIT 6''',(i,))]
            standings=[dict(r) for r in c.execute('''SELECT u.id,u.username,u.wins,u.losses,COUNT(*) AS division_wins FROM division_challenges ch JOIN users u ON u.id=ch.winner WHERE ch.district=? AND ch.status='completed' GROUP BY ch.winner ORDER BY division_wins DESC,u.wins DESC LIMIT 5''',(i,))]
            rows.append({'id':i,'name':name,'property_type':PROPERTY_TYPES[i],'king':dict(king) if king else None,'status':'contested' if pending else 'controlled' if king else 'unclaimed','since':crown['since'],'defenses':crown['defenses'],'version':crown['version'],'challenges':pending,'history':history,'standings':standings})
        return {'divisions':rows,'updated':time.time()}

def open_challenge(uid,district,room_id):
    if type(district) is not int or not 0<=district<9:raise ValueError('Invalid division')
    now=time.time()
    with storage.db() as c:
        c.execute('BEGIN IMMEDIATE')
        current=c.execute('SELECT king_id FROM division_crowns WHERE district=?',(district,)).fetchone()['king_id']
        if current==uid:raise ValueError('You already hold this crown')
        existing=c.execute("SELECT id FROM division_challenges WHERE district=? AND status IN ('pending','active')",(district,)).fetchone()
        if existing:raise ValueError('Division currently has an active challenge')
        c.execute('INSERT INTO division_challenges(id,district,challenger,defender,room_id,status,created) VALUES(?,?,?,?,?,?,?)',(room_id,district,uid,current,room_id,'pending',now))
    return {'room_id':room_id,'district':district,'status':'pending','defender_id':current}

def authorize_join(uid,room_id):
    with storage.db() as c:
        ch=c.execute('SELECT * FROM division_challenges WHERE room_id=?',(room_id,)).fetchone()
        if not ch:return True
        if ch['status'] not in ('pending','active'):raise ValueError('Challenge closed')
        # Crowned defender required when challenged. Unclaimed divisions may be challenged by any second registered human.
        if ch['defender'] and uid not in (ch['challenger'],ch['defender']):raise ValueError('Only the reigning King may defend this crown')
        if uid==ch['challenger']:return True
        c.execute("UPDATE division_challenges SET status='active' WHERE room_id=? AND status='pending'",(room_id,))
        return True

def settle(arena):
    """Idempotent, single-writer, atomic crown settlement; winner must be match participant."""
    if arena.status!='finished' or len(arena.players)!=2 or 'AI_OPPONENT' in arena.players: return False
    if arena.winner not in (None,0,1):return False
    with storage.db() as c:
        c.execute('BEGIN IMMEDIATE')
        ch=c.execute('SELECT * FROM division_challenges WHERE room_id=?',(arena.room_id,)).fetchone()
        if not ch or ch['status'] not in ('pending','active'):return False
        challenger=ch['challenger'];defender=ch['defender']
        if challenger not in arena.players:return False
        opponent=next((p for p in arena.players if p!=challenger),None)
        if not opponent or opponent=='AI_OPPONENT':return False
        if defender and opponent!=defender:return False
        king=c.execute('SELECT king_id FROM division_crowns WHERE district=?',(ch['district'],)).fetchone()['king_id']
        if king!=defender:
            c.execute("UPDATE division_challenges SET status='stale',completed=? WHERE id=?",(time.time(),ch['id']))
            return False
        winner=arena.players[arena.winner] if arena.winner is not None else None
        now=time.time()
        if winner==challenger:
            c.execute('UPDATE division_crowns SET king_id=?,since=?,defenses=0,version=version+1 WHERE district=?',(challenger,now,ch['district']))
            c.execute('INSERT INTO division_events(district,old_king,new_king,room_id,created) VALUES(?,?,?,?,?)',(ch['district'],king,challenger,arena.room_id,now))
        elif winner==defender and defender:
            c.execute('UPDATE division_crowns SET defenses=defenses+1,version=version+1 WHERE district=?',(ch['district'],))
        c.execute("UPDATE division_challenges SET status='completed',winner=?,completed=? WHERE id=?",(winner,now,ch['id']))
        return True
