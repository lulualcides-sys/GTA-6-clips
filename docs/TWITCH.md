# Twitch Helix — radar ASTRA

## Regra vigente (14/11/2026)

O pedido ASTRA substitui a restrição antiga a GTA V: antes da data configurada, o radar busca até **12 categorias populares ou configuradas**, incluindo jogos e categorias IRL retornadas pela Twitch. Em `2026-11-19T03:00:00Z`, passa automaticamente ao perfil `gta6_only`. A data é uma configuração operacional fornecida pelo usuário, não uma nova verificação do calendário da Rockstar.

`TWITCH_DISCOVERY_MODE=auto` usa essa virada. `trending`, `gta5_only` e `gta6_only` são intervenções manuais persistentes; o painel recebe `manual_override=true` quando aplicável. Categoria GTA VI ausente gera erro explícito e não substitui por outro jogo.

## Configuração local

```ini
TWITCH_ENABLED=1
TWITCH_CLIENT_ID=<id-da-sua-aplicacao>
TWITCH_CLIENT_SECRET=<segredo-somente-no-PC>
TWITCH_POLL_SECONDS=900
TWITCH_DISCOVERY_MODE=auto
TWITCH_GTA6_LAUNCH_AT=2026-11-19T03:00:00+00:00
TWITCH_TRENDING_CATEGORIES=12
TWITCH_CLIPS_PER_CATEGORY=15
TWITCH_LOOKBACK_HOURS=72
# Opcional: até 12 IDs exatos; vazio usa GET games/top
TWITCH_CATEGORY_IDS=
# Opcional: até 100 IDs de criadores para verificar lives via GET streams
TWITCH_BROADCASTER_IDS=
# Override da categoria GTA VI (somente no perfil gta6_only)
TWITCH_GAME_ID=
# Override da categoria GTA V (somente no perfil gta5_only)
TWITCH_GTA5_GAME_ID=
```

IDs repetidos são eliminados. IDs não numéricos e configurações acima do limite são rejeitados. O perfil popular usa `games/top`; uma lista explícita usa `games?id=...`. O ranking continua heurístico (views, recência, duração e bônus PT-BR), sem compreender eventos. A lista mostra no máximo 100 candidatos; SQLite conserva histórico limitado a 5.000 registros. Deduplicação usa o identificador oficial do clipe.

## OAuth e monitoramento

OAuth de aplicação usa client credentials exclusivamente para consulta oficial de metadados. Resposta HTTP 401 invalida o token e permite uma única renovação/repetição. Erros HTTP, inclusive 429 e indisponibilidade, são registrados sem corpos de resposta ou tokens; a próxima varredura tenta novamente. Não há loop agressivo de retentativas. O intervalo mínimo do polling é 300 segundos.

Criadores em `TWITCH_BROADCASTER_IDS` são verificados por `GET /helix/streams` com parâmetros `user_id` repetidos. A tabela `twitch_streamers` persiste estado, ID real da transmissão e horário da consulta. Uma resposta bem-sucedida sem um criador o marca offline; falha de rede preserva o estado anterior e seu horário. `TwitchDiscovery.list_streamers()` retorna esses registros; `status()` inclui `monitored_streamers` e `live_streams` da última consulta. Conferir `checked_at` para identificar dados antigos. Isso é polling, **não EventSub**, e requer processo aberto/PC ligado.

A descoberta de clipes permanece por categoria; o cadastro de streamer monitora a live, mas ainda não faz consulta separada de clipes por criador. Não há download automático nem uso de URLs alternativas. A obtenção manual oficial e autorizada está disponível pela CLI separada: veja [TWITCH_DOWNLOAD.md](TWITCH_DOWNLOAD.md). Configurar segredos só no PC e nunca distribuí-los no executável. O segredo de aplicação local continua sendo uma limitação do fluxo atual; OAuth de usuário com concessões específicas para download exige integração adicional.

## Preparação da edição

GTA V é o laboratório para a chegada de GTA VI. A V8 aprovada (Counter-Strike) define **nível de acabamento**, não enquadramento único.

- **GTA RP/dialogo:** preservar quem falou, a preparação da conversa, a resposta e a reação; legendas PT-BR fiéis apenas quando ajudarem, sem falas fabricadas.
- **GTA V humor visual:** mostrar causa, ação inesperada, consequência e reação; título editorial breve, replay apenas se reforçar a piada.
- **GTA V perseguição/ação:** mostrar perseguição e evolução, decisões e acidente/fuga; zoom acompanhando veículo, mapa/elementos relevantes e reação.
- Em todos: marca Nexus Clips BR, crédito ao criador em letras pequenas, contexto completo, áudio legível e final seco, player online sem download obrigatório, **sem marca Descript**.
- Planejadores em `clipforge/editorial_profiles.py` exigem tempos revisados manualmente. Ainda não implementam identificação semântica nem edição automática por evento.

## Limites, direitos e testes

Um clipe público não é licença de republicação. `twitch_sources.json` sinaliza apenas uma permissão **declarada**, exige evidência para terceiros e não autoriza download por conta própria. Este módulo não baixa vídeos nem publica. O pipeline local continua exigindo manifesto de direitos separado.

API existente: `GET /api/twitch/status`, `GET /api/twitch/candidates` e `POST /api/twitch/refresh`. As respostas mantêm os campos anteriores e acrescentam contadores de monitoramento e indicação de override manual.

```bash
python -m unittest discover -s tests -p 'test_twitch*.py' -v
```

Os testes cobrem perfis/data/override, migração SQLite, deduplicação, permissões, consulta de streams, limites e OAuth. Um servidor HTTP **local real** exercita transporte urllib, erro 401, renovação e JSON. Os demais testes de Helix usam respostas controladas, sem chamar a Twitch. Não se afirma validação com conta real sem credenciais. EventSub permanece pendente. A CLI de obtenção oficial autorizada é descrita em [TWITCH_DOWNLOAD.md](TWITCH_DOWNLOAD.md); ainda requer validação com conta real.
