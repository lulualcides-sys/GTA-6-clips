# GTA-6-clips — Operação Astra

**v0.12.0:** erros de download explicados em português; **notificação nativa do Windows** quando algo falha (grátis, sem instalar nada); sugestões do AutoClip podem ser **recortadas antes de importar** e **refeitas** com as configurações atuais.

**v0.11.0:** **gravação da live em tempo real** de streamers autorizados (opcional, aba Atividade); ao fim da live, a gravação vai para o AutoClip. No Exportar, o início e o fim do trecho podem ser marcados tocando o vídeo.

**v0.10.0:** aba **Atividade** (histórico e fila de downloads com status, erro e modo automático/manual, falhas das últimas 24 h, botão **Verificar agora**); **monitor de lives da Twitch** para streamers autorizados, que baixa a VOD ao fim da live (opcional) e manda ao AutoClip; **Cortes do AutoClip** configuráveis (cortes por vídeo, enquadramento por rosto ou centro, legenda com fonte, tamanho, cores e posição); **exportação** com formato, resolução, qualidade, trecho e metadados de origem e autoria, sem perda quando possível e sem alterar o corte original. Veja [V010_AUTOMACAO.md](docs/V010_AUTOMACAO.md).

**v0.9.2:** a atualização pelo app não renomeia mais a pasta baixada (o Windows negava com WinError 5 logo após o autoteste, normalmente por causa do antivírus). A versão nova é extraída direto na pasta final, e as tentativas antigas são limpas.

**v0.9.1:** corrige a atualização pelo app recusada com "A nova versão falhou na validação". O autoteste herdava as configurações reais do usuário (Twitch, YouTube e downloads ligados) e o Windows não liberava arquivos abertos no fim. Agora o teste roda isolado, não falha só por limpeza de pasta temporária e, se for interrompido, mostra a etapa e o erro.

**v0.9.0:** nova aba **YouTube**. O radar usa a YouTube Data API oficial, com chave gratuita, e mostra os vídeos de jogos em alta no Brasil e os YouTubers grandes (≥ 100 mil inscritos). Depois de 19/11, busca também GTA VI. O radar lê a descrição do canal e dos vídeos para achar quem libera cortes, e a restrição sempre vence. **Ele autorizou** e **Confirmar** registram a permissão com evidência. Com o download ligado em **Conectar YouTube** (`YOUTUBE_PUBLIC_DOWNLOAD=1`, desligado por padrão), o app baixa os vídeos novos dos canais autorizados via yt-dlp. O app confere se o vídeo é mesmo do canal autorizado e bloqueia lives e vídeos com mais de `YOUTUBE_MAX_MINUTES`. Só depois manda o vídeo para o AutoClip. O ZIP do Windows traz o Deno (runtime JS exigido pelo yt-dlp, versão e SHA-256 fixados) e o yt-dlp-ejs. O YouTube costuma exigir cookies de um navegador logado: use uma conta Google secundária. Baixar do YouTube não tem API oficial e pode violar os Termos do YouTube (risco do proprietário). Na Twitch, a mensagem do **Ele autorizou** agora diz a verdade sobre o modo de download, e há um botão para ligar o download público no app Windows. Veja [YOUTUBE.md](docs/YOUTUBE.md).

**v0.8.2:** opção `TWITCH_PUBLIC_DOWNLOAD=1` (desligada por padrão): quando a conta não é editora do canal, baixa o clipe público via yt-dlp **somente de streamers autorizados** no Radar. Não é API oficial da Twitch e pode violar os Termos dela — risco assumido pelo proprietário.

**v0.8.1:** corrige o app Windows da v0.8.0 que pedia "Token do painel" (as abas apagavam o token automático antes da leitura); atualização pelo app tolera a primeira verificação do antivírus (autoteste do AutoClip até 180 s, total até 7 min) e mostra o motivo exato quando a atualização é recusada.

**v0.8.0:** novo visual por abas (Painel, Clipes, Radar viral, Publicar, Ajustes): cada seção cabe em uma tela, sem rolar a página; Aprovar/Rejeitar sempre visíveis ao lado do vídeo; barra de abas fixa no celular.

**v0.7.1:** o download automático segue o calendário: antes de 19/11 pega os clipes virais das categorias em alta (de streamers autorizados); a partir de 19/11 00:00 somente GTA VI, com lote máximo de 12 por rodada.

**v0.7.0:** botão **Preparar IA do AutoClip** — no Windows instala o Ollama oficial (assinatura digital conferida antes de executar), inicia o serviço local e baixa o modelo escolhido com barra de progresso; o AutoClip passa a iniciar o Ollama sozinho quando já instalado. Novo botão **Testar conexões** (Twitch, YouTube, TikTok, Postiz) com chamadas somente leitura, que também informa se a categoria GTA VI já existe na Twitch. Novo **Radar Viral BR**: lista os clipes com maior potencial viral (métricas públicas da Twitch, prioridade PT-BR) e os streamers em alta para pedir permissão; o botão **Ler bios** encontra quem libera cortes publicamente na bio da Twitch e deixa a confirmação pronta; **Ele autorizou** registra a permissão (o download só acontece se sua conta for editora do canal ou com o download público da v0.8.2 ligado). Veja [AUTOCLIP_ONLY.md](docs/AUTOCLIP_ONLY.md).

**v0.6.0 (Nexus Clips BR):** relatórios visuais opcionais por Ollama com visão, avisos técnicos de QA sem alteração dos vídeos, feedback de rejeição usado em ranking conservador, aprovação móvel privada por Tailscale Serve com código temporário, métricas reais YouTube/TikTok quando a conta e o vídeo estão autorizados. Veja [documentação e limites](docs/EDITORIAL_INTELLIGENCE_V060.md).

**Triagem GTA VI v0.5.1:** Helix paginado por janelas, até 1.000 candidatos em análise por rodada, filtro de pontuação/duração/engajamento, variedade de criadores e fila AutoClip somente para fontes autorizadas. Não promete identificar humor sem assistir ao vídeo. Veja [TWITCH](docs/TWITCH.md).

**Pipeline v0.5.0 (Windows):** AutoClip real (Python 3.12, Whisper, MediaPipe) incluído no ZIP; buscas Twitch baixam automaticamente apenas mídia própria/editor autorizada com OAuth de usuário e direitos documentados. Saídas AutoClip validadas vão para **Em revisão**, nunca aprovação ou publicação automática. Ollama/modelo ainda é necessário separadamente. Veja [AUTOCLIP_ONLY](docs/AUTOCLIP_ONLY.md) e [DESKTOP_WINDOWS](docs/DESKTOP_WINDOWS.md).

**Windows v0.4.3:** correção dos erros `0x80131515` ao carregar `Python.Runtime.dll` ou `Microsoft.Web.WebView2.Core.dll`. Após extrair o ZIP oficial, execute `Corrigir-e-Abrir-GTA6Clips.cmd` e confirme o reparo de bibliotecas exclusivamente na pasta `_internal`. A versão 0.4.2 não abrangia todas as DLLs. Veja [DESKTOP_WINDOWS](docs/DESKTOP_WINDOWS.md). Dados pessoais não são alterados.


**Política nova v0.4.1:** o AutoClip é o único editor de NOVOS vídeos. O Nexus não substitui com FFmpeg. Se não houver CLI AutoClip instalada e habilitada, nenhum novo vídeo é editado. Veja [AUTOCLIP_ONLY](docs/AUTOCLIP_ONLY.md).

Plataforma local-first para fontes autorizadas, edição vertical, revisão e fila de publicação. Python 3.11+, SQLite, FFmpeg e painel sem framework. A evolução preserva o aplicativo Windows existente.

**Estado da entrega:** veja [relatório Astra](docs/ASTRA_REPORT.md). Testes sintéticos comprovam o pipeline técnico; não comprovam qualidade editorial de clipes reais nem publicação pública. As contas sociais e a Twitch exigem credenciais e permissões próprias.

## Instalar e executar

Instale Python 3.11+ e FFmpeg/FFprobe no PATH. O núcleo usa a biblioteca padrão:

```bash
python -m pip install -r requirements.txt
python -m clipforge.web
```

Abra http://127.0.0.1:8000. No Windows, veja [aplicativo portátil](docs/DESKTOP_WINDOWS.md) e [auditoria Windows](docs/WINDOWS_ASTRA_AUDIT.md). Nunca salve mídias ou credenciais dentro da pasta do executável. Para acesso remoto, configure autenticação, proxy HTTPS e firewall; o aplicativo desktop permanece em loopback.

Recursos opcionais (modelos Whisper podem exigir download e memória):

```bash
python -m pip install -r requirements-ai.txt
```

`SMART_SCENES=1` habilita PySceneDetect; `AUTO_TRANSCRIBE=1` habilita transcrição após render. Ambos são desligados por padrão. Detecção de cenas e pontuação acústica **não compreendem humor, eventos ou linguagem**.

## Importar fonte autorizada

Coloque `data/incoming/video.mp4` e `data/incoming/video.mp4.rights.json`:

```json
{
  "creator": "Criador original",
  "rights_status": "permission_granted",
  "evidence": "Referência verificável da autorização de republicação",
  "source_url": "https://www.twitch.tv/criador",
  "start_sec": 2,
  "duration_sec": 12,
  "title": "TÍTULO CONFERIDO NO VÍDEO",
  "title_verified": true
}
```

Para fonte própria, use `owned`. O manifesto registra declaração, não verifica automaticamente licença. Títulos personalizados exigem conferência humana. Sem título, o sistema usa texto neutro. Para GTA declarado, a revisão de câmera/reação da mesma fonte é obrigatória: [regras](docs/REACTION_REQUIRED.md).

O render usa 1080×1920, H.264/AAC, crédito permanente, áudio normalizado e 30 FPS por padrão; `RENDER_MAX_FPS=60` permite 60 quando a fonte comporta. Saídas são versionadas e o original é conferido por SHA-256. O painel permite ajuste de corte, título e enquadramento, prévia original/editada e aprovação individual/em lote. Aprovar não publica.

## Twitch e lançamento

[Configuração Twitch](docs/TWITCH.md): radar de até 12 categorias antes da data de lançamento configurada; prioridade GTA VI a partir de **19/11/2026 às 00:00 de São Paulo**. A data é uma configuração operacional fornecida pelo usuário, não uma verificação independente do calendário oficial. `TWITCH_DISCOVERY_MODE` permite intervenção manual. OAuth de aplicação descobre metadados; não concede direitos de download/republicação.

[Download oficial por CLI](docs/TWITCH_DOWNLOAD.md) exige token de usuário com escopo específico, broadcaster/editor válidos e manifesto de direitos separado. Os contratos foram testados localmente; autorização real da conta continua necessária. Não há extração por métodos alternativos.

## Publicação

[Contrato e limites](docs/PUBLISHING.md). Fila SQLite com agendamento, deduplicação, aprovação/direitos, limite por plataforma e confirmação separada do envio. `PUBLISHING_ENABLED=0` por padrão; modo automático exige opção adicional explícita. Tokens OAuth são fornecidos privadamente, nunca embutidos no executável.

Adaptadores YouTube e TikTok estão sujeitos a OAuth, escopos e revisão das plataformas; envio privado não equivale a publicação pública. Instagram, login OAuth interativo e renovação de tokens ainda têm limitações documentadas. Falha ambígua de envio exige reconciliação e não gera repost automático.

## HyperFrames

Exportação HTML/CSS + MP4 + manifesto sem provas privadas, com título curto e crédito. Legendas somente quando solicitadas. O render final é opcional e requer Node 22+, HyperFrames e Chrome:

```bash
python -m clipforge.hyperframes ID_DO_CLIPE --title "TÍTULO CONFERIDO"
# Opcional, após instalar CLI/Chrome conforme docs/HYPERFRAMES.md:
python -m clipforge.hyperframes ID_DO_CLIPE --render
```

Exportar ZIP não significa renderizar. Um `final.mp4` existente não é sobrescrito.

## Verificar e gerar demonstrações próprias

```bash
python -m unittest discover -s tests -v
python -m compileall -q clipforge tests tools
python -m tools.smoke
python -m tools.scene_smoke
python -m tools.hyperframes_smoke
python -m tools.astra_smoke --output data/astra-demo-nova
```

`scene_smoke` requer PySceneDetect. `astra_smoke` usa FFmpeg e HTTP local reais, guarda duas versões MP4, testa áudio/quadro preto, prévia, aprovação, deduplicação e exportação; **publicação é simulada localmente**. Use uma pasta nova a cada execução. O relatório `report.json` e os vídeos ficam nessa pasta; nada é enviado a redes sociais.

[Arquitetura](docs/ARCHITECTURE.md) · [Plano](docs/superpowers/plans/2026-11-14-astra.md) · [Relatório e pendências](docs/ASTRA_REPORT.md)
