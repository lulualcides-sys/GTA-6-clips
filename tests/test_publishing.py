"""Fila real em SQLite; nenhum teste publica em redes sociais."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clipforge.core import ClipStore
from clipforge import publishing


class LocalConnector:
    connected = True
    limitations = 'Servidor de teste; sem postagem externa.'
    def __init__(self):
        self.submissions = 0
        self.result = {'state': 'confirmed', 'remote_id': 'remote-123', 'visibility': 'private'}
    def submit(self, job, path):
        self.submissions += 1
        return 'operation-123'
    def check(self, remote_id):
        return self.result


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ClipStore(Path(self.tmp.name))
        self.media = self.store.output / 'abc.mp4'
        self.media.write_bytes(b'media-specific-content')
        with self.store._db() as db:
            db.execute('''INSERT INTO clips
                (id,sha256,filename,creator,rights_status,input_path,output_path,duration_sec,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                ('abcdef123456','sourcehash','source.mp4','Autor','owned','source',str(self.media),10,'approved','2026-11-14'))
            db.commit()
        self.connector = LocalConnector()
        self.service = publishing.PublishingService(self.store, {'youtube': self.connector}, enabled=True)

    def enqueue(self, **kw):
        return self.service.enqueue('abcdef123456', 'youtube', 'Momento verificado', **kw)

    def test_enqueue_deduplicates_persisted_clip_platform(self):
        first = self.enqueue()
        self.assertEqual(first['id'], self.enqueue()['id'])
        second = publishing.PublishingService(self.store, {'youtube':self.connector}, enabled=True)
        self.assertEqual(1, len(second.all()))

    def test_supervised_requires_approval(self):
        self.store.update('abcdef123456', status='ready')
        with self.assertRaises(ValueError): self.enqueue()

    def test_input_types_cannot_enable_automatic_mode(self):
        for fields in ({'automatic': 'false'}, {'scheduled_at': True}):
            with patch.dict('os.environ', {'PUBLISHING_AUTO_ENABLED':'1'}), self.subTest(fields=fields), self.assertRaises(ValueError):
                self.enqueue(**fields)

    def test_telemetry_tracks_only_new_queue_and_actual_status(self):
        self.enqueue()
        self.enqueue()
        queued = [e for e in self.store.activity.recent() if e['agent'] == 'publicacao']
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]['state'], 'queued')
        self.service.process_one()
        recent = self.store.activity.recent()
        self.assertEqual(recent[0]['agent'], 'publicacao')
        self.assertEqual(recent[0]['state'], 'waiting')
        self.assertNotIn('remote-123', recent[0]['message'])

    def test_daily_limit_prevents_second_upload(self):
        self.service.daily_limit = 1
        self.enqueue()
        self.service.process_one()
        with self.store._db() as db:
            db.execute("UPDATE publication_jobs SET status='queued',next_attempt_at=0")
            db.commit()
        self.assertIsNone(self.service.process_one())
        self.assertEqual(self.connector.submissions, 1)

    def test_auto_requires_explicit_opt_in(self):
        with patch.dict('os.environ', {'PUBLISHING_AUTO_ENABLED':'0'}):
            with self.assertRaises(ValueError): self.enqueue(automatic=True)

    def test_revoked_rights_blocks_before_upload(self):
        self.enqueue()
        with self.store._db() as db:
            db.execute("UPDATE clips SET rights_status='unknown'")
            db.commit()
        self.assertEqual('blocked', self.service.process_one()['status'])
        self.assertEqual(0, self.connector.submissions)

    def test_submit_is_not_confirmation_and_private_stays_private(self):
        self.enqueue()
        pending = self.service.process_one()
        self.assertEqual('pending', pending['status'])
        self.assertIsNone(pending['remote_id'])
        with self.store._db() as db:
            db.execute('UPDATE publication_jobs SET next_attempt_at=0'); db.commit()
        result = self.service.process_one()
        self.assertEqual('confirmed', result['status'])
        self.assertEqual('remote-123', result['remote_id'])
        self.assertEqual('private', result['visibility'])
        self.assertIsNone(self.service.process_one())
        self.assertEqual(1, self.connector.submissions)

    def test_missing_confirmation_id_never_confirms(self):
        self.enqueue(); self.service.process_one()
        self.connector.result = {'state':'confirmed'}
        with self.store._db() as db:
            db.execute('UPDATE publication_jobs SET next_attempt_at=0'); db.commit()
        self.assertEqual('uncertain', self.service.process_one()['status'])

    def test_restart_does_not_repeat_ambiguous_submission(self):
        job = self.enqueue()
        with self.store._db() as db:
            db.execute("UPDATE publication_jobs SET status='submitting' WHERE id=?",(job['id'],)); db.commit()
        resumed = publishing.PublishingService(self.store, {'youtube':self.connector}, enabled=True)
        self.assertEqual('uncertain', resumed.all()[0]['status'])
        self.assertIsNone(resumed.process_one())
        self.assertEqual(0, self.connector.submissions)

    def test_changed_media_is_blocked(self):
        self.enqueue(); self.media.write_bytes(b'replaced')
        self.assertEqual('blocked', self.service.process_one()['status'])

    def test_scheduling_cancel_and_disabled_worker(self):
        job = self.enqueue(scheduled_at=9999999999)
        self.assertIsNone(self.service.process_one())
        self.assertTrue(self.service.cancel(job['id']))
        self.assertFalse(self.service.cancel(job['id']))

    def test_timeout_does_not_retry_upload(self):
        self.enqueue()
        self.connector.submit = lambda *_: (_ for _ in ()).throw(TimeoutError())
        self.assertEqual('uncertain', self.service.process_one()['status'])
        self.assertIsNone(self.service.process_one())

    def test_poll_failure_retries_with_backoff(self):
        self.enqueue(); self.service.process_one()
        self.connector.check = lambda *_: (_ for _ in ()).throw(TimeoutError())
        with self.store._db() as db:
            db.execute('UPDATE publication_jobs SET next_attempt_at=0'); db.commit()
        result = self.service.process_one()
        self.assertEqual('pending', result['status'])
        self.assertEqual(1, result['poll_attempts'])
        self.assertGreater(result['next_attempt_at'], 0)


if __name__ == '__main__': unittest.main()
