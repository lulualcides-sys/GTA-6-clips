# Últimas open source: seleção técnica com critérios

Referências principais, todas separadas do motor produtivo:

| Projeto | Onde ajuda | Onde NÃO ajuda / decisão |
| --- | --- | --- |
| [yihui-dev/awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos) | Exemplos de prompts, HTML, SVG, GSAP e Three.js para vinhetas, transições e elementos visuais | **Não** identifica cortes nem transforma lives em Shorts; usar seletivamente como inspiração, sem importar o repositório inteiro |
| [Donchitos/Claude-Code-Game-Studios](https://github.com/Donchitos/Claude-Code-Game-Studios) | Contratos de agentes por domínio, gates de QA, documentação e evidência visual | Framework de jogos, **não** serviço de clipes; adaptação do método ao AGENTS.md e testes, não instalação de 49 agentes |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | Pipeline de vídeo sintético/automatizado; referências para padrões de orquestração | Foco em vídeos gerados, não direitos de gameplay de terceiros; não adotar motor pesado |
| [FFmpeg](https://ffmpeg.org) | Transcodificar, cortar, mixar e validar vertical real | Já integrado; é a melhor base do MVP |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Legendas com fala realmente transcrita e timestamps | Agendar P1; custo de inferência variável |
| [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | Detectar transições e limites de cena | Planejar fusão com sinais de áudio. Não detecta evento engraçado sozinho |
| [Remotion](https://github.com/remotion-dev/remotion) | Templates de composição animada em React | Licenciamento e carga de render devem ser avaliados antes da adoção |
| [GSAP](https://gsap.com) | Animações no browser e motion graphics | Reutilização comercial e licenças aplicáveis precisam ser checadas |
| [Descript](https://www.descript.com) | Editor assistido e legendas; conector acessível na conversa | Ferramenta comercial opcional, não núcleo 100% open source |

## Aplicação real nesta fase

- Aproveitados de Claude Code Game Studios: ideia de **separar domínios**, exigir QA com evidências e um contrato de agentes. Estão em AGENTS.md e testes automatizados; não houve instalação do template.
- Aproveitados de Awesome Opus: referências de movimento para futura biblioteca de templates. **Ainda não há assets, SVGs ou animações do catálogo incorporados ao vídeo renderizado.**
- Adotada agora: descoberta via API oficial Twitch **sem download**. Permite avaliação antes do lançamento sem direitos violados nem custo de transcrição.

## Gatilhos para próximas integrações

1. Prioridade #1: áudio/legenda com faster-whisper e benchmark de tempo por 1 minuto.
2. Prioridade #2: PySceneDetect, comparando detecção de trechos com 10 vídeos licenciados e revisão editorial.
3. Prioridade #3: templates próprios em HTML/SVG/Remotion/GSAP (sem copiar exemplos sem verificar licença).
4. Só adicionar orquestradores pesados, armazenamento gerenciado, análise visual com IA paga ou APIs sociais depois de medir custo e confiabilidade.
