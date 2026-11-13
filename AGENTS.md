# AGENTS.md — instruções para todas as IAs que alterarem este repositório

**Leia primeiro.** Projeto independente GTA-6-clips. Não alterar WildVox, Pokémon Torre 2, Zumbi ou Nexus. A meta é produzir cortes autorizados de gameplay e reações, com revisão verificável, custo controlado e monitoramento móvel.

## Estado exato

- MVP implementado: scanner de vídeos LOCAIS com manifesto de direitos, SHA-256, seleção heurística por intensidade de áudio, FFmpeg 1080x1920/30fps, SQLite, API, fila local e dashboard.
- Implementado agora: descoberta de **metadados de clipes da Twitch** por OAuth de aplicativo, ranking heurístico de visualizações/recência/duração, marcação declarativa de permissão e painel de candidatos. Sem credenciais, retorna claramente que está desconfigurado.
- NÃO implementado: **baixar** lives/clipes Twitch, detecção SEMÂNTICA de melhores momentos, legendas automáticas, face tracking, Metricool conectado ao runtime, publicação social, Cloudflare hospedado. Nunca afirmar que funcionam.
- Aprovar no painel NÃO publica nas redes.
- Não inventar resultados, streams, vídeos, direitos, alcance ou testes.

## Mapa dos arquivos

- clipforge/core.py: ingestão, direitos, ffprobe, banco, FFmpeg e workers.
- clipforge/web.py: HTTP API e autenticação simples.\n- clipforge/twitch.py: OAuth app, consulta de **metadados** de clipes e ranking heurístico; não faz download.
- clipforge/static/: interface HTML/CSS/JS sem framework.
- tests/: testes e ferramentas de QA; tools/smoke.py: teste fim-a-fim sintético.
- docs/: arquitetura, arsenal, roadmap, operação e fontes Twitch. Atualize sempre que alterar contratos.\n- examples/: exemplos públicos sem IDs reais e sem segredos.
- data/: mídias e banco, nunca comitar.

## Regras

1. Processar apenas vídeos próprios ou com permissão documentada. Twitch Clip não é licença de republicação. Sem burlar APIs, DRM, paywalls ou marcas d'água.
2. Conservar fonte, autor e evidências. Nunca colocar tokens, dados privados ou mídias protegidas no Git.
3. Mudança grande em branch/PR com teste de regressão e plano de rollback; preservar funcionalidades aprovadas.
4. Priorizar ferramentas gratuitas/open source; instalar dependência somente após justificar necessidade, custo, licença e manutenção.
5. Não chamar de IA semântica algo que é score de volume de áudio.
6. Não expor dashboard sem HTTPS, autenticação, firewall e controles de acesso.
7. Testes focados durante desenvolvimento; testes completos e smoke test antes de publicar.
8. No frontend, usar textContent para dados do usuário e evitar innerHTML.
9. Não executar comandos de shell com entrada não confiável; validar caminhos e tamanho de arquivos.
10. Publicação automática requer canais reais conectados, regras de direitos, QA e opção de interrupção. Sem exceções.

## Definition of Done

- python -m unittest discover -s tests -v
- python -m compileall -q clipforge tests tools
- python tools/smoke.py (com ffmpeg/ffprobe)
- Confirmar dashboard e prévia em mobile quando possível.
- Relatar commit, testes realmente executados, falhas e limitações remanescentes.

## Sequência P1

Transcrição opcional faster-whisper, score de cena e áudio, modelos de edição e legendas; depois Twitch OAuth autorizado e Metricool. Não instalar o Arsenal completo em massa.
