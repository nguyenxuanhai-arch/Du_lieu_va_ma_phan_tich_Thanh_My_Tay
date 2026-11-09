"""Phân tích dữ liệu bản đồ OSM tại phường Thạnh Mỹ Tây."""
import argparse
import csv
import hashlib
import heapq
import itertools
import json
import logging
import math
import random
import statistics
import tempfile
import time
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.ticker import FuncFormatter
import networkx as nx
import osmium
import osmnx as ox
from pyproj import Transformer
from shapely.geometry import LineString, Point, mapping, shape
from shapely import transform as transform_geometry

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data/clean'
LOG = ROOT / 'logs/nhat_ky.tsv'
ROADS = ['Xô Viết Nghệ Tĩnh', 'Điện Biên Phủ', 'Nguyễn Gia Trí', 'Ung Văn Khiêm']
SPEED = {'truc': 18, 'hem': 12, 'khac': 15}  # km/h, kịch bản giả định
DRIVABLE = set('trunk trunk_link primary primary_link secondary secondary_link tertiary tertiary_link residential living_street unclassified service'.split())
ACCESS_KEYS = ('motorcycle', 'motor_vehicle', 'vehicle', 'access')
ALLOWED = {'yes', 'designated', 'permissive', 'official'}
BLOCKED = {'no', 'private', 'destination', 'customers', 'delivery', 'permit', 'agricultural', 'forestry', 'discouraged', 'use_sidepath'}
BARRIERS = {'gate', 'lift_gate', 'swing_gate', 'bollard', 'block', 'chain', 'cycle_barrier', 'yes'}
TURN_ANGLE = 35
TO_M = Transformer.from_crs(4326, 32648, always_xy=True).transform
TO_DEG = Transformer.from_crs(32648, 4326, always_xy=True).transform


def transform(projection, geometry):
    return transform_geometry(geometry, projection, interleaved=False)


def log(msg):
    logging.info(msg)


def table(name, fields, rows):
    path = OUT / (name + '.csv')
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(fields.split('|'))
        writer.writerows(rows)


def geojson(name, features):
    path = OUT / (name + '.geojson')
    path.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False), encoding='utf-8')


def feature(geom, **props):
    return {'type': 'Feature', 'geometry': mapping(geom), 'properties': props}


def access(tags):
    return next((tags[k] for k in ACCESS_KEYS if k in tags), '')


def read_sources(archive):
    log('SHA-256 ZIP gốc %s' % hashlib.sha256(archive.read_bytes()).hexdigest())
    with zipfile.ZipFile(archive) as z, tempfile.TemporaryDirectory() as tmp:
        base = 'Thanh_My_Tay/'
        checks = z.read(base + 'SHA256SUMS.txt').decode().splitlines()
        for line in checks:
            expected, name = line.split(maxsplit=1)
            assert hashlib.sha256(z.read(base + name.strip())).hexdigest() == expected, name
        source = 'Geofabrik · 02/11/2026 UTC'
        if base + 'nguon.json' in z.namelist():
            provenance = json.loads(z.read(base + 'nguon.json'))
            date = datetime.fromisoformat(provenance['map']['downloaded_at'])
            source = f'OSM API · tải {date:%d/%m/%Y} (UTC+07)'
        boundary_data = json.loads(z.read(base + 'ranh_gioi.geojson'))
        way_ids = {f['properties']['osm_id'] for f in json.loads(z.read(base + 'duong_giao_thong.geojson'))['features']}
        path = Path(tmp) / 'input.pbf'
        path.write_bytes(z.read(base + 'thanh_my_tay.osm.pbf'))
        nodes, ways, relations = {}, {}, []
        for obj in osmium.FileProcessor(path):
            tags = dict(obj.tags)
            if obj.is_node():
                assert obj.id not in nodes
                nodes[obj.id] = (TO_M(obj.lon, obj.lat), tags)
            elif obj.is_way() and 'highway' in tags and obj.id in way_ids:
                assert obj.id not in ways
                ways[obj.id] = ([n.ref for n in obj.nodes], tags)
            elif obj.is_relation() and tags.get('type', '').startswith('restriction'):
                relations.append((obj.id, tags, [(m.type, m.ref, m.role) for m in obj.members]))
    assert way_ids == ways.keys() and all(n in nodes for refs, _ in ways.values() for n in refs)
    boundary = transform(TO_M, shape(boundary_data['features'][0]['geometry']))
    assert boundary.is_valid and not boundary.is_empty
    log(f'Khớp {len(checks)} mã SHA-256; đọc {len(nodes)} node, {len(ways)} way đường, {len(relations)} relation cấm rẽ')
    return boundary, nodes, ways, relations, source


def restrictions(relations):
    forbidden, only = defaultdict(set), defaultdict(set)
    uncertain, retained, audit = set(), set(), []
    for rid, tags, members in relations:
        from_ids = [ref for kind, ref, role in members if kind == 'w' and role == 'from']
        to_ids = [ref for kind, ref, role in members if kind == 'w' and role == 'to']
        via = [(kind, ref) for kind, ref, role in members if role == 'via']
        label = tags.get('restriction:motorcycle', tags.get('restriction:motor_vehicle', tags.get('restriction', '')))
        if 'motorcycle' in tags.get('except', '').split(';') and 'restriction:motorcycle' not in tags:
            status = 'ngoại lệ xe máy'
        elif (len(via) == 1 and via[0][0] == 'n' and from_ids and to_ids
              and label.startswith(('only_', 'no_')) and not any('conditional' in k for k in tags)):
            via_id = via[0][1]
            retained.add(via_id)
            for a in from_ids:
                (only if label.startswith('only_') else forbidden)[a, via_id].update(to_ids)
            status = 'áp dụng tại nút'
        else:
            via_ways = {ref for kind, ref in via if kind == 'w'}
            uncertain.update(via_ways or from_ids)
            status = 'tạm loại way via/from khỏi mô hình'
        audit.append((rid, label or tags.get('restriction:conditional', ''), tags.get('except', ''), status))
    table('han_che_re', 'relation_osm|han_che|ngoai_le|xu_ly', audit)
    log(f'Hạn chế rẽ theo relation: {dict(Counter(r[3] for r in audit))}; way phòng ngừa: {sorted(uncertain)}')
    return forbidden, only, uncertain, retained


def line_parts(geom):
    if geom.geom_type == 'LineString':
        if geom.length > 1e-5:
            yield geom
    elif hasattr(geom, 'geoms'):
        for part in geom.geoms:
            yield from line_parts(part)


def make_graph(boundary, nodes, ways, uncertain, retained):
    graph = nx.MultiDiGraph(crs='EPSG:32648')
    geo_edges, review = [], []
    events = Counter()
    synthetic = {}

    def node_key(xy, a, b, way):
        for n in (a, b):
            if math.dist(nodes[n][0], xy) < 1e-5:
                return n
        key = (way, round(xy[0], 6), round(xy[1], 6))
        return synthetic.setdefault(key, -1 - len(synthetic))

    for wid, (refs, tags) in sorted(ways.items()):
        hwy = tags['highway']
        name = ' '.join(tags.get('name', '').split())
        kind = 'truc' if name.casefold() in {s.casefold() for s in ROADS} else (
            'hem' if name.casefold().startswith('hẻm ') or tags.get('service') == 'alley' else 'khac')
        permit = access(tags)
        direction = tags.get('oneway:motorcycle', tags.get('oneway:motor_vehicle', tags.get('oneway', '')))
        conditional = [k for k in tags if k.endswith(':conditional') and k.split(':')[0] in {*ACCESS_KEYS, 'oneway'} and
                       (k.split(':')[0] != 'oneway' or 'motorcar' not in k and 'bicycle' not in k)]
        directional_access = any(k.split(':')[0] in ACCESS_KEYS and k.endswith((':forward', ':backward')) for k in tags)
        if wid in uncertain:
            status = 'relation via-way chưa giải mã'
        elif permit in BLOCKED or permit and permit not in ALLOWED:
            status = 'hạn chế tiếp cận'
        elif conditional or directional_access or direction not in {'', 'yes', 'true', '1', '-1', 'no', 'false', '0'}:
            status = 'điều kiện hoặc chiều chưa giải mã'
        elif hwy not in DRIVABLE and not (hwy in {'footway', 'path', 'pedestrian'} and tags.get('motorcycle') in ALLOWED):
            status = 'loại đường ngoài mô hình'
        elif tags.get('service') in {'driveway', 'parking_aisle', 'drive-through', 'emergency_access'} and tags.get('motorcycle') not in ALLOWED:
            status = 'lối vào riêng hoặc đường nội bộ'
        elif tags.get('motorroad') == 'yes' and tags.get('motorcycle') not in ALLOWED:
            status = 'motorroad thiếu xác nhận xe máy'
        else:
            status = 'giữ'
        events[status] += 1
        length_in = 0.0
        seen = set()
        for a, b in itertools.pairwise(refs):
            pa, pb = nodes[a][0], nodes[b][0]
            if a == b or pa == pb:
                events['đoạn dài 0'] += 1
                continue
            segment = LineString([pa, pb])
            for part in line_parts(segment.intersection(boundary)):
                if math.dist(part.coords[0], pa) > math.dist(part.coords[-1], pa):
                    part = part.reverse()
                u, v = (node_key(xy, a, b, wid) for xy in (part.coords[0], part.coords[-1]))
                key = min(u, v), max(u, v)
                if key in seen:
                    events['đoạn lặp trong cùng way'] += 1
                    continue
                seen.add(key)
                length_in += part.length
                if status != 'giữ':
                    continue
                for n, xy in zip((u, v), (part.coords[0], part.coords[-1])):
                    if n not in graph:
                        nt = nodes[n][1] if n > 0 else {}
                        attrs = dict(x=xy[0], y=xy[1], barrier=nt.get('barrier', ''), stop=bool(
                            nt.get('barrier') in BARRIERS and access(nt) not in ALLOWED or access(nt) in BLOCKED))
                        if n < 0 or n in retained or attrs['stop']:
                            attrs['keep'] = True
                        graph.add_node(n, **attrs)
                attrs = dict(osmid=wid, kind=kind, name=name, highway=hwy, length=part.length, access=permit)
                if direction != '-1':
                    graph.add_edge(u, v, **attrs)
                if direction not in {'yes', 'true', '1'} and not (not direction and tags.get('junction') == 'roundabout'):
                    graph.add_edge(v, u, **attrs)
                geo_edges.append((kind, part))
        review.append((wid, name, hwy, kind, permit, direction, status, round(length_in, 2),
                       json.dumps(tags, ensure_ascii=False, sort_keys=True)))
    table('kiem_tra_way_osm', 'way_osm|ten|highway|nhom|access_uu_tien|oneway_khai_bao|xu_ly|chieu_dai_trong_ranh_m|the_osm', review)
    table('lam_sach', 'nhom_xu_ly|so_luong', sorted(events.items()))
    log(f'Làm sạch: {dict(events)}; {len(graph)} nút, {graph.number_of_edges()} cạnh có hướng trước đơn giản hóa')
    g = ox.simplification.simplify_graph(graph, node_attrs_include=['keep'], edge_attrs_differ=['osmid'], remove_rings=False)
    assert math.isclose(sum(d['length'] for *_, d in graph.edges(data=True)),
                        sum(d['length'] for *_, d in g.edges(data=True)), rel_tol=1e-10)
    log(f'OSMnx đơn giản hóa: {len(g)} nút, {g.number_of_edges()} cạnh có hướng; tổng chiều dài có hướng bảo toàn')
    return g, geo_edges, events


def build_edges(g):
    edges, outgoing, features = [], defaultdict(list), []
    for u, v, k, data in sorted(g.edges(keys=True, data=True)):
        geom = data.get('geometry') or LineString([(g.nodes[n]['x'], g.nodes[n]['y']) for n in (u, v)])
        start, end = geom.coords[0], geom.coords[-1]
        assert math.dist(start, (g.nodes[u]['x'], g.nodes[u]['y'])) < 0.01
        assert math.dist(end, (g.nodes[v]['x'], g.nodes[v]['y'])) < 0.01
        assert abs(geom.length - data['length']) < 0.01
        edge = dict(data, u=u, v=v, key=k, geometry=geom, seconds=data['length'] * 3.6 / SPEED[data['kind']])
        i = len(edges)
        outgoing[u].append(i)
        edges.append(edge)
        features.append(feature(transform(TO_DEG, geom), edge_id=i, u=u, v=v, way_osm=edge['osmid'],
                                nhom=edge['kind'], ten=edge['name'], highway=edge['highway'],
                                chieu_dai_m=round(edge['length'], 3), thoi_gian_gia_dinh_s=round(edge['seconds'], 3)))
    geojson('canh_dinh_tuyen', features)
    return edges, outgoing


def turn(a, b):
    p, q = a['geometry'].coords[-2:]
    r, s = b['geometry'].coords[:2]
    bearing_a = math.atan2(q[1]-p[1], q[0]-p[0])
    bearing_b = math.atan2(s[1]-r[1], s[0]-r[0])
    angle = abs(math.degrees(math.remainder(bearing_b-bearing_a, 2*math.pi)))
    return int(angle >= TURN_ANGLE)


def transitions(g, edges, outgoing, forbidden, only):
    result = {}
    for i, a in enumerate(edges):
        via = a['v']
        rule = a['osmid'], via
        result[i] = []
        if g.nodes[via]['stop']:
            continue
        for j in outgoing[via]:
            b = edges[j]
            if b['v'] == a['u'] or b['osmid'] in forbidden.get(rule, ()):
                continue
            if rule in only and b['osmid'] not in only[rule]:
                continue
            result[i].append((j, turn(a, b)))
    log(f'Áp dụng quy tắc theo cạnh đến: {sum(map(len, result.values()))} chuyển tiếp; {sum(g.nodes[n]["stop"] for n in g)} nút chắn')
    return result


def topology(g, edges, boundary):
    undirected = nx.Graph()
    alley = nx.Graph()
    attached = defaultdict(set)
    main_nodes = defaultdict(set)
    for e in edges:
        u, v = e['u'], e['v']
        undirected.add_edge(u, v)
        if e['kind'] == 'hem':
            alley.add_edge(u, v)
        elif e['kind'] == 'truc':
            name = next(r for r in ROADS if r.casefold() == e['name'].casefold())
            main_nodes[name].update((u, v))
    for name, ids in main_nodes.items():
        for n in ids & alley.nodes:
            if not g.nodes[n]['stop']:
                attached[n].add(name)
    open_nodes = {n for n in g if not g.nodes[n]['stop']}
    corridor_graph = alley.subgraph(open_nodes)
    components = sorted(nx.connected_components(corridor_graph), key=lambda c: (-len(c), min(c)))
    candidate_through, cluster_rows, cluster_features = set(), [], []
    cluster_by_node = {}
    for i, comp in enumerate(components, 1):
        ids = comp & attached.keys()
        names = sorted(set().union(*(attached[n] for n in ids)))
        if len(ids) >= 2:
            candidate_through.update(ids)
        cluster_rows.append((i, len(comp), len(ids), len(names), '; '.join(names)))
        cluster_by_node.update(dict.fromkeys(comp, i))
    for n, names in sorted(attached.items()):
        xy = (g.nodes[n]['x'], g.nodes[n]['y'])
        cluster_features.append(feature(transform(TO_DEG, Point(xy)), nut_osm=n, truc='; '.join(sorted(names)),
                                        cum=cluster_by_node.get(n)))
    table('cum_hem', 'ma_cum|so_nut|so_diem_noi_4_truc|so_truc_khac_nhau|ten_truc', cluster_rows)
    geojson('diem_noi', cluster_features)
    counts = [(r, sum(r in names for names in attached.values())) for r in ROADS]
    table('ket_noi_truc', 'truc_duong|so_nut_noi_hem', counts)
    dead, edge_nodes = set(), set()
    for n in alley:
        xy = (g.nodes[n]['x'], g.nodes[n]['y'])
        if undirected.degree(n) == 1 and not g.nodes[n]['stop']:
            if n < 0 or boundary.boundary.distance(Point(xy)) <= 15:
                edge_nodes.add(n)
            else:
                dead.add(n)
    rng = random.Random(20261109)
    sample = [(n, label) for label, candidates in (
        ('nghi đầu cụt', dead), ('điểm vào cụm có từ hai đấu nối', candidate_through))
        for n in rng.sample(sorted(candidates), min(len(candidates), 12))]
    assert 20 <= len(sample) <= 30
    flags = []
    for status, subset in [('nghi đầu cụt', dead), ('đầu mạng sát ranh', edge_nodes)]:
        for n in sorted(subset):
            lon, lat = TO_DEG(g.nodes[n]['x'], g.nodes[n]['y'])
            flags.append(feature(Point(lon, lat), nut=n, nhan_mo_hinh=status))
    geojson('dau_mut_hem', flags)
    points, rows = [], []
    for i, (n, label) in enumerate(sample, 1):
        lon, lat = TO_DEG(g.nodes[n]['x'], g.nodes[n]['y'])
        names = sorted({e['name'] for e in edges if e['kind'] == 'hem' and e['name'] and n in (e['u'], e['v'])})
        rows.append((f'HT{i:02}', n, round(lon, 8), round(lat, 8), label, '; '.join(names), '', '', '', '', ''))
        points.append(feature(Point(lon, lat), ma=f'HT{i:02}', nut_osm=n, nhan_mo_hinh=label))
    table('mau_doi_chieu', 'ma|nut_osm|kinh_do|vi_do|nhan_mo_hinh|ten_hem|ngay_gio_khao_sat|diem_vao_ra|bien_cam_cong_chan|nhan_thuc_dia|ghi_chu', rows)
    geojson('mau_doi_chieu', points)
    log(f'NetworkX: {len(components)} cụm hẻm, {len(attached)} nút đấu nối; {len(dead)} nghi đầu cụt, {len(edge_nodes)} sát ranh; chọn {len(sample)} vị trí; cắt 0 nhánh')
    return main_nodes, set(attached), counts, cluster_rows, sample, len(dead), len(edge_nodes)


def choose_pairs(g, main_nodes):
    rng = random.Random(20261109)
    pairs, used = [], set()
    for a, b in itertools.combinations(ROADS, 2):
        xs, ys = (sorted(n for n in main_nodes[r] if n > 0 and not g.nodes[n]['stop']) for r in (a, b))
        pool = []
        for u, v in itertools.product(xs, ys):
            distance = math.hypot(g.nodes[u]['x']-g.nodes[v]['x'], g.nodes[u]['y']-g.nodes[v]['y'])
            if distance >= 200:
                pool.append((u, v))
        rng.shuffle(pool)
        chosen = 0
        for u, v in pool:
            if frozenset((u, v)) in used:
                continue
            used.add(frozenset((u, v)))
            if chosen % 2:
                pairs.append((b, a, v, u))
            else:
                pairs.append((a, b, u, v))
            chosen += 1
            if chosen == 4:
                break
        assert chosen == 4, (a, b)
    return pairs


def search(g, edges, outgoing, links, source, target, penalty, use_astar=False, gateways=None):
    """Mở rộng theo cạnh đến, để phạt góc rẽ và kiểm tra relation."""
    # Với RQ2, phase là nút vào hẻm; 0 là chưa vào, None là đã ra ở nút khác.
    start = (-1, 0)
    dist, prev = {start: 0.0}, {}
    order = itertools.count()
    queue = [(0.0, next(order), 0.0, start)]
    expanded = 0
    goal_xy = g.nodes[target]['x'], g.nodes[target]['y']
    while queue:
        _, _, cost, state = heapq.heappop(queue)
        if cost > dist[state]:
            continue
        i, phase = state
        u = edges[i]['v'] if i >= 0 else source
        expanded += 1
        if u == target and (gateways is None or phase is None):
            route = []
            while state != start:
                route.append(state[0])
                state = prev[state]
            return cost, list(reversed(route)), expanded
        options = links[i] if i >= 0 else [(j, 0) for j in outgoing[source]]
        for j, r in options:
            edge = edges[j]
            v = edge['v']
            next_phase = phase
            if gateways is not None and phase is not None:
                if edge['kind'] == 'hem':
                    if phase == 0 and u in gateways:
                        next_phase = u
                    if next_phase != 0 and v != next_phase and v in gateways:
                        next_phase = None
                else:
                    next_phase = 0
            new = j, next_phase
            candidate = cost + edge['seconds'] + r * penalty
            if candidate < dist.get(new, math.inf):
                dist[new], prev[new] = candidate, state
                estimate = 0.0
                if use_astar:
                    estimate = math.dist((g.nodes[v]['x'], g.nodes[v]['y']), goal_xy) * 3.6 / max(SPEED.values())
                heapq.heappush(queue, (candidate+estimate, next(order), candidate, new))
    return None, [], expanded


def measure(g, edges, outgoing, links, main_nodes, gateways):
    pairs = choose_pairs(g, main_nodes)
    test_rows, od_rows, alternative_rows, sensitivity, lines, alternative_lines = [], [], [], [], [], []
    for n, (a, b, u, v) in enumerate(pairs, 1):
        pid = f'OD{n:02}'
        lon1, lat1 = TO_DEG(g.nodes[u]['x'], g.nodes[u]['y'])
        lon2, lat2 = TO_DEG(g.nodes[v]['x'], g.nodes[v]['y'])
        od_rows.append((pid, a, b, u, v, lon1, lat1, lon2, lat2))
        alternative_cost, alternative, _ = search(g, edges, outgoing, links, u, v, 8, gateways=gateways)
        visited = [u] + [edges[j]['v'] for j in alternative]
        no_loop = len(visited) == len(set(visited))
        status = ('có tuyến mẫu qua hẻm' if no_loop else 'ứng viên lặp nút') if alternative else 'không tìm thấy'
        alternative_rows.append((pid, status, round(alternative_cost, 4) if alternative else '',
                                 ';'.join(map(str, alternative))))
        if alternative and no_loop:
            coords = list(edges[alternative[0]]['geometry'].coords)
            for j in alternative[1:]:
                coords.extend(list(edges[j]['geometry'].coords)[1:])
            alternative_lines.append(feature(transform(TO_DEG, LineString(coords)), cap=pid))
        for penalty in (0, 8, 20):
            pair_results = []
            for algorithm in ('Dijkstra', 'A*'):
                args = (g, edges, outgoing, links, u, v, penalty, algorithm == 'A*')
                cost, route, expanded = search(*args)
                pair_results.append(cost)
                if cost is None:
                    total_m = seconds = turns = alley_m = None
                else:
                    assert edges[route[0]]['u'] == u and edges[route[-1]]['v'] == v
                    turns = sum(dict(links[i])[j] for i, j in itertools.pairwise(route))
                    seconds = sum(edges[j]['seconds'] for j in route)
                    assert math.isclose(seconds + penalty * turns, cost, rel_tol=1e-10)
                    total_m = sum(edges[j]['length'] for j in route)
                    alley_m = sum(edges[j]['length'] for j in route if edges[j]['kind'] == 'hem')
                if penalty != 8:
                    sensitivity.append((pid, algorithm, penalty, cost, total_m, seconds, turns, alley_m))
                    continue
                timings = []
                # Đo thêm theo từng lượt luân phiên phía dưới.
                test_rows.append([pid, algorithm, cost, total_m, seconds, turns, alley_m, expanded, timings, route])
                if route:
                    coords = []
                    for j in route:
                        coords.extend(list(edges[j]['geometry'].coords)[bool(coords):])
                    lines.append(feature(transform(TO_DEG, LineString(coords)), cap=pid, thuat_toan=algorithm,
                                         chi_phi_s=cost, so_re=turns, chieu_dai_m=total_m))
            x, y = pair_results
            assert (x is None and y is None) or (x is not None and y is not None and math.isclose(x, y, rel_tol=1e-10))
        r1, r2 = test_rows[-2:]
        for iteration in range(11):
            for r in ((r1, r2) if iteration % 2 == 0 else (r2, r1)):
                t0 = time.perf_counter_ns()
                _, _, _ = search(g, edges, outgoing, links, u, v, 8, r[1] == 'A*')
                r[8].append((time.perf_counter_ns()-t0) / 1000)
    table('cap_diem', 'cap|truc_xuat_phat|truc_dich|nut_dau|nut_cuoi|kinh_do_dau|vi_do_dau|kinh_do_cuoi|vi_do_cuoi', od_rows)
    table('lo_trinh_qua_hem', 'cap|ket_qua|chi_phi_tuong_duong_s|chuoi_edge_id', alternative_rows)
    fields = 'cap|thuat_toan|chi_phi_tuong_duong_s|chieu_dai_m|thoi_gian_gia_dinh_s|so_lan_re|chieu_dai_hem_m|trang_thai_da_xet|trung_vi_xu_ly_us|chuoi_edge_id'
    table('so_sanh', fields, ([*r[:8], round(statistics.median(r[8]), 2), ';'.join(map(str, r[9]))] for r in test_rows))
    table('luot_do', 'cap|thuat_toan|luot|thoi_gian_xu_ly_us',
          ((r[0], r[1], i, round(t, 2)) for r in test_rows for i, t in enumerate(r[8], 1)))
    table('do_nhay', 'cap|thuat_toan|phat_re_s|chi_phi_tuong_duong_s|chieu_dai_m|thoi_gian_gia_dinh_s|so_lan_re|chieu_dai_hem_m', sensitivity)
    geojson('lo_trinh', lines)
    geojson('lo_trinh_qua_hem', alternative_lines)
    log(f'Đã chạy {len(pairs)} cặp với 3 mức phạt, 11 lượt đo mỗi thuật toán/cặp; kiểm tra chi phí hai thuật toán khớp')
    return test_rows, od_rows, alternative_rows, lines


def make_figures(boundary, geometry, g, gateways, counts, results, alternative, routes, dst, provenance):
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'svg.fonttype': 'none'})
    colors = {'truc': '#1e3a62', 'hem': '#c34522', 'khac': '#c2c7cc'}
    labels = {'truc': 'Bốn trục nghiên cứu', 'hem': 'Hẻm theo thẻ hoặc tên OSM', 'khac': 'Đường khác trong mô hình'}
    source = f'© OpenStreetMap contributors · {provenance}'

    def map_base(title, subtitle):
        fig, ax = plt.subplots(figsize=(9.2, 7.2), layout='constrained')
        ax.set_aspect('equal')
        fig.suptitle(title, fontsize=16, weight='bold')
        ax.set_title(subtitle, fontsize=10, loc='left', pad=8)
        for line in line_parts(boundary.boundary):
            ax.plot(*line.xy, color='#29313b', lw=1.1, linestyle='--', label='Ranh OSM' if not ax.lines else None)
        for kind in ('khac', 'truc', 'hem'):
            ax.add_collection(LineCollection([list(line.coords) for cat, line in geometry if kind == cat],
                                             colors=colors[kind], linewidths=0.75 if kind == 'khac' else 1.2, label=labels[kind]))
        x0, y0, x1, y1 = boundary.bounds
        ax.set_xlim(x0-100, x1+120)
        ax.set_ylim(y0-120, y1+100)
        ax.annotate('N', (0.96, 0.92), (0.96, 0.99), xycoords='axes fraction', ha='center',
                    arrowprops={'arrowstyle': '<-', 'color': '#29313b'})
        ax.plot([x0, x0+500], [y0-65]*2, color='#29313b', lw=2)
        ax.text(x0+250, y0-45, '500 m', ha='center', fontsize=8)
        ax.set_axis_off()
        fig.text(0.012, 0.007, source, fontsize=8, color='#495565')
        return fig, ax

    def save(fig, name):
        fig.savefig(dst / (name + '.png'), dpi=200)
        plt.close(fig)

    fig, ax = map_base('Mạng hẻm và các điểm đấu nối tại Thạnh Mỹ Tây',
                       'Vị trí trên đồ thị OSM sau lọc cho mô hình xe máy')
    ordered = sorted(gateways)
    ax.scatter([g.nodes[n]['x'] for n in ordered], [g.nodes[n]['y'] for n in ordered],
               s=19, facecolor='#fff', edgecolor='#692113', linewidth=0.9, label='Điểm đấu nối', zorder=5)
    ax.legend(loc='upper right', bbox_to_anchor=(0.91, 1.0), frameon=True, fontsize=8)
    save(fig, 'Hinh_1_mang_hem_va_dau_noi')

    good = {r[0] for r in alternative if r[1] == 'có tuyến mẫu qua hẻm'}
    first = next((f for f in routes if f['properties']['chieu_dai_m'] and f['properties']['thuat_toan'] == 'Dijkstra'
                  and any(r[0] == f['properties']['cap'] and r[1] == 'Dijkstra' and r[6] for r in results)),
                 routes[0] if routes else None)
    if first:
        pid = first['properties']['cap']
        fig, ax = map_base(f'Lộ trình mô hình cho cặp {pid}', 'Chi phí kết hợp thời gian giả định và số lần rẽ')
        ln = transform(TO_M, shape(first['geometry']))
        for line in ax.lines:
            line.set_alpha(0.5)
        for coll in ax.collections:
            coll.set_alpha(0.4)
        ax.plot(*ln.xy, color='#115abe', lw=3, label='Tuyến Dijkstra', zorder=6)
        ax.scatter(*ln.coords[0], color='#16774b', s=38, label='Xuất phát', zorder=7)
        ax.scatter(*ln.coords[-1], color='#a82636', s=38, marker='s', label='Đích', zorder=7)
        ax.legend(loc='upper right', bbox_to_anchor=(0.91, 1.0), frameon=True, fontsize=8)
        save(fig, 'Hinh_2_vi_du_lo_trinh')

    fig, ax = plt.subplots(figsize=(8.7, 4.2), layout='constrained')
    xs = [n for _, n in counts]
    bars = ax.barh([r for r, _ in counts], xs, color='#285887')
    ax.bar_label(bars, padding=5)
    ax.set_xlim(0, max(xs)+4)
    ax.invert_yaxis()
    ax.set_xlabel('Số nút chung với hẻm')
    ax.set_title('Số điểm đấu nối hẻm theo trục đường', loc='left', weight='bold')
    save(fig, 'Hinh_3_dau_noi_theo_truc')

    solved = [r for r in results if r[2] is not None]
    if solved:
        fig, ax = plt.subplots(figsize=(8.7, 4.4), layout='constrained')
        ax.boxplot([[r[7] for r in solved if r[1] == a] for a in ('Dijkstra', 'A*')],
                   tick_labels=['Dijkstra', 'A*'], orientation='horizontal', patch_artist=True,
                   boxprops={'facecolor': '#d7e5f3'}, medianprops={'color': '#b74424', 'linewidth': 2})
        ax.xaxis.set_major_formatter(FuncFormatter(lambda n, _: f'{n:,.0f}'.replace(',', '.')))
        ax.set_xlabel('Số trạng thái đã xét mỗi cặp')
        ax.set_title(f'Số trạng thái tìm kiếm trên {len(solved)//2} cặp có tuyến', loc='left', weight='bold')
        save(fig, 'Hinh_4_trang_thai_tim_kiem')
    return good


def main():
    global OUT, LOG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='ZIP dữ liệu từ tai_du_lieu_osm.py')
    parser.add_argument('--run-dir', type=Path, help='Thư mục riêng cho bảng, hình và nhật ký')
    args = parser.parse_args()
    if args.archive is not None and args.run_dir is None:
        parser.error('--archive yêu cầu --run-dir để tách riêng kết quả')
    archive = args.archive or ROOT / 'data/raw/Du_lieu_Thanh_My_Tay_OSM.zip'
    run_dir = args.run_dir.resolve() if args.run_dir else ROOT
    if args.run_dir:
        run_dir.mkdir(parents=True, exist_ok=False)
    OUT = run_dir / 'data/clean'
    LOG = run_dir / 'logs/nhat_ky.tsv'
    figures = run_dir / 'figures'
    OUT.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter('%(asctime)s\t%(levelname)s\t%(message)s')
    fmt.formatTime = lambda record, datefmt=None: datetime.fromtimestamp(
        record.created, ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(timespec='milliseconds')
    handler = logging.FileHandler(LOG, encoding='utf-8')
    handler.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    log(f'Bắt đầu lượt phân tích; OSMnx {ox.__version__}, NetworkX {nx.__version__}; xuất cả lớp đầu mút và tuyến qua hẻm')
    boundary, nodes, ways, rel, source = read_sources(archive)
    log(f'Nguồn bản đồ: {source}')
    forbidden, only, uncertain, retained = restrictions(rel)
    g, geometry, events = make_graph(boundary, nodes, ways, uncertain, retained)
    edges, outgoing = build_edges(g)
    links = transitions(g, edges, outgoing, forbidden, only)
    table('chuyen_tiep', 'edge_den|edge_di|tinh_mot_lan_re',
          ((a, b, r) for a, choices in links.items() for b, r in choices))
    main_nodes, gateways, counts, clusters, sample, dead, near_edge = topology(g, edges, boundary)
    results, od_rows, alternative, routes = measure(g, edges, outgoing, links, main_nodes, gateways)
    good = make_figures(boundary, geometry, g, gateways, counts, results, alternative, routes, figures, source)
    totals = {'way_osm': len(ways), 'way_giu': events['giữ'], 'nut': len(g), 'canh_co_huong': len(edges),
              'cum_hem': len(clusters), 'cum_co_tu_hai_dau_noi': sum(r[2] >= 2 for r in clusters),
              'cum_noi_tu_hai_truc': sum(r[3] >= 2 for r in clusters),
              'dau_noi_khac_nhau': len(gateways), 'dau_noi_theo_truc': dict(counts),
              'nghi_dau_cut': dead, 'dau_cut_sat_ranh': near_edge, 'vi_tri_doi_chieu': len(sample),
              'nhanh_cat': 0, 'cap_diem': len(od_rows), 'cap_co_tuyen': sum(r[2] is not None for r in results)//2,
              'cap_co_tuyen_mau_qua_hem': len(good), 'trang_thai_tuyen_qua_hem': dict(Counter(r[1] for r in alternative)),
              'theo_thuat_toan': {}}
    for a in ('Dijkstra', 'A*'):
        rows = [r for r in results if r[1] == a and r[2] is not None]
        if rows:
            totals['theo_thuat_toan'][a] = {'trung_vi_trang_thai': statistics.median(r[7] for r in rows),
                                           'trung_vi_xu_ly_us': round(statistics.median(statistics.median(r[8]) for r in rows), 2),
                                           'cap_tuyen_toi_uu_co_hem': sum(r[6] > 0 for r in rows)}
    (OUT / 'tong_hop.json').write_text(json.dumps(totals, ensure_ascii=False, indent=2), encoding='utf-8')
    log(f'Đã xuất bảng, lớp GeoJSON, {len(list(figures.glob("*.png")))} hình và thống kê tổng hợp')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logging.exception('Phân tích dừng vì lỗi')
        raise
