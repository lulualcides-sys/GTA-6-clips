# GTA-6-clips

Projeto independente de **GTA 6**: ingestão de vídeos autorizados, seleção inicial de cortes por áudio, render vertical (9:16) e painel web de revisão. Organizado para manutenção por múltiplos agentes de IA.

> **Estado real:** MVP local-first. Ainda **não** coleta lives ou clipes da Twitch automaticamente, **não** transcreve falas, **não** publica nas redes e **não** está hospedado em domínio público.

## Iniciar (Python)

Requer Python 3.11+ e FFmpeg/ffprobe instalados no PATH:

```bash
python -m clipforge.web
```

Abra http://127.0.0.1:8000. Scanner a cada 30s, AUTO_RENDER=1 por padrão (somente fontes com manifesto válido).

## Cadastrar vídeo com direitos

Coloque `data/incoming/meu-video.mp4` e `data/incoming/meu-video.mp4.rights.json`:

```json
{
  "creator": "Nome do criador",
  "rights_status": "permission_granted",
  "evidence": "URL ou registro verificável da autorização",
  "source_url": "https://www.twitch.tv/...",
  "start_sec": 20,
  "duration_sec": 35
}
```

Para vídeo próprio, use `rights_status: "owned"`. O sidecar é autodeclaração; **não comprova automaticamente os direitos**. Sem `start_sec`, uma heurística de áudio escolhe a janela; não se trata de IA semântica. Saída: MP4 H.264/AAC, 1080x1920, 30 FPS, gameplay central e fundo desfocado, sem cortes destrutivos.

## Docker

```bash
cp .env.example .env
# Troque DASHBOARD_TOKEN por uma senha forte antes de executar
mkdir -p data
docker compose up --build
```

Acesse http://127.0.0.1:8000. Em Linux pode ser preciso ajustar permissões de `data/` para UID 10001 (container não-root). Não publique `.env` nem `data/`.

## Testes

```bash
python -m unittest discover -s tests -v
python -m compileall -q clipforge tests tools
python -m tools.smoke
```

O smoke gera vídeo **sintético**, testa a verificação de direitos e renderiza uma saída técnica real. GitHub Actions executa tudo após commits.

## Limites e segurança

- API com token `DASHBOARD_TOKEN` em acessos não locais; produção requer HTTPS e proteção adicional.
- Apenas **um render por vez** para limitar uso de CPU; persistência SQLite + mídia local.
- A tela permite aprovar/rejeitar. **Aprovação não é publicação**.
- Não ingerir sem autorização de terceiros. Respeitar termos da plataforma, direitos de voz/imagem e propriedade intelectual.
- Não hospedar mídia, banco, licenças privadas ou tokens no GitHub.

Leia **AGENTS.md** primeiro. Arquitetura em docs/ARCHITECTURE.md; inventário filtrado em docs/ARSENAL.md; prioridades em docs/ROADMAP.md; operações em docs/RUNBOOK.md.
