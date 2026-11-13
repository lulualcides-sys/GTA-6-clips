import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from clipforge.core import Runtime
from clipforge.web import make_handler


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ,{"DASHBOARD_TOKEN":"example-secret","AUTO_SCAN":"0","AUTO_RENDER":"0"})
        env.start()
        self.addCleanup(env.stop)
        self.runtime = Runtime(Path(self.temp.name))
        self.server = ThreadingHTTPServer(("127.0.0.1",0),make_handler(self.runtime))
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.runtime.executor.shutdown(wait=True)

    def request(self,method,path,token=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        headers={"Authorization":"Bearer "+token} if token else {}
        conn.request(method,path,headers=headers)
        response=conn.getresponse()
        data=response.read()
        status=response.status
        conn.close()
        return status,json.loads(data)

    def test_health_is_public(self):
        status,body=self.request("GET","/api/health")
        self.assertEqual(status,200)
        self.assertEqual(body["status"],"ok")

    def test_clips_requires_token(self):
        status,_=self.request("GET","/api/clips")
        self.assertEqual(status,401)
        status,body=self.request("GET","/api/clips","example-secret")
        self.assertEqual(status,200)
        self.assertEqual(body["clips"],[])

    def test_empty_scan(self):
        status,body=self.request("POST","/api/scan","example-secret")
        self.assertEqual(status,200)
        self.assertEqual(body["added"],[])


if __name__ == "__main__":
    unittest.main()
