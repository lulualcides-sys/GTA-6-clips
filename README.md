# GTA-6-clips — Operação Astra

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
