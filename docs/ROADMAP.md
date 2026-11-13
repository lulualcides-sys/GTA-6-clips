# Roadmap objetivo

## Etapa 0 — Base (implementada no código)

- [x] Repositório independente e AGENTS.md para qualquer IA.
- [x] Scanner local, manifesto de direitos, deduplicação SHA-256.
- [x] Renderização 9:16, SQLite, API, revisão e painel web responsivo.
- [x] Testes unitários e smoke test adicionados ao repositório.
- [ ] Confirmar CI verde e revisão visual do MP4 sintético.
- [ ] Hospedar painel com segurança e armazenamento persistente.

## Etapa 1 — Qualidade de edição

- [x] Exportador HyperFrames com HTML/CSS original, créditos, legenda SRT opcional, ZIP protegido e botão no painel.
- [x] Testes unitários/API de exportação adicionados.
- [ ] Render real no workflow HyperFrames deve ser verificado verde antes de considerar CLI validada.
- [ ] Integrar Whisper com legendas genuínas e análise visual com PySceneDetect; nenhum dos dois está implementado.


- [ ] Transcrição opcional com faster-whisper e cache de legendas sincronizadas.
- [ ] Audio + visual + fala para detectar trechos com contexto; métricas para avaliar score.
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
