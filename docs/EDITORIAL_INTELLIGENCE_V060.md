# Nexus Clips BR v0.6.0 — inteligência editorial, revisão móvel e métricas

## O que existe no código

- **Análise real de cenas (experimental):** depois que o **AutoClip** finaliza um vídeo,
  o Nexus extrai três quadros para análise por um modelo Ollama **com visão** previamente
  instalado no computador. Registra categoria, acontecimento supostamente observado,
  confiança informada pelo modelo e limitações. Não afirma conhecer áudio, humor nem
  ações entre quadros. **Não edita nem modifica o MP4**. Sem modelo visual, informa
  explicitamente `unavailable`. Configure `NEXUS_VISION_MODEL` apenas se tiver esse
  modelo instalado. Não faz download automático de pesos.
- **QA automático técnico:** usa FFmpeg somente para **análise de quadros e áudio**,
  verificando trechos pretos prolongados e silêncio prolongado. Os resultados são
  indicativos, não prova de defeito; áudio silencioso pode ser intencional. Persistência
  auditável em `editorial_insights`. Não altera MP4, não reprova sem intervenção humana.
  Verificação avançada de sincronização facecam/ação e semântica de áudio ainda exige
  modelos/testes adicionais.
- **Feedback e aprendizado:** aprovar/rejeitar cria `editorial_feedback` e histórico
  `editorial_feedback_events`. Rejeições registram motivo e nota opcional.
  Após **cinco decisões por criador**, aplica um ajuste conservador (máximo ±5) no
  desempate do ranking de candidatos, sem inventar reputação. Não usa dados privados
  da Twitch para treinar modelos externos. Antes da amostra mínima indica
  `insufficient_data`.
- **Revisão pelo celular:** painel HTML responsivo em `/review`, player sem etapa de
  download manual, relatórios, decisões e estatísticas. O backend Windows continua
  vinculado a **127.0.0.1** (porta preferencial 8855). **Não expor ao público.**
  Configure **Tailscale Serve** (não Funnel) uma vez no Windows:
  1. Instale e conecte Tailscale no PC e no celular à **mesma tailnet**.
  2. No Nexus do PC, clique em **Vincular celular** e obtenha o código temporário.
  3. Execute no Windows `tailscale serve --bg 8855`, ou use a porta exata exibida
     pelo Nexus se 8855 estiver ocupada.
  4. Abra a URL HTTPS da sua tailnet com o sufixo `/review`; informe o código.
     Após parear, o browser recebe cookie `Secure; HttpOnly; SameSite=Strict`,
     válido por até 12 horas, com acesso somente a player, QA e decisões.
     Código de 10 dígitos expira em 3 minutos, tem 8 tentativas e é de uso único.
  5. Para desligar o acesso use `tailscale serve off`. Ao reiniciar o Nexus,
     sessões móveis anteriores não persistem.
  **Não use port forwarding, host 0.0.0.0, Tailscale Funnel ou publicação HTTPS aberta
  na internet.** O PC precisa estar ligado e com o Nexus em execução.
- **Métricas reais:** consulta somente YouTube Data API `videos.list?part=statistics`
  e TikTok `/v2/video/query` com escopo `video.list`, para publicações confirmadas
  e com ID real vinculado à conta. Armazena fonte, data, erros e contadores recebidos.
  `NEXUS_PERFORMANCE_POLL=1` consulta a cada 6 horas no desktop, além do botão
  manual. **Não assume visualizações, retenção, ganhos ou alcance público** sem
  resposta de API. Retenção não é coletada nesta versão, pois requer acessos/APIs
  diferentes; Postiz e Instagram não recebem métricas inventadas.

## Condições e riscos

1. Para analisar visualmente a cena é preciso Ollama local com modelo vision.
   Apenas ter `llama3.1` textual não é suficiente.
2. AutoClip continua sendo o **único** motor de edição. FFmpeg é usado pelo Nexus
   apenas como leitor/validador, não para criar cortes alternativos.
3. O controle de qualidade é *consultivo* e precisa de calibração com vídeos reais;
   não pode prometer encontrar toda piada fraca, rosto cortado ou sincronização ruim.
4. O ranking considera amostras pequenas com cuidado e a qualidade final depende
   da avaliação humana; feedback nunca concede direitos de uso sobre conteúdo alheio.
5. Métricas só são capturadas com tokens OAuth autorizados e vídeos correspondentes;
   o upload privado dos conectores atuais pode produzir zero visualizações.
6. Os testes de CI usam mocks para modelos, plataformas, navegação e vídeos sintéticos;
   testes verdes **não comprovam desempenho, precisão editorial ou integração de conta real**.

## API

Rotas autenticadas: `GET /api/clips/:id/editorial`,
`POST /api/clips/:id/review` com JSON
`{"decision":"reject","reason":"sem_graca","note":"..."}` ou
`{"decision":"approve"}`, `GET /api/editorial/summary`, `GET /api/metrics`,
`POST /api/metrics/refresh` (somente proprietário).

Pareamento: `POST /api/mobile/pair` (somente token proprietário); 
`POST /api/mobile/connect` (código, HTTPS, mesma origem). Sessões móveis
**não podem** chamar publicação, configuração, upload, AutoClip manual ou
sincronização de plataformas.

## Testes focados

```bash
python -m unittest tests.test_editorial_intelligence tests.test_mobile_http -v
python -m unittest discover -s tests -v
node --check clipforge/static/editorial.js
node --check clipforge/static/mobile-review.js
```
