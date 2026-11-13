# Nexus Clips BR — padrão editorial de edição (v4, 13/11/2026)

Escopo: clipes de GTA e games voltados ao público brasileiro. O nome do canal, o estilo de cortes e a marca gráfica foram definidos pelo responsável editorial; esta especificação orienta revisões. **Nenhum vídeo recebe aprovação final ou licença de republicação apenas por cumprir o preset.**

## Marca e créditos
- Nome visual: **Nexus Clips BR** (terceira opção de logo, símbolo N branco com play verde, arco azul/verde e identidade neon). Usar a arte original aprovada, não gerar marca alternativa a cada clipe.
- Marca-d'água pequena no canto superior direito, preferencialmente apenas o símbolo, alpha 0,5–0,7, sem quadro opaco.
- Não adicionar banner grande, logo enorme, cabeçalho ou rodapé cheio que esconda a gameplay.
- Crédito de origem pequeno e legível, de preferência fora da ação principal: `Gameplay: <criador> | Twitch`. Crédito não significa licença.
- Não divulgar nem publicar conteúdo de terceiro antes da etapa de direitos.

## Texto e idioma
- Em clipes visuais engraçados, usar somente **título editorial curto e engraçado em PT-BR**, com um gancho inicial e, se ajudar a piada, uma segunda frase/punchline.
- Exemplo para o clipe “Splat” (xQc, GTA V): `ERA SÓ ATRAVESSAR A RUA...` → `VIROU BONECO DE PANO KKK`.
- **Não** colocar legendas redundantes, frases promocionais ou rótulo grande `REPLAY` no vídeo.
- Em clipes cuja graça depende de fala, produzir legendas PT-BR sincronizadas e fiéis ao sentido da fala real, se houver transcrição verificável; nunca inventar diálogo ou apresentar título editorial como tradução.
- Evitar texto institucional como `Versão para aprovação` dentro do vídeo.

## Montagem
- Formato 9:16, alvo 1080 × 1920 / H.264 / AAC / `+faststart`.
- Preservar a gameplay na área visível, preferindo fundo desfocado ou recorte que não destrua ação essencial.
- Manter zoom e replay em câmera lenta quando acrescentarem humor; **sem exibir a palavra REPLAY**.
- Encerrar o último frame com **corte seco**, sem fade, animação de marca ou end card.
- Áudio original e efeitos somente onde contribuírem; não esconder a piada.
- No teste do clipe Splat: 14 segundos originais, replay de 5,35–8,35s a 0,69× no encerramento. Tempo final ~18,3s.

## Garantias de qualidade
1. Verificar origem, criador, restrições e evidências antes da publicação.
2. Verificar se a marca está legível sem distrair.
3. Inspecionar quadros antes/durante/depois do momento engraçado e o último frame para garantir ausência de fade.
4. Confirmar resolução, codec, presença de áudio e duração por `ffprobe`.
5. Apresentar ao usuário em revisão, **sem aprovar nem publicar automaticamente**.
6. Manter dados reais; nunca fabricar captura, transcrição ou métricas da Twitch.

## Aplicação no produto
Este documento define as diretrizes. Implementação automática no runtime depende de um preset de renderização e do asset da terceira marca efetivamente instalado no pacote do app; não confundir a existência deste documento com essa integração.

## Ajustes aprovados na calibração (13/11/2026)
- **Clipe 01 aprovado editorialmente:** xQc, GTA V, “Splat”, versão Nexus Clips BR v4 (~18,3s). Manter replay mudo de rótulos, título curto em PT-BR, marca-d'água pequena, crédito e corte seco.
- **Entrega aprovada:** link de página de player responsiva abrindo diretamente no navegador do celular, sem obrigar download. Hospedagem de HTML no Vercel só é suficiente com vídeo acessível por URL válida e de duração conhecida. Evitar dependência de links assinados temporários que expirem; quando inevitável, avisar validade.
- **Radar por data (decisão final do usuário):** até 18/11/2026 procurar clipes em alta de quaisquer categorias e streamers; a partir da meia-noite (São Paulo) de **19/11/2026**, buscar **exclusivamente GTA VI**, ainda de qualquer streamer. Não é para focar só em LoL antes disso. Priorizar PT-BR no ranking sem excluir outros idiomas durante o período aberto. Créditos discretos, títulos curtos, replay oportuno e corte seco.
- **Calibração seguinte:** pelo menos três estilos para comparação: humor visual, diálogo com legenda fiel e reação. Não publicar nas redes sem checar direitos e aprovação do material específico.
