# HyperFrames — Compositor Visual de Cortes

**Status:** exportação HTML/CSS e download web implementados. Render CLI independente, sujeito a QA no workflow dedicado. Não faz seleção semântica, captura Twitch ou postagem.

Upstream: https://github.com/heygen-com/hyperframes (Apache-2.0, confirmar licenças de assets). Requisitos de render: Node.js 22+, CLI HyperFrames, Chrome/headless e FFmpeg.

## Fluxo operacional

1. Um vídeo com manifesto de direitos aprovado é renderizado e validado pelo FFmpeg existente.
2. No painel, selecionar vídeo pronto ou aprovado e clicar **Exportar HyperFrames**.
3. O backend cria pasta privada data/hyperframes/<id>, com index.html, style.css, source.mp4 e manifest.json.
4. O download é protegido por DASHBOARD_TOKEN; o ZIP contém arquivos editáveis por outras IAs, sem evidência privada de licença.
5. O HTML contém título personalizado, animações CSS finitas, crédito ao streamer e, quando existir, legenda SRT com timecodes reais.
6. O comando opcional python -m clipforge.hyperframes <id> --render executa CLI local e salva final.mp4 separado do vídeo original. Não publica nas redes.

## Comandos

Preparar uma composição: python -m clipforge.hyperframes abcdef123456 --title 'GTA VI • DESTAQUE'

Com SRT real: python -m clipforge.hyperframes abcdef123456 --srt ./legendas.srt

Renderização: npm install -g hyperframes ; hyperframes browser --install ; python -m clipforge.hyperframes abcdef123456 --render

Testar: python -m unittest discover -s tests -v ; python -m tools.hyperframes_smoke --render

O parser de SRT limita tamanho e quantidade de linhas, escapa HTML e respeita a duração da mídia. NÃO produz legendas sozinho: Whisper ainda não está conectado.

## Endpoints protegidos

- POST /api/clips/{id}/hyperframes — exporta apenas clipes ready/approved, retorna rendered=false.
- GET /api/clips/{id}/hyperframes.zip — entrega pacote, somente após exportar.

## Qualidade e segurança

- Render CLI é um estágio separado; o Docker da API principal NÃO instala Node/Chrome/HyperFrames por padrão.
- Não introduzir snippets HTML/JS de terceiros sem revisão; não incluir CDNs e fontes externas na composição.
- Verificar áudio, FPS, legendas, autor, recortes e layout no vídeo real antes de aprovar.
- Manter FFmpeg como fallback e preservar originais e permissões; no perfil padrão não existe autodeploy ou postagem.
- CI principal verifica os testes Python; workflow HyperFrames dedicado verifica navegador e MP4 sintético.
