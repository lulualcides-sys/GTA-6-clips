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

O EXE Windows **não inclui o motor AutoClip**. Instalar separadamente em ambiente compatível Python 3.11/3.12, com FFmpeg, Whisper e provedor/LLM configurado. Conferir instruções e comando `autoclip doctor` em https://github.com/artbyjazi/autoclip.

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
