# d4forge

Assistente de crafting para Diablo IV. Automatiza o ciclo de encantamento do
Occultist: aperta Enchant, aceita, **lê as duas opções na tela**, decide pelas
suas regras, e repete até achar o afixo que você quer.

Escopo atual: apenas encantamento.

---

## Instalação

Precisa de **Python 3.13**. O 3.14 ainda não tem wheel de `onnxruntime` nem de
`PySide6`, então não serve.

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Uso

```powershell
.venv\Scripts\python.exe run.py
```

ou duplo clique em `iniciar.bat`.

**F9** inicia e para. **F12** só para. Ambos funcionam com o jogo em foco — você
não precisa voltar na janela do app. Há uma espera configurável (4 s por padrão)
entre apertar Iniciar e o bot agir, para dar tempo de voltar ao jogo.

O caminho recomendado na primeira vez:

1. **Diagnóstico** — com o jogo aberto no Occultist, clique em *Começar a
   observar*. Confira que a tela detectada está certa e que os afixos são lidos
   corretamente. **Não pule esta etapa.**
2. **Catálogo** — o app aprende os afixos do seu jogo sozinho: quando algum
   aparece e não está cadastrado, surge uma caixa no Painel com um botão para
   adicioná-los. Sem eles no catálogo toda leitura vira "duvidosa" e o bot nunca
   aceita nada. Preencha `Roll mín/máx` se quiser usar o critério de qualidade.
3. **Alvos** — o Occultist troca um afixo por vez, então o alvo é um só: afixo +
   condição + valor.
4. **Painel** — deixe *Modo simulação* ligado e aperte F9. O app percorre o ciclo
   narrando o que faria, sem clicar. Nesse modo a tela não avança sozinha: você
   avança no jogo e ele comenta cada uma.
5. Só depois de ver o log correto, desligue a simulação.

Antes de iniciar, **escolha no jogo qual afixo trocar**.

### Parar

- **F9** ou **F12**
- botão Parar
- tirar o jogo do primeiro plano
- mexer no mouse

As duas últimas são configuráveis na aba Painel.

---

## Como funciona

O ciclo é o de [como-funciona-enchant.md](como-funciona-enchant.md):

```
Enchant -> [Accept] -> [lê as 2 opções] -> Replace Affix -> Close -> repete
```

`Accept` está entre colchetes porque **o diálogo de confirmação nem sempre
aparece** — observado no jogo, o clique em Enchant às vezes leva direto para a
tela Replace Affix. Por isso o engine não é uma sequência fixa e sim um
despachante: a cada volta ele olha em que tela o jogo *está* e escolhe a ação.

`No Change` já vem marcado por padrão na tela Replace Affix. É isso que torna
"não escolher nada" a ação segura, e é o comportamento do app sempre que ele não
tem certeza.

### Camadas

| módulo | papel |
|---|---|
| `window.py` | acha a janela do D4 e seu client rect |
| `capture.py` | captura via dxcam, com fallback para mss |
| `profile.py` | ROIs medidas em 1920x1080, escaladas para a resolução real |
| `vision/states.py` | identifica em qual das 5 telas o jogo está |
| `vision/ocr.py` | lê as linhas de texto (cache + RapidOCR) |
| `affixes.py` | catálogo, gramática da linha e correção de erro de OCR |
| `rules.py` | seu critério de aceite e a decisão final |
| `automation/` | SendInput, perfis de velocidade e travas de segurança |
| `profiling.py` | medição de tempo de cada etapa |
| `engine.py` | o despachante |

### Números medidos

| etapa | custo |
|---|---|
| captura de uma ROI (dxcam) | ~0,1 ms |
| detectar o estado da tela | ~1,0 ms |
| OCR de uma linha, em cache | ~0,3 ms |
| OCR de uma linha, primeira vez | 30–90 ms |
| 4 cliques (perfil `rápido`) | ~0,5 s |

O OCR não é o gargalo: o tempo de reação do próprio jogo domina o ciclo. A aba
**Desempenho** mede tudo isso na sua máquina e acumula entre sessões em
`data/timings.json`.

### Decisões tomadas contra medição

Coisas que pareciam boas ideias e os dados desmentiram:

- **Binarizar é melhor que tom de cinza.** O painel tem brilho ~4 e o texto
  150–217. Um limiar em 120 isola o texto e ainda apaga a marca d'água
  "PUBLIC TEST BUILD" — variantes em cinza liam o `73123` dela junto com o afixo.
- **A imagem precisa de margem branca.** Sem ela o detector corta as pontas e
  `+151 Dexterity` vira `ext`.
- **Ler a linha inteira, não em pedaços.** Separar "valor" e "nome" para cachear
  cada metade ficou mais rápido e bem pior: `+2 to Imbuement Skills` saiu como
  `to kil`.
- **Atlas de glifos não funciona nesta fonte.** As serifas se encostam e `Imbue`
  sai como um bloco único de 76 px. Ideia descartada.
- **Ordenar as caixas do detector é obrigatório.** Ele devolve em ordem
  arbitrária; juntar na ordem de chegada fazia `+4 Energy` virar `Energy +4`.
- **Varrer o painel inteiro custava 15,8 ms dos 16,2 ms** de detectar o estado.
  Subamostrar 1 pixel a cada 4 dá o mesmo resultado (0,0520 contra 0,0516) 15×
  mais rápido.
- **Esperas de tempo fixo eram chute.** Somavam 900 ms por volta. Agora o app
  compara quadros consecutivos e segue quando a animação para — ~30 ms típicos,
  e mais confiável, porque antes dava para ler durante a animação.

### O cursor faz parte da imagem

O Diablo IV desenha o próprio cursor **dentro do quadro renderizado** — não é o
cursor do Windows, e não dá para excluí-lo da captura.

Parado sobre a lista de afixos, ele acendia a ROI e a tela `enchant_locked` era
classificada como `enchant_select`, o que interrompia a sessão com "nenhum afixo
está marcado". Por isso o app **estaciona o cursor** num ponto morto da borda do
painel depois de cada clique. Dois testes garantem que esse ponto está vazio nas
cinco telas e não encosta em nenhuma ROI usada.

### Por que a correção de OCR é estrutural

A linha tem gramática rígida (`valor + unidade + nome`) e o nome vem de um
conjunto fechado. Em vez de exigir OCR perfeito, o parser testa candidatas, casa
o nome contra o catálogo por similaridade e conserta dígito trocado por letra.

Isso pega os erros silenciosos, que são os perigosos:

- `+3,0D0 Shadow Resistance` seria lido ingenuamente como valor **3,0** com nome
  `D0 Shadow Resistance`
- `1 0.0% Impairment Reduction` seria lido como valor **1** — e aqui o nome está
  certo, então conferir só o nome não pegaria o erro

O que não passa nessas checagens é marcado como duvidoso, e dúvida vira
No Change.

---

## Catálogo de afixos

**Não existe API oficial da Blizzard para dados do Diablo IV.** O Battle.net Game
Data API cobre WoW, Diablo III, Hearthstone e StarCraft II; o D4 ficou de fora —
e a API do WoW retorna dados de WoW, não serve de atalho.

O botão **Importar catálogo completo** (aba Catálogo) carrega ~870 nomes da
lista enUS do [d4lf](https://github.com/d4lfteam/d4lf), um loot filter que
também lê a tela do D4 por OCR — ou seja, os nomes vêm na grafia exata da
interface. Uma cópia vai empacotada em `d4forge/resources/`, então funciona
offline; a importação nunca sobrescreve o que você editou. Validado: cobre
20/20 dos afixos que apareceram nas sessões reais.

O que a importação **não** traz, e por quê:

- **Faixas de roll.** O [d4data](https://github.com/DiabloTools/d4data)
  datminerado até as tem, mas embutidas em fórmulas
  (`FloatRandomRangeWithIntervalUniqueAffixPityBonus(5, 45, 60)`) em arquivos
  nomeados por ID interno, sem junção viável com o nome de exibição —
  verificado: não há StringList homônimo. Faixas seguem manuais; os números
  estão em [d4builds.gg](https://d4builds.gg/database/gear-affixes/).
- **Mapa afixo → slot/classe.** Mesmo problema de junção. O catálogo tem a
  coluna **Slots** (helm, chest, gloves, pants, boots, amulet, ring, weapon,
  offhand — os espaços que o Occultist encanta) para preencher aos poucos;
  afixo sem slot aparece em todos os filtros. A aba Alvos filtra por slot.
- A **unidade** de cada afixo importado é palpite pelo nome e não corrige OCR
  até ser confirmada — trocar a unidade na tabela conta como confirmação.

O catálogo também cresce sozinho conforme o app vê afixos novos no jogo (exige
nome plausível e 2+ aparições, para não decorar lixo de OCR).

---

## Diagnóstico

Quando algo inesperado acontece, o app **salva o quadro** em `captures/`:

- `debug_sem_selecao_*.png`, `debug_orbe_nao_lido_*.png`,
  `debug_tela_desconhecida_*.png` — a tela no momento em que ele parou
- `ocr_opcao*_*.png` — o recorte exato que gerou uma leitura duvidosa

Foi assim que o problema do cursor foi encontrado. O log também mostra o texto
cru do OCR sempre que ele diverge da interpretação.

## Ferramentas

```powershell
.venv\Scripts\python.exe tools\snap.py   # F9 salva frame, F10 sai
.venv\Scripts\python.exe -m pytest tests -q
```

## Limitações conhecidas

- Calibrado em **1920x1080**. O perfil escala por proporção, mas em outra
  resolução a UI do D4 não escala exatamente igual e as ROIs podem sair do lugar.
- Os prints de referência são de um **PTR** (marca d'água "PUBLIC TEST BUILD").
  O limiar de binarização já a descarta, mas o layout de uma build de produção
  pode diferir.
- Cliente em **inglês**. O parser e o catálogo assumem os nomes em inglês.
- Exige o jogo em primeiro plano — a captura lê o monitor, não a janela.
- O ciclo completo já rodou contra o jogo ao vivo, mas em poucas sessões. Use o
  modo simulação ao mudar de item ou depois de patch do jogo.

## Aviso

Automatizar input em Diablo IV vai contra os termos de serviço da Blizzard e pode
resultar em suspensão da conta. Você assume esse risco.
