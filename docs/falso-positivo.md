# Reportar o falso positivo de antivírus

O executável do d4forge é acusado por 4 de 71 motores no VirusTotal, **todos
heurísticos ou de machine learning** — nenhum de assinatura. Este documento tem
o que enviar a cada fornecedor e o texto pronto.

Reportar é gratuito e costuma resolver em poucos dias. O da **Microsoft é o que
importa de verdade**: é o Defender que bloqueia o usuário final; os outros três
raramente aparecem numa máquina doméstica.

## Dados do arquivo

| campo | valor |
|---|---|
| arquivo | `d4forge.exe` |
| SHA-256 | `603a66c3eebd4e783a2ec41f490dc2ef8ae671c69de7de001abdd9e6dd16209a` |
| tamanho | 7,01 MB |
| VirusTotal | https://www.virustotal.com/gui/file/dff736ae7f4e783990bf781401047c2764a1dc64fe967ffe9c5cf470fa45328f |
| código-fonte | https://github.com/ferpgshy/d4forge |
| licença | GPL-3.0 |

> O SHA-256 muda a cada build. Confira o do arquivo que você for enviar:
> ```powershell
> (Get-FileHash dist\d4forge\d4forge.exe -Algorithm SHA256).Hash.ToLower()
> ```

## Onde reportar

| fornecedor | detecção | onde |
|---|---|---|
| **Microsoft** (prioridade) | `Trojan:Win32/Wacatac.B!ml` | https://www.microsoft.com/en-us/wdsi/filesubmission — escolha *Home customer*, marque **"I believe this file is incorrectly detected"** |
| SentinelOne | `Static AI - Suspicious PE` | https://www.sentinelone.com/report-false-positive/ |
| SecureAge | `Malicious` | falsepositive@secureage.com |
| Arctic Wolf | `Unsafe` | https://arcticwolf.com/contact/ (não há portal público de FP) |

Anexe o `.exe` — não o `.zip`. Vários portais rejeitam arquivos comprimidos.

## Texto para enviar

> This file is a false positive.
>
> d4forge is an open-source enchanting assistant for the game Diablo IV,
> released under GPL-3.0. The full source code is public at
> https://github.com/ferpgshy/d4forge and the binary is built from it with
> PyInstaller (onedir, no UPX compression).
>
> The detection appears to be a generic heuristic on PyInstaller-packed
> executables. Only 4 of 71 engines flag it, and all four are machine-learning
> or heuristic classifiers with no named malware family; no signature-based
> engine detects anything.
>
> The application does use APIs that are common in automation software and can
> resemble malicious behaviour: it sends synthetic mouse input (SendInput),
> captures the screen (DXGI Desktop Duplication), enumerates windows to locate
> the game, and raises its own process priority. All of these are the documented
> purpose of the tool: it reads the game's enchanting screen with OCR and clicks
> the buttons for the user. It does not perform any network communication,
> persistence, privilege escalation, code injection, or file encryption.
>
> Build details:
>   PyInstaller onedir (--noupx), Python 3.13, PySide6 + onnxruntime
>   SHA-256: 603a66c3eebd4e783a2ec41f490dc2ef8ae671c69de7de001abdd9e6dd16209a
>
> Please review and whitelist. Thank you.

## O que NÃO adianta tentar

- **Ofuscar ou empacotar diferente.** Piora: qualquer packer aumenta a suspeita.
  Por isso o build passa `--noupx` explicitamente.
- **`--onefile`.** É bem mais flagado que o `--onedir` que usamos, porque
  extrai-se sozinho num diretório temporário na execução — comportamento de
  dropper.
- **Remover as chamadas que disparam a heurística.** São o programa. Sem
  `SendInput` e sem captura de tela não sobra aplicativo.

A única solução definitiva é **assinar o binário** com um certificado de code
signing (OV ~US$ 200–400/ano, EV ~US$ 300–600/ano com reputação imediata no
SmartScreen). Decisão adiada enquanto o projeto for gratuito.
