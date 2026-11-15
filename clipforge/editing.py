"""Edição determinística e auditável; nenhuma heurística representa compreensão semântica."""
from __future__ import annotations
import math
import os
from pathlib import Path

DEFAULT_EDIT = {'title': '', 'title_verified': False, 'layout': 'preserve',
                'focus_x': 0.5, 'focus_y': 0.5, 'facecam_region': None,
                'game': '', 'reaction_review': None}


def rank_audio_windows(powers: list[float], length: float) -> list[dict]:
    """Até três sugestões distintas; volume isolado recebe penalidade de contexto.

    Continuidade e dinâmica são sinais técnicos, não riso, explosão ou relevância.
    Os valores ausentes continuam null em vez de inventar métricas editoriais.
    """
    window = max(1, min(int(length), len(powers)))
    if not powers:
        return []
    peak = max(powers) or 1
    noise_floor = max(120, sorted(powers)[len(powers) // 4] * 0.3)
    candidates = []
    for start in range(len(powers) - window + 1):
        section = powers[start:start + window]
        activity = sum(v > noise_floor for v in section) / window
        intensity = sum(min(1, v / peak) for v in section) / window
        dynamic = (max(section) - min(section)) / max(1, max(section))
        context = min(1, sum(v > noise_floor for v in section[:max(1, window // 3)]) / max(1, window // 3))
        quality = 1 - sum(v >= 32000 for v in section) / window
        score = round(100 * (0.40 * activity + 0.15 * intensity + 0.15 * dynamic + 0.20 * context + 0.10 * quality), 2)
        candidates.append({'start_sec': float(start), 'duration_sec': float(length), 'score': score,
                           'method': 'audio-heuristic', 'components': {
                               'activity': round(activity, 3), 'intensity': round(intensity, 3),
                               'dynamics': round(dynamic, 3), 'context_proxy': round(context, 3),
                               'audio_quality_proxy': round(quality, 3), 'semantic_relevance': None,
                               'entertainment': None, 'originality': None, 'retention_actual': None},
                           'warning': 'Atividade acústica não comprova humor nem compreensão do acontecimento.'})
    selected = []
    for candidate in sorted(candidates, key=lambda c: (-c['score'], c['start_sec'])):
        if all(abs(candidate['start_sec'] - item['start_sec']) >= max(3, length * 0.5) for item in selected):
            selected.append(candidate)
        if len(selected) == 3:
            break
    return selected


def validate_edit(edit: dict, item: dict, info: dict) -> dict:
    """Valida ajustes manuais e exige evidência de reação para jogos GTA declarados."""
    result = dict(edit)
    total = float(info.get('format', {}).get('duration', 0))
    start = result.get('start_sec')
    duration = result['duration_sec']
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 10 <= duration <= 60:
        raise ValueError('Duração precisa ser finita entre 10 e 60 segundos')
    if start is not None and (isinstance(start, bool) or not isinstance(start, (int, float)) or not math.isfinite(start) or start < 0 or start + duration > total + 0.1):
        raise ValueError('Início ou fim fora dos limites da fonte')
    title = result.get('title', '')
    if not isinstance(title, str) or len(title) > 72 or any(ord(c) < 32 for c in title):
        raise ValueError('Título deve ter até 72 caracteres, sem quebras de linha')
    if title and result.get('title_verified') is not True:
        raise ValueError('Título exige conferência editorial do acontecimento real')
    if result.get('title_verified') not in (True, False):
        raise ValueError('Conferência de título inválida')
    if result['layout'] not in {'preserve', 'focus', 'facecam'}:
        raise ValueError('Enquadramento desconhecido')
    for key in ('focus_x', 'focus_y'):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('Posição de foco deve estar entre 0 e 1')
    video = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), {})
    region = result.get('facecam_region')
    if region is not None:
        if not isinstance(region, (list, tuple)) or len(region) != 4 or any(isinstance(v, bool) or not isinstance(v, int) for v in region):
            raise ValueError('Facecam exige retângulo real em pixels da fonte')
        x, y, w, h = region
        if min(x, y) < 0 or min(w, h) < 2 or x + w > video.get('width', 0) or y + h > video.get('height', 0):
            raise ValueError('Facecam fora da imagem original')
    if result['layout'] == 'facecam' and region is None:
        raise ValueError('Facecam exige região revisada manualmente')
    game = result.get('game', '')
    if not isinstance(game, str) or len(game) > 100:
        raise ValueError('Jogo inválido')
    if 'grand theft auto' in game.lower() or game.lower().startswith('gta'):
        from .reaction_qa import ReactionReview
        review = result.get('reaction_review')
        if not isinstance(review, dict):
            raise ValueError('Reação e facecam GTA exigem revisão humana registrada')
        try:
            audit = ReactionReview(**review).validate()
        except (TypeError, ValueError, AttributeError):
            raise ValueError('Revisão de reação inválida') from None
        if not audit['eligible_for_editorial_preview']:
            raise ValueError('Reação não aprovada: ' + '; '.join(audit['reasons']))
        if review['creator'] != item['creator'] or review['source_url'] != item['source_url'] or abs(review['duration'] - total) > .2:
            raise ValueError('Reação não pertence à fonte cadastrada')
        if start is None or start > review['setup_start'] or start + duration < review['reaction_end']:
            raise ValueError('O corte precisa preservar contexto e reação conferidos')
        # O crop de ação não pode ocultar a câmera aprovada.
        if result['layout'] == 'focus':
            raise ValueError('GTA com reação exige enquadramento preserve ou facecam')
        if result['layout'] == 'facecam' and list(region) != list(review['facecam_region']):
            raise ValueError('Facecam deve corresponder à região da revisão')
    return result


def source_fps(info: dict) -> int:
    """30 fps por padrão; 60 somente quando fonte e limite operacional permitem."""
    video = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), {})
    try:
        numerator, denominator = str(video.get('avg_frame_rate', '30/1')).split('/')
        rate = float(numerator) / float(denominator)
        maximum = int(os.getenv('RENDER_MAX_FPS', '30'))
    except (ValueError, ZeroDivisionError):
        return 30
    return 60 if rate >= 50 and maximum >= 60 else 30


def video_filter(edit: dict, fps: int) -> str:
    """Layout manual explícito; manter toda a fonte é o padrão conservador."""
    if edit['layout'] == 'focus':
        base = ('[0:v]scale=1080:1920:force_original_aspect_ratio=increase,'
                f"crop=1080:1920:(iw-ow)*{edit['focus_x']}:(ih-oh)*{edit['focus_y']}[composed];")
    elif edit['layout'] == 'facecam':
        x, y, w, h = edit['facecam_region']
        base = (f'[0:v]split=3[bg][fg][cam];[bg]scale=1080:1920:force_original_aspect_ratio=increase,'
                'crop=1080:1920,boxblur=24:2[blur];'
                '[fg]scale=1080:1100:force_original_aspect_ratio=decrease[sharp];'
                '[blur][sharp]overlay=(W-w)/2:700+(1100-h)/2:shortest=1[game];'
                f'[cam]crop={w}:{h}:{x}:{y},scale=960:500:force_original_aspect_ratio=decrease[camera];'
                '[game][camera]overlay=(W-w)/2:150+(500-h)/2:shortest=1[composed];')
    else:
        base = ('[0:v]split=2[bg][fg];[bg]scale=1080:1920:force_original_aspect_ratio=increase,'
                'crop=1080:1920,boxblur=24:2[blur];'
                '[fg]scale=1080:1700:force_original_aspect_ratio=decrease[sharp];'
                '[blur][sharp]overlay=(W-w)/2:(H-h)/2:shortest=1[composed];')
    # Texto vem de arquivos UTF-8 temporários: evita injeção em expressões FFmpeg.
    font = ''
    windows_font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'segoeui.ttf'
    if os.name == 'nt' and windows_font.is_file():
        escaped = windows_font.as_posix().replace(':', r'\:')
        font = f"fontfile='{escaped}':"
    return (base + f'[composed]setsar=1,fps={fps},'
            f'drawtext={font}textfile=title.txt:expansion=none:fontcolor=white:fontsize=40:'
            'x=(w-tw)/2:y=72:box=1:boxcolor=black@0.55:boxborderw=12,'
            f'drawtext={font}textfile=credit.txt:expansion=none:fontcolor=white:fontsize=24:'
            'x=(w-tw)/2:y=h-70:box=1:boxcolor=black@0.55:boxborderw=8,format=yuv420p[out]')
