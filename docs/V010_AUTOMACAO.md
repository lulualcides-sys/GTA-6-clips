# v0.10.0 — Radar com histórico e lives, AutoClip configurável, exportação e falhas

Tudo abaixo está implementado e testado. A última seção diz o que depende de contas ou autorizações externas.

## 1. Radar de conteúdo
- **Canais autorizados**: Twitch (Radar viral → "Ele autorizou"/bio) e YouTube (aba YouTube) gravam a evidência em `twitch_sources.json` / `youtube_sources.json`. Downloads só acontecem para esses canais.
- **Histórico e fila** (`clipforge/ingest_log.py`, tabela `ingest_jobs`): cada clipe, vídeo ou VOD tentado gera uma linha com plataforma, origem, status (`downloading`, `done`, `failed`), tentativas, erro real e **modo** (`automatico`/`manual`). Aba **Atividade**, com filtro por status.
- **Monitor de lives da Twitch** (`clipforge/live_monitor.py`, tabela `live_sessions`):
  - consulta a API oficial *Get Streams* a cada `TWITCH_LIVE_POLL_SECONDS` (padrão 120 s), somente para os streamers autorizados;
  - registra início, fim, título e jogo de cada live;
  - quando a live termina, busca a gravação pela API oficial *Get Videos* (`type=archive`).
  - Com a opção **"Baixar a VOD quando a live terminar"** ligada (`TWITCH_LIVE_VOD_DOWNLOAD=1`, que também liga `TWITCH_PUBLIC_DOWNLOAD=1`), o app baixa a VOD pública via yt-dlp: até 1080p, `TWITCH_VOD_MAX_MINUTES` (padrão 180) e 8 GiB, nunca ao vivo. Depois entrega a VOD à ingestão, e o AutoClip faz os cortes.
  - A live **não** é gravada em tempo real. A gravação contínua exigiria capturar o stream o tempo todo; a VOD é a alternativa estável.
- **Verificar agora**: roda Twitch, YouTube e lives na hora, e os itens ficam marcados como *Manual*.

## 2. AutoClip com IA local
A detecção de melhores momentos, os vários cortes por vídeo, o formato 9:16, a legenda sincronizada (Whisper) e o enquadramento por rosto (MediaPipe) são feitos pelo **AutoClip real**. Novo cartão **Ajustes → Cortes do AutoClip** (`clipforge/autoclip_settings.py`):
- **Cortes por vídeo:** de 1 a 8 (`--max-clips`).
- **Enquadramento:** automático, que segue rostos, ou centro fixo (`--centre-crop`).
- **Legenda:** 4 estilos prontos do AutoClip ou **Personalizada**, com fonte (Anton/Inter), tamanho, cor do texto, cor da palavra falada, contorno, posição, caixa, maiúsculas e palavras por linha.
  - A personalizada vira o preset `nexus_custom` do próprio AutoClip, registrado pelo `nexus_autoclip_runner.py` empacotado (variável `NEXUS_CAPTION_STYLE`).
  - O build Windows confere que o preset aparece em `autoclip styles`.
  - O registro foi testado contra a classe `CaptionStyle` real do AutoClip fixado.
- **Visualizar e editar antes de exportar:** as sugestões do AutoClip continuam com prévia, importação e aprovação. A edição do corte final é feita na exportação (trecho de início e fim, título).

## 3. Processamento e metadados (`clipforge/exporter.py`)
- **Aba Clipes → Exportar corte:**
  - formato: MP4 (H.264), MOV ou WebM (VP9);
  - resolução: original, 1080×1920, 720×1280 ou 540×960, com letterbox, sem distorcer;
  - qualidade: original, alta, média ou leve;
  - trecho: início e fim;
  - título.
- **Sem perda**: em MP4/MOV com resolução e qualidade "original" e sem trecho, a cópia é feita com `-c copy`, sem reencodar.
- **O MP4 do AutoClip nunca é alterado**: cada exportação é uma cópia nova em `data/exports`, com um `.json` de procedência ao lado.
- **Metadados legítimos**:
  - `title`, `artist`, `copyright` e `encoded_by` (criador e Nexus);
  - `comment`/`description`, com criador, link de origem e direitos;
  - `-map_metadata 0`, que preserva os metadados de origem.

  Não existe opção de apagar a origem nem de enganar detectores de conteúdo duplicado. Campos desconhecidos (ex.: `strip_origin`) são recusados.

## 4. Automação e publicação
- **Fila de publicação já existente**: APIs oficiais de YouTube e TikTok, mais o Postiz; agendamento; limite diário; dedupe; sem repost de envio incerto. Ela continua sendo usada.
- **Ações automáticas marcadas como tal** no histórico, nas notificações e nas publicações (`automatic`).
- **Falhas e avisos** (`clipforge/notifications.py`, aba Atividade) nas últimas 24 h:
  - downloads com falha;
  - edições do AutoClip com erro;
  - publicações que falharam;
  - último erro de cada automação.

  A aba mostra um contador, e o app avisa com um toast quando surge uma falha nova.

## Novas configurações (`config.env`)
`TWITCH_LIVE_MONITOR=1`, `TWITCH_LIVE_VOD_DOWNLOAD=0`, `TWITCH_LIVE_POLL_SECONDS=120`, `TWITCH_VOD_MAX_MINUTES=180`.

## Depende de autorização ou integração externa
- **Twitch (lives e VODs):** precisa de Client ID/Secret e de streamers autorizados. O download da VOD é público via yt-dlp e não é oficial, com risco perante os Termos da Twitch assumido pelo proprietário. VODs só para inscritos, ou com a gravação desativada pelo streamer, falham e aparecem no histórico.
- **IA local:** Ollama e modelo instalados pelo botão "Preparar IA do AutoClip".
- **Publicação real:**
  - YouTube: precisa de OAuth `youtube.upload`.
  - TikTok: precisa da Content Posting API aprovada pelo TikTok; até a aprovação, os posts ficam privados (`SELF_ONLY`).
  - Instagram: continua não implementado (exige conta profissional e hospedagem HTTPS do MP4).
- **Testes reais:** nada disso foi testado com contas reais nesta sessão. Os testes usam respostas simuladas da Twitch e mídia sintética própria, com FFmpeg real.

## v0.11.0 — gravação de live em tempo real e marcação de trecho
- **Gravar a live em tempo real** (`clipforge/live_recorder.py`, opção na aba Atividade, `TWITCH_LIVE_RECORD=1`, que liga também o download público):
  - quando um streamer **autorizado** entra ao vivo, o yt-dlp grava a live pública desde aquele momento (até 1080p, no máximo `TWITCH_RECORD_MAX_MINUTES`, padrão 240);
  - quando a live termina, a gravação passa por um remux sem reencode para MP4, ganha um manifesto de direitos (`download_method=live_recording_yt_dlp`) e vai para o AutoClip;
  - quem foi gravado não tem a VOD baixada de novo;
  - se a gravação falhar, o monitor tenta a VOD.
  - Não é oficial (risco perante os Termos da Twitch, assumido pelo proprietário), e lives de outros streamers nunca são gravadas.
- **Marcar trecho no vídeo**: no Exportar, os botões "⏱ Marcar no vídeo" usam o tempo atual do player como início ou fim.
