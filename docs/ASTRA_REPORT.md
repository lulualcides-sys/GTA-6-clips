# Operação Astra — relatório verificável

Data: 14/11/2026 (São Paulo). Base: `364a04dffed42f861ad9d8626fe258550ae8a0cb`, preservada na tag local `astra-baseline-2026-11-14`. Branch: `astra/platform-reliability`.

Verificação consolidada em 15/11/2026: **188 testes passaram** (`python -m unittest discover -s tests -v`, 20,455 s). Compilação Python, sintaxe dos quatro scripts do painel e `git diff --check` passaram. Resultados de navegador e CI são registrados separadamente abaixo.

Esta entrega é um incremento funcional amplo; **não satisfaz ainda todos os critérios de operação em produção**. Não houve postagem real, instalação no computador do usuário ou avaliação editorial de filmagem real de streamer.

## Auditoria e implementação

| Área | Evidência/implementação | Limite remanescente |
|---|---|---|
| Base | 123 testes da revisão original passaram em cópia separada | Testes iniciais no sandbox falharam por sockets proibidos; rerun autorizado passou |
| Direitos/origem | Manifesto, SHA-256, bloqueio de fonte alterada, aprovação separada | Declaração de licença não é verificação jurídica automática |
| Edição | 1080×1920, 30/60 FPS, título conferido, crédito, normalização, layouts, versões imutáveis, QA completo | Enquadramento manual; sem detector semântico, risadas/explosões ou tracking automático |
| Seleção | Pontuação acústica transparente e até três sugestões; PySceneDetect opcional | Sem métricas reais de retenção, originalidade semântica ou garantia de humor |
| Painel | Prévia original/editado com Range, ajustes, lote explícito e fila | Comparação de todas as versões persistidas e edição de timeline avançada ainda limitadas |
| Twitch | Até 12 categorias, override e virada configurável, lives por IDs, OAuth retry, dedupe | Polling, sem EventSub; teste externo depende de credenciais |
| Obtenção Twitch | CLI oficial Get Clips Download, token/scopes/editor, manifesto independente, CDN restrita, FFprobe | Sem botão no painel nem OAuth interativo; conta real ainda não validada |
| Publicação | SQLite, aprovação/direitos, hash, agenda, limites, dedupe, backoff de status, incerteza sem reupload | YouTube/TikTok testados em contratos locais; OAuth interativo/refresh e Instagram pendentes |
| Mission Control | Estados/contadores de publicação reais, histórico de tarefas | Credencial configurada não prova autenticação válida |
| HyperFrames | Exportação e render final real testados, título neutro, FPS preservado, não sobrescreve final | Execução exige CLI/Chrome; não incluídos no aplicativo padrão |
| Windows | Atualizador protege ZIP ADS/reservados/colisões, dados persistentes, HANDLE x64 e self-test | Build da revisão é CI Windows; instalação/janela nativa do usuário não verificadas |

## Demonstração integrada

Comando executado:

```bash
python -m tools.astra_smoke --output data/astra-demo
```

Resultado: **ASTRA E2E PASS**. Duas versões MP4 próprias geradas por FFmpeg, arquivo original preservado, FFprobe 1080×1920, áudio não silencioso, decodificação integral, nenhum intervalo preto no detector do teste, prévia HTTP Range, aprovação HTTP, ingestão deduplicada e fila de publicação com confirmação **simulada exclusivamente local**. Composição HyperFrames exportada. Os quadros de ambas as versões foram inspecionados.

Arquivos locais: `data/astra-demo/report.json`, `data/astra-demo/rendered/`, `data/astra-demo/hyperframes/`. Não entram no Git. O workflow CI gera artefato `astra-synthetic-demo` com vídeos próprios, relatório e ZIP. A mídia sintética comprova integridade técnica, não qualidade cômica/editorial de clipes reais.

## Testes executados

- Base imutável: `python -m unittest discover -s tests -v` — 123 testes, OK.
- PySceneDetect real: `/tmp/astra-qa-venv/bin/python -m tools.scene_smoke` — PASS; cortes detectados em 2,0 s e 4,0 s.
- HyperFrames exportação: `python -m tools.hyperframes_smoke` — PASS, mídia própria real.
- HyperFrames completo: `python -m tools.hyperframes_smoke --render` — PASS, MP4 1080×1920 via HyperFrames 0.9.52 + Chromium local. CLI instalada isoladamente em `/tmp/astra-hyperframes`, sem alteração nas dependências de produção.
- Aceitação Astra acima — PASS.
- Testes unitários e HTTP locais novos cobrem OAuth inválido, download autorizado/negado, seleção, títulos, caminhos Windows, fila, confirmação/dedupe e recuperação. Resultado consolidado da revisão final registrado abaixo após execução.

## Correções encontradas na revisão independente

Foram corrigidos: worker de publicação sem inicialização no ciclo de vida web/desktop; aprovação concorrente com edição; ID remoto/visibilidade omitidos no painel; estado de publicação fixo no Mission Control; timestamp escolhido sobrescrito por configuração antiga; pontuação/alternativas descartadas; configuração de publicação ausente no desktop. A fila é desativada por padrão e não houve postagem externa.

A verificação de API local usa servidores HTTP reais e SQLite; respostas remotas são contratos simulados, explicitamente separados da validação de produção. O teste de publicação nunca chama redes sociais.

## Reproduzir

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m compileall -q clipforge tests tools
python -m tools.smoke
python -m tools.hyperframes_smoke
python -m tools.astra_smoke --output data/astra-demo-nova
python -m clipforge.web
```

Para cenas: instalar `scenedetect>=0.7,<1` em ambiente de QA e executar `python -m tools.scene_smoke`. A instalação de teste usou ambiente temporário, sem modelos Whisper e sem alterar dependências do núcleo.

## Próximos critérios obrigatórios antes de produção

1. Validar OAuth/escopos e download oficial com conta Twitch e mídia autorizadas.
2. Rever amostras reais com facecam/reação para comprovar acabamento editorial; nenhum título humorístico deve ser inventado a partir de volume de áudio.
3. Conectar contas sociais, implementar login/renovação OAuth e Instagram conforme infraestrutura; validar visibilidade e confirmação externa real.
4. Validar instalação e janela do aplicativo Windows em máquina de destino.
5. Completar orquestração de descoberta→download, EventSub se necessário, editor de versões e seleção audiovisual contextual.
6. Fazer ensaio operacional de carga, falhas e recuperação com fontes autorizadas antes de habilitar publicação automática.

A data de 19/11/2026 às 00:00 America/Sao_Paulo é o alvo operacional solicitado, com override configurável; não foi apresentada como validação independente do calendário da Rockstar.
