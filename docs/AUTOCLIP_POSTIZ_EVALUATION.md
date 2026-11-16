# Avaliação de AutoClip + Postiz para o Astra

**16/11/2026 — documentação de decisão, NÃO integração em runtime.**

Referência curada do Arsenal: https://github.com/lulualcides-sys/Arsenal/blob/main/ferramentas/AUTOCLIP-POSTIZ-NEXUS-CLIPS-2026-11-16.md

## Estado do produto / onde encaixar

A PR [#25 — Operação Astra](https://github.com/lulualcides-sys/GTA-6-clips/pull/25) mantém pipeline de clipes, editor, revisão, fila SQLite e adaptadores diretos YouTube/TikTok em desenvolvimento. Seus testes são majoritariamente simulados; sem publicação real comprovada. **Não modificar esta PR e não presumir que ela foi mesclada.**

| Ferramenta | Origem e licença | Inserção candidata | Não fazer |
|---|---|---|---|
| [AutoClip — artbyjazi](https://github.com/artbyjazi/autoclip), MIT | Após ingestão **autorizada**, experimento local para segmentação por transcrição/LLM, reenquadramento falante, legendas e MP4 9:16 | Alternativa opt-in ao seletor/editor; preservar versões existentes | Não trocar editor aprovado nem instalar Python/Node/MediaPipe em produção sem teste e pacote isolado |
| [Postiz — gitroomhq](https://github.com/gitroomhq/postiz-app), AGPL-3.0 | Depois de direitos + QA + aprovação, possível adaptador externo para agendar/publicar | Escolher uma única autoridade de envio por clipe/plataforma | Não manter Postiz e fila local disparando o mesmo trabalho, nem confundir agendado com público |

Há outro projeto chamado [Autoclip — lmfrozza](https://github.com/lmfrozza/Autoclip), MIT, com pipeline Twitch específico; não misturar sua arquitetura/código com o AutoClip de edição acima sem análise separada.

## Ordem econômica de adoção

1. **AutoClip offline:** cinco a dez vídeos próprios/autorizados com gameplay e facecam. Comparar com baseline FFmpeg + PySceneDetect + faster-whisper usando os mesmos trechos, medindo acerto do momento, reação genuína, enquadramento, legenda correta PT-BR, fluidez 1080x1920 e tempo de CPU/GPU. Não aceitar melhoramento subjetivo sem amostras.
2. **Postiz sandbox:** executar em instância separada apenas se OAuth/integrações oficiais trouxerem vantagem sobre os adaptadores já presentes. Criar rascunhos, simular falhas e testar dedupe/reconciliação. Postar em rede real somente após permissão, contas autenticadas, aprovação editorial e autorização explícita de operação.
3. **Integração opcional:** interfaces desacopladas, feature flags desligadas por padrão, gerenciamento seguro de tokens, testes unitários/integração e retorno ao pipeline atual sem perda de estados.

## Contratos que não podem regredir

- O material deve ser próprio ou ter permissão documentada; uma clipagem pública na Twitch não equivale a licença de republicação.
- Preservar facecam e reação reais do mesmo vídeo; título engraçado só quando factual, sem diálogo inventado; crédito pequeno ao criador e final seco, conforme docs editoriais.
- Aprovado ≠ publicado. Enviado ≠ confirmado. Publicação pública só quando a plataforma comprovar ID e visibilidade; tratar 'uncertain' como exigência de reconciliação, nunca reupload cego.
- Não duplicar fila, nem incorporar engine inteira ao .exe Windows, nem vazar segredos no app/GitHub Actions/logs.
- AutoClip requer Python 3.11/3.12, FFmpeg com libass/libx264 e Node 20+ para build UI; avaliar CPU/GPU e dependências extras.
- Postiz self-hosted exige infraestrutura e manutenção; AGPL-3.0 impõe análise de licença antes de incorporar/modificar.
- Novas integrações em PR separada com testes e rollback. Esta nota apenas registra a decisão de avaliar.

## Definição de pronto de um piloto futuro

Relatório com commit, versões/licenças, amostras permitidas, resultados comparativos mensuráveis, custos de execução, erros de render/postagem, testes e risco de regressão. Só então converter protótipo em mudança operacional.
