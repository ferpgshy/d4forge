# Como Fazer Masterworking no Diablo IV

O **Masterworking** permite aprimorar um item várias vezes. Em determinados níveis, um dos afixos recebe um grande aumento chamado **Masterwork Affix**.

O objetivo é identificar em qual afixo o Masterwork caiu e verificar se é o atributo desejado.

---

# 1. Abra o Masterworking

Na aba de **Masterworking**, com o item selecionado, será exibido:

```text
Upgrade:
250,000 [EMOJI]
```

Clique em **Upgrade** para iniciar o processo.

---

# 2. Como funciona

Para um item que **nunca foi masterizado**, é necessário realizar os upgrades normalmente.

No **15º Upgrade**, será aplicado um **Masterwork Affix**.

Fluxo:

```text
Upgrade #1
Upgrade #2
...
Upgrade #14
Upgrade #15
↓
Masterwork Affix
```

---

# 3. Como saber se o item já foi Masterizado

Clique **uma vez** em `Upgrade` e observe o resultado.

### Se aparecer a animação

O item **já foi masterizado**.

Não é necessário fazer 15 cliques novamente. Continue realizando upgrades normalmente e aguarde a próxima animação de Masterwork.

### Se não aparecer a animação

O item ainda não chegou ao primeiro Masterwork.

Continue clicando em **Upgrade** até o 15º upgrade, quando a animação aparecer.

---

# 4. Pulando a animação

Quando a animação de Masterworking aparecer, utilize:

```text
ESC
ESC
```

Depois de pressionar **ESC duas vezes**, analise o resultado.

---

# 5. Current Masterwork Affix

Na tela de Masterworking será exibida:

```text
Current Masterwork Affix
```

Esse é o afixo que recebeu o Masterwork.

Exemplo:

```text
MASTERWORKING

ITEM
To upgrade
[RING]

Current Masterwork Affix

+80.0% Damage with Two-Handed Slashing Weapons

Reroll for a different Masterwork Affix

REQUIRED MATERIALS

Upgrade:
10,000,000
```

O valor de **Current Masterwork Affix** deve ser comparado com o afixo configurado como objetivo.

---

# 6. Exemplo

Imagine que o item tenha:

```text
+182 Strength

+375 Life on Kill
+[263 - 300]

+1,470 Armor
[981 - 1,225]

x14% Vulnerable Damage Multiplier
[8 - 14]%

+80.0% Damage with Two-Handed Slashing Weapons
```

E o objetivo seja:

```text
Strength
```

Se o resultado mostrar:

```text
Current Masterwork Affix

+182 Strength
```

o resultado está correto.

Se mostrar:

```text
+80.0% Damage with Two-Handed Slashing Weapons
```

o resultado está incorreto e deve continuar o processo.

---

# 7. Item que nunca foi Masterizado

Para um item novo:

```text
Upgrade #1
Upgrade #2
Upgrade #3
...
Upgrade #14
Upgrade #15
↓
Animação de Masterwork
↓
ESC
ESC
↓
Ler Current Masterwork Affix
```

Os primeiros 14 upgrades não precisam ser analisados individualmente.

No 15º, a animação aparecerá e o resultado deverá ser verificado.

---

# 8. Item que já foi Masterizado

Para um item que já possui Masterworking:

```text
Upgrade
↓
Apareceu animação?
↓
SIM
↓
ESC
ESC
↓
Ler Current Masterwork Affix
```

Não é necessário realizar novamente os 15 upgrades iniciais.

Depois de um Masterwork, continue clicando em **Upgrade** normalmente até aparecer a próxima animação.

---

# 9. Não verificar a cada Upgrade

O **Masterwork Affix** não acontece em todos os upgrades.

Portanto, não é necessário interromper o processo a cada clique.

A automação deve seguir:

```text
Upgrade
↓
Apareceu animação?
↓
NÃO → Upgrade novamente
↓
SIM
↓
ESC
ESC
↓
Ler Current Masterwork Affix
```

---

# 10. Verificação do resultado

O resultado deve ser comparado com o afixo desejado.

Exemplo:

```text
Objetivo:
Strength
```

Resultado:

```text
Current Masterwork Affix
+182 Strength
```

```text
CORRETO
```

Outro resultado:

```text
Current Masterwork Affix
+80.0% Damage with Two-Handed Slashing Weapons
```

```text
INCORRETO
```

Se estiver incorreto, continue o processo até o próximo Masterwork.

---

# 11. Reroll do Masterwork

Quando o Masterwork cair no afixo errado, o resultado deve ser considerado incorreto.

A tela possui:

```text
Reroll for a different Masterwork Affix
```

O objetivo é continuar o processo de Masterworking até obter o afixo configurado como alvo.

---

# 12. Fluxo completo

```text
Selecionar item
      ↓
Clicar Upgrade
      ↓
Apareceu animação?
   ↙            ↘
 SIM            NÃO
  ↓               ↓
Item já foi       Continuar
masterizado       upgrades
  ↓               ↓
ESC               Até o 15º
ESC               Upgrade
  ↓               ↓
Ler Current       Animação
Masterwork        ↓
Affix             ESC
  ↓               ESC
É o desejado?     ↓
 ↙       ↘        Ler Current
SIM      NÃO      Masterwork Affix
 ↓         ↓
Finalizar  Continuar
           ↓
         Upgrade
           ↓
      Próximo Masterwork
           ↓
        ESC + ESC
           ↓
        Verificar
```

---

# 13. Resumo

1. Selecione o item.
2. Clique em **Upgrade**.
3. Verifique se o item já foi masterizado.
4. Se for novo, faça os **15 upgrades iniciais**.
5. Quando aparecer a animação, pressione **ESC duas vezes**.
6. Leia o **Current Masterwork Affix**.
7. Compare com o afixo desejado.
8. Se estiver correto, finalize.
9. Se estiver errado, continue realizando upgrades.
10. Não interrompa upgrades que não possuem animação de Masterwork.
11. Sempre que a animação aparecer, use **ESC + ESC** e leia novamente o **Current Masterwork Affix**.
12. Continue até obter o Masterwork no afixo desejado.

> **Objetivo:** fazer o Masterwork cair no afixo configurado como alvo.
