# AI Pipeline — Scenes + Real Speech Subtitles

**Status:** implemented behind explicit feature flags; native dependencies are excluded from the default Docker image and from routine unit tests. Validation in CI covers fake Whisper inference and a separate real synthetic PySceneDetect video. Speech accuracy on licensed streamer gameplay has NOT been evaluated.

## Why two optional tools

- **PySceneDetect** detects scene boundaries, not which GTA 6 event is entertaining. With `SMART_SCENES=1`, the source-media audio heuristic is nudged at most ~10 seconds toward a cut; if the optional package fails, the FFmpeg/audio pipeline continues as before.
- **faster-whisper** transcribes already-rendered, rights-gated clips with actual speech/word timestamps. The generated SRT is fed into HyperFrames HTML templates. No speech means no invented captions.
- Both steps are opt-in to control CPU, model download, disk usage and latency.

## Installation (dedicated worker / local machine)

1. Install Python 3.11+, FFmpeg/ffprobe, and run `python -m pip install -r requirements-ai.txt` on a machine with enough RAM and disk.
2. For source scene selection set `SMART_SCENES=1` when starting the existing application. Default is off.
3. For subtitles set `WHISPER_MODEL=base` or `small`, `WHISPER_LANGUAGE=pt` (or `en`, `es`, or empty for auto). Starting inference may download model weights; cache/size and model licenses must be reviewed beforehand.
4. Set `AUTO_TRANSCRIBE=1` only when a persistent CPU worker has been provisioned and its costs are acceptable. Otherwise use the explicit **Gerar legendas IA** button after the video finishes.
5. Run `python -m unittest discover -s tests -v` and `python -m tools.scene_smoke`. The latter requires OpenCV/PySceneDetect.
6. SRT files are stored privately under `data/captions/<id>.srt`; statuses persist in the SQLite `clip_captions` table.

## Docker CPU profile (optional)

For a local machine or provisioned persistent server, use:
```bash
cp .env.example .env
# Edit DASHBOARD_TOKEN to a unique, strong value
docker compose -f compose.yaml -f compose.ai.yaml up --build
```
The override builds `Dockerfile.ai`, which installs PySceneDetect/OpenCV and faster-whisper. The default container remains small. The model cache lives inside the `/app/data` persistent volume, so downloads are reused across restarts. Auto-transcription remains off unless `AUTO_TRANSCRIBE=1` is explicitly enabled.

**Never use GitHub Actions as a persistent AI server.** The optional scene workflow is an acceptance test, not a daemon.

## Pipeline states and API

- Existing clip remains `ready` even if caption generation fails; a failed optional postprocess must not destroy approved gameplay.
- `GET /api/captions`: per-clip caption status (`not_started`, `queued`, `processing`, `ready`, `failed`).
- `POST /api/clips/{id}/transcribe`: authenticated and rights-gated local transcription request. Concurrent duplicate requests are rejected.
- `GET /api/clips/{id}/captions.srt`: authenticated SRT download only if the video's fingerprint matches its generated captions.
- `POST /api/clips/{id}/hyperframes`: automatically includes valid saved SRT, if any. It still exports a project, not a posted social video.
- `GET /api/clips`: hides license evidence and local input paths to avoid leaking private agreements.

## Measurable constraints

- Selection is **not semantic intelligence**; it ranks speech activity and video cut boundaries only.
- Scene scan is limited to the first five minutes; scenes elsewhere are not analyzed.
- Max rendered video for Whisper: 320 MiB; max subtitles: 150 short cues; one inference at a time.
- Transcription may contain errors, especially game audio, crosstalk, screaming or background music. Editorial review remains mandatory.
- Whisper must not be promised as accurate without testing against manually verified transcripts.
- No unauthorized Twitch downloads, no YouTube/TikTok/Instagram posting, no cloud AI charges initiated by this update.

## Acceptance tests

- Unit: rights gate, model whitelist, no hallucinated caption on silence, timestamp grouping, stale-cache invalidation, API authentication and HyperFrames handoff.
- Synthetic real-video: PySceneDetect detects two hard edits; FFmpeg and HyperFrames continue to use previous validated tests.
- Pending: full speech inference on authorized gameplay; human QA on Portuguese caption correctness and presence of streamed music; CPU benchmarking on intended persistent server.

## Other AI agents

Read AGENTS.md, docs/ARCHITECTURE.md, docs/HYPERFRAMES.md, docs/TWITCH.md and this file before changing any source/scoring logic. Record whether each measurement came from actual media, a mocked language model, or synthetic scene footage. Never treat a passing unit test as real production performance.
