"""Regression: the approved map must remain the live divisions visual."""
from pathlib import Path
import re
from PIL import Image
from fastapi.testclient import TestClient
import main

ROOT=Path(__file__).parent
HTML=(ROOT/'static/divisions.html').read_text()

def test_approved_map_original_size_and_asset_route():
    asset=ROOT/'static/street-kings-approved-divisions.jpg'
    assert asset.is_file()
    with Image.open(asset) as im:
        assert im.size==(1536,1024)
    r=TestClient(main.app).get('/street-kings-approved-divisions.jpg')
    assert r.status_code==200
    assert r.content==asset.read_bytes()

def test_exact_approved_art_and_nine_responsive_regions():
    assert '<image href="/street-kings-approved-divisions.jpg"' in HTML
    assert 'viewBox="0 0 1536 1024"' in HTML
    assert 'id="divisionZones"' in HTML
    assert 'renderZones();refresh()' in HTML
    assert 'pattern id="blocks"' not in HTML
    m=re.search(r'const polygons=(\[[^;]+\]);',HTML)
    assert m
    import json
    shapes=json.loads(m.group(1))
    assert len(shapes)==9
    for shape in shapes:
        points=[tuple(map(int,xy.split(','))) for xy in shape.split(' ')]
        assert len(points)>=4
        assert all(0<=x<=1536 and 0<=y<=1024 for x,y in points)
    assert "window.location.assign('/crown-plaza.html?district=0')" in HTML
    assert "'/api/divisions/challenge'" in HTML
    assert "'/api/divisions'" in HTML
