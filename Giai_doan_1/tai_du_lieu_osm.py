"""Tải ranh và mạng đường OSM của phường Thạnh Mỹ Tây."""
import argparse
import hashlib
import json
import math
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from zipfile import ZIP_DEFLATED, ZipFile

import osmium
from shapely.geometry import LineString, mapping
from shapely.ops import polygonize_full, unary_union

ROOT = Path(__file__).resolve().parent
API = 'https://api.openstreetmap.org/api/0.6'
RELATION = 19260956
TZ = ZoneInfo('Asia/Ho_Chi_Minh')
PADDING = 0.002  # độ; giữ thêm dữ liệu quanh đường cắt ranh


def now():
    return datetime.now(TZ)


def checksum(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def log(folder, message):
    stamp = now().isoformat(timespec='seconds')
    with (folder / 'nhat_ky.tsv').open('a', encoding='utf-8') as f:
        f.write(f'{stamp}\t{message}\n')
    print(message, flush=True)


def download(url, target):
    log(target.parent, f'GET {url}')
    request = Request(url, headers={'User-Agent': 'ThanhMyTayResearch/1.0 (university research; one ward download)'})
    partial = target.with_suffix(target.suffix + '.part')
    try:
        with urlopen(request, timeout=90) as response, partial.open('wb') as f:
            shutil.copyfileobj(response, f)
            metadata = {'url': url, 'http_date': response.headers.get('Date'),
                        'downloaded_at': now().isoformat(timespec='seconds')}
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    metadata['sha256'] = checksum(target)
    metadata['bytes'] = target.stat().st_size
    log(target.parent, f"Đã tải {target.name}: {metadata['bytes']} byte; SHA-256 {metadata['sha256']}")
    return metadata


def boundary_from(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    objects = {(e['type'], e['id']): e for e in data['elements']}
    relation = objects['relation', RELATION]
    boundary = {}
    for role in ('outer', 'inner'):
        lines = []
        for m in relation['members']:
            if m['role'] != role:
                continue
            way = objects['way', m['ref']]
            nodes = [objects['node', n] for n in way['nodes']]
            lines.append(LineString([(n['lon'], n['lat']) for n in nodes]))
        polygons, cuts, dangles, invalid = polygonize_full(lines)
        if not (cuts.is_empty and dangles.is_empty and invalid.is_empty):
            raise ValueError(f'Ranh OSM có phần {role} chưa khép kín')
        boundary[role] = unary_union(list(polygons.geoms))
    geom = boundary['outer'].difference(boundary['inner'])
    if geom.is_empty or not geom.is_valid or geom.geom_type not in {'Polygon', 'MultiPolygon'}:
        raise ValueError('Polygon ranh OSM không hợp lệ')
    props = dict(relation['tags'], osm_relation_id=RELATION, osm_version=relation['version'],
                 osm_relation_timestamp=relation.get('timestamp'))
    return geom, props


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')


def write_features(path, features):
    write_json(path, {'type': 'FeatureCollection', 'features': features})


def feature(geom, props):
    return {'type': 'Feature', 'geometry': mapping(geom), 'properties': props}


def collect_roads(raw, polygon, staging):
    ways, required_nodes, features = set(), set(), []
    for obj in osmium.FileProcessor(raw, osmium.osm.NODE | osmium.osm.WAY).with_locations():
        if not obj.is_way() or 'highway' not in obj.tags or len(obj.nodes) < 2:
            continue
        coords = [(n.lon, n.lat) for n in obj.nodes]
        if len(set(coords)) < 2:
            continue
        clipped = LineString(coords).intersection(polygon)
        lines = [clipped] if clipped.geom_type in {'LineString', 'MultiLineString'} else [
            part for part in getattr(clipped, 'geoms', ()) if part.geom_type == 'LineString']
        if not lines or not any(line.length > 0 for line in lines):
            continue
        geom = unary_union(lines)
        ways.add(obj.id)
        required_nodes.update(n.ref for n in obj.nodes)
        features.append(feature(geom, dict(dict(obj.tags), osm_id=obj.id, osm_type='w')))
    if not ways:
        raise ValueError('Không tìm thấy way có thẻ highway giao với phường')
    write_features(staging / 'duong_giao_thong.geojson', features)
    count = 0
    with osmium.SimpleWriter(staging / 'thanh_my_tay.osm.pbf') as writer:
        for obj in osmium.FileProcessor(raw):
            restriction = (obj.is_relation() and obj.tags.get('type', '').startswith('restriction')
                           and any(m.type == 'w' and m.ref in ways for m in obj.members))
            if obj.is_node() and obj.id in required_nodes or obj.is_way() and obj.id in ways or restriction:
                writer.add(obj.replace(user='', uid=0, changeset=0))
                count += int(restriction)
    return len(ways), len(required_nodes), count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'data'/'thu_thap_osm'/now().strftime('%Y%m%d_%H%M%S'))
    folder = parser.parse_args().output_dir.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'nhat_ky.tsv').write_text('thoi_gian_utc_plus_7\tsu_kien\n', encoding='utf-8')
    try:
        relation = folder / 'ranh_api.json'
        relation_source = download(f'{API}/relation/{RELATION}/full.json', relation)
        polygon, props = boundary_from(relation)
        log(folder, f"Ranh relation {RELATION}, phiên bản {props['osm_version']}")
        left, bottom, right, top = polygon.bounds
        # Làm tròn ra ngoài để vùng yêu cầu luôn phủ đủ ranh và vùng đệm.
        bbox = [math.floor((left-PADDING)*1e6)/1e6, math.floor((bottom-PADDING)*1e6)/1e6,
                math.ceil((right+PADDING)*1e6)/1e6, math.ceil((top+PADDING)*1e6)/1e6]
        query = urlencode({'bbox': ','.join(f'{x:.6f}' for x in bbox)}, safe=',')
        raw = folder / 'mang_duong_bbox.osm'
        map_source = download(f'{API}/map?{query}', raw)
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            staging = Path(tmp)
            write_features(staging / 'ranh_gioi.geojson', [feature(polygon, props)])
            counts = collect_roads(raw, polygon, staging)
            write_json(staging / 'nguon.json', {
                'provider': 'OpenStreetMap API 0.6', 'license': 'ODbL 1.0',
                'relation': relation_source, 'relation_version': props['osm_version'],
                'bbox_wgs84': bbox, 'map': map_source,
                'way_count': counts[0], 'node_count': counts[1], 'restriction_count': counts[2],
            })
            checks = [f'{checksum(p)}  {p.name}\n' for p in sorted(staging.iterdir())]
            (staging/'SHA256SUMS.txt').write_text(''.join(checks), encoding='utf-8')
            archive = folder / 'Du_lieu_Thanh_My_Tay_OSM.zip'
            with ZipFile(archive, 'x', ZIP_DEFLATED) as z:
                for path in sorted(staging.iterdir()):
                    z.write(path, 'Thanh_My_Tay/'+path.name)
        log(folder, f'Đã xuất {counts[0]} way đường, {counts[1]} nút tham chiếu và {counts[2]} relation hạn chế rẽ')
        log(folder, f'Gói đầu vào: {archive.name}; SHA-256 {checksum(archive)}')
    except Exception as error:
        log(folder, f'Dừng vì lỗi: {error}')
        raise


if __name__ == '__main__':
    main()
