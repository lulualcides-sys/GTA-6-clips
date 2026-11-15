"""Adaptadores das APIs oficiais; tokens OAuth vêm do ambiente privado.

Não implementa login interativo nem renova tokens. Credenciais expiradas exigem
reconexão. Os testes de contrato locais não comprovam aprovação dos aplicativos
pelas plataformas, nem publicação pública.
"""
from __future__ import annotations

import http.client
import json
import os
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, token, body=None, method=None):
    headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
    data = None if body is None else json.dumps(body).encode()
    with build_opener(NoRedirect).open(Request(url, data=data, headers=headers, method=method), timeout=45) as response:
        raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Resposta da API excessiva.')
        return json.loads(raw), response.headers


def upload_file(url, path, allowed_domains, token=None):
    """Upload limitado a hosts oficiais e sem carregar o MP4 inteiro em RAM."""
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in {None,443}
            or not parsed.hostname or not any(parsed.hostname == domain or parsed.hostname.endswith('.' + domain)
                       for domain in allowed_domains)):
        raise ValueError('URL de upload fora da API oficial.')
    size = path.stat().st_size
    conn = http.client.HTTPSConnection(parsed.hostname, timeout=120)
    try:
        conn.putrequest('PUT', parsed.path + ('?' + parsed.query if parsed.query else ''))
        conn.putheader('Content-Type', 'video/mp4')
        conn.putheader('Content-Length', str(size))
        conn.putheader('Content-Range', f'bytes 0-{size-1}/{size}')
        if token:
            conn.putheader('Authorization', 'Bearer ' + token)
        conn.endheaders()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                conn.send(block)
        response = conn.getresponse()
        raw = response.read(1024 * 1024 + 1)
        if not 200 <= response.status < 300 or len(raw) > 1024 * 1024:
            raise ValueError('API não confirmou o recebimento do upload.')
        return json.loads(raw) if raw else {}
    finally:
        conn.close()


class YouTubeConnector:
    limitations = ('Requer OAuth youtube.upload e consulta videos.list. Envio privado por padrão; '
                   'projetos não auditados podem permanecer privados. Shorts depende da classificação do YouTube.')
    def __init__(self, token=''):
        self.token = token
        self.connected = bool(token)

    def submit(self, job, path):
        # Privado deliberadamente: visibilidade pública exige configuração auditada futura.
        body = {'snippet': {'title':job['title'], 'description':job['description'], 'categoryId':'20'},
                'status': {'privacyStatus':'private', 'selfDeclaredMadeForKids':False}}
        data = json.dumps(body).encode()
        request = Request('https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',
                          data=data, method='POST', headers={
                              'Authorization':'Bearer ' + self.token, 'Content-Type':'application/json',
                              'X-Upload-Content-Type':'video/mp4', 'X-Upload-Content-Length':str(path.stat().st_size)})
        with build_opener(NoRedirect).open(request, timeout=45) as response:
            location = response.headers.get('Location', '')
        result = upload_file(location, path, {'googleapis.com'}, self.token)
        if not result.get('id'):
            raise ValueError('YouTube não retornou ID.')
        return result['id']

    def check(self, remote_id):
        result, _ = request_json('https://www.googleapis.com/youtube/v3/videos?' + urlencode(
            {'part':'status','id':remote_id}), self.token)
        items = result.get('items', [])
        if not items:
            return {'state':'pending'}
        item = items[0]
        status = item.get('status', {})
        if status.get('uploadStatus') in {'failed','rejected','deleted'}:
            return {'state':'failed'}
        if status.get('uploadStatus') == 'processed' and item.get('id') == remote_id:
            return {'state':'confirmed','remote_id':item['id'],'visibility':status.get('privacyStatus','unknown')}
        return {'state':'pending'}


class TikTokConnector:
    limitations = ('Requer Content Posting API, escopo video.publish e revisão do aplicativo. '
                   'Somente SELF_ONLY; não anuncia publicação pública. Limite local de upload: 64 MiB.')
    def __init__(self, token=''):
        self.token = token
        self.connected = bool(token)

    def _post(self, endpoint, body):
        result, _ = request_json('https://open.tiktokapis.com/v2/post/publish/' + endpoint,
                                 self.token, body)
        if result.get('error', {}).get('code') not in {None, 'ok'}:
            raise ValueError('TikTok recusou a operação.')
        return result.get('data', {})

    def submit(self, job, path):
        size = path.stat().st_size
        if not 0 < size <= 64 * 1024 * 1024:
            raise ValueError('Upload TikTok requer arquivo até 64 MiB neste conector.')
        creator = self._post('creator_info/query/', {})
        if 'SELF_ONLY' not in creator.get('privacy_level_options', []):
            raise ValueError('Conta não permite visibilidade privada solicitada.')
        data = self._post('video/init/', {
            'post_info': {'title':job['title'] + ('\n' + job['description'] if job['description'] else ''),
                          'privacy_level':'SELF_ONLY','disable_duet':True,
                          'disable_comment':False,'disable_stitch':True},
            'source_info': {'source':'FILE_UPLOAD','video_size':size,'chunk_size':size,'total_chunk_count':1}})
        if not data.get('publish_id'):
            raise ValueError('TikTok não retornou identificador de operação.')
        upload_file(data['upload_url'], path, {'tiktokapis.com'})
        return data['publish_id']

    def check(self, remote_id):
        data = self._post('status/fetch/', {'publish_id':remote_id})
        if data.get('status') == 'FAILED':
            return {'state':'failed'}
        if data.get('status') == 'PUBLISH_COMPLETE':
            # A API usa esta grafia; publish_id é operação, não ID de vídeo.
            ids = data.get('publicaly_available_post_id', [])
            return {'state':'confirmed','remote_id':str(ids[0]) if ids else None,'visibility':'private'}
        return {'state':'pending'}


class InstagramUnavailable:
    connected = False
    limitations = ('Bloqueado: configurar conta profissional, OAuth e hospedagem HTTPS do MP4 '
                   'autorizado para a API de Reels. Upload/publicação Instagram ainda não implementados.')


def configured_connectors():
    return {'youtube':YouTubeConnector(os.getenv('YOUTUBE_ACCESS_TOKEN','')),
            'tiktok':TikTokConnector(os.getenv('TIKTOK_ACCESS_TOKEN','')),
            'instagram':InstagramUnavailable()}
