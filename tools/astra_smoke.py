"""Aceitação integrada com mídia própria e publicação exclusivamente simulada.

Guarda MP4, composição HyperFrames e relatório para inspeção. Não acessa redes
sociais e não carrega conectores configurados no ambiente do operador.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from clipforge.core import Runtime, probe, render_clip
from clipforge.hyperframes import export_composition
from clipforge.publishing import PublishingService
from clipforge.web import make_handler


class LocalTestConnector:
    """Dublê explícito apenas neste teste; não é integração com plataforma real."""
    connected = True
    limitations = 'Simulação local de teste, nenhuma publicação real.'

    def __init__(self):
        self.uploads = 0

    def submit(self, job, path):
        assert path.is_file()
        self.uploads += 1
        return 'local-test-operation'

    def check(self, operation):
        assert operation == 'local-test-operation'
        return {'state': 'confirmed', 'remote_id': 'SIMULATED-NOT-A-PUBLICATION',
                'visibility': 'local-test-only'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('data/astra-demo'))
    args = parser.parse_args()
    root = args.output.resolve()
    if (root / 'clips.sqlite3').exists():
        raise SystemExit('Use uma pasta nova: este teste preserva demonstrações anteriores.')
    os.environ.update(AUTO_SCAN='0', AUTO_RENDER='0', TWITCH_ENABLED='0',
                      AUTO_TRANSCRIBE='0', PUBLISHING_ENABLED='0',
                      DASHBOARD_TOKEN='astra-local-synthetic-test')
    runtime = Runtime(root)
    store = runtime.store
    source = store.incoming / 'geometria-propria.mp4'
    subprocess.run([
        'ffmpeg', '-n', '-v', 'error', '-f', 'lavfi', '-i',
        'testsrc2=size=960x540:rate=30', '-f', 'lavfi', '-i',
        'sine=frequency=440:sample_rate=48000', '-t', '12', '-shortest',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', str(source)], check=True, timeout=90)
    manifest = source.with_name(source.name + '.rights.json')
    # A imagem é gerada pelo teste; o título descreve exatamente esse conteúdo.
    manifest.write_text(json.dumps({'creator': 'Laboratório Astra — mídia sintética própria',
        'rights_status': 'owned', 'start_sec': 1, 'duration_sec': 10,
        'title': 'TESTE DE CORES EM MOVIMENTO', 'title_verified': True},
        ensure_ascii=False), encoding='utf-8')
    found = store.scan()
    assert len(found['added']) == 1 and not found['errors'], found
    clip_id = found['added'][0]
    assert store.scan()['added'] == [], 'Ingestão duplicada'
    store.update(clip_id, status='queued')
    render_clip(store, clip_id)
    item = store.get(clip_id)
    assert item['status'] == 'ready', item
    first = Path(item['output_path'])
    first_hash = hashlib.sha256(first.read_bytes()).hexdigest()
    # Compare duas composições reais da mesma fonte, preservando a primeira.
    store.edit(clip_id, layout='focus', focus_x=0.5, focus_y=0.5)
    store.update(clip_id, status='queued')
    render_clip(store, clip_id)
    item = store.get(clip_id)
    assert item['status'] == 'ready', item
    assert hashlib.sha256(first.read_bytes()).hexdigest() == first_hash
    second = Path(item['output_path'])
    assert second != first
    for output in (first, second):
        check = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(output),
            '-vf', 'blackdetect=d=0.1:pix_th=0.10', '-af', 'volumedetect',
            '-f', 'null', '-'], capture_output=True, text=True, check=True, timeout=90)
        assert 'black_start:' not in check.stderr, check.stderr
        assert 'mean_volume: -inf' not in check.stderr, 'Áudio perdido'
    local_connector = LocalTestConnector()
    runtime.publishing = PublishingService(store, {'test-local': local_connector}, enabled=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(runtime))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(method, path, body=None, extra=None):
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=15)
        headers = {'Authorization': 'Bearer astra-local-synthetic-test'}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        headers.update(extra or {})
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse()
        status, data = response.status, response.read()
        conn.close()
        return status, data

    try:
        for route in ('original', 'video'):
            status, data = request('GET', f'/api/clips/{clip_id}/{route}', extra={'Range': 'bytes=0-255'})
            assert status == 206 and len(data) == 256, (status, route)
        status, _ = request('POST', f'/api/clips/{clip_id}/approve')
        assert status == 200 and store.get(clip_id)['status'] == 'approved'
        status, data = request('POST', f'/api/clips/{clip_id}/publish',
            {'platform': 'test-local', 'title': 'Teste sintético próprio'})
        assert status in (200, 201, 202), (status, data)
        job = runtime.publishing.all()[0]
        assert runtime.publishing.enqueue(clip_id, 'test-local', 'Mesmo vídeo')['id'] == job['id']
        pending = runtime.publishing.process_one()
        assert pending['status'] == 'pending' and not pending['remote_id']
        with store._db() as db:
            db.execute('UPDATE publication_jobs SET next_attempt_at=0')
            db.commit()
        confirmed = runtime.publishing.process_one()
        assert confirmed['status'] == 'confirmed' and local_connector.uploads == 1
        assert runtime.publishing.process_one() is None
        composition = export_composition(store, clip_id, title='TESTE DE CORES EM MOVIMENTO')
        report = {'source': str(source), 'clip_id': clip_id,
            'videos': [{'path': str(path), 'ffprobe': probe(path)} for path in (first, second)],
            'checks': ['rights-owned', 'sha256-deduplication', 'ffmpeg-vertical-real',
                       'full-decode', 'audio-non-silent', 'no-black-frames',
                       'original-preserved', 'http-range-preview', 'http-approval',
                       'publication-queue-local-simulation', 'hyperframes-export'],
            'publication': {'simulated': True, 'actual_social_posts': 0},
            'hyperframes_export': str(composition), 'hyperframes_rendered': False,
            'editorial_quality_of_real_clips_verified': False}
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('ASTRA E2E PASS:', root / 'report.json')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
        runtime.executor.shutdown(wait=True)
        runtime.captions.stop()
        runtime.publishing.stop()


if __name__ == '__main__':
    main()
