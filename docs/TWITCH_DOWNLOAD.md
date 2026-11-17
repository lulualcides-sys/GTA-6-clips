> **Nexus v0.5.0:** além da CLI opt-in documentada abaixo, o aplicativo Windows oferece `Autorizar downloads Twitch` para o próprio canal com OAuth de usuário (callback `http://localhost:3000`), renovação do token e download automático de até dois clipes autorizados por consulta, seguidos de AutoClip e revisão. O token é privado e armazenado no `%LOCALAPPDATA%\\GTA6Clips\\config.env` (arquivo local em texto simples, portanto deve ser protegido como senha). O navegador só envia o código OAuth para `localhost`; o token não é devolvido à interface JavaScript. A API decide sobre a permissão. O radar de clipes públicos continua **metadados apenas** quando não existe concessão oficial para download. As restrições e advertências legais abaixo continuam válidas.\n\n# Obtenção autorizada de clipes Twitch

## Contrato oficial consultado

Em 14/11/2026 foi consultada a documentação oficial:

- https://dev.twitch.tv/docs/api/reference/clips#get-clips-download
- https://dev.twitch.tv/docs/authentication/validate-tokens/

`GET https://api.twitch.tv/helix/clips/downloads` aceita `broadcaster_id`, `editor_id` e até dez `clip_id`. Este cliente faz **uma obtenção explícita por execução**, com token de usuário que possua `editor:manage:clips` ou `channel:manage:clips`. `editor_id` deve corresponder ao usuário do token; quando o próprio broadcaster autoriza, os dois IDs são iguais. O endpoint pode omitir clipes inexistentes, inacessíveis ou de outro broadcaster. A API decide se o usuário é editor autorizado; não contornamos 401/403.

A documentação também permite token de app quando já existe concessão específica do editor. Essa variante **não está implementada**, evitando confundir o OAuth de descoberta de metadados com autorização de download.

## Uso

O fluxo de concessão OAuth de usuário ainda deve ser feito na integração privada da aplicação. Não colar tokens no código, argumento de linha de comando ou GitHub. Disponibilizar `TWITCH_CLIENT_ID` e `TWITCH_USER_ACCESS_TOKEN` no ambiente privado do processo. O token é validado em `/oauth2/validate` **a cada execução**; não é gravado no banco ou manifesto e nunca é enviado ao CDN.

Crie um manifesto privado com dados verdadeiros e autorização de reutilização:

```json
{
  "creator": "Nome real do criador",
  "broadcaster_id": "123456",
  "rights_status": "permission_granted",
  "evidence": "Referência privada verificável da autorização de reutilização",
  "duration_sec": 35
}
```

Para fonte própria, `rights_status` pode ser `owned`. A capacidade de baixar como editor **não é** licença para republicar; por isso o manifesto é obrigatório e independente do token.

```bash
python -m clipforge.twitch_download ID_DO_CLIPE --broadcaster-id 123456 --editor-id 123456 --rights /caminho/privado/autorizacao.json --incoming data/incoming
```

No Windows, informar a pasta `incoming` do volume em LocalAppData usado pelo aplicativo. O destino será `twitch-ID_DO_CLIPE.mp4` com o sidecar `.rights.json`. O scanner existente poderá ingeri-lo na próxima varredura; gates de direitos, QA e aprovação continuam aplicáveis. O comando **não aprova nem publica**.

## Proteções e limites

- Usa apenas o link retornado pelo endpoint oficial. Não constrói links por thumbnail, scraping ou GraphQL.
- Aceita somente HTTPS no host oficial documentado `production.assets.clips.twitchcdn.net`, sem credenciais na URL ou portas alternativas. Mudança de CDN bloqueia o download até revisão explícita do contrato.
- Recusa redirecionamentos de API ou mídia. URLs assinadas não ficam nos logs ou manifesto.
- Limite de 512 MiB e limite de tempo; valida vídeo e duração com FFprobe.
- Arquivos parciais têm extensão `.part`; o sidecar só aparece atomicamente depois da mídia validada. Arquivos existentes nunca são substituídos.
- Preserva origem, broadcaster, ID do clipe, método de obtenção e SHA-256. Não altera o conteúdo da mídia.
- A CLI não possui refresh token nem autorização interativa; tokens inválidos exigem nova concessão pelo operador. Não há execução automática em lote ou botão de download no painel nesta entrega.

## Verificação realizada

`python -m unittest discover -s tests -p 'test_twitch*.py' -v`

Inclui servidor HTTP local real e MP4 sintético gerado com FFmpeg, validação FFprobe, recusa de scope ausente, limites, ausência de token no pedido de mídia, redirecionamento bloqueado, deduplicação e manifesto resultante. O hostname local é substituído exclusivamente no teste; o runtime mantém o CDN fixo.

Não houve download com conta Twitch real: depende de token de usuário, permissões editor/broadcaster e mídia autorizada. O transporte e contrato foram testados localmente; não anunciar integração externa validada em produção.
