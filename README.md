# GTA-6-clips

Pipeline **independente do WildVox**, com ingestão de vídeos autorizados, escolha heurística de trecho, renderização vertical e painel web de revisão. Preparado para colaboração com outras IAs.

> **Situação:** MVP local-first. Não está conectado à Twitch, não coleta lives de terceiros automaticamente, não possui publicação automática nem está hospedado publicamente. Não anuncia cortes como publicados.

## Executar

Requer **Python 3.11+** e **FFmpeg/ffprobe** no PATH.

\`\`\`bash
python -m clipforge.web
\`\`\`

Abra http://127.0.0.1:8000. Por padrão, a aplicação verifica a pasta data/incoming a cada 30 segundos e renderiza arquivos novos com manifesto de direitos válido. Também há botão de varredura manual.

Ou use Docker:

\`\`\`bash
docker compose up --build
\`\`\`

## Inserir uma mídia autorizada

Copie o vídeo para data/incoming/exemplo.mp4 e crie data/incoming/exemplo.mp4.rights.json:

\`\`\`json
{
  "creator": "Nome do criador",
  "rights_status": "permission_granted",
  "evidence": "URL ou referência verificável da permissão",
  "source_url": "https://www.twitch.tv/...",
  "start_sec": 20,
  "duration_sec": 35
}
\`\`\`

Para vídeo próprio, use rights_status=owned. Se start_sec for omitido, uma heurística de volume de áudio escolhe um trecho: **não é IA semântica** e pode errar o momento interessante. O arquivo gerado tem 1080×1920, 30 fps, H.264/AAC, com gameplay inteiro centralizado e fundo desfocado.

O painel permite ver filas, status, prévia e aprovar ou rejeitar vídeos. **Aprovação não publica em redes sociais.** Distribuição via Metricool é uma etapa posterior, com consentimento e credenciais.

## Segurança e limites

- Direitos: não reutilizar conteúdo de streamer sem autorização documentada; o manifesto é autodeclaração, não verificação jurídica.
- Instância local: HOST=127.0.0.1 por padrão; ao abrir em rede, DASHBOARD_TOKEN obrigatório, com proxy HTTPS recomendado.
- **Nunca** enviar arquivos de mídia, banco SQLite, tokens nem provas privadas de licenças ao GitHub.
- Sem coleta automática, remoção de marcas d'água ou bypass de APIs.
- O scanner é contínuo enquanto o processo roda, não depende do navegador. Um único render por vez limita sobrecarga.

Consulte **AGENTS.md** antes de qualquer alteração. Veja docs/ARCHITECTURE.md, docs/ARSENAL.md e docs/ROADMAP.md.
