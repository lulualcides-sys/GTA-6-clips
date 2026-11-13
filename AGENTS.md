# AGENTS.md — instruções para todas as IAs que alterarem este repositório

**Leia primeiro.** Projeto independente GTA-6-clips. Não alterar WildVox, Pokémon Torre 2, Zumbi ou Nexus. A meta é produzir cortes autorizados de gameplay e reações, com revisão verificável, custo controlado e monitoramento móvel.

## Estado exato

- MVP implementado: scanner de vídeos LOCAIS com manifesto de direitos, SHA-256, seleção heurística por intensidade de áudio, FFmpeg 1080x1920/30fps, SQLite, API, fila local e dashboard.
- Implementado agora: descoberta de **metadados de clipes da Twitch** por OAuth de aplicativo, ranking heurístico de visualizações/recência/duração, marcação declarativa de permissão e painel de candidatos. Sem credenciais, retorna claramente que está desconfigurado.
- Adicionado: `clipforge/hyperframes.py` e `clipforge/templates/shorts.css` para exportar composição HTML/CSS HyperFrames, manifesto sem evidências privadas e ZIP protegido pelo token. O MP4-base permanece inalterado. `--render` é **opcional** e precisa de CLI/Chrome em máquina local; botão web apenas exporta.
- NOVO: `clipforge/smart.py` adiciona detecção opcional de mudanças de cena via PySceneDetect (não é reconhecimento semântico); `clipforge/captions.py` enfileira faster-whisper opcional após clipes prontos e cria SRT com timestamps reais. UI permite acionar transcrição; HyperFrames pode incorporar o SRT disponível. Dependências extras em requirements-ai.txt, não instaladas no Docker padrão.
- NÃO implementado: **baixar** lives/clipes Twitch, detecção SEMÂNTICA de melhores momentos, face tracking, Metricool conectado ao runtime, publicação social, Cloudflare hospedado. Legendas automáticas REQUEREM pacote/modelo instalado e ativação explícita. Nunca afirmar funcionamento em produção sem testes reais.
- Aprovar no painel NÃO publica nas redes.
- Não inventar resultados, streams, vídeos, direitos, alcance ou testes.

## Mapa dos arquivos

- clipforge/core.py: ingestão, direitos, ffprobe, banco, FFmpeg e workers.
- clipforge/web.py: HTTP API e autenticação simples.
- clipforge/desktop.py + desktop_launcher.py: shell Windows pywebview/Edge WebView2, HTTP somente 127.0.0.1 com token por processo, persistência em %LOCALAPPDATA%\\GTA6Clips e FFmpeg portátil.
- tools/build_windows.py + windows-app.yml: geração de ZIP de aplicativo Windows, autoteste congelado e compilação somente em Windows.
- clipforge/telemetry.py: histórico durável de eventos reais, 9 módulos visuais; não fabricar status.
- clipforge/demo.py: teste sintético próprio, opt-in e limitado a 3 entradas por volume; sem conteúdo de streamers.
- clipforge/smart.py: seleção visual opcional e compatível com fallback áudio.
- clipforge/captions.py: SRT de fala real, jobs limitados, cache e proteção de direitos.
- clipforge/hyperframes.py: pós-produção opcional, exportação HTML/CSS + SRT, empacotamento, CLI local.
- clipforge/templates/: presets de composição 9:16 próprios e sem dependência CDN.
- clipforge/twitch.py: OAuth app, consulta de **metadados** de clipes e ranking heurístico; não faz download.
- clipforge/static/: interface HTML/CSS/JS sem framework.
- tests/: testes de API, segurança e exportação HyperFrames; tools/smoke.py: render FFmpeg; tools/hyperframes_smoke.py: piloto HyperFrames.
- docs/: arquitetura, arsenal, roadmap, operação, análise de cenas, legendas, fontes Twitch e Mission Control.
- clipforge/static/agents.js e agents.css: dashboard de etapas ligado ao GET /api/agents, sem dados fictícios.
- tools/browser_smoke.mjs: QA visual Playwright PC/mobile; workflow mission-ui.yml. Atualize sempre que alterar contratos.
- examples/: exemplos públicos sem IDs reais e sem segredos.
- data/: mídias e banco, nunca comitar.

## Regras

**Desktop:** nunca mudar dados de LocalAppData para diretório temporário de PyInstaller, nem expor HTTP externo. Não declarar que o aplicativo já foi instalado no PC do usuário; somente o usuário pode baixar/executar o `.exe`. Para saber o estado do build, conferir GitHub Actions e o autoteste do executável.

1. Processar apenas vídeos próprios ou com permissão documentada. Twitch Clip não é licença de republicação. Sem burlar APIs, DRM, paywalls ou marcas d'água.
2. Conservar fonte, autor e evidências. Nunca colocar tokens, dados privados ou mídias protegidas no Git.
3. Mudança grande em branch/PR com teste de regressão e plano de rollback; preservar funcionalidades aprovadas.
4. Priorizar ferramentas gratuitas/open source; instalar dependência somente após justificar necessidade, custo, licença e manutenção.
5. Não chamar de IA semântica algo que é score de volume de áudio. Os nove cartões representam componentes automatizados e controles editoriais, não nove agentes de IA independentes. Não simular atividade; logar somente operações reais.
6. Não expor dashboard sem HTTPS, autenticação, firewall e controles de acesso.
7. Testes focados durante desenvolvimento; testes completos e smoke test antes de publicar.
8. No frontend, usar textContent para dados do usuário e evitar innerHTML.
9. Não executar comandos de shell com entrada não confiável; validar caminhos e tamanho de arquivos.
10. Publicação automática requer canais reais conectados, regras de direitos, QA e opção de interrupção. Sem exceções.

## Definition of Done

- python -m unittest discover -s tests -v
- python -m compileall -q clipforge tests tools
- python -m tools.smoke (com ffmpeg/ffprobe)
- python -m tools.scene_smoke (CI isolado com PySceneDetect instalado, usando cenas sintéticas)
- Confirmar dashboard e prévia em mobile quando possível.
- Relatar commit, testes realmente executados, falhas e limitações remanescentes.

## Sequência P1

Validar desempenho e qualidade da transcrição com vídeo autorizado, verificar seleção visual (não semântica), integrar dados para edição, concluir autenticação Twitch e publicação nas redes somente com canal GTA próprio. Não instalar o Arsenal completo em massa.
