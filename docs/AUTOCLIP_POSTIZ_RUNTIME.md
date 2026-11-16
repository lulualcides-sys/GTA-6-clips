# AutoClip + Postiz dentro do Nexus Clips BR — integração de runtime

Implementado na branch de integração, baseada em `astra/platform-reliability` da PR #25.
**Não afirmar que o AutoClip está instalado, que existe conta Postiz conectada, ou que
um vídeo foi publicado sem dados reais de execução.** Esta integração não instala
o serviço Postiz nem incorpora a base de código AGPL no aplicativo.

## AutoClip (motor externo isolado, acionado pelo painel)

- A ponte `clipforge/autoclip_bridge.py` fornece status por `GET /api/autoclip`,
  execução por `POST /api/clips/{id}/autoclip` e
  visualização de propostas por `GET /api/clips/{id}/autoclip-preview/{index}` e\n  importação explícita por `POST /api/clips/{id}/autoclip-import/{index}`.
- Botão **AutoClip · sugerir cortes** na revisão. Analisa **a mídia fonte local**
  de clipes importados com direitos, nunca vídeos de Twitch sem autorização.
- Confere localização dentro de `incoming`, SHA-256 e evidência de direitos.
  Limita-se a um processo de cada vez, até três sugestões 9:16, 30 minutos por
  análise e captura resultados isolados em `data/extensions/autoclip`.
- **Não altera o vídeo original, não aprova, não importa resultados automaticamente
  para a biblioteca e não posta.** Prévia das sugestões é separada do editor
  Nexus. A qualidade de corte, facecam real e reação requerem avaliação humana.
- Estados básicos persistem em `nexus-jobs.json`; processo interrompido é
  marcado como `interrupted`. Nenhum segredo é retornado pela API.
- Python do AutoClip exige versão 3.11/3.12; FFmpeg completo com libass e x264,
  Whisper e um modelo local Ollama ou provedor de LLM configurado. Não é parte
  da imagem Docker nem do EXE Windows, para não introduzir muitas dependências
  pesadas e risco de incompatibilidade. Para instalações isoladas consulte:
  https://github.com/artbyjazi/autoclip e rode `autoclip doctor`.
- Configurar somente em ambiente privado e reiniciar o aplicativo:
  `AUTOCLIP_ENABLED=1` e `AUTOCLIP_BINARY=/caminho/para/autoclip`
  (ou `autoclip` no PATH). O comando usa `AUTOCLIP_HOME` isolado
  dentro da pasta de dados do Nexus; para configurar o provedor, usar esse
  mesmo `AUTOCLIP_HOME` ao chamar `autoclip config set-secret ...`.
- **Custos:** transcrição/LLM usam CPU/GPU; API paga pode custar por uso,
  se selecionada. Ajuste 1 vídeo de teste autorizado antes de escalonar.

## Postiz (destinos opcionais na fila de distribuição existente)

- `clipforge/postiz_connector.py` implementa API pública Postiz:
  upload de MP4 em chunks (não lê inteiro em memória), criação de post,
  consulta a posts e verificação da URL de publicação.
- Destinos `postiz_youtube` e `postiz_tiktok` aparecem no painel,
  sem substituir os conectores oficiais do Nexus nem compartilhar suas
  credenciais. Criação de postagem é privada (YouTube `private`;
  TikTok `SELF_ONLY`).
- A fila do Nexus continua exigindo clipe aprovado, direito declarado e
  evidência de terceiros, hash do MP4, agendamento, limite de envio e dedupe.
  Um job é considerado confirmado **somente** se o Postiz informar
  `state=PUBLISHED` e `releaseURL`. Entrega do arquivo ao Postiz NÃO
  significa vídeo publicado; estado incerto bloqueia reenvio automático.
- Criar/obter a API key no Postiz e conectar os canais na plataforma:
  https://docs.postiz.com/public-api/introduction .
  Obter o `id` de cada canal pela API `GET /public/v1/integrations`.
  Em configuração privada (não commitar):
  ```dotenv
  POSTIZ_ENABLED=1
  POSTIZ_API_KEY=
  POSTIZ_YOUTUBE_INTEGRATION_ID=
  POSTIZ_TIKTOK_INTEGRATION_ID=
  # A fila continua desativada até escolher a conta e testar:
  PUBLISHING_ENABLED=0
  ```
  Credenciais configuradas não significam autenticação ou permissão de
  postagem validada. Para iniciar o worker, habilitar
  `PUBLISHING_ENABLED=1` apenas após ensaio privado e revisão da conta.
- Para evitar duplicação entre Postiz e conectores diretos, escolher somente
  um destino por conta/clipe; o dedupe SQL atual é por plataforma, não é
  uma garantia cross-platform (`tiktok` ≠ `postiz_tiktok`).
- O conector usa endpoint oficial HTTPS `https://api.postiz.com`.
  Implantação Postiz self-hosted exige adaptação futura de host allowlist e
  infraestrutura separada; não foi implantada.
- Postiz exige licença AGPL-3.0 para seu próprio código; este projeto usa
  apenas API documentada, sem copiar código Postiz no Nexus.

## Verificação e aceitação

```bash
python -m unittest tests.test_autoclip_postiz -v
python -m unittest discover -s tests -v
python -m compileall -q clipforge tests tools
node --check clipforge/static/app.js
python -m tools.smoke
```

Os testes novos usam **mocks locais**: verificam permissões, diretórios,
carga multipart, payload privado e confirmação semântica de publicação.
Não verificam qualidade de IA nem conectividade OAuth real. Conferir os
workflows do GitHub Actions e smoke Windows antes de distribuir release.

### Antes de produção

1. Instalar e testar a CLI AutoClip no computador de execução, configurar
   provedor LLM, validar clips reais autorizados com facecam/reação.
2. Configurar Postiz e canais de YouTube/TikTok, testar upload privado em conta
   real e confirmar URL externa. Nunca versionar segredos ou mídia de terceiros.
3. Adicionar importação revisável de sugestões AutoClip ao editor, se o piloto
   mostrar ganho mensurável, evitando duplicação de overlays/legendas.
4. Não promover esta branch a release sem CI, aceitação visual e QA de direitos.
