# Nexus Clips BR — reação real obrigatória

Critério aprovado após a revisão da V9, em 13/11/2026.

**Sem webcam/facecam autêntica do streamer na gravação e sem reação verificável ao acontecimento: descartar o clipe.** A presença de voz ou volume alto sem câmera **não** satisfaz a condição. Proibido usar câmera sintética, efeito de rosto falso ou reação de uma transmissão diferente.

## Montagem

- Facecam do próprio material, em destaque na região superior (sem recortar cabeça/mãos). Pode ampliar a câmera com crop se a fonte original permitir.
- Gameplay em área legível, com zoom quando houver ação relevante, sem esconder HUD essencial.
- Contexto suficiente até chegar ao acontecimento; preservar a reação e terminar com corte seco.
- Áudio original inteligível; sem inventar legendas ou gritos. Duração ditada pela história, não por 7 segundos.
- Título curto PT-BR, logo Nexus Clips BR discreto e crédito do autor.
- Replay opcional após o payoff, nunca separado da reação. Não imprimir a palavra REPLAY.
- Para GTA VI aplicar os mesmos princípios de reação autêntica aos criadores de gameplay e RP que tiverem webcam.

## Implementação atual

`clipforge/reaction_qa.py` fornece **checagem de informações revisadas manualmente**: localização real da webcam no frame, começo do contexto, payoff e reação com timestamps na mesma gravação. Não detecta faces automaticamente; não torna a integração Twitch/editores nem a publicação automática prontas.

A V9 com perseguição, bicicleta e queda permanece **reprovada para nossa linha editorial** por não mostrar câmera e reação. Não alteramos os MP4 antigos, e o aplicativo precisa integrar o gate ao pipeline para rejeição automatizada.
