# Curadoria do Arsenal — GTA-6-clips

Origem: [Arsenal do usuário](https://github.com/lulualcides-sys/Arsenal). O catálogo é uma coleção de referências, NÃO significa que tudo está instalado ou liberado para uso comercial. Não copiar bibliotecas ou assets externos sem conferir licença.

| Prioridade | Ferramenta | Uso | Status verificado neste repo |
| --- | --- | --- | --- |
| P0 | FFmpeg + ffprobe | Corte, H.264/AAC, conversão 9:16 e QA de duração/resolução | Implementado no código; executável externo obrigatório |
| P0 | Python stdlib + SQLite | Scanner de permissões, SHA-256, fila e histórico | Implementado |
| P0 | HTML/CSS/JavaScript | Painel responsivo leve, sem dependências frontend | Implementado |
| P0 | GitHub Actions + unittest | Testes de lógica, API e render sintético | Configurado, validar workflow |
| P1 | HyperFrames (heygen-com/hyperframes) | Pacote HTML/CSS 9:16 com títulos animados, crédito e legendas SRT opcionais | **Exportador e download implementados**; render CLI é opcional e tem workflow piloto separado |
| P1 | faster-whisper / WhisperX | SRT e marcas de palavras detectadas; modelo local opt-in | **faster-whisper implementado como opcional**, dependência não instalada no Docker básico; WhisperX continua apenas referência |
| P1 | OpenCV + PySceneDetect | Detecção de cortes e ajuste conservador do início | **PySceneDetect implementado como opcional**; benchmark e detecção semântica ainda pendentes |
| P1 | Twitch Helix + OAuth | Descobrir metadados por categoria/canal | **Implementado em código**, requer credenciais reais; captura de mídia não implementada |
| P1 | Metricool | Publicar/agendar nas contas conectadas | Planejado, NÃO integrado ao código |
| P2 | Remotion | Templates em React com timeline reprodutível | Referência, não instalado |
| P2 | GSAP / SVG.js / Friction | Cartelas, chamadas visuais, overlays animados | Referência, não instalado |
| P2 | Descript | Criar cortes/legendas com agente editor | Conector disponível; não integrado ao pipeline |
| P2 | Cloudflare Workers + D1 + R2 | Painel/armazenamento/fila hospedados | Planejado; render pesado fora de Workers |
| P2 | Playwright | Testes do painel no mobile | Planejado |
| P2 | Sentry / Prometheus / Grafana | Alertas e métricas de produção | Planejado |
| P3 | Awesome Opus 5.5 Videos | Referências visuais para motion graphics | Referência criativa; não gerador de vídeos |
| P3 | Spec Kit / Superpowers / REA / Graphiti | Organização, QA e memória para outros agentes | Referência; uso seletivo |
| P3 | PixelFX / Effekseer / Natron / OpenToonz / Synfig | VFX e composição avançados | Fora do MVP por custo e complexidade |

## Padrão de edição

- Gameplay inteiro no quadro, fundo desfocado; não cortar a facecam nem os eventos essenciais.
- Reação natural e progressão de contexto; evitar clipes genéricos, repetidos ou manipulados.
- 20–60 segundos como meta editorial, mínimo técnico de 10 segundos.
- Legendas curtas, sincronizadas e de alto contraste quando a transcrição real for implementada.
- Preservar criador e origem; a aprovação técnica NÃO substitui revisão editorial e autorização.
- Medir custo de processamento, tempo, retrabalho, retenção e reprovações antes de adicionar tecnologia.

## Critérios para instalar

Problema medido, repositório oficial, licença, versão fixada, custo, teste comparativo, plano de rollback. Não instalar o Arsenal completo de uma só vez.
