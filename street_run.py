"""Server-authoritative STREET RUN: tactical city routes, contracts, influence and interception.
All resources and mission progress exist only inside a competitive Arena. No paid assets.
"""
from dataclasses import dataclass, field

# Fictional interconnected districts; their canonical IDs remain unchanged.
EDGES = ((1, 4), (0, 2, 3), (1, 3, 5, 7), (1, 2, 4, 5), (0, 3, 6), (2, 3, 8), (4, 7), (3, 6, 8), (5, 7))
# Five missions rotate after delivery; both players receive an identical deterministic series.
ROUTES = ((4, 2, 8), (7, 3, 0), (6, 1, 5), (2, 4, 7), (0, 5, 3), (8, 6, 1), (3, 7, 2))

@dataclass
class Run:
    position: list = field(default_factory=lambda:[4,4])
    packages: list = field(default_factory=lambda:[False,False])
    mission: list = field(default_factory=lambda:[0,0])
    momentum: list = field(default_factory=lambda:[0,0])
    run_points: list = field(default_factory=lambda:[0,0])
    influence: list = field(default_factory=lambda:[[0]*9,[0]*9])
    intercepted: list = field(default_factory=lambda:[0,0])
    last_motion: list = field(default_factory=lambda:[-100.,-100.])
    last_skill: list = field(default_factory=lambda:[-100.,-100.])
    combo: list = field(default_factory=lambda:[0,0])

    def objective(self, idx):
        pickup, drop = ROUTES[self.mission[idx] % len(ROUTES)][1:]
        return {'pickup': pickup, 'dropoff': drop, 'carrying':self.packages[idx], 'number':self.mission[idx]+1}

    def execute(self, seat, district, move, now):
        if seat not in (0,1) or type(district) is not int or district not in range(9):
            raise ValueError('Invalid position or player')
        current=self.position[seat]
        other=1-seat
        objective=self.objective(seat)
        points=0
        if move=='drive':
            if district not in EDGES[current]: raise ValueError('Drive only along connected streets')
            if now-self.last_motion[seat]<0.65: raise ValueError('Driving cooldown')
            self.position[seat]=district;self.last_motion[seat]=now
            self.momentum[seat]=min(4,self.momentum[seat]+1)
            points=2+self.momentum[seat]
            # Entering a controlled hotspot rewards timing and route selection.
            if self.influence[seat][district]>self.influence[other][district]:points+=3
        elif move=='pickup':
            if current!=objective['pickup'] or self.packages[seat]: raise ValueError('Reach your pickup first')
            if now-self.last_skill[seat]<0.8:raise ValueError('Skill action cooldown')
            self.packages[seat]=True;self.last_skill[seat]=now;points=25
        elif move=='deliver':
            if current!=objective['dropoff'] or not self.packages[seat]:raise ValueError('Reach your drop-off with cargo')
            if now-self.last_skill[seat]<0.8:raise ValueError('Skill action cooldown')
            self.packages[seat]=False;self.mission[seat]+=1
            self.combo[seat]=min(5,self.combo[seat]+1)
            self.last_skill[seat]=now;points=90+15*self.combo[seat]
        elif move=='hustle':
            if district!=current:raise ValueError('You must be at the target district')
            if now-self.last_skill[seat]<2.0:raise ValueError('Hustle cooldown')
            self.last_skill[seat]=now
            self.influence[seat][current]=min(5,self.influence[seat][current]+1)
            points=16 if self.influence[seat][current]>=self.influence[other][current] else 10
        elif move=='intercept':
            if district!=current or current!=self.position[other]:raise ValueError('Rival must occupy your district')
            if not self.packages[other]:raise ValueError('Rival must be carrying a contract')
            if now-self.last_skill[seat]<3.0:raise ValueError('Interception cooldown')
            self.last_skill[seat]=now
            self.packages[other]=False
            self.combo[other]=0
            # One score award per actual intercepted contract; no repeat farming.
            points=30+5*min(3,self.influence[seat][current]);self.intercepted[seat]+=1
        else:raise ValueError('Unknown STREET RUN move')
        self.run_points[seat]+=points
        return {'points':points,'position':self.position[seat], 'objective':self.objective(seat)}

    def view(self):
        return {'positions':self.position[:], 'missions':[self.objective(0),self.objective(1)],
                'run_points':self.run_points[:], 'influence':[x[:] for x in self.influence],
                'momentum':self.momentum[:], 'combos':self.combo[:], 'interceptions':self.intercepted[:],
                'edges':[list(e) for e in EDGES], 'ruleset':'street-run-v1'}

    def snapshot(self):return {k:getattr(self,k) for k in ('position','packages','mission','momentum','run_points','influence','intercepted','last_motion','last_skill','combo')}

    @classmethod
    def restore(cls, data):
        r=cls()
        for k,v in (data or {}).items():
            if k in r.snapshot():setattr(r,k,v)
        return r
