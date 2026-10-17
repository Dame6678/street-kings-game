import pytest,time,sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from realtime import Arena
from engine import settle
import storage,tournament

def test_human_join_ready_and_live_actions():
    a=Arena(duration=30);assert a.join('alice')==0;assert a.join('bob')==1
    assert a.join('alice')==0
    with pytest.raises(ValueError):a.join('charlie')
    a.set_ready(0,now=100);assert a.status=='waiting';a.set_ready(1,now=100);assert a.status=='running'
    a.action(0,0,'claim',now=101);a.action(1,1,'claim',now=101)
    assert a.blocks[0].owner==0 and a.blocks[1].owner==1
    assert a.cash[0]==130 and a.cash[1]==127
    with pytest.raises(ValueError):a.action(1,0,'claim',now=102)
    with pytest.raises(ValueError):a.action(0,1,'build',now=102)

def test_income_upgrade_ownership_and_takeover():
    a=Arena(duration=60);a.join('a');a.join('b');a.set_ready(0,100);a.set_ready(1,100)
    a.action(0,0,'claim',now=101)
    a.action(0,0,'build',0,now=102)
    assert a.blocks[0].level==2 and a.cash[0]==105
    a.advance(107)
    assert a.cash[0]==114 # 3 basic + 6 barbershop each 5s
    a.action(0,0,'defend',now=108)
    a.action(1,0,'takeover',now=109)
    assert a.blocks[0].owner==1 and a.blocks[0].defense==0 and a.blocks[0].level==1

def test_countdown_timeout_and_deterministic_tie():
    a=Arena(duration=20);a.join('a');a.join('b');a.set_ready(0,100);a.set_ready(1,100)
    a.advance(121);assert a.status=='finished' and a.winner is None
    with pytest.raises(ValueError):a.action(0,0,'claim',now=122)
    assert a.state(now=122)['remaining']==0

def test_winner_conflicts_cooldowns_and_score():
    a=Arena(duration=20);a.join('a');a.join('b');a.set_ready(0,100);a.set_ready(1,100)
    a.action(0,0,'claim',now=101)
    with pytest.raises(ValueError):a.action(0,1,'claim',now=101.1)
    a.advance(121);assert a.winner==0
    assert a.state(now=122)['scores'][0]>a.state(now=122)['scores'][1]

def test_payout_math():
    for n in (2,5,10,20,50,100):
        parts=None if n==2 else ['0.5','0.25','0.15','0.07','0.03']
        out=settle([500]*n,splits=parts)
        assert out['pool_cents']==500*n
        assert sum(out['payouts_cents'])==out['prizes_cents']
        assert out['platform_cents']+out['prizes_cents']==out['pool_cents']

def test_registration_login_db_and_wallet():
    with TemporaryDirectory() as d:
        old=storage.DB_PATH;storage.DB_PATH=str(Path(d)/'demo.db');storage.init_db()
        try:
            u=storage.register('alice','securepassword11');v=storage.register('bobby','securepassword22')
            token=storage.login('alice','securepassword11');assert storage.authenticate(token)==u
            assert storage.authenticate('fake') is None
            with pytest.raises(ValueError):storage.login('alice','incorrectpass')
            with pytest.raises(ValueError):storage.register('alice','securepassword11')
            with storage.db() as c:storage.move_credit(c,u,-250,'test','tx1')
            assert storage.profile(u)['balance']==9750
            with pytest.raises(ValueError):
                with storage.db() as c:storage.move_credit(c,u,-12000,'test','tx2')
            assert storage.profile(u)['balance']==9750
            assert len(storage.ledger(u))==1
            a=Arena(duration=15);a.join(u);a.join(v);a.set_ready(0,100);a.set_ready(1,100);a.action(0,0,'claim',now=101);a.advance(116)
            storage.save_match(a);storage.store_result(a);storage.store_result(a)
            assert storage.profile(u)['wins']==1 and storage.profile(v)['losses']==1
            with storage.db() as c:assert c.execute('SELECT count(*) FROM matches').fetchone()[0]==1
            tid=tournament.create(2,500)
            tournament.join(tid,u);out=tournament.join(tid,v)
            assert out['status']=='active'
            assert storage.profile(u)['balance']==9250
            assert storage.ledger(u)[0]['kind']=='tournament_entry'
        finally:storage.DB_PATH=old

def test_state_roundtrip_and_restart():
    from realtime import restore_arena,snapshot_arena
    a=Arena(duration=23);a.join('x');a.join('y');a.set_ready(0,100);a.set_ready(1,100);a.action(0,1,'claim',now=101)
    r=restore_arena(snapshot_arena(a))
    assert r.state(now=102)==a.state(now=102)
    r.advance(124);assert r.status=='finished'

def test_verified_tournament_pairing_and_settlement():
    with TemporaryDirectory() as d:
        old=storage.DB_PATH;storage.DB_PATH=str(Path(d)/'tour.db');storage.init_db()
        try:
            people=[storage.register('player'+str(i),'passphrase0000') for i in range(5)]
            tid=tournament.create(5,500)
            for uid in people:tournament.join(tid,uid)
            games={}
            def make(a,b):
                game=Arena(duration=15);game.join(a);game.join(b);games[game.room_id]=game;return game.room_id
            fixtures=tournament.assign_rooms(tid,make)
            assert len(fixtures)==5
            assert {u:sum(u in f['players'] for f in fixtures) for u in people}=={u:2 for u in people}
            for fixture in fixtures:
                a=games[fixture['room_id']];a.set_ready(0,100);a.set_ready(1,100)
                a.action(0,0,'claim',now=101);a.advance(116)
                assert tournament.record_fixture(tid,a)
                assert not tournament.record_fixture(tid,a)
            result=tournament.info(tid)
            assert result['status']=='finished'
            assert result['platform_cents']==750
            assert sum(result['payouts'].values())==1750
            assert sum(storage.profile(u)['balance'] for u in people)==5*10000-750
        finally:storage.DB_PATH=old
