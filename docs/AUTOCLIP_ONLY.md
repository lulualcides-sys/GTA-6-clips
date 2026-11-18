# Política de edição exclusiva — AutoClip (Nexus Clips BR v0.4.1)

**Regra permanente:** a edição de qualquer NOVO vídeo no Nexus usa exclusivamente a CLI real [AutoClip](https://github.com/artbyjazi/autoclip). O FFmpeg do Nexus não pode ser acionado como editor, nem como fallback se a CLI falhar ou estiver ausente. Remotion, cortes heurísticos e HyperFrames não substituem o AutoClip. Os vídeos já concluídos permanecem inalterados.

## Pipeline vigente

1. Descoberta Twitch e ingestão de arquivos locais com direitos declarados continuam separadas.
2. O botão **Editar com AutoClip** (rota compatível `POST /api/clips/{id}/render`) chama apenas `AutoClipBridge.queue()`. A rota `POST /api/clips/{id}/autoclip` continua disponível.
3. A CLI roda isolada e gera até três propostas verticais na pasta `data/extensions/autoclip/exports`. Não há edição inventada quando a CLI falha ou não está instalada.
4. O usuário assiste às propostas no painel e importa uma. O importador verifica o hash da fonte, direitos declarados, duração de 10 a 60 s, proporção 9:16, trilhas de vídeo/áudio e decodificação integral. FFmpeg é usado **somente** para QA (decodifica para `null`).
5. O MP4 criado pelo AutoClip é copiado **byte a byte, sem re-encode**, para `data/rendered`, marcado `ready` e encaminhado à aprovação editorial. O JSON de QA registra `engine=autoclip`.
6. Envio às redes só ocorre após aprovação e demais políticas de publicação. Nenhuma credencial é embutida.

## Falha fechada

- Se `AUTOCLIP_ENABLED=0`, a CLI não existir ou o motor falhar, retorna erro explícito e não cria vídeo substituto.
- Pedidos antigos de FFmpeg ainda interrompidos são marcados como `failed` na primeira inicialização da versão nova e não são retomados. Fonte original e edições anteriores permanecem em disco.
- `render_clip()`, o antigo gerador FFmpeg, bloqueia todas as chamadas de produção. `NEXUS_LEGACY_TEST_RENDER=1` existe **apenas para regressões e amostras sintéticas CI**, nunca para operação do usuário.
- A API `POST /api/clips/{id}/edit` rejeita edição manual. O formulário antigo fica desativado na interface.
- Não existe autorização automática de upload ou publicação após gerar uma proposta.

## Instalação real no computador que executa o Nexus

Desde v0.5.0, o workflow Windows empacota **o motor real AutoClip** em `autoclip_runtime/`, com Python 3.12 isolado, Whisper, MediaPipe e dependências de edição. O código upstream MIT é fixado em um commit versionado, e o build precisa executar imports e `autoclip styles` para passar. Esse runtime é mais pesado que o pacote antigo; não existe fallback para outro editor. No Linux/Docker a CLI continua exigindo instalação separada.

**IA local dentro do app (v0.7.0):** o painel tem o bloco **IA do AutoClip** com o botão **Preparar IA do AutoClip** (rota `POST /api/local-ai/prepare`, somente token do proprietário; estado em `GET /api/local-ai`). No Windows ele:
1. baixa `OllamaSetup.exe` do endereço oficial `https://ollama.com/download/OllamaSetup.exe` (limite de tamanho, HTTPS obrigatório);
2. confere a assinatura Authenticode (`Valid` e certificado da Ollama) e **bloqueia** a execução se não bater;
3. instala com `/SILENT`, inicia `ollama serve` somente em `127.0.0.1:11434`;
4. baixa um modelo da lista fechada (`llama3.1:8b` recomendado ~4,9 GB, ou `llama3.2:3b` ~2 GB) pela API oficial `/api/pull`, verificando espaço em disco antes.
Os pesos ficam na pasta do Ollama do usuário, nunca no ZIP do app nem no GitHub. Em Linux/macOS a instalação do Ollama é manual; o botão então só inicia o serviço e baixa o modelo. Quando o Ollama já está instalado mas parado, o AutoClip o inicia sozinho antes de editar. Código: `clipforge/local_ai.py`; testes: `tests/test_local_ai.py` (mocks — não comprovam instalação real em um PC Windows).

**Modelo de IA:** a distribuição do motor não inclui os pesos de um LLM. O Nexus encontra automaticamente modelos já instalados no Ollama local em `127.0.0.1:11434`; sem Ollama/modelo adequado ou outro provedor previamente configurado, não é possível editar. Um `ollama pull llama3.1:8b` separado é uma opção de modelo local, não um arquivo incluído no instalador. A qualidade da seleção depende fortemente do modelo.

**Pipeline sem cliques por vídeo:** busca pública Twitch (metadados) → somente fontes com OAuth oficial `channel:manage:clips` ou `editor:manage:clips` **e** declaração de direitos → download Helix `/clips/downloads` → ingestão, deduplicação e fila AutoClip → IA produz até três MP4s → QA vertical/áudio/hash → MP4s em `ready` na biblioteca. **Nunca aprovar nem publicar automaticamente.** Para o próprio canal, usar `Autorizar downloads Twitch` no desktop (consentimento uma vez e callback local `http://localhost:3000`, que deve estar registrado no Developer Console). Para outros canais, a concessão de editor e evidência de reutilização são exigidas; uma busca de clipes públicos sozinha não libera as mídias. Tokens de acesso e atualização são guardados no `config.env` local do usuário e não enviados ao GitHub.

Em configuração local privada:
```dotenv
AUTOCLIP_ENABLED=1
AUTOCLIP_BINARY=autoclip
AUTO_RENDER=1
```
`AUTO_RENDER=1` inicia apenas a análise AutoClip das novas fontes quando a CLI estiver disponível; nunca aciona FFmpeg. Não salvar tokens/segredos no GitHub.

## Validação

```bash
python -m unittest tests.test_autoclip_exclusive tests.test_autoclip_postiz -v
python -m unittest discover -s tests -v
python -m tools.smoke
node --check clipforge/static/app.js
```
`tools.smoke` testa separadamente o renderizador antigo **com mídia sintética apenas** para verificar regressões internas; não é resultado de IA. O teste de contrato da CLI AutoClip usa mocks; **somente teste real com uma instalação e vídeo válido prova a edição inteligente**.
