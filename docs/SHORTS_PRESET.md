# Shorts — ação + reação

Preset integrado ao editor e ao renderizador FFmpeg em 15/11/2026. Não exige novas dependências. Não é detector semântico, rastreador de facecam nem promessa de alcance/monetização.

## Uso

1. Selecione uma fonte com direitos registrados e abra **Original e ajustes**.
2. Defina início, duração e um título curto fiel ao acontecimento; confirme o título após assistir.
3. Escolha **Shorts — ação + reação**.
4. Informe facecam e região da ação como `x, y, largura, altura`, em pixels da fonte original. A região precisa conter o acontecimento durante todo o trecho; estas coordenadas são manuais e não transferíveis automaticamente entre streamers.
5. Salve, renderize e confira a prévia. Só então aprove.

O preset gera 1080×1920 com facecam superior, gameplay em destaque, fundo desfocado escurecido, crédito permanente e título separado da ação. Mantém a proporção dos recortes, normaliza o áudio original e usa corte seco. Sem título informado, não insere uma frase genérica. `RENDER_MAX_FPS=60` permite 60 FPS quando a fonte suporta; padrão econômico 30 FPS.

Os layouts anteriores continuam disponíveis. Alterações invalidam a prévia anterior; arquivos aprovados permanecem protegidos. O modo GTA continua exigindo revisão de reação vinculada à mesma fonte. O preset não concede direitos nem publica nas redes.

## Limites desta entrega

Não inclui reprise automática, zoom guiado por eventos, escolha semântica do momento, geração automática de títulos contextuais ou marcação visual de regiões com o mouse. As reprises dos vídeos editados manualmente anteriormente não foram incorporadas neste incremento. O enquadramento deve ser revisto quando a câmera do jogo muda. Fontes com facecam pequena terão ampliação limitada pela resolução original.

## Verificação local

- 193 testes Python passaram.
- `python -m tools.astra_smoke --output data/astra-preset-qa-20261115`: preset real, FFmpeg, áudio não silencioso, ausência de intervalos pretos, originais preservados, prévia e aprovação HTTP, exportação HyperFrames e fila simulada.
- `python -m tools.smoke`: fluxo base preservado.
- `/tmp/astra-qa-venv/bin/python -m tools.scene_smoke`: cortes sintéticos detectados em 2 e 4 s.
- `tools/browser_editor_smoke.mjs`: passou no Chromium com MP4 original/editado, preset salvo, render real, proteção dos aprovados, aprovação em lote e viewport mobile de 390 px.

A mídia sintética comprova funcionamento técnico, não qualidade editorial ou potencial de audiência. Não representa instalação no PC do usuário nem novo executável Windows validado.
