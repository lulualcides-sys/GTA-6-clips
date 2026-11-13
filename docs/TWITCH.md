# Twitch Helix — descoberta geral até GTA VI, exclusiva após lançamento

## Política de categorias

**Regra definida:** até **18/11/2026**, buscar clipes em até 12 categorias populares da Twitch, incluindo jogos e categorias IRL. Na virada para **19/11/2026 à 00:00 em São Paulo**, monitorar **somente** a categoria exata `Grand Theft Auto VI` (ou `Grand Theft Auto 6`, caso a Twitch use esse nome).

A data foi definida a partir da informação oficial da Rockstar em https://www.rockstargames.com/VI e https://support.rockstargames.com/articles/29jV3Cv2cCgvwM1XgtMO5o/grand-theft-auto-vi-regional-pre-load-and-release-times-on-playstation-5-and-xbox-series-x-or-s . Se a Rockstar alterar o lançamento, ajuste a variável local `TWITCH_GTA6_LAUNCH_AT` antes do novo prazo.

- **Antes do lançamento:** `GET /helix/games/top` retorna categorias principais, `GET /helix/clips?game_id=...` retorna até 15 clipes por categoria em janela de 72h; ordenação por atividade popular/recência/duração. Não há cobertura de todas as categorias da Twitch nem reconhecimento semântico de momentos engraçados.
- **Após o lançamento:** consulta e lista exclusivas de GTA VI. O sistema verifica a categoria com nome exato; nunca usa GTA V como substituta silenciosa. Se a categoria não existir ou a API falhar, mostrará erro.
- **Banco:** preserva histórico e anota nome/ID de cada categoria; a lista após a virada **filtra GTA VI** mesmo se o banco ainda tiver registros antigos de outras categorias.
- **Limite:** 12 categorias, 15 clipes por categoria, uma atualização a cada 15 minutos por padrão, com até 100 candidatos exibidos. Evita consultas excessivas.

## Ativação no aplicativo Windows

1. Abra o **GTA VI Clips** no PC.
2. Crie um app de desenvolvedor no [Twitch Developer Console](https://dev.twitch.tv/console/apps) e obtenha **Client ID** e **Client Secret**.
3. Clique em **Conectar Twitch** no aplicativo. Digite os dois valores na janela local. O programa **testa a autenticação na API oficial antes de salvar** e não exibe o segredo após isso.
4. Alternativamente, clique em **Configurações** e edite o arquivo `%LOCALAPPDATA%\GTA6Clips\config.env` diretamente:

```dotenv
TWITCH_ENABLED=1
TWITCH_CLIENT_ID=seu-client-id
TWITCH_CLIENT_SECRET=seu-client-secret
TWITCH_POLL_SECONDS=900
TWITCH_GTA6_LAUNCH_AT=2026-11-19T03:00:00+00:00
```

5. Salve (ou use **Salvar no PC** na janela de conexão) e reinicie o aplicativo. O monitor começa a consultar **metadados** automaticamente. O botão **Buscar clipes** permite uma consulta manual.
6. No painel, confira se aparece "Monitoramento ativo", qual o modo atual e as categorias de fato encontradas.

**Importante para quem já tinha o programa:** a atualização **não sobrescreve** `config.env`. Se a sua cópia antiga diz `TWITCH_ENABLED=0`, troque manualmente para `1`. Sem Client ID e Client Secret não é possível fazer uma consulta real à API Twitch. Não é necessário login de espectadores: o OAuth de aplicação usa `client_credentials`.

## Direitos, arquivos e publicação

- A integração consulta **somente metadados públicos, URLs de clipes e categorias**. Não captura lives, baixa gravações ou publica em TikTok/Shorts/Reels.
- Para usar vídeo próprio ou de terceiro, o sistema de edição exige um arquivo local com manifesto de autorização separado. Criar um clipe na Twitch **não** dá licença de republicação.
- Um arquivo privado `data/twitch_sources.json` pode documentar broadcasters com permissão declarada; não é comprovante jurídico.
- `TWITCH_CLIENT_SECRET` permanece no PC, não no GitHub, no frontend nem em logs de atividades.

## API protegida

- `GET /api/twitch/status`: modo ativo (`prelaunch_multi` ou `gta6_only`), categorias monitoradas, status OAuth e última atualização.
- `GET /api/twitch/candidates`: até 100 candidatos, cada um com `game_name`/`game_id`.
- `POST /api/twitch/refresh`: busca manual, requer OAuth configurado.
- O painel local usa autenticação por token aleatório e API acessível apenas em `127.0.0.1`.

## Restrições

A busca mostra clipes existentes na API; não garante que as transmissões serão interessantes ou que haja permissão de reprodução comercial. O aplicativo precisa estar aberto e o PC ligado para monitoramento contínuo. Ele não cria uma transmissão, não substitui credenciais do Twitch Developer Console e não mantém um servidor público.

## Para outras IAs

Não modificar a política de virada automática, não confundir "popular" com "todo conteúdo da Twitch", não expor secrets e não trazer GTA V para a lista após o lançamento. Para alterar a data, confirmar notícia oficial e atualizar também o valor padrão e os testes. Antes de publicar versão Windows, testar comportamento antes e depois do limite e verificar CI principal e Windows.
