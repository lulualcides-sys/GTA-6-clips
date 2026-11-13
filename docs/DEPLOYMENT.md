# Preparação para colocar o painel na web

**Status:** aplicação funciona como processo/container. Não há hospedagem ativa confirmada.

## Arquitetura recomendada

- Serviço contínuo de container Docker com FFmpeg, API e scanner de fontes;
- Volume persistente para `/app/data`: banco SQLite, fontes privadas, renders e manifesto;
- Reverse proxy HTTPS com autenticação, limite de upload/requisições e firewall;
- `DASHBOARD_TOKEN` forte e `TWITCH_CLIENT_SECRET` em Secrets, nunca hardcoded;
- Observabilidade e backups; uma instância apenas enquanto for SQLite + worker único.

Para Railway ou similar, importar o GitHub, usar Dockerfile, configurar variáveis no provedor, anexar volume em `/app/data`, adicionar domínio HTTPS e verificar endpoints. Atenção: serviço persistente, volume e renderização podem custar dinheiro, mesmo que o código seja gratuito. Sem instrução explícita para aceitar cobrança, não ativar plano pago automaticamente.

## Checklist antes de expor na internet

- [ ] Pipeline CI verde no commit de produção.
- [ ] Teste real HTTPS e autenticação por token.
- [ ] Testes de privacidade: sem arquivos de mídia/SQLite/segredos públicos.
- [ ] Volume persistente montado, backup/restore testados.
- [ ] Limites de CPU, espaço em disco e filas configurados.
- [ ] Login por usuário, rate-limiting e trilha de auditoria (necessários para uso com vários colaboradores).
- [ ] Verificar preview de MP4 no celular real.
- [ ] Somente a descoberta de **metadados** da Twitch ativada após configurar credenciais.

**Não usar GitHub Actions como servidor 24/7**: runners são temporários e podem parar; não armazenar vídeos lá. Workers serverless sem FFmpeg contínuo não substituem o render worker.
