# Nexus Clips BR — preparação editorial do GTA V para GTA VI
**Pesquisa:** 13/11/2026. **Status:** catálogo de planejamento e testes integráveis; ainda não é edição automática nem vídeo publicado.

## Material oficial verificado
- Rockstar confirma **Jason e Lucia**, narrativa criminal e um trabalho que dá errado, em **Vice City/Leonida**: https://www.rockstargames.com/VI e https://www.rockstargames.com/br/newswire/article/517572321a549a/watch-the-grand-theft-auto-vi-launch-trailer
- Rockstar apresenta a ambientação de **Leonida** e os personagens **Real Dimez**, com presença de redes sociais na **história**, em: https://www.rockstargames.com/VI/only-in-leonida/vice-city
- Trailer e apresentação estendida de GTA VI: https://www.rockstargames.com/newswire/article/4k138k8okkk483/grand-theft-auto-vi-an-extended-look-now-playing
- Lançamento anunciado oficialmente para **19/11/2026, PS5 e Xbox Series X|S**, com horário de virada do radar definido para **00:00 America/Sao_Paulo**: https://www.rockstargames.com/VI

**Não confirmado nestas fontes:** que exista o mesmo GTA RP/multiplayer no lançamento, possibilidade de postar vídeos no celular do jogo, IA policial específica, física de ragdoll melhorada, interações com todos os animais, ou recursos de modificação e replay idênticos ao GTA V. Não tratá-los como mecânicas presentes. As imagens e trailers oferecem hipóteses editoriais; apenas clipes reais confirmam um acontecimento específico.

## Preparação dos vídeos: 7 arquétipos
| Tipo | Treinar agora no GTA V | Possível cenário no GTA VI | Prioridade de edição |
|---|---|---|---|
| **Perseguição** | Polícia, fuga, carros e acidentes | Corrida/fuga se ocorrer na gameplay real | Conservar perseguição inteira, vias, risco, acidente e reação |
| **Assalto** | Golpes/heists com objetivo e consequência | História criminal de Jason e Lucia | Planejamento → tentativa → imprevisto → desfecho |
| **Dupla** | Dois jogadores, parceria, discussão e traição | Relação Jason–Lucia, conforme história anunciada | Quem fala/faz o quê, decisão e reação, sem fala inventada |
| **Humor físico** | Fails, veículos, NPCs, acrobacias | Acontecimento inesperado se existir no material real | Causa → payoff → reação; replay só quando melhora |
| **Momento viral** | Cena estranha de GTA V ou RP | Ambientação social/viral de Leonida | Mostrar situação real sem fingir vídeo/post do jogo |
| **Exploração** | Lugares curiosos, encontros e detalhes | Vice City, Leonida Keys, outras regiões mostradas | Local e descoberta legíveis, zoom seletivo sem cortar revelação |
| **Diálogo RP** | Conversa engraçada de GTA RP | Cena com fala que funcione no GTA VI; não pressupor modo RP | Áudio original, PT-BR fiel quando necessário, sem replay forçado |

## Padrão visual compartilhado
- O CS V8 aprovado define **acabamento, não um layout único**. No GTA, o enquadramento varia por ação: veículo na perseguição, atores em diálogo, ambientes na exploração, facecam perto do topo quando relevante.
- Contexto → desenrolar → clímax → reação, sem duração artificial de 7–15 segundos. A história determina o tempo.
- Uma chamada curta e natural em PT-BR; no momento decisivo, títulos não devem esconder a ação.
- Créditos pequenos, somente marca Nexus Clips BR e vídeo vertical com áudio real.
- Replay opcional **sem exibir REPLAY**, apenas depois do payoff; final seco, sem card ou fade.
- Entregar revisões por **player web direto**, sem download necessário e sem marca Descript.
- Qualidade de curadoria: descartar clipes em que o humor não faz sentido sem explicação, mesmo que tenham muitas views.

## Código entregue neste PR
- `clipforge/gta6_readiness.py`: 7 cenários editoriais. `available_scenarios()` lista perfis, seus campos de enquadramento/áudio/replay e URL oficial quando há base narrativa.
- `plan_gta_clip("GTA V", "assalto", beats)` permite preparar um storyboard com tempos **fornecidos por editor**. Mesmo perfil poderá operar sobre `"GTA VI"` quando houver clipes reais.
- `tests/test_gta6_readiness.py`: cobre os 7 perfis, preservação de contexto, rejeição de jogos/tempos errados e separação de fatos oficiais de hipóteses editoriais.

Exemplo de uso, com marcações **ilustrativas** (não representam um clipe existente):
```python
from clipforge.gta6_readiness import plan_gta_clip
story = plan_gta_clip("GTA V", "assalto",
  {"setup": 5, "development": 19, "climax": 37, "reaction": 46, "end": 52})
```

**Ainda não implementado:** identificação de cena pela IA, escolha de clipes de maior potencial sem inspeção, transcrição e cortes sem revisão, render automático conforme os perfis, captura social e publicação em massa. Não afirmar funcionalidade end-to-end a partir deste planejamento.

## Roteiro de validação priorizado
1. Criar três novos clips GTA V reais: **um humor visual**, **um assalto/perseguição** e **um diálogo/dupla**. Rejeitar cenas sem causa/efeito inteligíveis.
2. Aplicar respectivos roteiros em edições com a qualidade da V8, não copiando os zooms e posições de CS.
3. Mostrar três vídeos por URLs HTTPS com player, para aprovação do usuário.
4. Congelar somente técnicas aprovadas em cada categoria, com exemplos reais, antes da troca automática do radar para GTA VI.
5. No lançamento, analisar primeiras amostras GTA VI e revisar os roteiros conforme **comportamento observado**, não rumor.
