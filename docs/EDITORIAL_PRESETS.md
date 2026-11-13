# Nexus Clips BR — edição narrativa adaptativa (versão de planejamento)

A **V8 do Counter-Strike foi aprovada como referência de acabamento**, mas seu enquadramento e tempo de replay **não** devem ser copiados mecanicamente para todos os jogos.

## Regra central

**O evento manda mais que o jogo.** Um GTA RP com uma conversa engraçada precisa priorizar diálogo e reação. Um GTA VI com perseguição precisa priorizar a ação e o acidente. O mesmo vale para Fortnite, Minecraft ou LoL: identificar *o que aconteceu* vem antes de escolher zoom, título, layout ou replay.

| Estilo | Exemplo | Proteção de informações | Uso do replay |
|---|---|---|---|
| `humor_visual` | GTA V, trollagem, física inesperada | mostrar causa, erro e reação | somente se reforçar a piada |
| `dialogo` | GTA RP, conversa engraçada | falas compreensíveis, facecams e legendas PT-BR fiéis | geralmente nenhum |
| `clutch` | CS2, Fortnite, Warzone | HUD, munição, adversários e placar | lance decisivo depois da ação |
| `teamfight` | LoL, luta coordenada | equipes, barra de vida e habilidades importantes | se ajudar a entender a jogada |
| `sobrevivencia` | Minecraft, jogos de terror | objetivo, risco, ameaça e reação | para surpresa clara |
| `competicao` | Rocket League, corrida, esporte | placar, tempo restante, bola/veículo | após gol, defesa ou erro |
| `narrativo` | jogo desconhecido | contextualizar a ação sem pressupor gênero | apenas quando fizer sentido |

Os estilos são **recomendações**, não rótulos semânticos descobertos por inteligência artificial. Exemplos de jogos são sugestões iniciais; a cena permite alterar o estilo livremente.

## Regra de montagem

1. **Contexto**: o que está acontecendo e por que importa.
2. **Desenvolvimento**: tentativas, decisões, suspense ou conversa.
3. **Clímax**: o acontecimento principal, sem sobrepor texto ao elemento decisivo.
4. **Reação/consequência**: mostrar o desfecho, e terminar com corte seco.

A duração acompanha a história, **sem teto artificial de 7 ou 15 segundos**. O vídeo pode ter 20, 40, 70 ou mais segundos se o conteúdo sustentar. Remover somente silêncio/tempo morto que não contribua.

**Aspectos permanentes**: título editorial curto em PT-BR (nunca fala inventada), logo Nexus Clips BR pequeno, créditos corretos, áudio original, replay opcional **sem palavra “REPLAY”**, nenhuma marca Descript, 9:16 e player no navegador sem download obrigatório.

## Planejador já implementado

O módulo `clipforge/editorial_profiles.py` gera um *storyboard* a partir de tempos escolhidos manualmente após revisar o vídeo. Assim, o mesmo editor usa diretrizes adequadas a cada jogo sem alterar os clips antigos.

Exemplo:

```bash
python -m tools.editorial_plan --game "Rocket League" --event "competicao" --beats '{"setup":0,"development":9,"climax":29,"reaction":35,"end":42}' --replay 28 31
```

Saída: perfil, trechos de contexto/desenvolvimento/clímax/reação, replay explícito e alertas de progressão incompleta.

**O que ainda não faz**: detectar automaticamente piadas/gols/abates, editar e renderizar com base nesse storyboard, definir zoom a partir do conteúdo visual, publicar vídeos ou garantir direitos. Essas funções exigem análise semântica da mídia, renderizador por etapas e QA reais. Não confundir um perfil de edição com um vídeo final.

## Próxima validação

Produzir **três provas com eventos diferentes** (ex.: GTA RP diálogo, Minecraft sobrevivência e Fortnite clutch), cada uma com contexto, desenvolvimento e desfecho. O controle A/B deve comparar V8 como referência de acabamento, **não** copiar os cortes do CS. Só tornar presets permanentes após avaliação de cada tipo.

**Radar vigente:** até 18/11/2026 somente GTA V, incluindo GTA RP e streamers variados; a partir de 19/11/2026, 00h em São Paulo, somente GTA VI. **O tipo de cena continua sendo mais importante que o jogo**: ação, humor visual, perseguição e diálogo dentro de GTA precisam de montagens diferentes. V8 de CS é referência de acabamento, não motivo para buscar CS.
