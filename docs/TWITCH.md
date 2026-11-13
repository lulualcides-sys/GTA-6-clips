# Twitch Helix — monitoramento de clipes GTA VI (metadados somente)

## Fluxo implementado
1. OAuth client credentials por `TWITCH_CLIENT_ID` e `TWITCH_CLIENT_SECRET`; escopo de aplicativo, sem necessidade de login dos espectadores.
2. Busca da categoria exata `Grand Theft Auto VI` em `/helix/search/categories`, ou `TWITCH_GAME_ID` informado explicitamente após confirmar o ID na Twitch.
3. Busca de até 100 clipes recentes (72h) em `GET /helix/clips?game_id=...`.
4. Persiste metadados em SQLite, aplica score de visualizações/idade/duração, deduplicando por ID.
5. Dashboard lista candidatos e abre o URL original da Twitch. **Não captura, baixa, corta ou publica esse material automaticamente**.
6. Arquivo local opcional `data/twitch_sources.json` marca `declared_permission` quando criador está cadastrado com evidência; essa marca não comprova juridicamente a autorização. O editor continua exigindo sidecar de direitos no vídeo local.

## Configurar

Crie um aplicativo no [Twitch Developer Console](https://dev.twitch.tv/console/apps) e obtenha Client ID e Client Secret. Salve **somente** em variáveis de ambiente, nunca no Git. No Docker Compose, edite `.env` local:

```dotenv
DASHBOARD_TOKEN=use-um-segredo-longo
TWITCH_CLIENT_ID=seu-client-id
TWITCH_CLIENT_SECRET=seu-client-secret
TWITCH_ENABLED=1
TWITCH_POLL_SECONDS=900
# TWITCH_GAME_ID=... (opcional, depois de verificar a categoria exata)
```

Reinicie a aplicação. Com `TWITCH_ENABLED=1`, o monitor consulta em segundo plano a cada 15 minutos (mínimo 5 minutos). Sem habilitar, o painel pode chamar "Buscar clipes" manualmente se houver credenciais.

Para fontes com licença, copie `examples/twitch_sources.example.json` para `data/twitch_sources.json`, substitua IDs pelos IDs **numéricos** reais do broadcaster e documente a permissão. Esse arquivo é privado e já fica fora do Git. Clipe descoberto sem permissão aparece como **direitos não verificados**. Nunca pressupor que a ação de criar clipe na Twitch seja autorização para uso comercial em outra plataforma.

## Endpoints protegidos

- `GET /api/twitch/status`: configurado, monitor ligado, última consulta e quantidade de candidatos.
- `GET /api/twitch/candidates`: top 100 candidatos, com nota heurística 0–100.
- `POST /api/twitch/refresh`: consulta manual (sem body). Retorna erro 503 informativo quando não configurado/API falha.
- Todos exigem `DASHBOARD_TOKEN` quando ele está configurado.

## Limites e princípios

- O score **não é reconhecimento por IA** e não mede humor, emoção ou conteúdo do gameplay. Requer revisão humana.
- Uma página de até 100 clipes limita API e custo; não promete cobertura exaustiva da categoria.
- No lançamento, a categoria GTA VI pode ainda não existir: o sistema informa indisponibilidade, não muda silenciosamente para GTA V.
- A API oficial fornece URL original e metadados. Download depende de direitos e condições específicas; esta integração propositalmente não implementa isso.
- `TWITCH_CLIENT_SECRET` nunca aparece no painel, no repositório ou nos logs.
- Para hospedar 24/7, requer servidor/container persistente e domínio protegido por HTTPS; o dashboard **não** está publicado automaticamente.
