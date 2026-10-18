"""Server-side AI opponent for simulated-credit STREET KINGS real-time matches.
AI uses the exact same validated action and economy rules as human players.
No external model, network requests, or privileged credit injection.
"""
import random
from engine import BUSINESSES

AI_ID='AI_OPPONENT'

def advance_ai(arena, now=None):
    """One or more paced decisions; invoked under the arena's existing lock."""
    import time
    now=time.time() if now is None else now
    if arena.status!='running' or AI_ID not in arena.players:return
    seat=arena.players.index(AI_ID)
    # Pace turns at ~2.4 seconds, no instantaneous action spam.
    last=getattr(arena,'_ai_last',None)
    if last is None:
        arena._ai_last=now-2.5
        last=arena._ai_last
    if now-last<2.4:return
    arena._ai_last=now
    run=arena.street_run
    objective=run.objective(seat)
    here=run.position[seat]
    target=objective['dropoff'] if objective['carrying'] else objective['pickup']
    try:
        if here==target:
            arena.action(seat,here,'deliver' if objective['carrying'] else 'pickup',now=now)
        else:
            from street_run import EDGES
            queue=[(here,[])];seen={here}
            while queue:
                node,path=queue.pop(0)
                if node==target:
                    arena.action(seat,path[0],'drive',now=now)
                    break
                for nxt in EDGES[node]:
                    if nxt not in seen:seen.add(nxt);queue.append((nxt,path+[nxt]))
    except ValueError:pass
    cash=arena.cash[seat]
    owned=[i for i,b in enumerate(arena.blocks) if b.owner==seat]
    enemy=[i for i,b in enumerate(arena.blocks) if b.owner==1-seat]
    free=[i for i,b in enumerate(arena.blocks) if b.owner==-1]
    options=[]
    # Evaluate affordable legal moves with offensive, income and territory priorities.
    for i in free:
        cost=20+3*i
        if cash>=cost:
            options.append((95-cost*.65+random.random()*18,'claim',i,0))
    for i in owned:
        b=arena.blocks[i]
        if b.level<5:
            for kind in range(len(BUSINESSES)):
                cost=BUSINESSES[kind][1]+(b.level-1)*10
                if cash>=cost:
                    income=BUSINESSES[kind][2]
                    options.append((37+income*4-cost*.35+(5-b.level)*2+random.random()*14,'build',i,kind))
        if b.defense<4 and cash>=15+10*b.defense:
            pressure=14 if len(enemy)>0 else 0
            options.append((16+pressure-b.defense*5+random.random()*15,'defend',i,0))
    for i in enemy:
        b=arena.blocks[i]
        cost=40+20*b.defense+15*(b.level-1)
        if cash>=cost:
            options.append((62+12*b.level-cost*.36+random.random()*22,'takeover',i,0))
    if not options:return
    options.sort(reverse=True)
    for _,move,i,kind in options:
        try:
            arena.action(seat,i,move,kind,now=now)
            return
        except ValueError:
            continue
