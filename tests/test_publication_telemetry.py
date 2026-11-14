"""Mission Control acompanha fila persistida, sem presumir postagem pública."""
import tempfile
import unittest
from pathlib import Path

from clipforge.core import Runtime
from clipforge.publishing import PublishingService


class PublicationTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name))
        self.addCleanup(self.runtime.executor.shutdown, wait=True)
        self.addCleanup(self.runtime.captions.stop)
        self.runtime.publishing = PublishingService(self.runtime.store, {}, enabled=False)

    def test_pending_job_is_visible_even_with_worker_disabled(self):
        with self.runtime.store._db() as db:
            db.execute('''INSERT INTO publication_jobs
                (id,clip_id,platform,title,description,media_sha256,status,automatic,
                 scheduled_at,next_attempt_at,created_at,updated_at)
                VALUES ('job','abcdef123456','youtube','Teste','','hash','pending',0,0,0,0,0)''')
            db.commit()
        snapshot = self.runtime.store.activity.snapshot(self.runtime)
        stage = next(s for s in snapshot['stages'] if s['id'] == 'publicacao')
        self.assertEqual(stage['state'], 'waiting')
        self.assertIn('confirmação', stage['message'])
        self.assertEqual(snapshot['counts']['publication_pending'], 1)

    def test_private_confirmation_never_claims_public_visibility(self):
        with self.runtime.store._db() as db:
            db.execute('''INSERT INTO publication_jobs
                (id,clip_id,platform,title,description,media_sha256,status,automatic,
                 scheduled_at,next_attempt_at,created_at,updated_at,remote_id,visibility)
                VALUES ('job','abcdef123456','youtube','Teste','','hash','confirmed',0,0,0,0,0,'real-id','private')''')
            db.commit()
        snapshot = self.runtime.store.activity.snapshot(self.runtime)
        self.assertEqual(snapshot['counts']['publication_confirmed'], 1)
        self.assertEqual(snapshot['counts']['publication_public'], 0)
        stage = next(s for s in snapshot['stages'] if s['id'] == 'publicacao')
        self.assertIn('visibilidade', stage['message'])
