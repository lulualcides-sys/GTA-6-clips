# Roadmap objetivo

## Atualização gratuita do aplicativo Windows

- [x] Verificador de GitHub Releases estáveis, comparação SemVer e botão de atualização na interface.
- [x] Download com validação SHA-256, extração protegida, autoteste da nova versão e atualizador externo com rollback.
- [x] Publicação automática de GitHub Release versionada pelo CI quando uma nova versão é aprovada no main.
- [ ] Conferir CI Windows verde e release v0.2.0 publicada antes de entregar pacote atualizado.
- [ ] Validar ciclo completo de atualização em Windows de usuário, incluindo fechamento, instalação, reabertura e rollback.

## Aplicativo Windows sem servidor pago

- [x] Lançador pywebview que reaproveita Mission Control e APIs locais com token aleatório.
- [x] Dados persistentes em LocalAppData, controles para abrir pastas e configurações do app.
- [x] Workflow Windows x64 prepara ZIP portátil com FFmpeg/ffprobe e autoteste do executável.
- [ ] CI Windows verde e artefato para baixar no GitHub (verificar antes de marcar).
- [ ] Validar abertura da janela gráfica num Windows 10 real e prévia em resolução 144 Hz.
- [ ] Testar edição de vídeo próprio no PC e configurar Twitch OAuth autorizado.
- [ ] Decidir modo inicializar com Windows somente após preferência explícita.


## Etapa 0 — Base (implementada no código)

- [x] Repositório independente e AGENTS.md para qualquer IA.
- [x] Scanner local, manifesto de direitos, deduplicação SHA-256.
- [x] Renderização 9:16, SQLite, API, revisão e painel web responsivo.
- [x] Testes unitários e smoke test adicionados ao repositório.
- [ ] Confirmar CI verde e revisão visual do MP4 sintético.
- [ ] Hospedar painel com segurança e armazenamento persistente.

## Painel Mission Control

- [x] Central visual com nove módulos conectados, feed SQLite e estados reais, responsiva e com controles de revisão preservados.
- [x] Teste com mídia sintética própria, opt-in, com limite por volume, para observar automações reais.
- [x] Testes de backend e endpoints; workflow Playwright para capturar screenshots em desktop e mobile.
- [ ] Publicar dashboard num servidor com HTTPS, armazenamento persistente, backup, autenticação forte e orçamento definido.
- [ ] Testar com gameplay de streamer autorizado antes de afirmar qualidade editorial.
- [ ] Integrar redes GTA separadas do WildVox.

## Etapa 1 — Qualidade de edição

- [x] Exportador HyperFrames com HTML/CSS original, créditos, legenda SRT opcional, ZIP protegido e botão no painel.
- [x] Testes unitários/API de exportação adicionados.
- [x] Render real HyperFrames validado com vídeo sintético no CI (sem comprovação editorial em gameplay real).
- [x] Implementar componentes opcionais PySceneDetect e faster-whisper, testes de API e legendas, com flags desligadas no Docker padrão.\n- [ ] Testar a precisão da transcrição com vídeos reais autorizados e medir CPU/latência.\n- [ ] Habilitar IA em worker com capacidade e custos definidos.


- [x] Transcrição opt-in faster-whisper e cache privado com detecção de mídia alterada.\n- [ ] Validar a qualidade de legendas e a escolha do trecho com criadores autorizados.
- [x] Heurística conservadora áudio + cortes visuais (não identifica eventos semanticamente).\n- [ ] Evoluir score com sinais de fala e métricas humanas, sem alegar compreensão semântica.
- [ ] Template facecam/gameplay, créditos, zooms moderados e safe area do app.
- [ ] Verificar silêncio, clipping, telas pretas, congelamento, legibilidade e duplicata perceptual.
- [ ] Testar 10 clipes autorizados e registrar qualidade editorial real.

## Etapa 2 — Coleta autorizada e autonomia

- [x] **Descoberta apenas de metadados** por Twitch Helix/OAuth com ranking, deduplicação e painel; sem credenciais a sincronização permanece desativada.
- [x] Marca local de fontes com direitos **declarados** (sem validação jurídica) via arquivo privado.
- [ ] Integrar autorização verificável de criadores e mídia licenciada; download ainda NÃO implementado.
- [ ] Testar autenticação com credenciais reais e categoria GTA VI no dia do lançamento.
- [ ] Job queue durável, retry seguro, backup, alertas, worker hospedado com disponibilidade.
- [ ] Custos e limites por dia; não rodar transcrição sem necessidade.

## Etapa 3 — Publicação

- [ ] Canais próprios para GTA 6, contas reais conectadas.
- [ ] Integração Metricool com agendamento, erro e confirmações de postagem.
- [ ] Publicação automática apenas após autorização + QA + política editorial; interrupção manual.
- [ ] Métricas reais por plataforma, sem inventar views ou monetização.

**Meta piloto:** até 5 cortes bons por dia, não 5 por obrigação. Escalar somente após validar qualidade, direitos e custo por clipe.
