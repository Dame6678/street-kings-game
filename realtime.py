"""Server-authoritative, wall-clock, simultaneous STREET KINGS gameplay.
Preserves legacy engine.py for v0.1 compatibility. All credits are simulated.
"""
import time
from dataclasses import dataclass, field
from uuid import uuid4
from engine import Block, BUSINESSES
from street_run import Run

DISTRICTS = ['Crown Plaza','Gold Block','Downtown','Sneaker Row','Midtown','Studio District','Uptown','Market Street','The Heights']

@dataclass
class Arena:
    room_id: str = field(default_factory=lambda: uuid4().hex[:10])
    duration: int = 180
    status: str = 'waiting'
    players: list = field(default_factory=list)
    ready: list = field(default_factory=lambda:[False,False])
    cash: list = field(default_factory=lambda:[150,150])
    blocks: list = field(default_factory=lambda:[Block() for _ in range(9)])
    started_at: float | None = None
    ended_at: float | None = None
    last_income_at: float | None = None
    winner: int | None = None
    history: list = field(default_factory=list)
    revision: int = 0
    actions_at: list = field(default_factory=lambda:[-1.,-1.])
    street_run: Run = field(default_factory=Run)
    def join(self, user_id):
        if user_id in self.players: return self.players.index(user_id)
        if len(self.players)==2 or self.status!='waiting': raise ValueError('Room full or started')
        self.players.append(user_id);self.revision+=1
        return len(self.players)-1
    def set_ready(self, idx, now=None):
        now=time.time() if now is None else now
        if idx>=len(self.players):raise ValueError('Not a player')
        self.ready[idx]=True
        if len(self.players)==2 and all(self.ready) and self.status=='waiting':
            self.status='running';self.started_at=now;self.last_income_at=now
        self.revision+=1
    def _income(self, p):
        return 3+sum(BUSINESSES[b.kind][2] * max(0,b.level-1) for b in self.blocks if b.owner==p)
    def advance(self, now=None):
        now=time.time() if now is None else now
        if self.status!='running':return
        deadline=self.started_at+self.duration
        capped=min(now,deadline)
        steps=max(0,int((capped-self.last_income_at)//5))
        if steps:
            for p in range(2):self.cash[p]+=steps*self._income(p)
            self.last_income_at+=steps*5
            self.revision+=1
        if now>=deadline:self.finish(deadline)
    def score(self,p):
        return self.street_run.run_points[p]+sum(35+15*(b.level-1)+10*b.defense+10*b.kind*max(0,b.level-1) for b in self.blocks if b.owner==p)+self.cash[p]//10
    def finish(self,now=None):
        if self.status=='finished':return
        if self.status!='running':raise ValueError('Match not running')
        self.status='finished';self.ended_at=time.time() if now is None else now
        a,b=self.score(0),self.score(1)
        if a!=b:self.winner=0 if a>b else 1
        else:
            owns=[sum(x.owner==p for x in self.blocks) for p in (0,1)]
            if owns[0]!=owns[1]:self.winner=0 if owns[0]>owns[1] else 1
            elif self.cash[0]!=self.cash[1]:self.winner=0 if self.cash[0]>self.cash[1] else 1
            else:self.winner=None
        self.revision+=1
    def action(self,idx,block,move,kind=0,now=None):
        now=time.time() if now is None else now
        self.advance(now)
        if self.status!='running':raise ValueError('Match not active')
        if idx not in (0,1) or idx>=len(self.players) or block not in range(9):raise ValueError('Invalid player or block')
        if now-self.actions_at[idx]<0.2:raise ValueError('Action cooldown')
        if move in ('drive','pickup','deliver','hustle','intercept'):
            outcome=self.street_run.execute(idx,block,move,now)
            self.history.append({'at':round(now,3),'player':idx,'block':block,'move':move,'points':outcome['points']})
            self.revision+=1
            return
        b=self.blocks[block]; cost=0
        if move=='claim':
            if b.owner!=-1:raise ValueError('District already owned')
            cost=20+block*3
        elif move=='build':
            if b.owner!=idx:raise ValueError('Not your district')
            if kind not in range(len(BUSINESSES)):raise ValueError('Invalid business')
            if b.level>=5:raise ValueError('Maximum business level')
            cost=BUSINESSES[kind][1]+(b.level-1)*10
        elif move=='defend':
            if b.owner!=idx or b.defense>=4:raise ValueError('Cannot defend')
            cost=15+10*b.defense
        elif move=='takeover':
            if b.owner!=1-idx:raise ValueError('Not rival territory')
            cost=40+20*b.defense+15*(b.level-1)
        else:raise ValueError('Invalid action')
        if self.cash[idx]<cost:raise ValueError('Insufficient simulated credits')
        self.cash[idx]-=cost
        if move=='claim':b.owner=idx;b.level=1;b.kind=0;b.defense=0
        if move=='build':b.kind=kind;b.level+=1
        if move=='defend':b.defense+=1
        if move=='takeover':b.owner=idx;b.defense=0;b.level=max(1,b.level-1)
        self.actions_at[idx]=now;self.revision+=1
        self.history.append({'at':round(now,3),'player':idx,'block':block,'move':move,'cost':cost,'kind':kind,'revision':self.revision})
    def state(self, now=None):
        now=time.time() if now is None else now
        self.advance(now)
        left=self.duration if self.started_at is None else max(0,int(self.started_at+self.duration-now+0.999))
        return {'room_id':self.room_id,'status':self.status,'duration':self.duration,'remaining':left,'players':self.players[:], 'ready':self.ready[:], 'cash':self.cash[:], 'scores':[self.score(0),self.score(1)],'blocks':[vars(b).copy() for b in self.blocks],'winner':self.winner,'revision':self.revision,'history':self.history[-25:],'street_run':self.street_run.view(),'money_mode':'SIMULATED CREDITS ONLY'}

def restore_arena(snapshot):
    """Reconstruct gameplay after a single-worker restart, preserving the original countdown."""
    a=Arena(room_id=snapshot['room_id'],duration=snapshot['duration'])
    a.status=snapshot['status'];a.players=list(snapshot['players']);a.ready=list(snapshot['ready'])
    a.cash=list(snapshot['cash']);a.blocks=[Block(**b) for b in snapshot['blocks']]
    a.started_at=snapshot.get('started_at');a.last_income_at=snapshot.get('last_income_at')
    a.ended_at=snapshot.get('ended_at');a.winner=snapshot.get('winner')
    a.history=list(snapshot.get('history',[]));a.revision=snapshot.get('revision',0)
    a.actions_at=list(snapshot.get('actions_at',[-1.,-1.]))
    a.street_run=Run.restore(snapshot.get('street_run'))
    return a

def snapshot_arena(a):
    return {'room_id':a.room_id,'duration':a.duration,'status':a.status,'players':a.players,'ready':a.ready,'cash':a.cash,'blocks':[vars(b).copy() for b in a.blocks], 'started_at':a.started_at,'last_income_at':a.last_income_at,'ended_at':a.ended_at,'winner':a.winner,'history':a.history,'revision':a.revision,'actions_at':a.actions_at,'street_run':a.street_run.snapshot()}
