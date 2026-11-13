# Roadmap objetivo

## Etapa 0 — Base (implementada no código)

- [x] Repositório independente e AGENTS.md para qualquer IA.
- [x] Scanner local, manifesto de direitos, deduplicação SHA-256.
- [x] Renderização 9:16, SQLite, API, revisão e painel web responsivo.
- [x] Testes unitários e smoke test adicionados ao repositório.
- [ ] Confirmar CI verde e revisão visual do MP4 sintético.
- [ ] Hospedar painel com segurança e armazenamento persistente.

## Etapa 1 — Qualidade de edição

- [ ] Transcrição opcional com faster-whisper e cache de legendas sincronizadas.
- [ ] Audio + visual + fala para detectar trechos com contexto; métricas para avaliar score.
- [ ] Template facecam/gameplay, créditos, zooms moderados e safe area do app.
- [ ] Verificar silêncio, clipping, telas pretas, congelamento, legibilidade e duplicata perceptual.
- [ ] Testar 10 clipes autorizados e registrar qualidade editorial real.

## Etapa 2 — Coleta autorizada e autonomia

- [ ] Cadastro de streamers, permissões e fonte Twitch Helix/OAuth.
- [ ] Capturar metadados dos clipes, download somente quando licenciado e permitido.
- [ ] Job queue durável, retry seguro, backup, alertas, worker hospedado com disponibilidade.
- [ ] Custos e limites por dia; não rodar transcrição sem necessidade.

## Etapa 3 — Publicação

- [ ] Canais próprios para GTA 6, contas reais conectadas.
- [ ] Integração Metricool com agendamento, erro e confirmações de postagem.
- [ ] Publicação automática apenas após autorização + QA + política editorial; interrupção manual.
- [ ] Métricas reais por plataforma, sem inventar views ou monetização.

**Meta piloto:** até 5 cortes bons por dia, não 5 por obrigação. Escalar somente após validar qualidade, direitos e custo por clipe.
