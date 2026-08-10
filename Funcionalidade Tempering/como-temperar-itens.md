# Como Temperar Itens no Diablo IV

O sistema de **Tempering** permite adicionar um novo afixo ao item através do **Ferreiro**.

Ao temperar, você escolhe uma categoria de afixos, seleciona uma receita e tenta obter o maior valor possível daquele afixo.

> **Objetivo:** obter o afixo desejado com o **maior valor possível**, preferencialmente em **GA (Greater Affix)**.

---

# 1. Abra o Tempering

Vá até o **Blacksmith (Ferreiro)** e abra a aba:

```text
Tempering
```

Selecione o item que deseja temperar.

Com o item selecionado, o sistema permitirá escolher uma categoria de afixos.

---

# 2. Escolha uma categoria

As categorias disponíveis podem incluir:

```text
Weapons
Offensive
Defensive
Utility
Mobility
Resource
```

Escolha a categoria que contém o afixo que você deseja adicionar ao item.

Por exemplo:

```text
Defensive
```

---

# 3. Escolha a receita

Após selecionar uma categoria, será aberto o painel:

```text
TEMPERING RECIPES

DEFENSIVE (10)
```

Nesse painel serão exibidas as receitas disponíveis para aquela categoria.

Exemplo:

```text
+[1,500 - 2,500] Fire Resistance
+[1,500 - 2,500] Lightning Resistance
+[1,500 - 2,500] Cold Resistance
+[1,500 - 2,500] Poison Resistance
+[1,500 - 2,500] Shadow Resistance
+[1,500 - 2,500] Physical Resistance
+[1,000 - 1,500] Maximum Life
+[1,250 - 2,000] Armor
+[60 - 70] Resistance to All Elements
```

A lista pode possuir mais opções do que as que aparecem inicialmente.

> **Importante:** se o afixo que você procura não estiver visível, utilize o **scroll** para descer a lista e procurar por ele.

---

# 4. Selecione o afixo desejado

Encontre o afixo que deseja adicionar ao item.

Exemplo:

```text
+[1,500 - 2,500] Physical Resistance
```

Selecione essa receita.

Depois, clique em:

```text
Temper Item
```

no canto inferior da tela.

---

# 5. Pule a animação

Após clicar em **Temper Item**, o jogo exibirá uma animação mostrando o resultado do Tempering.

Essa animação pode ser ignorada clicando em:

```text
Skip
```

Assim, o resultado será exibido imediatamente.

---

# 6. Analise o resultado

O resultado pode aparecer, por exemplo, como:

```text
+1,738 Physical Resistance
[1,500 - 2,500]
```

Nesse caso, o afixo correto foi obtido, porém o valor não está no máximo.

O objetivo é continuar tentando até obter o melhor resultado possível.

---

# 7. Quando o resultado não estiver no máximo

Caso o resultado não seja o máximo desejado:

1. Clique em **Close**.
2. Clique novamente em **Temper Item**.
3. Pule a animação com **Skip**.
4. Analise o novo resultado.
5. Se ainda não estiver no máximo, repita.

### Importante

Depois que a receita já foi selecionada e o primeiro Tempering foi realizado, **não é necessário selecionar novamente o afixo na lista de receitas**.

O fluxo passa a ser simplesmente:

```text
Close
   ↓
Temper Item
   ↓
Skip
   ↓
Resultado
   ↓
Close
   ↓
Temper Item
```

Continue repetindo até obter o resultado desejado.

---

# 8. Resultado normal x GA

O valor exibido normalmente segue o intervalo definido pela receita.

Exemplo:

```text
+[1,500 - 2,500] Physical Resistance
```

Um resultado normal poderia ser:

```text
+1,738 Physical Resistance
```

Esse resultado ainda está dentro do intervalo normal.

Porém, o objetivo é obter um **Greater Affix (GA)**.

Um resultado GA pode ultrapassar o limite máximo normal do afixo.

Por exemplo:

```text
+3,125 Physical Resistance
```

Nesse caso, o valor está acima do limite normal:

```text
Normal:
1,500 → 2,500

GA:
3,125
```

> **Importante:** para a configuração desejada, sempre priorize o resultado com **GA**.

---

# 9. Fluxo completo

## Primeira tentativa

```text
Ferreiro
   ↓
Tempering
   ↓
Selecionar item
   ↓
Escolher categoria
   ↓
Escolher receita
   ↓
Temper Item
   ↓
Skip
   ↓
Verificar resultado
```

---

## Próximas tentativas

Depois da primeira tentativa, a receita já está selecionada.

Portanto:

```text
Close
   ↓
Temper Item
   ↓
Skip
   ↓
Verificar resultado
   ↓
Close
   ↓
Temper Item
   ↓
...
```

Não é necessário voltar para a lista de receitas a cada tentativa.

---

# 10. Exemplo completo

Imagine que você queira:

```text
Physical Resistance
```

Na aba **Tempering**:

### 1. Selecione:

```text
Defensive
```

### 2. Encontre:

```text
+[1,500 - 2,500] Physical Resistance
```

### 3. Clique em:

```text
Temper Item
```

### 4. Pule a animação:

```text
Skip
```

### 5. Resultado:

```text
+1,738 Physical Resistance
```

O valor não está no máximo e não é o GA desejado.

Clique:

```text
Close
```

Depois:

```text
Temper Item
```

Pule novamente a animação.

Se o resultado for:

```text
+2,412 Physical Resistance
```

ainda não é o resultado desejado.

Repita:

```text
Close
→ Temper Item
→ Skip
→ Resultado
```

até obter um resultado GA, por exemplo:

```text
+3,125 Physical Resistance
```

---

# 11. Regra de decisão

A automação deve avaliar o resultado do Tempering nesta ordem:

```text
Afixo correto?
    ↓
SIM
    ↓
É GA?
    ↓
SIM
    ↓
Resultado ideal
```

Se não for GA:

```text
Afixo correto
    ↓
Não é GA
    ↓
Close
    ↓
Temper Item
    ↓
Tentar novamente
```

---

# 12. Resumo

O processo de Tempering funciona assim:

```text
1. Abrir o Ferreiro
2. Abrir a aba Tempering
3. Selecionar o item
4. Escolher a categoria
5. Localizar a receita desejada
6. Selecionar o afixo
7. Clicar em Temper Item
8. Clicar em Skip
9. Verificar o resultado
10. Se não for o resultado desejado:
       Close
       ↓
       Temper Item
       ↓
       Skip
       ↓
       Verificar novamente
11. Repetir até conseguir o GA desejado
```

> **Objetivo final:** obter o afixo desejado em **GA**, com o maior valor possível. Depois que a receita foi selecionada pela primeira vez, as novas tentativas devem utilizar apenas **Close → Temper Item → Skip**, sem precisar selecionar novamente a receita.


# 13. Recarregando os Temper Rerolls

Cada item possui uma quantidade de:

```text
Temper Rerolls Remaining
```

Esses rerolls são consumidos a cada tentativa de Tempering.

Quando chegar a:

```text
Temper Rerolls Remaining: 0
```

não será mais possível continuar temperando o item normalmente.

Nesse momento, é necessário adicionar novos **Temper Rerolls**.

## Como adicionar Rerolls

Ao lado direito do item existe um **botão circular com um ícone de recarga**.

Clique nesse botão para adicionar novos Temper Rerolls.

A ação consome **Pergaminhos**.

### Quando houver poucos Pergaminhos

Caso a quantidade de Pergaminhos seja limitada, não é recomendado adicionar vários rerolls de uma vez.

A automação deve seguir:

```text
Rerolls = 0
      ↓
Clique no botão circular
      ↓
Adiciona 1 Temper Reroll
      ↓
Temper Item
      ↓
Rerolls = 0
      ↓
Clique novamente no botão circular
      ↓
Adiciona outro Reroll
      ↓
Temper Item
```

Ou seja, deve ser feito **um Reroll por vez**, especialmente quando a quantidade de Pergaminhos disponíveis for baixa.

---

# 14. Fluxo completo com Rerolls

O fluxo final fica:

```text
Selecionar item
      ↓
Escolher categoria
      ↓
Selecionar receita
      ↓
Temper Item
      ↓
Skip
      ↓
Verificar resultado
      ↓
É GA ideal?
   ↙       ↘
 SIM       NÃO
  ↓          ↓
 Close      Close
             ↓
       Rerolls > 0?
          ↙     ↘
        SIM      NÃO
         ↓        ↓
   Temper Item   Botão circular
         ↓        ↓
       Skip   Adicionar 1 Reroll
         ↓        ↓
      Resultado  Temper Item
                  ↓
                 Skip
                  ↓
              Resultado
```

> **Importante:** quando `Temper Rerolls Remaining` chegar a `0`, não tente clicar novamente em **Temper Item**. Primeiro é necessário adicionar um novo Reroll através do botão circular ao lado direito do item, consumindo um Pergaminho.

A regra principal da automação fica:

**Enquanto houver rerolls → `Close → Temper Item → Skip`.**

**Quando chegar a 0 → adicionar 1 reroll com o botão circular → continuar.**

Se os Pergaminhos estiverem acabando, a automação deve **evitar adicionar vários rerolls de uma vez** e consumir **um por vez**.
