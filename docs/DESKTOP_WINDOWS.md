# GTA VI Clips — aplicativo gratuito para Windows

**Versão portátil (sem instalação tradicional):** o programa abre o Mission Control como uma janela do Windows usando pywebview + Microsoft Edge WebView2. O backend Python, FFmpeg, banco SQLite, vídeos e módulos existentes executam **no próprio computador**, sem contratar Railway nem servidor.

## Atualização pelo GitHub sem reinstalação manual

O aplicativo a partir da versão **0.2.0** verifica, ao abrir e a cada três horas, a última versão estável publicada em [GitHub Releases](https://github.com/lulualcides-sys/GTA-6-clips/releases). Se uma versão maior existir, o próprio painel exibirá **Atualizar**.

Ao clicar, o aplicativo baixa o ZIP do GitHub, confere o SHA-256 informado pela API oficial, extrai apenas arquivos de caminhos seguros, executa o autoteste da nova versão e fecha a janela. Um atualizador separado substitui a pasta do programa, mantém uma cópia de segurança da instalação anterior e abre a nova versão. **Nada é instalado silenciosamente sem o clique no botão**. Caso o download ou autoteste falhe, a versão atual permanece intacta.

Os arquivos de usuário continuam em `%LOCALAPPDATA%\GTA6Clips\data` e as configurações em `%LOCALAPPDATA%\GTA6Clips\config.env`, fora da pasta de instalação. Nunca são apagados pelo atualizador. Se a troca de pasta falhar, o programa tenta restaurar a instalação anterior. O atualizador não exige hospedagem paga, mas depende de internet para verificar e baixar releases.

**Primeira atualização:** quem já tem um pacote antigo **sem** esse recurso precisará baixar manualmente a versão 0.2.0 uma única vez. Daí em diante o programa pode avisar sobre novas releases e aplicar atualizações com um clique. Se a instalação estiver numa pasta protegida por administrador, mova o aplicativo para uma pasta editável do próprio usuário.

**Segurança:** o arquivo do projeto ainda não é assinado digitalmente. SHA-256 confirma a integridade do arquivo fornecido pelo repositório oficial, mas não substitui assinatura de código, antivírus ou revisão do código. Nenhum vídeo é enviado para o GitHub.

Para desenvolvedores, atualizar `clipforge/version.py` e mesclar uma PR testada no `main` faz o workflow Windows compilar e, se passar, publicar automaticamente uma **nova GitHub Release** da versão. A mesma versão não é republicada; os arquivos da release não são sobrescritos.



1. Abra [GitHub Actions do projeto](https://github.com/lulualcides-sys/GTA-6-clips/actions/workflows/windows-app.yml).
2. Escolha a execução **Windows app - build and verify** com resultado verde. Confirme que passou o passo de autoteste do executável.
3. Em **Artifacts**, baixe **GTA6Clips-Windows-Portable**. O GitHub pode pedir que você esteja conectado para baixar um artefato.
4. Extraia o ZIP integralmente em uma pasta, por exemplo `C:\GTA6Clips`. **Não execute o `.exe` de dentro do ZIP**.
5. Execute `GTA6Clips.exe` na pasta extraída. Não são necessários Python, FFmpeg ou Docker instalados separadamente.

**Importante:** o programa gerado em CI não é assinado digitalmente. Windows Defender/SmartScreen pode solicitar verificação. Verifique a origem no repositório e o histórico da compilação; não ignore alertas de segurança sem verificar a procedência.

## Dados permanentes no próprio PC

Todos os originais, cortes, históricos, legendas e credenciais locais ficam no diretório do usuário:

`%LOCALAPPDATA%\GTA6Clips\`

- `data\incoming\` — vídeos autorizados e arquivos de permissão.
- `data\rendered\` — MP4 1080x1920 produzidos pelo FFmpeg.
- `data\clips.sqlite3` — tarefas e histórico de agentes.
- `data\captions\` — SRT privados quando um worker Whisper for instalado.
- `data\hyperframes\` — projetos editáveis HyperFrames.
- `config.env` — parâmetros da instalação local.

**Atualizar:** feche o app, substitua a pasta do programa pela versão mais recente; seus dados ficam em LocalAppData e não serão excluídos. Faça backup dessa pasta antes de mudanças grandes.

## Testar a edição

1. Clique em **Abrir vídeos para editar**.
2. Copie `minha-gravacao.mp4`, de sua propriedade ou com permissão verificável.
3. Ao lado crie `minha-gravacao.mp4.rights.json` com o seguinte exemplo para conteúdo próprio:

```json
{
  "creator": "Meu canal",
  "rights_status": "owned",
  "duration_sec": 35
}
```

4. A ingestão verifica a pasta periodicamente e enfileira o FFmpeg quando `AUTO_SCAN=1` e `AUTO_RENDER=1` (padrões).
5. Na janela, acompanhe os módulos de ingestão, direitos, curadoria, edição e revisão. Abra **Abrir clipes prontos** para ver os MP4 salvos.

**Atenção:** declarar `owned` exige que o vídeo seja realmente seu. Não use esta configuração para reclassificar vídeos de streamers sem autorização. Para terceiros use `permission_granted` e `evidence` verificável. Criar Twitch Clips não concede direito automático de republicação.

## Twitch: várias categorias agora, GTA VI exclusivamente no lançamento

A partir da versão 0.3.0, o monitor usa categorias populares da Twitch antes do lançamento e muda automaticamente para a categoria exata Grand Theft Auto VI em 19/11/2026 (00:00 São Paulo), sem precisar atualizar manualmente a seleção. O aplicativo exige `TWITCH_CLIENT_ID` e `TWITCH_CLIENT_SECRET` próprios, cadastrados no Twitch Developer Console. `TWITCH_ENABLED=1` só ativa a busca se essas credenciais estiverem configuradas.

Quem atualiza a partir de uma versão antiga deve abrir `config.env` e mudar `TWITCH_ENABLED=0` para `TWITCH_ENABLED=1`, pois o atualizador preserva configurações existentes. Consulte [TWITCH.md](TWITCH.md).

## Configurações sem servidor

Na janela clique em **Configurar Twitch e IA**. Isso abre `config.env`, sem enviar nenhuma informação à nuvem. Salve e **reinicie o programa**.

```dotenv
TWITCH_ENABLED=1
TWITCH_CLIENT_ID=
TWITCH_CLIENT_SECRET=
TWITCH_POLL_SECONDS=900
TWITCH_GTA6_LAUNCH_AT=2026-11-19T03:00:00+00:00
SMART_SCENES=0
AUTO_TRANSCRIBE=0
ENABLE_SYNTHETIC_DEMO=0
```

Para monitorar **metadados da Twitch**, cadastre sua aplicação oficial em https://dev.twitch.tv/console/apps e forneça o Client ID e o Client Secret. Altere `TWITCH_ENABLED=1`. O sistema não baixa nem republica streams automaticamente.

`ENABLE_SYNTHETIC_DEMO=1` habilita o botão opcional de gerar amostras técnicas próprias (até três por banco). É um teste real de FFmpeg, não simulação de atividade.

## Segurança

- API interna acessível só em `127.0.0.1` com **token aleatório por execução**. O navegador incorporado recebe o token apenas no fragmento da URL, removido após abrir.
- Nenhum serviço fica acessível publicamente na internet e não se exige senha de administrador para rodar a versão portátil.
- O app não publica vídeos, não coleta lives e não instala automaticamente credenciais nem serviços pagos.
- Para iniciar com o Windows será necessária opção explícita; não habilitamos autostart oculto.
- Nunca envie `config.env`, `data\` ou arquivos de autorização ao GitHub.

## Limites atuais

- **Windows 10/11 x64**. O PC precisa ter o Microsoft Edge WebView2 Runtime, normalmente presente em instalações atualizadas. Se estiver ausente, a abertura da janela pode falhar; consulte https://developer.microsoft.com/microsoft-edge/webview2/.
- FFmpeg/ffprobe estão incluídos no ZIP do executável quando o workflow de empacotamento passa.
- O binário portátil é leve no sentido de **não embutir pesos de IA**: PySceneDetect e faster-whisper continuam opcionais e não vêm prontos neste instalador. Para IA completa, será necessário um pacote adicional testado.
- HyperFrames continua exportando projetos, mas render final avançado requer CLI/Chrome/Node configurados separadamente.
- O monitoramento de Twitch só ocorre enquanto o programa e o PC estiverem ligados; acesso remoto ao painel não faz parte do pacote.

## Desenvolvimento e teste de pacote

`python -m unittest discover -s tests -v`

`python -m tools.smoke`

`python -m tools.build_windows` (Windows, com `pywebview`, `pyinstaller`, FFmpeg no PATH)

Autoteste do EXE: `GTA6Clips.exe --self-test C:\caminho\resultado.json`. O teste verifica FFmpeg, ffprobe, backend em loopback e autenticação de `/api/agents`, sem abrir a janela nem acessar a Twitch.

## Para outras IAs

Leia `AGENTS.md`, `clipforge/desktop.py`, `desktop_launcher.py` e `docs/DESKTOP_WINDOWS.md` antes de modificar o app. Preservar os contratos da API, dados em LocalAppData e as integrações do painel. Nunca alegar que a janela nativa foi testada apenas porque o autoteste sem GUI passou.
