# GTA-6-clips

**Windows sem hospedagem paga:** há um aplicativo desktop portátil em construção, que aproveita o painel visual existente. Veja [Como instalar o app Windows](docs/DESKTOP_WINDOWS.md) e o workflow [Windows app — build](.github/workflows/windows-app.yml). O `.exe` é distribuído como artefato de GitHub Actions somente após os testes de build. O app fica no PC; não existe instalação remota automática.

Projeto independente de **GTA 6**: ingestão de vídeos autorizados, seleção inicial de cortes por áudio, render vertical (9:16) e painel web de revisão. Organizado para manutenção por múltiplos agentes de IA.

> **Estado real:** MVP local-first para web local e aplicativo Windows (empacotamento em validação). Ainda **não** baixa lives ou clipes da Twitch, **não** transcreve automaticamente sem ativação dos recursos opcionais, **não** publica nas redes e **não** está hospedado em domínio público.

## Iniciar (Python)

Requer Python 3.11+ e FFmpeg/ffprobe instalados no PATH:

```bash
python -m clipforge.web
```

Abra http://127.0.0.1:8000. Scanner a cada 30s, AUTO_RENDER=1 por padrão (somente fontes com manifesto válido).

## Cadastrar vídeo com direitos

Coloque `data/incoming/meu-video.mp4` e `data/incoming/meu-video.mp4.rights.json`:

```json
{
  "creator": "Nome do criador",
  "rights_status": "permission_granted",
  "evidence": "URL ou registro verificável da autorização",
  "source_url": "https://www.twitch.tv/...",
  "start_sec": 20,
  "duration_sec": 35
}
```

Para vídeo próprio, use `rights_status: "owned"`. O sidecar é autodeclaração; **não comprova automaticamente os direitos**. Sem `start_sec`, uma heurística de áudio escolhe a janela; não se trata de IA semântica. Saída: MP4 H.264/AAC, 1080x1920, 30 FPS, gameplay central e fundo desfocado, sem cortes destrutivos.

## Docker

```bash
cp .env.example .env
# Troque DASHBOARD_TOKEN por uma senha forte antes de executar
mkdir -p data
docker compose up --build
```

Acesse http://127.0.0.1:8000. Em Linux pode ser preciso ajustar permissões de `data/` para UID 10001 (container não-root). Não publique `.env` nem `data/`.

## Testes

```bash
python -m unittest discover -s tests -v
python -m compileall -q clipforge tests tools
python -m tools.smoke
```

O smoke gera vídeo **sintético**, testa a verificação de direitos e renderiza uma saída técnica real. GitHub Actions executa tudo após commits.

## Limites e segurança

- API com token `DASHBOARD_TOKEN` em acessos não locais; produção requer HTTPS e proteção adicional.
- Apenas **um render por vez** para limitar uso de CPU; persistência SQLite + mídia local.
- A tela permite aprovar/rejeitar. **Aprovação não é publicação**.
- Não ingerir sem autorização de terceiros. Respeitar termos da plataforma, direitos de voz/imagem e propriedade intelectual.
- Não hospedar mídia, banco, licenças privadas ou tokens no GitHub.

## Monitoramento Twitch — múltiplas categorias até GTA VI

**Regra operacional:** até 18/11/2026 buscar clipes em até 12 categorias populares da Twitch, incluindo IRL e jogos. **À meia-noite de 19/11/2026, horário de São Paulo**, mudar automaticamente para **somente Grand Theft Auto VI**. A data pode ser atualizada caso a Rockstar altere o lançamento. A busca é apenas de metadados; não baixa ou publica material de terceiros.

**Ativação no Windows:** no aplicativo clique em **Conectar Twitch**, preencha `Client ID` e `Client Secret` recebidos no Twitch Developer Console. O programa verifica o OAuth antes de salvar localmente; reinicie o programa. Credenciais ficam apenas no arquivo `config.env` no seu PC, fora do GitHub. Veja [docs/TWITCH.md](docs/TWITCH.md).

## Descoberta de clipes na Twitch

O painel agora tem uma área de **candidatos da Twitch**. Com `TWITCH_CLIENT_ID` e `TWITCH_CLIENT_SECRET`, ela busca até 100 registros públicos na categoria exata Grand Theft Auto VI, classifica por visualizações/recência/duração e indica se a permissão foi declarada no arquivo privado `data/twitch_sources.json`. Modo automático opcional `TWITCH_ENABLED=1` (varredura a cada 15 min).

**Não baixa lives ou clipes da Twitch e não os publica**: essa etapa é apenas a descoberta de metadados. Consulte [docs/TWITCH.md](docs/TWITCH.md) e [docs/OPEN_SOURCE_DECISIONS.md](docs/OPEN_SOURCE_DECISIONS.md) antes de conectar fontes.

## Acabamento visual HyperFrames (integração opcional)

O sistema gera agora **composições HTML/CSS reais e editáveis** usando [HyperFrames](https://github.com/heygen-com/hyperframes) (Apache-2.0). O botão **Exportar HyperFrames**, disponível para clipes prontos ou aprovados, prepara um ZIP para baixar no painel, contendo `index.html`, `style.css`, `source.mp4` e `manifest.json`. Ele inclui título original, animações CSS finitas, crédito permanente ao criador e, quando fornecido, legenda SRT com timestamps reais. Sem SRT, **não inventa legendas**.

Para preparar manualmente por linha de comando:

```bash
python -m clipforge.hyperframes abcdef123456 --title "MOMENTO ABSURDO NO GTA VI"
# IDs devem existir no SQLite e ter vídeo renderizado válido
```

Para executar render final pelo HyperFrames em uma máquina de edição com Node.js 22+, FFmpeg, Chrome e CLI do HyperFrames previamente instalados:

```bash
npm install -g hyperframes
hyperframes browser ensure
python -m clipforge.hyperframes abcdef123456 --title "DESTAQUE DO STREAMER" --render
```

O render final fica separado em `data/hyperframes/<id>/final.mp4`, e **nunca sobrescreve o MP4-base aprovado**. O Docker de produção não instala HyperFrames/Chromium por padrão. No painel, **Exportar não significa renderizar nem publicar**: para render final use uma máquina com CLI instalada. Veja [docs/HYPERFRAMES.md](docs/HYPERFRAMES.md).

## Análise visual e legendas com IA (novidade)

Agora existem módulos **opcionais** de análise de cenas por PySceneDetect e de transcrição real via faster-whisper. O botão **Gerar legendas IA** cria SRT com os tempos das palavras, quando houver fala detectada; o HyperFrames reaproveita automaticamente esse SRT na exportação. A seleção por cena considera cortes visuais mais próximos do trecho com atividade de áudio, **mas não compreende semântica, humor ou acontecimentos do jogo**.

Os pacotes estão em `requirements-ai.txt` e **não são instalados no Docker básico**. `SMART_SCENES=0` e `AUTO_TRANSCRIBE=0` por padrão; ative apenas em máquina com CPU/memória adequadas. O primeiro uso do faster-whisper pode baixar pesos de modelos. Veja [docs/AI_PIPELINE.md](docs/AI_PIPELINE.md).

## Mission Control — central visual dos agentes

O painel agora tem uma área de automações com nove módulos conectados, histórico real de tarefas, filtros, estado de cada etapa e indicadores de trabalho. Selecionar um clipe atualiza o fluxo daquele arquivo. Os cartões são **módulos operacionais, não modelos de IA autônomos**; não há agentes falsamente marcados como trabalhando.

O recurso persiste eventos no banco SQLite e mantém a edição, revisão, HyperFrames e Twitch existentes. Para um teste de ponta a ponta com mídia sintética própria, configure `ENABLE_SYNTHETIC_DEMO=1` em um servidor controlado e use **Testar fluxo real**. É desativado por padrão e limitado a três testes por volume, sem postar nada.

Veja [docs/MISSION_CONTROL.md](docs/MISSION_CONTROL.md). A interface continua local-first; a hospedagem pública depende de infraestrutura segura e orçamento.

Leia **AGENTS.md** primeiro. Arquitetura em docs/ARCHITECTURE.md; inventário filtrado em docs/ARSENAL.md; prioridades em docs/ROADMAP.md; operações em docs/RUNBOOK.md.
