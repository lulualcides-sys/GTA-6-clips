# GTA VI Mission Control — Painel visual de automações

**Objetivo:** mostrar quais componentes estão trabalhando e o que realmente foi feito. O painel usa nove módulos conectados, histórico cronológico persistente e seleção de clipes para revisão.

**Importante:** os cartões representam componentes técnicos do pipeline, não nove modelos de IA autônomos. Os estados decorrem de ações reais.

## Tela web

- Cabeçalho Mission Control e cartões ligados em fluxo visual 3 × 3.
- Radar Twitch, Ingestão, Direitos, Curadoria, Edição FFmpeg, Legendas Whisper, Motion HyperFrames, Revisão e Publicação.
- Estados possíveis: idle, waiting, blocked, queued, running, complete e failed.
- Feed com data/hora e filtros por módulo e estado, consultando o servidor a cada seis segundos.
- Ao selecionar um clipe na biblioteca, a visão foca apenas naquele arquivo.
- Reproduzir, aprovar, rejeitar, exportar HyperFrames e consultar Twitch continuam disponíveis.
- Interface responsiva, sem bibliotecas visuais pagas e sem simulação de agentes trabalhando.

## Eventos no backend

- Radar: Twitch consulta metadados por API oficial (sem download).
- Ingestão: origem local deduplicada e adicionada.
- Direitos: manifesto aceito; isso NÃO prova juridicamente a permissão.
- Curadoria: marcação explícita ou início do trecho escolhido por heurística.
- Edição: job enfileirado, processando, pronto ou falhou via FFmpeg.
- Legendas: faster-whisper na fila, processando, pronto ou falhou.
- Motion: solicitação efetiva de exportação HTML/CSS HyperFrames.
- Revisão: aprovação ou rejeição editorial pelo painel.
- Publicação: BLOQUEADO enquanto não houver contas GTA conectadas.

O backend grava a tabela agent_activity em data/clips.sqlite3, preservando após reinicialização. Sem fontes, mostra zero tarefas ativas; nunca inventa atividade. Histórico limitado a 3000 eventos e consulta de até 80 por clipe.

A API autenticada GET /api/agents aceita parâmetro opcional clip_id com 12 caracteres. Logs NÃO incluem credenciais, caminhos internos, contratos privados nem texto de transcrições.

## Testar o fluxo sem gravações de streamers

1. Mantenha ENABLE_SYNTHETIC_DEMO=0 no uso normal.
2. Para piloto local ou servidor controlado, configure ENABLE_SYNTHETIC_DEMO=1 e reinicie.
3. No painel, use o botão Testar fluxo real. FFmpeg gera vídeo e áudio sintéticos, ambos próprios.
4. O arquivo recebe manifesto owned e percorre o MESMO fluxo de ingestão, seleção e renderização.
5. Ao aparecer mission-demo-1.mp4, selecione-o para ver estados e prévia.
6. Máximo de três amostras por volume de dados. A amostra não é publicada nem usa mídia de terceiros.

## Verificações

Executar python -m unittest discover -s tests -v, python -m tools.smoke e node --check clipforge/static/agents.js. O workflow .github/workflows/mission-ui.yml usa Playwright para capturar screenshots reais em desktop e mobile em um servidor local com banco vazio. Screenshots são artefatos de QA, não prova de postagem social.

## Continuidade por outras IAs

Ler AGENTS.md, docs/MISSION_CONTROL.md, docs/AI_PIPELINE.md, docs/TWITCH.md e docs/HYPERFRAMES.md antes de alterar. Só criar eventos quando uma operação acontecer de fato. Preservar dados existentes e separação do projeto WildVox.

## Hospedagem

O painel continua local-first. Para acesso remoto no celular é necessário um servidor persistente, HTTPS, autenticação reforçada, backup, limites de requisição e orçamento aprovado. Não ativar cobrança em Railway ou outro provedor sem verificar o custo.
