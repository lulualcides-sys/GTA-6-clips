# Twitch Helix — radar ASTRA

## Radar aprofundado GTA VI com pré-triagem editorial (v0.5.1)

A partir de 19/11/2026 (configuração de início já existente) o perfil `auto` muda para `gta6_only`. Também é possível ativar `TWITCH_DISCOVERY_MODE=gta6_only` mais cedo **se** a categoria exata já existir na Twitch; antes do lançamento real, não há garantia de clipes de gameplay.

**Descoberta:** o cliente consulta o endpoint oficial Twitch Helix `GET /clips?game_id=...` com cursores e janelas menores (`TWITCH_GTA6_WINDOW_HOURS=12`; `TWITCH_GTA6_PAGES_PER_WINDOW=3`), deduplicando pelo ID. Até 30 consultas por rodada do radar e até 48 no limite de segurança do método. Isso amplia bastante a amostra em comparação com uma única página, mas NÃO é garantia de todos os clipes: a API tem paginação e cotas, e pode devolver resultados parciais.

**Pré-triagem de custo:** o Nexus considera até 1.000 candidatos pontuados por busca, antes de obter mídia. Com `TWITCH_AUTO_MIN_SCORE=78` só seleciona títulos não genéricos, 14–70 s, sinais de visualizações compatíveis com a idade do clipe e no máximo `TWITCH_AUTO_PER_CREATOR=2` clipes por criador por rodada. O filtro `TWITCH_AUTO_GTA6_ONLY=1` evita que outros jogos sejam enviados para edição. `TWITCH_GTA6_BATCH=5` limita os downloads autorizados por rodada (configurável até 12) para evitar uso excessivo de banda, armazenamento e créditos de IA. Exibir clipe na busca **não** equivale a autorização para baixá-lo.

A nota é heurística, baseada em metadados; **não mede com precisão humor, reação, contexto, ritmo ou qualidade audiovisual.** Só a análise do vídeo pelo AutoClip e a revisão editorial podem julgar essas características. O motor AutoClip continua sendo o editor exclusivo; sem modelo local operacional, o Nexus não baixa mídias para a fila. Os arquivos já ingeridos mas ainda não enfileirados são retomados nas varreduras subsequentes. Nenhuma publicação ocorre antes da aprovação.


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

## Status de conexão na interface Windows (v0.4.4)

O botão **Conectar Twitch** chama uma validação real das credenciais com
a API oficial. Se a validação falhar, **não salva** Client ID e Client Secret.
Ao salvar com sucesso, o desktop aplica a configuração ao runtime ativo,
inicia um único worker de descoberta e atualiza o selo **Twitch configurada ·
buscando**. Após uma consulta de metadados bem-sucedida, o selo passa a
**Twitch conectada · monitorando**. Erros de consulta são exibidos
separadamente, sem expor credenciais.

**Serviço online** na barra principal indica somente a saúde do backend local,
não a autenticação Twitch. Clientes antigos exigem reiniciar após salvar o
Client ID e Client Secret. Caso o app tenha sido atualizado por ZIP mas a
configuração tenha sido preservada, verifique localmente
`%LOCALAPPDATA%\\GTA6Clips\\config.env` sem compartilhar o Secret.

A conexão **apenas consulta metadados oficiais**. Não baixa vídeo, não
instala a CLI AutoClip e não autoriza publicação.

## OAuth e monitoramento

OAuth de aplicação usa client credentials exclusivamente para consulta oficial de metadados. Resposta HTTP 401 invalida o token e permite uma única renovação/repetição. Erros HTTP, inclusive 429 e indisponibilidade, são registrados sem corpos de resposta ou tokens; a próxima varredura tenta novamente. Não há loop agressivo de retentativas. O intervalo mínimo do polling é 300 segundos.

Criadores em `TWITCH_BROADCASTER_IDS` são verificados por `GET /helix/streams` com parâmetros `user_id` repetidos. A tabela `twitch_streamers` persiste estado, ID real da transmissão e horário da consulta. Uma resposta bem-sucedida sem um criador o marca offline; falha de rede preserva o estado anterior e seu horário. `TwitchDiscovery.list_streamers()` retorna esses registros; `status()` inclui `monitored_streamers` e `live_streams` da última consulta. Conferir `checked_at` para identificar dados antigos. Isso é polling, **não EventSub**, e requer processo aberto/PC ligado.

A descoberta agora também consulta os clipes do próprio canal com OAuth válido e pode baixar mídia pela API oficial de downloads para o AutoClip. Para canais de terceiros continua exigindo concessão de editor e direitos documentados; veja [TWITCH_DOWNLOAD.md](TWITCH_DOWNLOAD.md). O radar público continua sendo apenas metadados. Guarde o Client Secret e tokens OAuth exclusivamente no PC.

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
