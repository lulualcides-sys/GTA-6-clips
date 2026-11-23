"""Preferências do AutoClip escolhidas no painel (cortes, enquadramento, legendas).

Tudo vira argumentos reais da CLI AutoClip. A legenda personalizada é registrada
como preset "nexus_custom" pelo nexus_autoclip_runner.py empacotado (variável
NEXUS_CAPTION_STYLE); com uma CLI externa sem esse runner, cai no preset
escolhido mais próximo e o status informa isso.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PRESETS = {
    "bold_pop": "Bold Pop (palavra cresce e fica amarela)",
    "karaoke_fill": "Karaokê (palavras preenchem ao falar)",
    "clean_lower": "Discreta (rodapé, sem animação)",
    "boxed": "Caixa (texto sobre bloco escuro)",
    "custom": "Personalizada",
}
FONTS = {"Anton": "Anton-Regular.ttf", "Inter": "Inter-Variable.ttf"}
FRAMING = {"auto": "Automático: segue rostos (MediaPipe)", "center": "Centro fixo"}
COLOR = re.compile(r"#[0-9A-Fa-f]{6}")

DEFAULTS = {
    "max_clips": 3,
    "framing": "auto",
    "caption_preset": "boxed",
    "font": "Anton",
    "size_percent": 5.5,      # altura da letra em % da altura do vídeo
    "primary": "#FFFFFF",
    "accent": "#FFE500",      # palavra falada; vazio = sem destaque
    "outline": "#000000",
    "position_percent": 24,   # distância do rodapé em % da altura
    "boxed": False,
    "all_caps": True,
    "max_words": 4,
}


def _path(root: Path) -> Path:
    return Path(root) / "autoclip_settings.json"


def validate(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Configuração inválida")
    out = dict(DEFAULTS)
    for key, value in data.items():
        if key not in DEFAULTS:
            raise ValueError(f"Campo desconhecido: {key}")
        out[key] = value
    try:
        out["max_clips"] = int(out["max_clips"])
        out["size_percent"] = round(float(out["size_percent"]), 2)
        out["position_percent"] = int(out["position_percent"])
        out["max_words"] = int(out["max_words"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Números inválidos na configuração") from exc
    if not 1 <= out["max_clips"] <= 8:
        raise ValueError("Cortes por vídeo: de 1 a 8")
    if out["framing"] not in FRAMING:
        raise ValueError("Enquadramento inválido")
    if out["caption_preset"] not in PRESETS:
        raise ValueError("Estilo de legenda inválido")
    if out["font"] not in FONTS:
        raise ValueError("Fonte disponível: Anton ou Inter")
    if not 2.5 <= out["size_percent"] <= 9:
        raise ValueError("Tamanho da legenda: de 2,5% a 9%")
    if not 5 <= out["position_percent"] <= 45:
        raise ValueError("Posição da legenda: de 5% a 45% do rodapé")
    if not 2 <= out["max_words"] <= 8:
        raise ValueError("Palavras por linha: de 2 a 8")
    for key in ("primary", "outline"):
        if not COLOR.fullmatch(str(out[key])):
            raise ValueError("Cor inválida (use #RRGGBB)")
    if out["accent"] and not COLOR.fullmatch(str(out["accent"])):
        raise ValueError("Cor de destaque inválida (use #RRGGBB ou vazio)")
    out["boxed"] = bool(out["boxed"])
    out["all_caps"] = bool(out["all_caps"])
    return out


def load(root: Path) -> dict:
    path = _path(root)
    try:
        if path.is_file() and not path.is_symlink() and path.stat().st_size < 16_000:
            return validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return dict(DEFAULTS)


def save(root: Path, data: dict) -> dict:
    settings = validate(data)
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return settings


def caption_style_spec(settings: dict) -> dict:
    """Formato lido pelo nexus_autoclip_runner.py para registrar 'nexus_custom'."""
    return {
        "font": settings["font"], "font_file": FONTS[settings["font"]],
        "size_ratio": round(settings["size_percent"] / 100, 4),
        "primary": settings["primary"], "accent": settings["accent"] or None,
        "outline": settings["outline"], "outline_width": 0.0 if settings["boxed"] else 4.0,
        "margin_v_ratio": round(settings["position_percent"] / 100, 3),
        "boxed": settings["boxed"], "all_caps": settings["all_caps"],
        "max_words": settings["max_words"],
        "animation": "scale" if settings["accent"] else "none",
    }


def cli_args(settings: dict, custom_supported: bool) -> tuple[list[str], dict]:
    """Argumentos da CLI + variáveis de ambiente para uma execução."""
    style = settings["caption_preset"]
    env = {}
    if style == "custom":
        if custom_supported:
            env["NEXUS_CAPTION_STYLE"] = json.dumps(caption_style_spec(settings))
            style = "nexus_custom"
        else:
            style = "boxed" if settings["boxed"] else "bold_pop"
    args = ["--max-clips", str(settings["max_clips"]), "--ratio", "9:16", "--style", style]
    if settings["framing"] == "center":
        args.append("--centre-crop")
    return args, env


RUNNER_SOURCE = '''import json, os
from autoclip.cli import app

_spec = os.environ.get("NEXUS_CAPTION_STYLE")
if _spec:
    # Legenda personalizada no painel do Nexus -> preset real do AutoClip.
    from autoclip.pipeline import captions as _captions
    _data = json.loads(_spec)
    _captions.PRESETS["nexus_custom"] = _captions.CaptionStyle(
        key="nexus_custom", label="Nexus", description="Personalizada no Nexus Clips BR",
        **_data)

if __name__ == "__main__":
    app()
'''
