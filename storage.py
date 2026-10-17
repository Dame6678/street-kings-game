"""SQLite-backed identities, match snapshots, ledgers, tournament records."""
import sqlite3, os, json, secrets, hashlib, hmac, time
from contextlib import contextmanager
from pathlib import Path
DB_PATH=os.environ.get('STREET_KINGS_DB',str(Path(__file__).parent/'streetkings.sqlite3'))
SCHEMA='''
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, hash TEXT NOT NULL, balance INTEGER NOT NULL DEFAULT 10000, wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS matches(id TEXT PRIMARY KEY, status TEXT NOT NULL, snapshot TEXT NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT,room_id TEXT NOT NULL,user_id TEXT NOT NULL,outcome TEXT NOT NULL,score INTEGER NOT NULL,created REAL NOT NULL,UNIQUE(room_id,user_id));
CREATE TABLE IF NOT EXISTS tournaments(id TEXT PRIMARY KEY,capacity INTEGER NOT NULL,fee INTEGER NOT NULL,status TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS entrants(tournament_id TEXT NOT NULL,user_id TEXT NOT NULL,joined REAL NOT NULL,PRIMARY KEY(tournament_id,user_id));
CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY AUTOINCREMENT,txid TEXT UNIQUE NOT NULL,user_id TEXT NOT NULL,delta INTEGER NOT NULL,kind TEXT NOT NULL,created REAL NOT NULL);
'''
@contextmanager
def db():
    c=sqlite3.connect(DB_PATH,timeout=20);c.row_factory=sqlite3.Row;c.execute('PRAGMA busy_timeout=20000');c.execute('PRAGMA foreign_keys=ON')
    try:yield c;c.commit()
    except: c.rollback();raise
    finally:c.close()
def init_db():
    Path(DB_PATH).parent.mkdir(parents=True,exist_ok=True)
    with db() as c:c.executescript(SCHEMA)
def register(username,password):
    username=username.strip().lower()
    if len(username)<3 or len(username)>24 or not username.replace('_','').isalnum():raise ValueError('Username 3-24 letters, numbers, underscore')
    if len(password)<10:raise ValueError('Password must be at least 10 characters')
    uid=secrets.token_hex(12);salt=secrets.token_hex(16)
    hashed=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),260000).hex()
    try:
        with db() as c:c.execute('INSERT INTO users(id,username,salt,hash,created) VALUES(?,?,?,?,?)',(uid,username,salt,hashed,time.time()))
    except sqlite3.IntegrityError:raise ValueError('Username taken')
    return uid
def login(username,password):
    with db() as c:u=c.execute('SELECT * FROM users WHERE username=?',(username.strip().lower(),)).fetchone()
    if not u:raise ValueError('Invalid credentials')
    hashed=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(u['salt']),260000).hex()
    if not hmac.compare_digest(hashed,u['hash']):raise ValueError('Invalid credentials')
    token=secrets.token_urlsafe(32)
    with db() as c:c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],time.time()+86400))
    return token
def authenticate(token):
    if not token:return None
    with db() as c:
        r=c.execute('SELECT user_id FROM sessions WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return r['user_id'] if r else None
def profile(uid):
    with db() as c:u=c.execute('SELECT id,username,balance,wins,losses FROM users WHERE id=?',(uid,)).fetchone()
    return dict(u) if u else None
def move_credit(c,uid,delta,kind,txid):
    try:
        r=c.execute('UPDATE users SET balance=balance+? WHERE id=? AND balance+?>=0',(delta,uid,delta))
        if r.rowcount!=1:raise ValueError('Insufficient simulated credits')
        c.execute('INSERT INTO ledger(txid,user_id,delta,kind,created) VALUES(?,?,?,?,?)',(txid,uid,delta,kind,time.time()))
    except sqlite3.IntegrityError:raise ValueError('Duplicate transaction')
def ledger(uid):
    with db() as c:return [dict(x) for x in c.execute('SELECT txid,delta,kind,created FROM ledger WHERE user_id=? ORDER BY id DESC LIMIT 100',(uid,))]
def save_match(arena):
    from realtime import snapshot_arena
    with db() as c:c.execute('INSERT INTO matches VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,snapshot=excluded.snapshot,updated=excluded.updated',(arena.room_id,arena.status,json.dumps(snapshot_arena(arena)),time.time()))
def store_result(arena):
    with db() as c:
        for idx,uid in enumerate(arena.players):
            outcome='draw' if arena.winner is None else ('win' if idx==arena.winner else 'loss')
            result=c.execute('INSERT OR IGNORE INTO history(room_id,user_id,outcome,score,created) VALUES(?,?,?,?,?)',(arena.room_id,uid,outcome,arena.score(idx),time.time()))
            if result.rowcount and outcome!='draw':c.execute('UPDATE users SET '+('wins=wins+1' if outcome=='win' else 'losses=losses+1')+' WHERE id=?',(uid,))
def ranking():
    with db() as c:return [dict(x) for x in c.execute('SELECT username,wins,losses FROM users ORDER BY wins DESC,losses ASC LIMIT 30')]

def load_matches():
    from realtime import restore_arena
    with db() as c:return [restore_arena(json.loads(x['snapshot'])) for x in c.execute('SELECT snapshot FROM matches')]
