"""CPU-only, standard-library CAD metadata/text fallback. Never loads model code."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import urllib.parse
import urllib.request

MAX_BYTES = 8 * 1024 * 1024
ROOT = Path('E:/OneLine_diffusion/cad_conditioning')
MANIFEST = Path(__file__).with_name('assets.json')
# Trust policy is code-reviewed, not supplied by a remote manifest.
ALLOW = {
    'iamdarshg/drone-arm': {
        'hardware/motor_release/rotor_bell.step',
        'hardware/motor_release/stator_housing.step',
    },
    'iamdarshg/drone-mech': {
        'highspeed_edf/deliverables/phase15_geometry/step/lifting_wing_left_sector_with_duct_and_elevon_reliefs.step',
    },
}


def validate(asset):
    if asset['repo'] not in ALLOW or asset['path'] not in ALLOW[asset['repo']]:
        raise ValueError('Repository/path not allowlisted')
    if not re.fullmatch(r'[0-9a-f]{40}', asset['commit']):
        raise ValueError('A full pinned commit is required')
    if not re.fullmatch(r'[0-9a-f]{64}', asset['sha256']):
        raise ValueError('A SHA256 digest is required')
    if not isinstance(asset['size'], int) or not 0 < asset['size'] <= MAX_BYTES:
        raise ValueError('Invalid asset size')
    if not re.fullmatch(r'[a-z0-9_]{1,64}', asset['id']):
        raise ValueError('Invalid asset id')
    if not re.fullmatch(r'[A-Za-z0-9 ,.-]{1,120}', asset['subject']):
        raise ValueError('Subject must be reviewed plain descriptive text')
    return asset


def verify(data, asset):
    validate(asset)
    if len(data) != asset['size'] or hashlib.sha256(data).hexdigest() != asset['sha256']:
        raise ValueError('Asset size/hash mismatch; no automatic approval or normalization')
    return data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect refused')


def request(url, limit):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'api.github.com', 'raw.githubusercontent.com'}:
        raise ValueError('Only public GitHub HTTPS endpoints are permitted')
    # No environment credentials, git credential helpers, cookies, proxies or executable downloads.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    req = urllib.request.Request(url, headers={'User-Agent': 'OneLine-CAD-provenance/1', 'Accept': 'application/vnd.github+json'})
    with opener.open(req, timeout=20) as response:
        if int(response.headers.get('Content-Length', '0')) > limit:
            raise ValueError('Download too large')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Download too large')
    return data


def raw_url(asset):
    validate(asset)
    return f"https://raw.githubusercontent.com/{asset['repo']}/{asset['commit']}/{asset['path']}"


def e_path(path):
    path = Path(path).resolve()
    if path.drive.upper() != 'E:' or not Path('E:/').is_dir():
        raise ValueError('Bulk/output storage must be on available E:')
    return path


def store(data, digest, root=ROOT):
    root = e_path(root)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / (digest + '.cad')
    if dest.exists():
        if dest.read_bytes() != data:
            raise ValueError('Existing immutable cache entry differs')
    else:
        with dest.open('xb') as handle:
            handle.write(data)
    return dest


def metadata(data, suffix):
    """Conservative syntax metadata, not a CAD kernel or geometric validity test."""
    if len(data) > MAX_BYTES:
        raise ValueError('CAD too large')
    if suffix.lower() in {'.step', '.stp'}:
        text = data.decode('ascii', errors='strict')
        if not text.lstrip().startswith('ISO-10303-21;') or 'END-ISO-10303-21;' not in text:
            raise ValueError('Not a complete STEP exchange file')
        # Never copy arbitrary file labels/comments into a model prompt.
        stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
        stripped = re.sub(r"'(?:''|[^'])*'", "''", stripped)
        count = lambda name: len(re.findall(r'\b' + name + r'\s*\(', stripped))
        return {'format': 'STEP', 'manifold_solid_brep_entities': count('MANIFOLD_SOLID_BREP'),
                'advanced_face_entities': count('ADVANCED_FACE'),
                'units_hint': 'millimetre' if re.search(r'SI_UNIT\s*\(\s*\.MILLI\.\s*,\s*\.METRE\.', stripped) else 'not inferred',
                'geometry_validated': False,
                'warning': 'Entity counts are syntax metadata, not assembly counts; no physical bounds inferred from control points.'}
    if suffix.lower() != '.stl':
        raise ValueError('Only STEP/STP/STL metadata supported')
    vertices = []
    if len(data) >= 84 and 84 + 50 * struct.unpack_from('<I', data, 80)[0] == len(data):
        triangles = struct.unpack_from('<I', data, 80)[0]
        for offset in range(84, len(data), 50):
            values = struct.unpack_from('<12f', data, offset)
            vertices.extend([values[3:6], values[6:9], values[9:12]])
    else:
        text = data.decode('ascii', errors='strict')
        if not text.lstrip().startswith('solid') or 'endsolid' not in text:
            raise ValueError('Not STL')
        for match in re.finditer(r'\bvertex\s+(\S+)\s+(\S+)\s+(\S+)', text):
            vertices.append(tuple(float(x) for x in match.groups()))
        triangles = len(vertices) // 3
    if not vertices or len(vertices) % 3 or not all(math.isfinite(x) for v in vertices for x in v):
        raise ValueError('Invalid STL vertices')
    return {'format': 'STL', 'triangles': triangles, 'units_hint': 'unspecified (STL has no units)',
            'vertex_bounds': [[min(v[i] for v in vertices), max(v[i] for v in vertices)] for i in range(3)],
            'geometry_validated': False}


def build(asset, data, mode='pinned', approved=True):
    verify(data, asset)
    info = metadata(data, Path(asset['path']).suffix)
    prompt = (f"A slow engineering studio turntable animation of an {asset['subject']}. "
              'Neutral dark background, clear silhouette, steady camera, restrained lighting. ')
    if info['format'] == 'STEP':
        prompt += f"The source CAD contains {info['manifold_solid_brep_entities']} manifold solid BREP entities. "
    prompt += 'Show the mechanical subject without captions or invented readable labels.'
    return {'schema': 1, 'conditioning': 'cad_metadata_to_text_fallback', 'prompt': prompt,
            'geometry_guarantee': False, 'renderer_control_conditioning': 'unimplemented',
            'fine_tuned': False, 'mode': mode, 'approved_snapshot': approved,
            'asset': asset, 'source_url': raw_url(asset), 'metadata': info}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('asset', choices=[x['id'] for x in json.loads(MANIFEST.read_text())['assets']])
    p.add_argument('--fetch', action='store_true', help='Explicit network opt-in, pinned asset')
    p.add_argument('--live-latest', action='store_true', help='Explicit fetch of public default HEAD; unapproved candidate, never replaces manifest')
    p.add_argument('--local', type=Path, help='Offline exact-byte verification against approved manifest')
    p.add_argument('--output', type=Path, required=True, help='New JSON report on E:; never overwrite')
    a = p.parse_args()
    if sum([a.fetch, a.live_latest, a.local is not None]) != 1:
        p.error('Choose exactly one of --fetch, --live-latest, --local')
    output = e_path(a.output)
    if output.exists():
        p.error('Output exists; choose a new report path')
    asset = dict(next(x for x in json.loads(MANIFEST.read_text())['assets'] if x['id'] == a.asset))
    validate(asset)
    mode = 'pinned'
    if a.live_latest:
        head = json.loads(request(f"https://api.github.com/repos/{asset['repo']}/commits?per_page=1", 1024 * 1024))[0]['sha']
        if not re.fullmatch(r'[0-9a-f]{40}', head):
            raise ValueError('Invalid resolved HEAD')
        asset['commit'] = head
        data = request(raw_url(asset), MAX_BYTES)
        asset.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
        mode = 'live_latest_candidate'
    elif a.fetch:
        data = request(raw_url(asset), asset['size'])
    else:
        if a.local.stat().st_size > MAX_BYTES:
            raise ValueError('Local file too large')
        data = a.local.read_bytes()
    report = build(asset, data, mode, not a.live_latest)
    report['cache_path'] = str(store(data, asset['sha256']))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
