"""Contratos editoriais: dados reais, limites e proteção das versões aprovadas."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from clipforge.core import ClipStore


class EditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ClipStore(Path(self.temp.name))
        media = self.store.incoming / 'source.mp4'
        media.write_bytes(b'own media')
        self.manifest = media.with_name(media.name + '.rights.json')
        self.manifest.write_text(json.dumps({'creator': 'Test Creator', 'rights_status': 'owned',
                                           'start_sec': 0, 'duration_sec': 10}))
        self.info = {'format': {'duration': '60'}, 'streams': [{'codec_type': 'video', 'width': 640, 'height': 360}]}
        with patch('clipforge.core.probe', return_value=self.info):
            self.item = self.store.ingest(self.manifest)

    def test_ready_edit_preserves_old_render(self):
        output = self.store.output / 'approved-original.mp4'
        output.write_bytes(b'unchanged original')
        self.store.update(self.item['id'], status='ready', output_path=str(output))
        with patch('clipforge.core.probe', return_value=self.info):
            edit = self.store.edit(self.item['id'], start_sec=5, duration_sec=12,
                                   title='ERA SÓ TESTAR', title_verified=True)
        self.assertEqual(edit['title'], 'ERA SÓ TESTAR')
        self.assertEqual(self.store.get(self.item['id'])['status'], 'detected')
        self.assertEqual(output.read_bytes(), b'unchanged original')

    def test_approved_edit_is_blocked(self):
        self.store.update(self.item['id'], status='approved')
        with self.assertRaisesRegex(ValueError, 'aprovado|estado'):
            self.store.edit(self.item['id'], start_sec=2)

    def test_non_finite_timestamps_rejected(self):
        with patch('clipforge.core.probe', return_value=self.info):
            for invalid in [float('nan'), float('inf'), -1]:
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    self.store.edit(self.item['id'], start_sec=invalid)

    def test_unverified_title_is_blocked(self):
        with self.assertRaisesRegex(ValueError, 'título|Título'):
            self.store.edit(self.item['id'], title='ACIDENTE INCRÍVEL')

    def test_gta_reaction_required(self):
        with patch('clipforge.core.probe', return_value=self.info):
            with self.assertRaisesRegex(ValueError, 'reação|Reação'):
                self.store.edit(self.item['id'], game='Grand Theft Auto VI')

    def test_ingest_rejects_nan_timestamp(self):
        self.manifest.write_text(json.dumps({'creator': 'Test', 'rights_status': 'owned',
                                            'start_sec': float('nan'), 'duration_sec': 10}))
        with patch('clipforge.core.probe', return_value=self.info), self.assertRaises(ValueError):
            self.store.ingest(self.manifest)

    def test_rank_penalizes_isolated_noise(self):
        from clipforge.editing import rank_audio_windows
        # Um ruído isolado alto não supera atividade contínua e variável.
        powers = [0] * 10 + [30000] + [0] * 9 + [3000, 6000, 4000, 8000, 5000] * 2
        ranked = rank_audio_windows(powers, 10)
        self.assertGreaterEqual(ranked[0]['start_sec'], 17)
        self.assertEqual(ranked[0]['method'], 'audio-heuristic')
        self.assertIsNone(ranked[0]['components']['semantic_relevance'])
        self.assertLessEqual(len(ranked), 3)


class RecoveryTests(unittest.TestCase):
    def test_restart_resubmits_interrupted_jobs_with_limit(self):
        import os
        from clipforge.core import Runtime
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'AUTO_SCAN': '0', 'AUTO_RENDER': '0', 'TWITCH_ENABLED': '0'}):
            store = ClipStore(Path(temp))
            with store._db() as db:
                db.execute("INSERT INTO clips VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           ('interrupted1', 'a' * 64, 's.mp4', 'Creator', '', '', 'owned',
                            '/not-present.mp4', None, 0, 10, None, 'rendering', None, '2026'))
                db.commit()
            with patch('clipforge.core.render_clip') as renderer:
                runtime = Runtime(Path(temp))
                runtime.executor.shutdown(wait=True)
            renderer.assert_called_once_with(runtime.store, 'interrupted1')
            self.assertEqual(runtime.store.get('interrupted1')['status'], 'queued')
            for _ in range(2):
                with patch('clipforge.core.render_clip') as renderer:
                    runtime = Runtime(Path(temp))
                    runtime.executor.shutdown(wait=True)
                    renderer.assert_called_once()
            with patch('clipforge.core.render_clip') as renderer:
                runtime = Runtime(Path(temp))
                runtime.executor.shutdown(wait=True)
                renderer.assert_not_called()
            self.assertEqual(runtime.store.get('interrupted1')['status'], 'failed')
            self.assertIn('limite', runtime.store.get('interrupted1')['error'])

    def test_immutable_source_is_checked_before_rendering(self):
        from clipforge.core import render_clip
        with tempfile.TemporaryDirectory() as temp:
            store = ClipStore(Path(temp))
            source = store.incoming / 's.mp4'
            source.write_bytes(b'original')
            manifest = source.with_name('s.mp4.rights.json')
            manifest.write_text(json.dumps({'creator': 'Creator', 'rights_status': 'owned', 'duration_sec': 10}))
            with patch('clipforge.core.probe', return_value={'format': {'duration': '10'}, 'streams': []}):
                item = store.ingest(manifest)
            source.write_bytes(b'changed after authorization')
            store.update(item['id'], status='queued')
            render_clip(store, item['id'])
            self.assertEqual(store.get(item['id'])['status'], 'failed')
            self.assertIn('changed', store.get(item['id'])['error'])


class SelectionPersistenceTests(unittest.TestCase):
    setUp = EditingTests.setUp

    def test_selected_start_overrides_original_automatic_setting(self):
        with self.store._db() as db:
            db.execute("UPDATE clip_edits SET settings=? WHERE clip_id=?",
                       (json.dumps({'start_sec': None, 'duration_sec': 10}), self.item['id']))
            db.commit()
        self.store.update(self.item['id'], start_sec=12, score=81)
        self.assertEqual(self.store.get_edit(self.item['id'])['start_sec'], 12)

    def test_audio_candidates_have_scores_and_survive_reopen(self):
        from array import array
        from types import SimpleNamespace
        from clipforge.core import analyze_highlight
        pcm = array('h', ([1000]*8000 + [5000]*8000)*15).tobytes()
        with patch('clipforge.core.subprocess.run', return_value=SimpleNamespace(stdout=pcm)):
            start, analysis = analyze_highlight(Path('source.mp4'), 30, 10)
        self.assertTrue(analysis['candidates'])
        self.assertIsInstance(analysis['candidates'][0]['score'], (int, float))
        self.assertFalse(analysis['semantic_understanding'])
        self.store.save_analysis(self.item['id'], analysis=analysis)
        reopened = ClipStore(self.store.root)
        self.assertEqual(reopened.get_edit(self.item['id'])['analysis'], analysis)


if __name__ == '__main__':
    unittest.main()
