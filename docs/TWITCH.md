# Twitch Helix — GTA V até 18/11, GTA VI a partir de 19/11

**Decisão editorial atualizada (13/11/2026):** enquanto treinamos a edição, o radar consulta **exclusivamente Grand Theft Auto V**, incluindo criadores de GTA RP que usem essa categoria. A partir de **19/11/2026 às 00:00 America/Sao_Paulo** (UTC 03:00), passa a consultar **exclusivamente Grand Theft Auto VI**. É uma mudança de foco editorial em relação à antiga busca geral; não criar exceções por nome de streamer.

A hora de lançamento deve acompanhar a informação oficial da Rockstar: https://www.rockstargames.com/VI . Quando o horário oficial mudar, ajustar `TWITCH_GTA6_LAUNCH_AT` e os testes; não antecipar uma virada com base em rumor.

## O que está implementado

- OAuth de aplicação: `TWITCH_CLIENT_ID` e `TWITCH_CLIENT_SECRET` configurados localmente.
- A busca pré-lançamento resolve por nome exato `Grand Theft Auto V` pela API `search/categories`, com `TWITCH_GTA5_GAME_ID` como override opcional. **Não** usar `TWITCH_GAME_ID` para GTA V.
- Após a virada resolve a categoria exata `Grand Theft Auto VI` (também aceita `Grand Theft Auto 6`), com `TWITCH_GAME_ID` como override opcional. Se não encontrar a categoria, emite erro explícito; nunca volta silenciosamente para GTA V.
- Busca `GET /helix/clips?game_id=...` em janela padrão de 72 horas, até 15 clipes por consulta (configurável até 30). Ranking heurístico por views, recência, duração e leve bônus PT-BR. **Não** identifica semântica de piadas, falas ou eventos.
- Banco SQLite mantém todos os registros anteriores, mas listagem e contagem em cada perfil mostram somente o jogo ativo; não misturar GTA V com GTA VI depois da virada.
- `TWITCH_ENABLED` ativa consultas periódicas somente com credenciais válidas, aplicativo aberto e PC ligado.

## Configuração

Em `config.env` local, após conectar a Twitch pelo aplicativo:

```ini
TWITCH_ENABLED=1
TWITCH_CLIENT_ID=<id-da-sua-aplicacao>
TWITCH_CLIENT_SECRET=<segredo-somente-no-PC>
TWITCH_POLL_SECONDS=900
TWITCH_GTA6_LAUNCH_AT=2026-11-19T03:00:00+00:00
# Opcional, somente antes do lançamento:
# TWITCH_GTA5_GAME_ID=<id-exato-da-categoria-GTA-V>
# Opcional, somente depois:
# TWITCH_GAME_ID=<id-exato-da-categoria-GTA-VI>
```

Para credenciais: https://dev.twitch.tv/console/apps . Não as colocar no GitHub. A atualização do app **não sobrescreve** um `config.env` existente; verificar `TWITCH_ENABLED` se uma instalação antiga não monitora.

## Preparação da edição

GTA V é o laboratório para a chegada de GTA VI. A V8 aprovada (Counter-Strike) define **nível de acabamento**, não enquadramento único.

- **GTA RP/dialogo:** preservar quem falou, a preparação da conversa, a resposta e a reação; legendas PT-BR fiéis apenas quando ajudarem, sem falas fabricadas.
- **GTA V humor visual:** mostrar causa, ação inesperada, consequência e reação; título editorial breve, replay apenas se reforçar a piada.
- **GTA V perseguição/ação:** mostrar perseguição e evolução, decisões e acidente/fuga; zoom acompanhando veículo, mapa/elementos relevantes e reação.
- Em todos: marca Nexus Clips BR, crédito ao criador em letras pequenas, contexto completo, áudio legível e final seco, player online sem download obrigatório, **sem marca Descript**.
- Planejadores em `clipforge/editorial_profiles.py` exigem tempos revisados manualmente. Ainda não implementam identificação semântica nem edição automática por evento.

## Limites e segurança

A API entrega metadados; este monitor **não baixa vídeos nem publica automaticamente** no TikTok/Instagram/YouTube. Um clipe público não é, por si só, licença de reutilização em outras plataformas. O renderizador local usa material com manifesto de direitos. A revisão editorial é separada da autorização de republicação.

API: `GET /api/twitch/status` informa `gta5_only` ou `gta6_only`, jogo focado, credenciais, contagem e horário da última consulta; `GET /api/twitch/candidates` mostra os candidatos; `POST /api/twitch/refresh` consulta o jogo ativo.
