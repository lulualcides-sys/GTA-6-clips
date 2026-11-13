# Operação e solução de problemas

## Local

Instale Python 3.11+ e ffmpeg/ffprobe no PATH. Na raiz do repositório:
```bash
python -m unittest discover -s tests -v
python -m compileall -q clipforge tests tools
python -m tools.smoke
python -m clipforge.web
```
Abra http://127.0.0.1:8000. Copie mídia autorizada e sidecar para data/incoming. AUTO_SCAN=1 e AUTO_RENDER=1 por padrão. O painel consulta a API a cada 6 segundos.

## Docker

```bash
cp .env.example .env
# Troque DASHBOARD_TOKEN por uma senha forte e mantenha .env privado.
mkdir -p data
docker compose up --build
```
No Linux, se houver erro de permissão em `./data`, ajuste o proprietário do diretório para UID 10001 do container; nunca deixe mídia privada pública. Acesse somente http://127.0.0.1:8000.

## Diagnóstico

- `/api/health`: indica se HTTP está vivo, sem validar FFmpeg.
- `/api/scan`: retorna arquivos importados e manifestos rejeitados.
- `failed`: conferir campo `error`; usar Renderizar após corrigir.
- `ready`: vídeo técnico existe; ainda exige revisão humana.
- `approved`: apenas status interno, não houve publicação.
- Mesmo SHA-256 não é importado duas vezes.
- Se falhar render, confirmar `ffmpeg -version` e `ffprobe -version`.

## Incidentes

Desative `AUTO_RENDER=0`, preserve o banco e os originais, reproduza erro com mídia sintética, corrija em branch, teste, compare saída e só depois retome. Não apague histórico para mascarar problemas.
