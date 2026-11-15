# Publicação — fila local e contratos oficiais

## Estado real

`clipforge/publishing.py` implementa fila durável SQLite. `clipforge/social_connectors.py` implementa adaptadores de envio/consulta para YouTube e TikTok. **Nenhuma conta ou publicação externa foi validada nesta entrega.** Os testes usam SQLite e HTTP local; nenhum teste publica em redes sociais.

Instagram permanece explicitamente bloqueado: falta implementar o adaptador após configurar conta profissional, concessões OAuth e hospedagem HTTPS autorizada do vídeo. Login OAuth interativo, armazenamento em cofre criptografado e renovação automática de tokens não estão implementados. Presença de token é configuração, não autenticação comprovada.

## Ativação privada

O padrão é `PUBLISHING_ENABLED=0`: a fila pode ser preparada, mas o worker não envia. Configure no ambiente privado do processo ou no `config.env` do aplicativo Windows, fora do repositório e do pacote:

| Variável | Padrão | Uso |
|---|---|---|
| `PUBLISHING_ENABLED` | `0` | `1` autoriza processamento dos trabalhos agendados |
| `PUBLISHING_AUTO_ENABLED` | `0` | `1` permite chamar `enqueue(..., automatic=True)` em clipes prontos; não descobre/enfileira sozinho |
| `PUBLISHING_DAILY_LIMIT` | `5` | Máximo de submissões por plataforma nas últimas 24 horas |
| `PUBLISHING_MAX_POLLS` | `20` | Limite de consultas para confirmar processamento |
| `YOUTUBE_ACCESS_TOKEN` | vazio | Token OAuth privado com concessões necessárias |
| `TIKTOK_ACCESS_TOKEN` | vazio | Token OAuth privado com `video.publish` |

O arquivo Windows é texto local, não cofre de segredos. Restrinja acesso ao usuário do sistema; não distribua esse arquivo ou valores em logs. Tokens expirados exigem nova concessão pelo operador. Não há client secret social embutido no executável.

## Gates e estados

Modo supervisionado exige clipe `approved`. Modo automático exige opção explícita e clipe `ready` ou `approved`. Ambos revalidam direitos `owned`/`permission_granted`, evidência para terceiros e MP4 no diretório de saída. Antes do envio, a autorização e o hash do artefato são verificados novamente. O manifesto registra direitos declarados; não é verificação jurídica automática.

`queued → submitting → pending → confirmed`.

- `queued`: preparado e agendado, sem postagem.
- `submitting`: operação remota iniciada. Após reinício vira `uncertain`, porque o processo pode ter caído depois de a plataforma receber o vídeo.
- `pending`: API devolveu identificador de operação; ainda não há confirmação de publicação.
- `confirmed`: consulta oficial devolveu confirmação e identificador de vídeo. O campo `visibility` é independente; `private` não significa publicação pública.
- `blocked`: direitos, arquivo ou conta indisponíveis; requer revisão.
- `uncertain`: não é seguro reenviar; conferir manualmente a conta/plataforma.
- `failed`: plataforma confirmou rejeição/falha.
- `cancelled`: cancelado enquanto ainda aguardava envio.

`UNIQUE(clip_id, platform)` e `UNIQUE(media_sha256, platform)` impedem duplicação persistente. Trabalhos repetidos devolvem o existente; não mudam silenciosamente título ou agendamento. Um limite por plataforma evita mais submissões que o configurado. Consultas de status usam backoff exponencial até uma hora e número máximo de tentativas. Upload incerto **nunca** é repetido automaticamente.

A recuperação pressupõe uma instância do aplicativo por volume SQLite. Não abra dois aplicativos simultâneos com o mesmo volume: inicialização reconcilia estados interrompidos. A reserva SQLite protege a seleção de trabalho, mas isso não substitui liderança de múltiplos processos.

`publication_events` guarda transições; Mission Control recebe mensagens fixas sem tokens, títulos ou URLs assinadas. ID remoto e visibilidade ficam no histórico de trabalhos. Retentativas de status são registradas. Não existe interface de reconciliação de envio incerto nesta versão; não edite o banco para reenviar sem conferir a conta.

## Adaptadores

### YouTube

Upload resumível oficial (`www.googleapis.com/upload/youtube/v3/videos`) e consulta `videos.list(part=status)`. Somente marca confirmado após `uploadStatus=processed` com o ID correspondente. Falhas/rejeições são distinguidas. O envio é **privado por padrão e nesta versão**; classificação como Short depende do YouTube. Projetos não auditados podem permanecer restritos. Requer concessões OAuth para upload e leitura do status do próprio vídeo; validar no projeto real antes de habilitar.

### TikTok

Content Posting API oficial: consulta de opções do criador, inicialização `FILE_UPLOAD` e consulta `status/fetch`. Envia apenas quando `SELF_ONLY` está disponível. Limite deste adaptador: 64 MiB em um chunk. Não troca um `publish_id` (operação) por ID de vídeo. Se `PUBLISH_COMPLETE` não trouxer ID em `publicaly_available_post_id`, o serviço exige reconciliação; não anuncia publicação pública.

URLs de upload são HTTPS em domínios oficiais permitidos; credenciais na URL e portas alternativas são recusadas. A mídia é transmitida em blocos, sem carregar todo o MP4 na memória. Respostas têm limite de tamanho. Redirecionamentos HTTP não recebem credenciais.

## Contrato de integração

```python
service = PublishingService(store)
service.enqueue(clip_id, 'youtube', 'Título conferido',
                description='Descrição conferida', scheduled_at=timestamp_unix)
service.start()  # apenas se PUBLISHING_ENABLED=1
service.stop()
```

API web: `GET /api/publishing` consulta fila/configuração, `POST /api/clips/{id}/publish` agenda com aprovação, `POST /api/publishing/process` processa uma etapa quando habilitado. Todas seguem autenticação do painel. Não habilite publicação automática por simples existência de token.

## Verificação

```bash
python -m unittest discover -s tests -p test_publishing.py -v
python -m unittest discover -s tests -p test_social_connectors.py -v
```

14 testes da fila e 7 testes de contratos passaram em 15/11/2026 UTC. Cobrem direitos revogados, aprovação, opt-in, tipos inválidos, arquivo alterado, agenda, cancelamento, duplicação, limite, backoff, reinício, status privado, ID real obrigatório, redirecionamento e hosts de upload. A suíte integrada final e a demonstração FFmpeg/HTTP são registradas no relatório Astra.
