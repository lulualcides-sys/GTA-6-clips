"""Contratos HTTP em servidor local; nunca envia mídia às plataformas."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from clipforge import social_connectors as social


class ContractHandler(BaseHTTPRequestHandler):
    response = {}
    requests = []
    redirect = False
    def log_message(self, *args): pass
    def do_GET(self):
        self.__class__.requests.append((self.path, self.headers.get('Authorization')))
        if self.redirect:
            self.send_response(302); self.send_header('Location','http://127.0.0.1:1/leak'); self.end_headers(); return
        raw = json.dumps(self.response).encode()
        self.send_response(200); self.send_header('Content-Length',str(len(raw)))
        self.end_headers(); self.wfile.write(raw)
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length','0')))
        self.__class__.requests.append(json.loads(body))
        self.do_GET()


class ContractTests(unittest.TestCase):
    def setUp(self):
        ContractHandler.requests = []
        ContractHandler.redirect = False
        self.server = ThreadingHTTPServer(('127.0.0.1',0),ContractHandler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.addCleanup(self.close)
    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
    def transport(self, url, token, body=None, method=None):
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        return self.real_request(self.base + parsed.path + '?' + parsed.query, token, body, method)
    def redirected_transport(self):
        self.real_request = social.request_json
        return patch.object(social,'request_json',side_effect=self.transport)

    def test_youtube_requires_processed_status_and_matching_id(self):
        connector = social.YouTubeConnector('test-token')
        with self.redirected_transport():
            ContractHandler.response = {'items':[{'id':'yt123','status':{'uploadStatus':'uploaded'}}]}
            self.assertEqual('pending',connector.check('yt123')['state'])
            ContractHandler.response = {'items':[{'id':'yt123','status':{'uploadStatus':'processed','privacyStatus':'private'}}]}
            self.assertEqual({'state':'confirmed','remote_id':'yt123','visibility':'private'},connector.check('yt123'))
            self.assertEqual('Bearer test-token',ContractHandler.requests[-1][1])
            self.assertIn('part=status',ContractHandler.requests[-1][0])

    def test_youtube_rejected_upload_is_failed(self):
        ContractHandler.response = {'items':[{'id':'yt123','status':{'uploadStatus':'rejected'}}]}
        with self.redirected_transport():
            self.assertEqual('failed',social.YouTubeConnector('test').check('yt123')['state'])

    def test_tiktok_operation_id_does_not_become_post_id(self):
        ContractHandler.response = {'data':{'status':'PUBLISH_COMPLETE'},'error':{'code':'ok'}}
        with self.redirected_transport():
            result = social.TikTokConnector('test').check('operation123')
        self.assertIsNone(result['remote_id'])
        self.assertEqual({'publish_id':'operation123'},ContractHandler.requests[0])

    def test_tiktok_confirmed_real_id(self):
        ContractHandler.response = {'data':{'status':'PUBLISH_COMPLETE','publicaly_available_post_id':['post123']},'error':{'code':'ok'}}
        with self.redirected_transport():
            self.assertEqual('post123',social.TikTokConnector('test').check('operation123')['remote_id'])

    def test_credentials_not_redirected(self):
        ContractHandler.redirect = True
        with self.assertRaises(HTTPError): social.request_json(self.base,'secret-test')
        self.assertEqual(1,len(ContractHandler.requests))

    def test_upload_rejects_non_official_host_before_reading_file(self):
        for url in ['http://googleapis.com/upload','https://googleapis.com.attacker.test/upload',
                    'https://user@googleapis.com/upload','https://googleapis.com:444/upload',
                    'https:///missing-host','https://googleapis.com:bad/upload']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                social.upload_file(url,Path('/nonexistent'),{'googleapis.com'})

    def test_missing_credentials_and_instagram_are_disconnected(self):
        with patch.dict('os.environ',{},clear=True):
            connectors = social.configured_connectors()
        self.assertTrue(all(not item.connected for item in connectors.values()))


if __name__ == '__main__': unittest.main()
