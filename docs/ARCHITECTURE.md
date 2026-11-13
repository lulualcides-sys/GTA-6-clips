# Arquitetura v0.1

```text
Vídeo local autorizado + *.rights.json
               |
       Validação de direitos
       ffprobe + SHA-256 único
               |
         SQLite / detected
               |
     Worker único / queued
               |
      timestamp explícito
          OU heurística
        de volume de áudio
               |
     FFmpeg -> 1080x1920
       H.264 + AAC / QA
               |
          ready / failed
               |
       Painel web / review
          approve/reject
               |
       [Publicar: PENDENTE]
```

## Manifesto (obrigatório)

Arquivo `data/incoming/<nome-do-video>.rights.json` ao lado do vídeo:
- `creator`: texto com identificação do criador, obrigatório.
- `rights_status`: `owned` ou `permission_granted`; outros valores rejeitados.
- `evidence`: referência verificável exigida para material de terceiros.
- `source_url`: opcional, identifica o original.
- `start_sec`: opcional; caso ausente, análise heurística da atividade de áudio no começo do arquivo (até 15min).
- `duration_sec`: de 10 a 60s, padrão 35s.

Não confundir preenchimento do manifesto com verificação jurídica. Não ingerir sem permissão.

## Estados e API

`detected → queued → rendering → ready → approved` ou `rejected`; falhas em `failed`. Um render por vez; após reinício, trabalhos interrompidos recebem `failed` e aguardam nova ação.

| Método | Endpoint | Comportamento |
| --- | --- | --- |
| GET | /api/health | Indicador de saúde sem detalhes de dados |
| GET | /api/clips | Lista de clipes e estados |
| POST | /api/scan | Ler manifestos e opcionalmente enfileirar |
| POST | /api/clips/{id}/render | Enfileirar trabalho |
| POST | /api/clips/{id}/approve | Aprovar um vídeo pronto |
| POST | /api/clips/{id}/reject | Rejeitar vídeo pronto/aprovado |
| GET | /api/clips/{id}/video | Carregar MP4 renderizado |

As rotas de clipes exigem token Bearer se `DASHBOARD_TOKEN` for definido. Servidor recusa bind externo sem token. Para produção remota, usar HTTPS, proteção adicional, firewall e limitação de requisições.

## Limitações declaradas

Heurística de áudio não identifica significado, piadas ou melhores jogadas. Sem transcrição/legendas automáticas. Sem download da Twitch e sem publicação social. Prévia transfere o MP4 para o browser. Worker local não garante operação 24/7. Dados SQLite e arquivos precisam de backup. Interface pública ainda não implantada.
