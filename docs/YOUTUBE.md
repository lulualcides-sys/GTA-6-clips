# YouTube — radar de YouTubers grandes e cortes de canais autorizados (v0.9.0)

## O que faz

1. **Radar (oficial, gratuito):** a aba **YouTube** lista os vídeos de jogos em alta no Brasil (`chart=mostPopular`, categoria Jogos) e, depois de 19/11, também a busca `GTA 6|GTA VI` dos últimos 3 dias. Mostra só canais com pelo menos `YOUTUBE_MIN_SUBSCRIBERS` inscritos (padrão: 100 mil). A nota vem só de metadados públicos: views por hora, engajamento, idioma e duração. Ela não entende o vídeo e não garante viralização.
2. **Quem libera cortes:** a descrição do canal e as dos vídeos em alta são lidas em busca de frases como "cortes liberados". Uma restrição ("proibido", "dou strike"…) sempre vence. Isso é só uma **sugestão**: a autorização exige o seu clique em **Confirmar** ou **Ele autorizou**, com a evidência salva.
3. **Download e edição (opt-in, não oficial):** com o download ligado, a cada 30 min o app verifica os uploads recentes dos canais autorizados. Ele escolhe os melhores (sem live, entre 2 min e `YOUTUBE_MAX_MINUTES`, só GTA VI depois da virada) e baixa até `YOUTUBE_AUTO_BATCH` por rodada com o yt-dlp. Depois envia ao AutoClip, que gera até 3 cortes 9:16 para **Em revisão**. Nada é aprovado ou publicado sozinho.

## Configurar (app Windows)

1. Crie um projeto no Google Cloud, ative a **YouTube Data API v3** e crie uma **Chave de API**. A cota gratuita é de 10.000 unidades/dia: o radar gasta ~100 por atualização e fica em cache por 30 min.
2. Na aba **YouTube**, clique em **Conectar YouTube** e cole a chave. A chave é validada com uma chamada de leitura e salva só no `config.env` do seu PC.
3. Marque **Baixar vídeos dos canais autorizados** se quiser o download automático.
4. Em **Cookies do navegador**, escolha um navegador logado. O YouTube de 2026 bloqueia a maioria dos downloads anônimos com "Sign in to confirm you're not a bot". Recomendações:
   - **Firefox**. O Chrome e o Edge no Windows criptografam cookies de um jeito que o yt-dlp muitas vezes não consegue ler.
   - Uma **conta Google secundária**, nunca a do canal onde você publica.
   - Feche esse navegador durante os downloads.
5. Autorize os canais na lista e use **Baixar e editar agora**, ou espere a próxima rodada automática.

## Riscos e limites (leia)

- **Termos do YouTube:** não existe API oficial para baixar vídeos de outros canais. O download via yt-dlp pode violar os Termos do YouTube, e a conta dos cookies pode ser sinalizada. Esse risco é do proprietário. Por isso o download fica desligado por padrão.
- **Direitos:** a permissão do criador (a descrição que libera cortes, ou a autorização direta) é o que permite republicar. Sem ela, o app não baixa. Mesmo com permissão, o Content ID pode reivindicar vídeos.
- **Quebra:** o YouTube muda com frequência, e o yt-dlp e o Deno ficam congelados na versão de cada release do app. Quando os downloads começarem a falhar, atualize o app: cada release reconstrói o runtime com o yt-dlp mais novo.
- **Máquina:** vídeos longos pesam. O AutoClip transcreve o vídeo inteiro, e o tempo limite dele cresce com a duração (2x, até 3 h). O limite padrão é de 60 min por vídeo e 2 vídeos por rodada.

## Chaves do `config.env`

| Chave | Padrão | Uso |
|---|---|---|
| `YOUTUBE_API_KEY` | vazio | Chave da Data API v3 (radar e uploads) |
| `YOUTUBE_PUBLIC_DOWNLOAD` | `0` | `1` liga o download via yt-dlp dos autorizados |
| `YOUTUBE_COOKIES_BROWSER` | vazio | `firefox`, `edge`, `chrome`, `brave`… |
| `YOUTUBE_MAX_MINUTES` | `60` | Duração máxima do vídeo baixado (2–120) |
| `YOUTUBE_AUTO_BATCH` | `2` | Vídeos por rodada (1–6) |
| `YOUTUBE_AUTO_PER_CHANNEL` | `1` | Vídeos por canal por rodada |
| `YOUTUBE_WINDOW_DAYS` | `3` | Só vídeos publicados nesse intervalo |
| `YOUTUBE_MIN_SUBSCRIBERS` | `100000` | Filtro de "YouTuber grande" no radar |
| `YOUTUBE_POLL_SECONDS` | `1800` | Intervalo da rodada automática |
| `YOUTUBE_SEARCH_QUERY` | vazio | Troca a busca (padrão `GTA 6\|GTA VI` após a virada) |
| `YOUTUBE_AUTO_GTA6_ONLY` | `1` | Segue o calendário; `force` sempre GTA VI; `0` qualquer jogo |
| `AUTOCLIP_TIMEOUT_SECONDS` | vazio | Força o tempo limite do AutoClip |

## O que foi testado

- **Testes locais (`tests/test_youtube.py`):**
  - parse de duração ISO e nota;
  - filtro de live, duração e jogo;
  - autorização com evidência;
  - radar com canais grandes, política com restrição vencendo e cache;
  - chave que nunca aparece em erro;
  - download só de autorizado, `channel_id` divergente descartado, mensagem da checagem anti-robô e duplicado bloqueado;
  - entrada automática pegando só o vídeo elegível;
  - rotas HTTP privadas;
  - timeout proporcional;
  - varredura que não relê arquivos inalterados.
- **Build Windows:** baixa o Deno fixado, confere o SHA-256, roda `deno --version` e importa `yt_dlp_ejs` no runtime empacotado.
- **Não testado:** download real do YouTube e chamada real da Data API. A rede desta sessão de desenvolvimento não alcança o YouTube. O primeiro teste real será no PC do usuário.
