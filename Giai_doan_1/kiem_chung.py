"""Đối chiếu đầu ra bằng NetworkX và dữ liệu hình học OSM."""
import csv
import io
import json
import math
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import networkx as nx
from pyproj import Transformer
from shapely import transform
from shapely.geometry import LineString, shape
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / 'data/clean'
LOG = ROOT / 'logs/nhat_ky.tsv'
TO_M = Transformer.from_crs(4326, 32648, always_xy=True).transform


def read_csv(name):
    with (CLEAN / f'{name}.csv').open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def read_geojson(name):
    return json.loads((CLEAN / f'{name}.geojson').read_text(encoding='utf-8'))['features']


with zipfile.ZipFile(ROOT / 'data/raw/Du_lieu_Thanh_My_Tay_OSM.zip') as archive:
    boundary_src = json.load(io.BytesIO(archive.read('Thanh_My_Tay/ranh_gioi.geojson')))['features'][0]
reference = json.loads((ROOT / 'data/raw/OSM_ranh_doi_chieu.geojson_source.json').read_text(encoding='utf-8'))
elements = {(e['type'], e['id']): e for e in reference['elements']}
relation = elements['relation', 19260956]
assert relation['version'] == boundary_src['properties']['osm_version']
outer = [elements['way', m['ref']] for m in relation['members'] if m['role'] == 'outer']
rings = [LineString([(elements['node', n]['lon'], elements['node', n]['lat']) for n in w['nodes']]) for w in outer]
api_geom = unary_union(list(polygonize(rings)))
assert api_geom.equals(shape(boundary_src['geometry']))
boundary = transform(shape(boundary_src['geometry']), TO_M, interleaved=False).buffer(.02)

edges = {f['properties']['edge_id']: f['properties'] for f in read_geojson('canh_dinh_tuyen')}
for name in ('canh_dinh_tuyen', 'lo_trinh', 'lo_trinh_qua_hem'):
    for f in read_geojson(name):
        geom = transform(shape(f['geometry']), TO_M, interleaved=False)
        assert geom.is_valid and boundary.covers(geom), name

links = {(int(r['edge_den']), int(r['edge_di'])): int(r['tinh_mot_lan_re']) for r in read_csv('chuyen_tiep')}
assert all(edges[a]['v'] == edges[b]['u'] for a, b in links)
assert all(edges[a]['u'] != edges[b]['v'] for a, b in links)
pairs = {r['cap']: (int(r['nut_dau']), int(r['nut_cuoi'])) for r in read_csv('cap_diem')}
assert len(pairs) == len({frozenset(p) for p in pairs.values()}) == 24
samples = read_csv('mau_doi_chieu')
assert len(samples) == len({r['nut_osm'] for r in samples}) == 24
assert all(not r['nhan_thuc_dia'] for r in samples)

baseline = read_csv('so_sanh')
assert len(baseline) == 48
sens = read_csv('do_nhay')
for penalty, rows in ((0, sens), (8, baseline), (20, sens)):
    network = nx.DiGraph()
    network.add_nodes_from(edges)
    network.add_weighted_edges_from((a, b, edges[b]['thoi_gian_gia_dinh_s'] + penalty * n) for (a, b), n in links.items())
    relevant = [r for r in rows if int(r.get('phat_re_s', 8)) == penalty]
    assert len(relevant) == 48
    for pid, (u, v) in pairs.items():
        starts = [e for e, d in edges.items() if d['u'] == u]
        targets = [e for e, d in edges.items() if d['v'] == v]
        network.add_weighted_edges_from(('S', e, edges[e]['thoi_gian_gia_dinh_s']) for e in starts)
        network.add_weighted_edges_from((e, 'T', 0) for e in targets)
        try:
            ref = nx.shortest_path_length(network, 'S', 'T', weight='weight')
        except nx.NetworkXNoPath:
            ref = None
        for r in [r for r in relevant if r['cap'] == pid]:
            actual = r['chi_phi_tuong_duong_s']
            assert ref is None if not actual else ref is not None and math.isclose(ref, float(actual), abs_tol=.15), (pid, penalty)
            if penalty == 8 and actual:
                ids = list(map(int, r['chuoi_edge_id'].split(';')))
                assert edges[ids[0]]['u'] == u and edges[ids[-1]]['v'] == v
                turns = sum(links[a, b] for a, b in zip(ids, ids[1:]))
                assert turns == int(r['so_lan_re'])
        network.remove_nodes_from(['S', 'T'])

gates = {f['properties']['nut_osm'] for f in read_geojson('diem_noi')}
proved = []
for r in read_csv('lo_trinh_qua_hem'):
    if r['ket_qua'] != 'có tuyến mẫu qua hẻm':
        continue
    u, v = pairs[r['cap']]
    ids = list(map(int, r['chuoi_edge_id'].split(';')))
    assert edges[ids[0]]['u'] == u and edges[ids[-1]]['v'] == v
    seen = [u] + [edges[i]['v'] for i in ids]
    assert len(seen) == len(set(seen))
    assert all((a, b) in links for a, b in zip(ids, ids[1:]))
    entrance = None
    found = False
    for i in ids:
        d = edges[i]
        if d['nhom'] != 'hem':
            entrance = None
            continue
        if entrance is None and d['u'] in gates:
            entrance = d['u']
        found |= entrance is not None and d['v'] in gates and d['v'] != entrance
    assert found
    proved.append(r['cap'])

assert set(proved) == {f['properties']['cap'] for f in read_geojson('lo_trinh_qua_hem')}
msg = (f'Kiểm chứng: polygon OSM API trùng bản gốc; các tuyến nằm trong ranh; '
       f'{len(pairs)} cặp × 3 mức phạt khớp với NetworkX; {len(proved)} tuyến qua hẻm kiểm tra được từng cạnh')
now = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(timespec='milliseconds')
with LOG.open('a', encoding='utf-8') as f:
    f.write(f'{now}\tINFO\t{msg}\n')
print(msg)
