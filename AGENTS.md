# AGENTS.md — instruções para todas as IAs que alterarem este repositório

**REGRA DE EDIÇÃO (16/11/2026): SOMENTE AUTOCLIP.** Todos os novos vídeos devem ser editados exclusivamente pela CLI real AutoClip (artbyjazi/autoclip). Não fazer edição de substituição com FFmpeg, Remotion, HyperFrames, heurísticas acústicas, cortes manuais ou código próprio quando a CLI falhar ou não estiver instalada. FFmpeg/ffprobe são permitidos apenas para validação/decodificação, mídia sintética dos testes e dependências internas do próprio AutoClip. Importar a saída AutoClip validada diretamente para revisão; não re-renderizar pelo Nexus. Preservar saídas anteriores e aprovações. Testar pipeline e informar bloqueio verdadeiro caso CLI ausente. Publicar somente após testes verdes e edição real verificada.

**Leia primeiro.** Projeto independente GTA-6-clips. Não alterar WildVox, Pokémon Torre 2, Zumbi ou Nexus. A meta é descobrir clipes públicos de qualquer categoria em alta, preparar prévias para revisão e publicar apenas com direitos necessários, custo controlado e monitoramento móvel.

## Atualização Astra — 14/11/2026 (prevalece sobre inventário histórico abaixo)

O pedido atual do usuário substitui a antiga restrição pré-lançamento `gta5_only`: até 12 categorias configuráveis/populares, prioridade GTA VI na data configurada e override manual. Não alterar a data com base em suposição.

Edição agora usa ajustes persistentes, títulos conferidos, crédito FFmpeg, layouts manuais, saída versionada, SHA da fonte e QA de decodificação. A heurística acústica não detecta semanticamente gritos, risos ou acontecimentos. Facecam é região manual, não rastreamento automático. Preservar gate GTA de reação da mesma fonte.

Publicação possui fila e adaptadores oficiais, mas credenciais configuradas não comprovam conexão válida. Testes locais de contrato não comprovam publicação externa; diferenciar `pending`, `confirmed`, visibilidade privada e envio incerto. Não reenviar upload incerto. Consulte `docs/PUBLISHING.md` e `docs/ASTRA_REPORT.md` para limitações atuais.

Antes de afirmar conclusão, rodar suíte, smoke FFmpeg, smoke cenas (dependência opcional), integração Astra e browser. Testes Windows da revisão precisam de GitHub Actions; testes Python Linux não substituem instalação/execução nativa.

O restante deste arquivo registra a base anterior e suas restrições editoriais; descrições de recursos ausentes devem ser conferidas contra o relatório Astra.

## Estado exato

- MVP implementado: scanner de vídeos LOCAIS com manifesto de direitos, SHA-256, seleção heurística por intensidade de áudio, FFmpeg 1080x1920/30fps, SQLite, API, fila local e dashboard.
- Implementado agora: descoberta de **metadados de clipes da Twitch** por OAuth de aplicativo, ranking heurístico de visualizações/recência/duração, marcação declarativa de permissão e painel de candidatos. Sem credenciais, retorna claramente que está desconfigurado.
- Adicionado: `clipforge/hyperframes.py` e `clipforge/templates/shorts.css` para exportar composição HTML/CSS HyperFrames, manifesto sem evidências privadas e ZIP protegido pelo token. O MP4-base permanece inalterado. `--render` é **opcional** e precisa de CLI/Chrome em máquina local; botão web apenas exporta.
- NOVO: `clipforge/smart.py` adiciona detecção opcional de mudanças de cena via PySceneDetect (não é reconhecimento semântico); `clipforge/captions.py` enfileira faster-whisper opcional após clipes prontos e cria SRT com timestamps reais. UI permite acionar transcrição; HyperFrames pode incorporar o SRT disponível. Dependências extras em requirements-ai.txt, não instaladas no Docker padrão.
- NÃO implementado: **baixar** lives/clipes Twitch, detecção SEMÂNTICA de melhores momentos, face tracking, Metricool conectado ao runtime, publicação social, Cloudflare hospedado. Legendas automáticas REQUEREM pacote/modelo instalado e ativação explícita. Nunca afirmar funcionamento em produção sem testes reais.
- Aprovar no painel NÃO publica nas redes.
- Entregas de vídeo em revisão: preferir URL HTTPS com player diretamente no navegador, sem exigir download do MP4; confirmar que a fonte da mídia não expirou.
- Não inventar resultados, streams, vídeos, direitos, alcance ou testes.

## Regra nova de câmera e reação (13/11/2026)

**O usuário rejeitou a V9 por não mostrar câmera e reação.** Para novos cortes GTA V/GTA VI, selecionar **somente** clipes com webcam/facecam real visível **e reação do próprio streamer ao evento na mesma fonte**. Não usar câmera fictícia nem importar reação de outra live. `clipforge/reaction_qa.py` é um gate de auditoria de dados conferidos manualmente, **não é detector automático**. Ver docs/REACTION_REQUIRED.md. A V9 não deve virar preset. Ainda falta integrar o gate ao fluxo de seleção e renderização.

## Padrão editorial Nexus Clips BR (13/11/2026)

Até o lançamento, para cortes de humor visual de GTA V e GTA RP, consultar **docs/nexus-clips-br-editorial.md** antes da revisão: título curto em PT-BR, sem rótulo de replay, replay lento opcional, crédito pequeno ao criador, marca-d'água compacta Nexus Clips BR e final com corte seco. Para cenas cujo humor dependa da fala, a legenda PT-BR deve traduzir fielmente o áudio de verdade; não inventar diálogo. Aprovação editorial e direitos de publicação são gates distintos. A implementação automática do preset no aplicativo e o PNG no instalador ainda dependem de integração e testes; este documento não os configura por si só.

## Perfis narrativos por tipo de evento (planejamento, ainda não render automático)

A V8 de CS é uma referência de **acabamento aprovado**, não um recorte universal. Antes de editar outros jogos, consultar **docs/EDITORIAL_PRESETS.md** e usar `clipforge/editorial_profiles.py` / `python -m tools.editorial_plan` para sugerir contexto, desenrolar, clímax, reação e replay. **Evento prevalece sobre jogo:** GTA RP pode ser diálogo; GTA VI pode ser ação ou humor; Minecraft pode ser sobrevivência ou zoeira. Esses perfis dependem de tempos identificados e validados manualmente e **não** detectam jogadas, piadas, falas ou o rosto de um streamer. Não alegar que a implementação destes planejadores já automatizou a edição ou está instalada no Windows. Preservar os vídeos e padrões aprovados.

## Preparação específica do GTA VI (13/11/2026)

Consultar **docs/GTA6_EDITORIAL_READINESS.md** e **clipforge/gta6_readiness.py**. Treinar em GTA V com 7 roteiros editoriais transferíveis para GTA VI: perseguição, assalto, dupla, humor físico, momento viral, exploração e diálogo RP. Confirmado oficialmente: história de Jason/Lucia, Vice City/Leonida, crime e presença de redes sociais na ambientação. **Não** assumir GTA VI RP/multiplayer, postagens in-game, física ou IA policial específica antes de evidência concreta. Aplicar a qualidade da V8 de CS (aprovada) adaptando enquadramento e cortes ao evento. Planejador requer timestamps humanos, não é sistema de edição automática. Até 18/11 o radar monitora GTA V; em 19/11 passa a GTA VI conforme regra vigente. Preservar trilha de aprovação e direitos de terceiros.

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
- clipforge/twitch.py: OAuth e busca somente de **metadados** (sem download). **Até 18/11/2026**, perfil `gta5_only`: consultar somente a categoria exata GTA V (que inclui streamers de GTA RP), de qualquer criador. **Em 19/11/2026, 00:00 America/Sao_Paulo** (`2026-11-19T03:00:00Z`), comutação automática para `gta6_only`: somente GTA VI, sem trazer registros antigos de GTA V. `TWITCH_GTA5_GAME_ID` pode indicar ID exato antes da virada; `TWITCH_GAME_ID` é reservado para o ID GTA VI depois. `TWITCH_GTA6_LAUNCH_AT` altera a data apenas se o calendário oficial mudar. PT-BR tem prioridade sem excluir outros idiomas, mas nunca misturar outros jogos. APIs continuam exigindo credenciais.
- clipforge/static/: interface HTML/CSS/JS sem framework.
- tests/: testes de API, segurança e exportação HyperFrames; tools/smoke.py: render FFmpeg; tools/hyperframes_smoke.py: piloto HyperFrames.
- docs/: arquitetura, arsenal, roadmap, operação, análise de cenas, legendas, fontes Twitch e Mission Control.
- clipforge/static/agents.js e agents.css: dashboard de etapas ligado ao GET /api/agents, sem dados fictícios.
- tools/browser_smoke.mjs: QA visual Playwright PC/mobile; workflow mission-ui.yml. Atualize sempre que alterar contratos.
- examples/: exemplos públicos sem IDs reais e sem segredos.
- data/: mídias e banco, nunca comitar.

## Sistema de atualizações Windows

- `clipforge/version.py`: número SemVer atual; nunca anunciar versão maior antes de release válida.
- `clipforge/updater.py`: consulta API GitHub Releases, exige digest SHA-256, limita download/extração, valida novo EXE com `--self-test`.
- `desktop_update_helper.py`: compilado como EXE independente; espera processo antigo encerrar, troca diretórios, mantém backup e tenta rollback em falhas.
- `tools/build_windows.py`: empacota também `GTA6ClipsUpdater.exe`; releases estáveis só após pipeline Windows verde.
- `tests/test_updater.py`: cobertura de URL oficial, releases estáveis, SHA-256, zip-slip, persistência e caminhos seguros.
- Atualização é **um clique** no painel, não auto-instalação silenciosa. Primeira versão antiga requer baixar novo pacote manualmente.
- Nunca colocar mídias, bancos de dados, arquivos `config.env` ou segredos dentro do ZIP do programa. Armazenar dados só em LocalAppData.
- Bump de versão **somente** quando realmente quiser lançar nova release; release do GitHub não deve ser reescrita ou substituída.

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

Conectar OAuth Twitch real no Windows (segredos privados) e validar consulta exclusiva de GTA V antes do lançamento e GTA VI após a virada. Validar desempenho e qualidade da transcrição com vídeo autorizado, verificar seleção visual (não semântica), integrar dados para edição, concluir autenticação Twitch e publicação nas redes somente com canal GTA próprio. Não instalar o Arsenal completo em massa.

## IA local do AutoClip e teste de conexões (v0.7.0, 18/11/2026)

O motor AutoClip já vai no EXE (`autoclip_runtime/`). O usuário pediu a IA instalada direto no app: `clipforge/local_ai.py` instala o Ollama oficial **somente após clique do proprietário**, com assinatura Authenticode verificada, e baixa modelo de lista fechada. Não embutir pesos de modelo no ZIP nem no Git; não aceitar nomes de modelo arbitrários; não pular a verificação de assinatura. `clipforge/connection_check.py` faz uma chamada somente leitura por plataforma: nunca postar, nunca devolver tokens. Teste real no Windows do usuário ainda não foi feito.

`clipforge/viral_radar.py` + `static/viral.js` (Radar Viral BR): ranking somente por metadados públicos (reusa `curation.qualifies`/`ranked_shortlist`), sem baixar mídia. O botão "Ele autorizou" grava `twitch_sources.json` com evidência obrigatória (somente token do proprietário). O usuário pediu baixar/postar clipes sem autorização "para resolver depois": **recusado** — não implementar download por yt-dlp/scraping nem pular a lista de autorizados.
Leitura de bios (`POST /api/twitch/policies`, Get Users oficial) só **sugere** política de cortes (`allowed`/`restricted`/`unknown`; restrição sempre vence); a autorização exige confirmação do proprietário, com o trecho da bio salvo como evidência. Painéis da Twitch não estão na API oficial e não são lidos.

## AutoClip e Postiz (integração opt-in, 16/11/2026)

Consultar `docs/AUTOCLIP_POSTIZ_RUNTIME.md`. A ponte AutoClip via CLI gera até 3 prévias isoladas de fonte autorizada e permite importação manual para a biblioteca, criando novo clipe pendente de revisão (não altera original/edições/aprovações). A integração Postiz adiciona destinos privados à fila existente, mas depende de API key, IDs dos canais e opt-in; **não é postagem comprovada**. Não instalar AutoClip automaticamente no EXE (Python 3.11/12, dependências pesadas) e não copiar Postiz AGPL para este repositório. Preservar worker, deduplicação e validação de direitos; usar somente um publicador por canal. Testes obrigatórios: `tests/test_autoclip_postiz.py`, suíte geral e fumaça de navegador/Windows antes do lançamento. O usuário solicitou os dois dentro do Nexus; conclusão parcial precisa distinguir interface/código integrado de serviço local instalado/contas conectadas.
