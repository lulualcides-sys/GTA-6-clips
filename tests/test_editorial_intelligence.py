"""Nexus editorial intelligence, private mobile pairing and metrics regression tests."""
import hashlib
import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from clipforge.core import ClipStore
from clipforge.editorial_intelligence import (
    EditorialIntelligence, _vision_insights, _technical_check, _verified_transcript,
)
from clipforge.mobile_pairing import MobilePairing
from clipforge.performance_metrics import PerformanceMetrics
from clipforge.curation import ranked_shortlist


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ClipStore(Path(self.temp.name))
        self.intelligence = EditorialIntelligence(self.store)
        self.addCleanup(self.intelligence.pool.shutdown, wait=True)
        self._clip("one000000000", "Creator A")

    def _clip(self, name, creator):
        name = name.ljust(12, "0")  # Real Nexus IDs contain 12 alphanumeric chars.
        with self.store.lock, self.store._db() as db:
            db.execute("""INSERT INTO clips
                (id,sha256,filename,creator,source_url,evidence,rights_status,
                 input_path,output_path,start_sec,duration_sec,score,status,error,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (name, name.ljust(64, "f"), name+".mp4", creator, "",
                 "", "owned", "/tmp/original.mp4", "/tmp/final.mp4",
                 0, 25, 90, "ready", None, datetime.now(timezone.utc).isoformat()))
            db.commit()

    def test_rejection_requires_valid_reason(self):
        with self.assertRaisesRegex(ValueError, "obrigatório"):
            self.intelligence.review("one000000000", "reject")
        with self.assertRaisesRegex(ValueError, "inválid"):
            self.intelligence.review("one000000000", "not_a_decision")
        self.assertEqual(self.store.get("one000000000")["status"], "ready")

    def test_reject_then_persist_feedback_without_fabricating_quality(self):
        value = self.intelligence.review("one000000000", "reject", "sem_graca", "Nenhum momento surpreendente")
        self.assertEqual(value["status"], "rejected")
        self.assertEqual(self.store.get("one000000000")["status"], "rejected")
        self.assertEqual(self.intelligence.get("one000000000")["feedback"]["reason"], "sem_graca")
        self.assertEqual(self.intelligence.get("one000000000")["analysis_status"], "not_started")
        self.assertEqual(self.intelligence.feedback_summary()["reasons"]["sem_graca"], 1)

    def test_approval_cannot_alter_already_approved_or_rejected(self):
        self.intelligence.review("one000000000", "approve")
        self.assertEqual(self.intelligence.feedback_summary()["approval_rate"], 100.0)
        with self.assertRaisesRegex(ValueError, "disponível"):
            self.intelligence.review("one000000000", "approve")
        self.intelligence.review("one000000000", "reject", "corte_ruim")
        self.assertEqual(self.intelligence.feedback_summary()["reviewed"], 1)
        self.assertEqual(self.intelligence.feedback_summary()["rejected"], 1)

    def test_five_reviews_create_conservative_creator_bias(self):
        for index in range(2, 6):
            self._clip("clip"+str(index), "Creator A")
        for name in ["one000000000", "clip20000000", "clip30000000", "clip40000000", "clip50000000"]:
            self.intelligence.review(name, "approve")
        result = self.intelligence.feedback_summary()
        self.assertEqual(result["reviewed"], 5)
        self.assertGreater(result["creator_bias"]["creator a"], 0)
        self.assertLessEqual(result["creator_bias"]["creator a"], 5)
        now = datetime.now(timezone.utc).isoformat()
        items = [
            {"id": "a", "creator_name": "Creator A", "broadcaster_id": "1",
             "title": "Queda engraçada no canal", "score": 81,
             "view_count": 1000, "duration": 30, "game_name": "Grand Theft Auto VI",
             "created_at": now},
            {"id": "b", "creator_name": "Creator B", "broadcaster_id": "2",
             "title": "Cena inacreditável na moto", "score": 82,
             "view_count": 1000, "duration": 30, "game_name": "Grand Theft Auto VI",
             "created_at": now},
        ]
        picks = ranked_shortlist(items, creator_bias=result["creator_bias"])
        self.assertEqual(picks[0]["id"], "a")

    def test_vision_never_claims_analysis_without_model(self):
        with patch("clipforge.editorial_intelligence._ollama_json", return_value={"models": []}):
            report = _vision_insights(Path("/fake/no-video.mp4"), 40.0)
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(report["frames_analyzed"], 0)


    def test_verified_transcript_requires_matching_rendered_media_hash(self):
        folder = self.store.root / "captions"
        folder.mkdir()
        (folder / "one000000000.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nWatch out, a car is coming!\n",
            encoding="utf-8",
        )
        media_hash = "b" * 64
        with self.store._db() as db:
            db.execute("""CREATE TABLE clip_captions (
                clip_id TEXT PRIMARY KEY, video_sha TEXT, status TEXT, cues INTEGER
            )""")
            db.execute("INSERT INTO clip_captions VALUES(?,?,?,?)",
                       ("one000000000", media_hash, "ready", 1))
            db.commit()
        evidence = _verified_transcript(self.store, "one000000000", media_hash)
        self.assertEqual(evidence["status"], "ready")
        self.assertIn("Watch out, a car is coming!", evidence["text"])
        self.assertNotIn("-->", evidence["text"])
        with self.store._db() as db:
            db.execute("UPDATE clip_captions SET video_sha=? WHERE clip_id=?",
                       ("a" * 64, "one000000000"))
            db.commit()
        stale = _verified_transcript(self.store, "one000000000", media_hash)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["text"], "")



    def test_queue_rechecks_when_verified_transcript_appears_later(self):
        clip_id = "one000000000"
        video = self.store.output / f"{clip_id}.mp4"
        video.write_bytes(b"approved AutoClip output")
        media_hash = hashlib.sha256(video.read_bytes()).hexdigest()
        self.store.update(clip_id, output_path=str(video))
        folder = self.store.root / "captions"
        folder.mkdir()
        (folder / f"{clip_id}.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nNow I understand the crash!\n",
            encoding="utf-8",
        )
        with self.store._db() as db:
            db.execute("""CREATE TABLE clip_captions (
                clip_id TEXT PRIMARY KEY, video_sha TEXT, status TEXT, cues INTEGER
            )""")
            db.execute("INSERT INTO clip_captions VALUES(?,?,?,?)",
                       (clip_id, media_hash, "ready", 1))
            db.execute("""INSERT INTO editorial_insights
                (clip_id,media_sha256,status,report,updated_at) VALUES(?,?,?,?,?)""",
                (clip_id, media_hash, "complete",
                 json.dumps({"transcript": {
                     "status": "not_available", "chars": 0, "sha256": ""
                 }}), time.time()))
            db.commit()
        with patch.object(self.intelligence.pool, "submit") as submit:
            self.assertTrue(self.intelligence.queue(clip_id))
        submit.assert_called_once_with(self.intelligence._assess, clip_id)
        self.intelligence.pending.discard(clip_id)

    def test_assessment_passes_only_verified_speech_to_visual_model(self):
        clip_id = "one000000000"
        video = self.store.output / f"{clip_id}.mp4"
        video.write_bytes(b"approved AutoClip output")
        media_hash = hashlib.sha256(video.read_bytes()).hexdigest()
        spoken = "Cuidado, tem um carro vindo pela esquerda!"
        captions = self.store.root / "captions"
        captions.mkdir()
        (captions / f"{clip_id}.srt").write_text(
            f"1\n00:00:01,000 --> 00:00:03,000\n{spoken}\n", encoding="utf-8"
        )
        with self.store._db() as db:
            db.execute("UPDATE clips SET output_path=? WHERE id=?",
                       (str(video), clip_id))
            db.execute("""CREATE TABLE clip_captions (
                clip_id TEXT PRIMARY KEY, video_sha TEXT, status TEXT, cues INTEGER
            )""")
            db.execute("INSERT INTO clip_captions VALUES(?,?,?,?)",
                       (clip_id, media_hash, "ready", 1))
            db.commit()
        with patch("clipforge.core.probe", return_value={"format": {"duration": "25"}, "streams": []}), \
             patch("clipforge.core.duration_of", return_value=25.0), \
             patch("clipforge.editorial_intelligence._technical_check",
                   return_value={"status": "checked", "warnings": []}), \
             patch("clipforge.editorial_intelligence._vision_insights",
                   return_value={"status": "visual_partial", "audio_transcript_used": True}) as vision:
            self.intelligence._assess(clip_id)
        vision.assert_called_once_with(video, 25.0, spoken)
        analysis = self.intelligence.get(clip_id)["analysis"]
        self.assertEqual(analysis["transcript"], {"status": "ready", "chars": len(spoken)})

    def test_visual_analysis_uses_verified_transcript_as_context(self):
        captured = {}
        def ollama(endpoint, payload=None, timeout=10):
            if endpoint == "/api/tags":
                return {"models": [{"name": "llava:7b"}]}
            captured["prompt"] = payload["messages"][0]["content"]
            return {"message": {"content": json.dumps({
                "event": "Streamer avisa sobre carro e ocorre colisão",
                "category": "acidente", "context_clear": True,
                "visual_hook": True, "confidence": 0.8,
            })}}
        transcript = "Cuidado, tem um carro vindo pela esquerda!"
        with patch("clipforge.editorial_intelligence._ollama_json", side_effect=ollama), \
             patch("clipforge.editorial_intelligence._frames", return_value=[str(i) for i in range(9)]):
            report = _vision_insights(Path("actual.mp4"), 35, transcript)
        self.assertTrue(report["audio_transcript_used"])
        self.assertEqual(report["transcript_chars"], len(transcript))
        self.assertFalse(report["audio_understood"])
        self.assertIn(transcript, captured["prompt"])
        self.assertIn("não afirme ter ouvido", captured["prompt"])

    def test_vision_only_reports_observed_frames(self):
        def ollama(endpoint, payload=None, timeout=10):
            if endpoint == "/api/tags":
                return {"models": [{"name": "llava:7b"}]}
            return {"message": {"content": json.dumps({
                "event": "Carro batendo em muro", "category": "acidente",
                "context_clear": False, "visual_hook": True, "confidence": 0.67,
            })}}
        with patch("clipforge.editorial_intelligence._ollama_json", side_effect=ollama), \
             patch("clipforge.editorial_intelligence._frames", return_value=[str(i) for i in range(9)]):
            report = _vision_insights(Path("actual.mp4"), 35)
        self.assertEqual(report["status"], "visual_partial")
        self.assertFalse(report["audio_understood"])
        self.assertEqual(report["frames_analyzed"], 9)
        self.assertEqual(report["category"], "acidente")

    def test_audio_black_check_is_advisory(self):
        def run(args, **kw):
            if "-vf" in args:
                return SimpleNamespace(returncode=0, stderr=b"black_start:1.1 black_end:3.5")
            return SimpleNamespace(returncode=0, stderr=b"")
        with patch("clipforge.editorial_intelligence.subprocess.run", side_effect=run):
            report = _technical_check(Path("video.mp4"), 35)
        self.assertEqual(report["status"], "checked")
        self.assertTrue(any("escuro" in x for x in report["warnings"]))


class MobilePairingTests(unittest.TestCase):
    def setUp(self):
        self.auth = MobilePairing()
        self.origin = "https://private.example.ts.net"
        self.host = "private.example.ts.net"

    def test_one_use_code_private_cookie_and_scoped_permissions(self):
        code = self.auth.new_code()["code"]
        self.assertEqual(len(code), 10)
        with self.assertRaises(PermissionError):
            self.auth.claim(code, "http://private.example.ts.net", self.host)
        token = self.auth.claim(code, self.origin, self.host)
        self.assertTrue(self.auth.valid_cookie("nexus_review="+token))
        self.assertFalse(self.auth.valid_cookie("nexus_review=incorrect"))
        with self.assertRaises(PermissionError):
            self.auth.claim(code, self.origin, self.host)
        self.assertTrue(self.auth.allowed("GET", "/api/clips/a1/video"))
        self.assertTrue(self.auth.allowed("POST", "/api/clips/a1/review"))
        self.assertFalse(self.auth.allowed("POST", "/api/clips/a1/publish"))
        self.assertFalse(self.auth.allowed("GET", "/api/publishing"))
        self.assertFalse(self.auth.allowed("POST", "/api/metrics/refresh"))
        self.auth.revoke_all()
        self.assertFalse(self.auth.valid_cookie("nexus_review="+token))

    def test_wrong_codes_rate_limited(self):
        self.auth.new_code()
        for _ in range(8):
            with self.assertRaises(PermissionError):
                self.auth.claim("0000000000", self.origin, self.host)
        with self.assertRaisesRegex(PermissionError, "excedidas"):
            self.auth.claim("0000000000", self.origin, self.host)


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ClipStore(Path(self.temp.name))
        with self.store.lock, self.store._db() as db:
            db.execute("""CREATE TABLE publication_jobs
                (id TEXT PRIMARY KEY,platform TEXT,remote_id TEXT,visibility TEXT,
                 status TEXT,updated_at REAL,clip_id TEXT)""")
            db.execute("INSERT INTO publication_jobs VALUES (?,?,?,?,?,?,?)",
                       ("job1", "youtube", "abcdefghijk", "private",
                        "confirmed", time.time(), "clip1"))
            db.execute("INSERT INTO publication_jobs VALUES (?,?,?,?,?,?,?)",
                       ("job2", "tiktok", "1234567891234567", "private",
                        "confirmed", time.time()-1, "clip20000000"))
            db.commit()
        self.metrics = PerformanceMetrics(self.store)

    def test_metrics_are_from_verified_youtube_and_tiktok_ids(self):
        def fake(url,token,body=None):
            if "youtube" in url:
                return {"items": [{"id": "abcdefghijk",
                                   "statistics": {"viewCount": "94", "likeCount": "5"}}]}
            return {"data": {"videos": [{
                "id": "1234567891234567", "view_count": 50,
                "share_count": 4
            }]}, "error": {"code": "ok"}}
        with patch.dict("os.environ", {
             "YOUTUBE_ACCESS_TOKEN": "test-token", "TIKTOK_ACCESS_TOKEN": "test-token"
        }), patch.object(self.metrics, "_get_json", side_effect=fake):
            result = self.metrics.refresh(limit=10)
        self.assertEqual(result["updated"], 2)
        summary = self.metrics.summary()
        self.assertEqual(summary["totals"]["views"], 144)
        self.assertIsNone(summary["totals"]["shares"])  # YouTube share count unavailable.
        self.assertEqual(summary["metric_coverage"]["shares"], 1)
        self.assertEqual(next(item["metrics"]["shares"] for item in summary["items"]
                              if item["platform"]=="tiktok"), 4)
        self.assertIsNone(summary["retention"])
        self.assertEqual(summary["measured_publications"], 2)

    def test_optional_analytics_retention_is_real_or_absent(self):
        report = {
            "columnHeaders": [{"name": "averageViewDuration"}, {"name": "averageViewPercentage"}],
            "rows": [[21.6, 72.4]],
        }
        with patch.dict("os.environ", {"YOUTUBE_ANALYTICS_ACCESS_TOKEN": "analytics-token"}), \
             patch.object(self.metrics, "_get_json", return_value=report) as api:
            result = self.metrics._youtube_retention("abcdefghijk")
        self.assertEqual(result["average_view_percentage"], 72.4)
        self.assertEqual(result["average_view_duration_sec"], 21.6)
        self.assertIn("youtubeanalytics.googleapis.com", api.call_args.args[0])
        with patch.dict("os.environ", {"YOUTUBE_ANALYTICS_ACCESS_TOKEN": ""}):
            self.assertIsNone(self.metrics._youtube_retention("abcdefghijk"))

    def test_errors_never_generate_fake_views(self):
        with patch.dict("os.environ", {"YOUTUBE_ACCESS_TOKEN": "", "TIKTOK_ACCESS_TOKEN": ""}):
            result = self.metrics.refresh()
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["errors"], 2)
        self.assertIsNone(self.metrics.summary()["totals"])


if __name__ == "__main__":
    unittest.main()
