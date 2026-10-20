"""Aerial city integration regression tests; browser imagery is separately verified."""
import re
from pathlib import Path
from fastapi.testclient import TestClient
import main
from empire import DISTRICTS

ROOT=Path(__file__).parent

def test_approved_homepage_links_into_real_city():
    html=(ROOT/'static/index.html').read_text()
    assert "if(page==='city'){window.location.assign('/city.html');return;}" in html
    assert 'PLAY FOR REAL MONEY. WIN REAL CASH.' in html
    assert "'/my-empire.html'" in html
    assert "'/divisions.html'" in html

def test_aerial_has_real_imagery_sources_without_illustrated_city():
    s=(ROOT/'static/city.html').read_text()
    assert 'basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/' in s
    assert 'img.nj.gov/imagerywms/Natural2015?' in s
    assert 'new maplibregl.Map(' in s
    assert 'touchZoomRotate.disableRotation' in s
    assert "map.on('click','territory-fills'" in s
    assert 'streetkings:division-selected' in s
    assert 'streetkings:select-division' in s
    assert '/api/divisions' in s and '/api/empire' in s
    assert 'street-kings-live.html' not in s
    assert 'id="pad"' not in s
    assert 'id="world"' not in s

def test_exact_nine_divisions_and_grounded_game_geojson():
    s=(ROOT/'static/city.html').read_text()
    for name in DISTRICTS:assert "name:'"+name+"'" in s
    assert s.count("{name:'") == 9
    assert "type:'FeatureCollection'" in s
    assert "type:'Polygon'" in s
    assert 'Fictional game location' in s

def test_divisions_replaces_aerial_with_interactive_regions_and_keeps_challenge():
    s=(ROOT/'static/divisions.html').read_text()
    assert 'src="/city.html?embedded=1"' not in s
    assert 'id="divisionZones"' in s
    assert '/crown-plaza.html?district=0' in s
    assert 'renderZones()' in s
    assert "'/api/divisions/challenge'" in s
    assert "'/api/divisions'" in s
    assert 'ENTER KINGSLEY STREET' in s
    assert 'VIEW DIVISION' in s
    assert 'CURRENT KING' in s

def test_fastapi_serves_city_divisions_and_homepage():
    c=TestClient(main.app)
    for path in ['/city.html','/divisions.html','/index.html']:
        r=c.get(path)
        assert r.status_code==200, (path,r.status_code)
        assert '<html' in r.text.lower()

def test_previous_city_urls_route_to_new_aerial_environment():
    s=(ROOT/'static/street-kings-live.html').read_text()
    assert "city:'/city.html'" in s
    assert "divisions:'/divisions.html'" in s
    assert "empire:'/my-empire.html'" in s
    assert "if(m&&routes[m])location.replace(routes[m])" in s
