"""Crown Plaza city navigation and preserved source regression."""
from pathlib import Path
from fastapi.testclient import TestClient
import main
root=Path(__file__).parent


def test_division_selection_and_scene_are_served():
    c=TestClient(main.app)
    for path in ('/index.html','/divisions.html','/crown-plaza.html','/city-segments.js'):
        r=c.get(path)
        assert r.status_code==200,path
    homepage=c.get('/index.html').text
    divisions=c.get('/divisions.html').text
    scene=c.get('/crown-plaza.html').text
    assert "window.location.assign('/divisions.html')" in homepage
    assert 'id="divisionZones"' in divisions and 'id="aerialMap"' not in divisions
    assert '/crown-plaza.html?district=0' in divisions
    for name in ('CROWN PLAZA','GOLD BLOCK','DOWNTOWN','SNEAKER ROW','MIDTOWN','STUDIO DISTRICT','UPTOWN','MARKET STREET','THE HEIGHTS'):
        assert name in homepage
    engine=c.get('/crown-plaza-3d.js')
    assert engine.status_code == 200
    assert 'id="world"' in scene
    assert 'crown-plaza-3d.js' in scene
    assert "getContext('webgl'" in engine.text
    assert "requestAnimationFrame(draw)" in engine.text
    assert "function blocked(x,z)" in engine.text
    assert "data-control=\"run\"" in scene
    assert c.get('/kingsley-original-engine.html').status_code == 200



def test_existing_backends_and_legacy_city_are_preserved():
    c=TestClient(main.app)
    assert c.get('/api/divisions').status_code == 200
    assert len(c.get('/api/divisions').json()['divisions']) == 9
    assert c.get('/city.html').status_code == 200
    assert c.get('/kingsley-preview.html').status_code == 200
    assert 'register(segment)' in c.get('/city-segments.js').text
