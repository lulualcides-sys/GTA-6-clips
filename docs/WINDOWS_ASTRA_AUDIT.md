# Auditoria Windows — Operação Astra

Inspeção em 14/11/2026, base `364a04dffed42f861ad9d8626fe258550ae8a0cb`.

## Evidência existente consultada no GitHub

- [Build Windows da base](https://github.com/lulualcides-sys/GTA-6-clips/actions/runs/43502988685): concluído com sucesso em 13/11/2026. Job `132153293130` passou testes Python/API, render sintético FFmpeg, compilação PyInstaller, autoteste do executável congelado e helper.
- [Artefato dessa execução](https://github.com/lulualcides-sys/GTA-6-clips/actions/runs/43502988685/artifacts/14074272996): `GTA6Clips-Windows-Portable`, não expirado na consulta; contém a versão anterior a estas alterações.
- [Release estável v0.3.0](https://github.com/lulualcides-sys/GTA-6-clips/releases/tag/v0.3.0): publicada em 13/11/2026 a partir de `574f8bd4cdfb6710c387c2a6e82bbcaeadfdc01b`, portanto não representa o HEAD desta entrega. ZIP de 102719750 bytes; digest informado pela API `08bb9fb1f99ba01fdfab0855483b5283b50877567bdc6d61d86cdba7d1520dbf`.

## Correções implementadas

1. Atualizador valida todos os nomes do ZIP antes de escrever arquivos. Rejeita ADS NTFS (`arquivo:stream`), dispositivos reservados (`NUL`, `CON`, `COM1` etc.), caracteres Windows proibidos, espaços/pontos finais e duplicações sem distinguir caixa.
2. Bloqueia instalação dentro **ou acima** da pasta persistente. Antes, instalar num ancestral de LocalAppData poderia mover dados junto com o programa durante atualização.
3. Declara assinaturas Win32 de `OpenProcess`, `WaitForSingleObject` e `CloseHandle` com HANDLE do tamanho de ponteiro. Distingue PID encerrado de erro ao abrir processo, impedindo substituição quando não se pode confirmar encerramento.
4. O autoteste do helper agora verifica caminhos com diretórios reais temporários; em Windows também abre HANDLE do processo atual e confirma timeout. Antes apenas imprimia sucesso.
5. Desktop passa a carregar os controles de categorias, streamers, modo e janela temporal Twitch da configuração privada.
6. Workflow existente continua compilando em PRs e `workflow_dispatch`; preserva relatório JSON do EXE, rejeita arquivos privados conhecidos no pacote e entrega SHA-256 junto ao ZIP. Não houve aumento de versão nem sobrescrita de release.

## Validação local executada

```bash
python -m unittest discover -s tests -p test_updater.py -v
python -m unittest discover -s tests -p test_desktop.py -v
python desktop_update_helper.py --self-test
python -m compileall -q clipforge/desktop.py clipforge/updater.py desktop_update_helper.py
```

Resultado: 13 testes de atualização e 10 testes desktop passaram em Linux; autoteste do helper e compilação Python passaram. Os testes de arquivo usam ZIPs e diretórios reais. Testes desktop acessam HTTP loopback real, autenticado; neste ambiente exigiram execução com permissão de rede local. O contrato de HANDLE é verificado com substituição da biblioteca Windows em Linux; a chamada nativa só pode ser validada pelo runner Windows.

## Compilar e verificar a nova entrega

Em Windows x64, Python 3.12 e FFmpeg/FFprobe no PATH:

```powershell
python -m pip install "pyinstaller>=6.12,<7" "pywebview>=5.4,<7"
python -m unittest discover -s tests -v
python -m tools.smoke
python -m tools.build_windows
$env:GTA6_SELFTEST_PATH = "$env:TEMP\gta6-desktop-selftest.json"
$p = Start-Process ./dist/GTA6Clips/GTA6Clips.exe -ArgumentList '--self-test' -PassThru -Wait
if ($p.ExitCode -ne 0) { throw 'Autoteste do EXE falhou' }
Get-Content $env:GTA6_SELFTEST_PATH
./dist/GTA6Clips/GTA6ClipsUpdater.exe --self-test
```

O workflow [Windows app — build](../.github/workflows/windows-app.yml) executa essas verificações e só disponibiliza ZIP após sucesso. A execução da nova revisão deve ser identificada pelo SHA do PR; sucesso do build antigo não valida alterações novas. Aprovação do autoteste sem GUI não comprova abertura da janela WebView2 nem instalação no PC do usuário. A validação interativa Windows e atualização/rollback em uma instalação real continuam necessárias.
