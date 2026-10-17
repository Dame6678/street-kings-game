from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from random import Random

BUSINESSES = [('Barbershop',25,6),('Sneaker Shop',40,10),('Studio',60,16)]

@dataclass
class Block:
    owner: int = -1
    level: int = 0
    kind: int = 0
    defense: int = 0

@dataclass
class Match:
    seed: int = 7
    ticks: int = 0
    max_ticks: int = 18
    cash: list = field(default_factory=lambda:[150,150])
    blocks: list = field(default_factory=lambda:[Block() for _ in range(9)])
    history: list = field(default_factory=list)
    def score(self, player):
        return sum((25+b.level*20+b.defense*8) for b in self.blocks if b.owner==player) + self.cash[player]//5
    def action(self, player, block_id, move, kind=0):
        if self.ticks >= self.max_ticks: raise ValueError('Match finished')
        if player not in (0,1) or block_id not in range(9): raise ValueError('Invalid player/block')
        b=self.blocks[block_id]
        if move=='claim':
            if b.owner!=-1: raise ValueError('Occupied block')
            cost=20+block_id*3
            if self.cash[player]<cost: raise ValueError('Insufficient funds')
            self.cash[player]-=cost;b.owner=player;b.level=1
        elif move=='build':
            if b.owner!=player: raise ValueError('Not your block')
            if kind not in range(3): raise ValueError('Invalid business')
            cost=BUSINESSES[kind][1]
            if self.cash[player]<cost: raise ValueError('Insufficient funds')
            self.cash[player]-=cost;b.level+=1;b.kind=kind
        elif move=='defend':
            if b.owner!=player or self.cash[player]<15: raise ValueError('Unavailable defense')
            self.cash[player]-=15;b.defense+=1
        elif move=='takeover':
            if b.owner!=1-player: raise ValueError('No rival owner')
            cost=35+15*b.defense+10*(b.level-1)
            if self.cash[player]<cost: raise ValueError('Insufficient funds')
            self.cash[player]-=cost;b.owner=player;b.defense=0
        else:raise ValueError('Invalid move')
        self.ticks+=1
        # Both players receive fixed income each completed action; no random scoring.
        for p in (0,1):
            self.cash[p]+=10+sum(BUSINESSES[b.kind][2]*b.level for b in self.blocks if b.owner==p)
        self.history.append({'player':player,'block':block_id,'move':move})
        return self.state()
    def bot_move(self):
        p=1
        for i,b in enumerate(self.blocks):
            if b.owner==-1 and self.cash[p]>=20+i*3: return self.action(p,i,'claim')
        own=[i for i,b in enumerate(self.blocks) if b.owner==p]
        if own and self.cash[p]>=25:return self.action(p,own[0],'build',0)
        return self.pass_turn(p)
    def pass_turn(self,player):
        if self.ticks>=self.max_ticks:raise ValueError('Match finished')
        self.ticks+=1;self.cash[player]+=10;return self.state()
    def state(self):
        scores=[self.score(0),self.score(1)]
        return {'ticks':self.ticks,'max_ticks':self.max_ticks,'cash':self.cash[:],'scores':scores,'blocks':[vars(b).copy() for b in self.blocks],'finished':self.ticks>=self.max_ticks,'winner':(scores.index(max(scores)) if scores[0]!=scores[1] else None) if self.ticks>=self.max_ticks else None}

def settle(entries_cents, rate=Decimal('0.30'), splits=None):
    if not entries_cents or any(type(v)!=int or v<0 for v in entries_cents):raise ValueError('Invalid entries')
    if not (Decimal('0')<=rate<Decimal('1')):raise ValueError('Invalid rate')
    pool=sum(entries_cents)
    platform=int((Decimal(pool)*rate).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    prizes=pool-platform
    if splits is None:splits=[Decimal('1')]
    if sum(map(Decimal,splits))!=1:raise ValueError('Prize shares must sum to 1')
    payouts=[int((Decimal(prizes)*Decimal(str(s))).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) for s in splits[:-1]]
    payouts.append(prizes-sum(payouts))
    if min(payouts)<0:raise ValueError('Invalid payouts')
    assert sum(payouts)+platform==pool
    return {'pool_cents':pool,'platform_cents':platform,'prizes_cents':prizes,'payouts_cents':payouts}
