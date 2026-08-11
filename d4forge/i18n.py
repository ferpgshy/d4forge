"""Textos da interface em português e inglês.

Um dicionário por idioma, chaves iguais nos dois. `t()` cai no português se uma
chave faltar em inglês — texto na língua errada incomoda menos que uma tela com
buraco.
"""

from __future__ import annotations

DEFAULT = "pt-BR"

LANGUAGES: dict[str, str] = {
    "pt-BR": "Português (BR)",
    "en": "English",
}

# Rotulo curto para o botao do cabecalho: com o nome inteiro, o botao mudava de
# largura ao trocar de idioma e empurrava os botoes de janela para o lado.
LANGUAGE_SHORT: dict[str, str] = {
    "pt-BR": "PT",
    "en": "EN",
}

STRINGS: dict[str, dict[str, str]] = {
    "pt-BR": {
        # -- janela e cabeçalho
        "app.title": "d4forge",
        "app.subtitle": "Encantamento e Tempering — Diablo IV",
        "app.window": "d4forge",
        # -- abas
        "tab.enchant": "Enchant",
        "tab.catalog": "Catálogo",
        # -- painel
        "panel.idle": "Parado",
        "panel.running": "Rodando",
        "panel.stopping": "Parando",
        "panel.found": "Achou!",
        "panel.hint": "Abra o Occultist, escolha o afixo a trocar e aperte F9.",
        "panel.hotkey_hint": "F9 e F12 funcionam com o jogo em foco.",
        "panel.start": "Iniciar",
        "panel.stop": "Parar",
        "panel.limits": "Limites",
        "panel.max_attempts": "Tentativas",
        "panel.max_minutes": "Minutos",
        "panel.no_limit": "sem limite",
        "panel.start_delay": "Espera ao iniciar",
        "panel.start_delay_tip": (
            "Só é usada quando o Windows recusa o foco automático. Com o foco "
            "confirmado, o ciclo começa na hora."
        ),
        "panel.safety": "Segurança",
        "panel.abort_focus": "parar se o jogo sair do foco",
        "panel.abort_mouse": "parar se eu mexer no mouse",
        "panel.focus_game": "focar o jogo ao iniciar",
        "panel.focus_game_tip": (
            "Ao apertar Iniciar ou F9, traz o Diablo IV para frente sozinho. "
            "Com isso a espera abaixo deixa de ser necessária."
        ),
        "panel.mouse_speed": "Velocidade do mouse",
        "panel.mouse_speed_tip": (
            "Instantâneo vai direto ao alvo. Os outros imitam movimento humano "
            "e custam até 0,8 s por rodada."
        ),
        "panel.attempts_done": "{count} tentativa(s) em {seconds:.0f}s",
        # -- alvo
        "target.box": "Alvo — parar quando aparecer",
        "target.slot": "Peça",
        "target.slot_all": "Todas",
        "target.slot_tip": "Filtra os afixos pela peça que você vai encantar.",
        "target.affix": "Afixo",
        "target.search_placeholder": "digite parte do nome — resist, dodge, life…",
        "target.condition": "Condição",
        "target.value": "Valor",
        "target.min_roll": "Roll mínimo",
        "target.min_roll_suffix": " % do máximo",
        "target.min_roll_ignore": "ignorar",
        "target.min_roll_tip": "Precisa de mín/máx preenchidos no Catálogo.",
        "target.climb": "Subir aos poucos: pega o afixo com qualquer valor e só troca por valores maiores",
        "target.climb_tip": (
            "Enquanto a peça não tem o afixo, aceita qualquer valor. Depois só "
            "aceita valor maior, até a meta."
        ),
        "target.save": "Salvar alvo",
        "target.saved": "Alvo: {rule}",
        "target.none": "Nenhum alvo definido",
        "target.no_range": "faixa não cadastrada",
        "target.range": "faixa {vmin:g} a {vmax:g}",
        "target.off_catalog": "fora do catálogo",
        "target.unit_flat": "pontos",
        "target.unit_percent": "%",
        "target.unit_rank": "níveis",
        # -- catálogo
        "catalog.hint": (
            "Preencha mín/máx para usar o critério de roll. Slots separados por "
            "vírgula; vazio vale para todas as peças."
        ),
        "catalog.affix": "Afixo",
        "catalog.unit": "Unidade",
        "catalog.min": "Roll mín",
        "catalog.max": "Roll máx",
        "catalog.slots": "Peças",
        "catalog.add": "Adicionar",
        "catalog.remove": "Remover",
        "catalog.save": "Salvar catálogo",
        "catalog.saved": "Catálogo salvo — {count} afixos",
        "catalog.new_affix": "Novo afixo",
        "catalog.count": "{count} afixos",
        "catalog.unknown_slot": "Peça desconhecida ignorada: {slot}",
        # -- afixos novos
        "unknown.box": "Afixos vistos que não estão no catálogo",
        "unknown.add": "Adicionar",
        "unknown.added": "{count} afixo(s) adicionado(s) — revise unidade e faixa no Catálogo",
        # -- mensagens
        "msg.no_target": "Escolha o afixo alvo no Enchant antes de iniciar.",
        "msg.no_target_title": "Sem alvo",
        "msg.monitor_off": "Observador desligado para não disputar CPU.",
        "msg.purged": "Removidos do catálogo por serem erro de leitura: {names}",
        "msg.ocr_ready": "Leitor pronto ({ms:.0f} ms)",
        "msg.catalog_loaded": "Catálogo com {count} afixos",
        # -- mensagens do ciclo (aparecem no Registro)
        "eng.window": "janela {w}x{h} em ({x},{y}) — escala {scale:.2f}x",
        "eng.widescreen": (
            "tela {w}x{h} não é 16:9. As regiões foram posicionadas pelo modelo "
            "(painel à esquerda, diálogo centrado), não por medição nesta "
            "proporção. Confira a primeira rodada antes de deixar rodando."
        ),
        "eng.limits": "limites: {limits}",
        "eng.rules": "regras: {count} ativa(s)",
        "eng.priority": "prioridade do processo elevada",
        "eng.focusing": "trazendo o Diablo IV para frente",
        "eng.focus_failed": "não consegui focar o jogo; troque com Alt+Tab",
        "eng.countdown": "começando em {seconds:.0f}s… deixe o jogo em foco",
        "eng.screen": "tela: {state}",
        "eng.click": "clique em {label} ({x},{y})",
        "eng.click_sim": "[simulado] clicaria em {label}",
        "eng.click_retry": "a tela não mudou depois de {label}; clicando de novo",
        "eng.sim_manual": "[simulado] a tela não muda sozinha — avance no jogo",
        "eng.frame_saved": "quadro salvo em captures/{name}",
        "eng.captures_cleared": "captures/ esvaziada ({count} arquivo(s) da sessão anterior)",
        "eng.current": "atual: {affix}",
        "eng.option": "opção {index}: {affix}",
        "eng.option_doubt": "opção {index}: {affix}  (duvidoso)",
        "eng.keeping": "mantendo: {reason}",
        "eng.option_confirmed": "opção {index} confirmada na tela",
        "eng.option_unconfirmed": "marquei a opção {index} mas a tela não confirmou; abortando",
        "eng.orb_samples": "orbe lido nas amostras: {samples}",
        "eng.orb_unread": "não identifiquei o orbe marcado; seguindo assim mesmo",
        "eng.attempt": "#{index}: {options}  →  {reason}",
        "eng.found": "afixo encontrado em {count} tentativa(s): {reason}",
        "eng.already_ok": "o item já tem {affix}, que atende '{rule}'",
        "eng.error": "erro inesperado: {error}",
        # -- motivos de parada
        "stop.cancelled": "cancelado pelo usuário",
        "stop.no_window": "janela do Diablo IV não encontrada",
        "stop.capture_failed": "captura de tela falhou",
        "stop.not_foreground": (
            "o Diablo IV não está em primeiro plano. Volte ao jogo com Alt+Tab e "
            "aperte F9, ou aumente a espera ao iniciar."
        ),
        "stop.unknown_screen": (
            "não reconheço a tela atual. Abra o Occultist na aba de encantamento."
        ),
        "stop.screen_stuck": (
            "depois de {what}, a tela continuou em '{state}' por {seconds:g}s. "
            "O clique pode ter errado o alvo."
        ),
        "stop.click_lost": (
            "cliquei em {label} {attempts}x e a tela continuou em '{state}'. "
            "Confira a calibração ou se o jogo travou."
        ),
        "stop.no_selection": (
            "nenhum afixo está marcado. Escolha no jogo qual afixo trocar antes "
            "de iniciar."
        ),
        "stop.unconfirmed": "não consegui confirmar a opção marcada",
        "stop.kill_key": "tecla de parada pressionada",
        "stop.max_attempts": "limite de {count} tentativas atingido",
        "stop.max_gold": "limite de ouro atingido",
        "stop.max_time": "limite de tempo atingido ({minutes:g} min)",
        "stop.window_gone": "janela do Diablo IV sumiu",
        "stop.lost_focus": "o jogo saiu do primeiro plano",
        "stop.mouse_moved": "mouse em movimento — parada de segurança",
        # -- decisões (aparecem na tabela de tentativas)
        "decision.no_rules": "nenhuma regra ativa",
        "decision.no_match": "nenhuma opção serve",
        "decision.doubtful": "leitura duvidosa em {count} opção(ões)",
        "decision.goal": "opção {index} atende '{rule}'",
        "decision.climb_first": "opção {index} — troca '{held}' pelo alvo",
        "decision.climb_up": "opção {index} — sobe de {current:g} para {value:g}",
        # -- painel de progresso
        "temper.goal": "meta: {goal}",
        "temper.goal_ga": "Greater Affix",
        "temper.goal_fraction": "{pct:.0f}% do intervalo",
        "temper.goal_value": "valor >= {value:g}",
        "temper.goal_any": "qualquer resultado",
        "temper.attempt": "#{index}: {affix}  →  {reason}",
        "temper.got_ga": "Greater Affix: {value:g}",
        "temper.got_value": "{value:g} atende o valor pedido",
        "temper.got_fraction": "{value:g} — {pct:.0f}% do intervalo",
        "temper.got_any": "{value:g}",
        "temper.keep_rolling": "{affix} — continua",
        "temper.other_affix": "não é o afixo pedido ('{want}')",
        "temper.unreadable": "leitura duvidosa",
        "temper.recharged": "recarreguei os rerolls ({count}x)",
        "temper.unknown_screen": "não reconheço a tela. Abra o Ferreiro na aba Tempering.",
        "temper.recipes_open": (
            "a lista de receitas está aberta. Escolha a receita e faça o "
            "primeiro Temper na mão; depois disso eu repito o ciclo."
        ),
        "temper.no_recipe": (
            "nenhuma receita escolhida neste item. Escolha a categoria e a "
            "receita no jogo antes de iniciar."
        ),
        "temper.out_of_rerolls": (
            "os Temper Rerolls acabaram. Recarregar consome Pergaminhos — ligue "
            "a recarga automática se quiser que eu faça isso."
        ),
        "temper.no_scrolls": (
            "os Temper Rerolls acabaram e não dá para recarregar: ou o item "
            "está no limite, ou os Pergaminhos acabaram."
        ),
        "temper.recharge_limit": "cheguei ao teto de {count} recarga(s) da sessão",
        "temper.recharge_runaway": (
            "cliquei em recarregar {count}x e o item não encheu. Parei para não "
            "continuar gastando Pergaminhos: confira se o botão de recarga está "
            "no lugar certo na tela."
        ),
        "temper.unreadable_stop": (
            "não consegui ler o resultado ({raw!r}) e não vou rolar por cima "
            "dele. Confira o item no jogo."
        ),
        "tab.temper": "Tempering",
        "temper.col_affix": "Afixo sorteado",
        "temper.col_done": "parou aqui",
        "temper.col_ga": "GA",
        "temper.col_rolled": "rolou",
        "temper.hint": (
            "Abra o Ferreiro na aba Tempering, escolha a categoria e a receita, "
            "e faça o primeiro Temper na mão. Depois disso aperte F10."
        ),
        "temper.goal_box": "Parar quando",
        "temper.mode_ga": "sair um Greater Affix",
        "temper.mode_ga_tip": (
            "No GA o jogo mostra só o valor, sem o intervalo entre colchetes. "
            "É por isso que dá para reconhecê-lo sem cadastrar faixa nenhuma."
        ),
        "temper.mode_fraction": "o roll chegar a",
        "temper.mode_fraction_suffix": "% do intervalo",
        "temper.mode_value": "o valor chegar a",
        "temper.affix_filter": "e o afixo contiver",
        "temper.affix_filter_ph": "deixe vazio para aceitar qualquer afixo",
        "temper.affix_filter_tip": (
            "Algumas receitas sorteiam entre vários afixos. Sem isto, o ciclo "
            "pararia num GA do afixo errado."
        ),
        "temper.rerolls_box": "Quando os Temper Rerolls acabarem",
        "temper.recharge_stop": "parar e me avisar",
        "temper.recharge_one": "recarregar 1 por vez",
        "temper.recharge_full": "encher até o máximo do item",
        "temper.recharge_cap": "no máximo",
        "temper.recharge_no_cap": "sem limite",
        "temper.recharge_cap_suffix": " recarga(s) nesta sessão",
        "temper.recharge_warn": (
            "Recarregar consome Pergaminhos. Cada item tem seu próprio limite "
            "de Temper Rerolls, e o botão circular fica cinza ao chegar nele — "
            "ou quando os Pergaminhos acabam."
        ),
        "temper.start": "Iniciar Tempering",
        "temper.hotkey_hint": "F10 inicia e para; F12 só para.",
        "temper.done": "{count} tentativa(s) em {seconds:.0f}s",
        "temper.idle": "Pronto. Abra o Ferreiro no Tempering e aperte F10.",
        "temper.running": "Rodando…",
        "progress.title": "Progresso",
        "progress.attempts": "Tentativas",
        "progress.elapsed": "Tempo",
        "progress.rate": "Ritmo",
        "progress.current": "Afixo atual",
        "progress.col_n": "#",
        "progress.col_opt1": "Opção 1",
        "progress.col_opt2": "Opção 2",
        "progress.col_result": "Resultado",
        "progress.kept": "manteve",
        "progress.took": "trocou",
        "progress.none": "—",
        "progress.details": "Detalhes técnicos",
        "progress.empty": "As tentativas aparecem aqui assim que o ciclo começa.",
        "progress.took_n": "pegou a opção {index}",
        "speed.humano": "humano",
        "speed.rápido": "rápido",
        "speed.instantâneo": "instantâneo",
        "progress.goal": "alvo atingido",
        "progress.rate_unit": "{seconds:.1f} s",
    },
    "en": {
        "app.title": "d4forge",
        "app.subtitle": "Enchanting & Tempering — Diablo IV",
        "app.window": "d4forge",
        "tab.enchant": "Enchant",
        "tab.catalog": "Catalog",
        "panel.idle": "Idle",
        "panel.running": "Running",
        "panel.stopping": "Stopping",
        "panel.found": "Found it!",
        "panel.hint": "Open the Occultist, pick the affix to reroll, then press F9.",
        "panel.hotkey_hint": "F9 and F12 work while the game has focus.",
        "panel.start": "Start",
        "panel.stop": "Stop",
        "panel.limits": "Limits",
        "panel.max_attempts": "Attempts",
        "panel.max_minutes": "Minutes",
        "panel.no_limit": "no limit",
        "panel.start_delay": "Delay on start",
        "panel.start_delay_tip": (
            "Only used when Windows refuses the automatic focus. With focus "
            "confirmed, the cycle starts right away."
        ),
        "panel.safety": "Safety",
        "panel.abort_focus": "stop if the game loses focus",
        "panel.abort_mouse": "stop if I move the mouse",
        "panel.focus_game": "focus the game on start",
        "panel.focus_game_tip": (
            "Pressing Start or F9 brings Diablo IV to the front by itself. "
            "That makes the delay below unnecessary."
        ),
        "panel.mouse_speed": "Mouse speed",
        "panel.mouse_speed_tip": (
            "Instant jumps straight to the target. The others mimic human "
            "movement and cost up to 0.8 s per round."
        ),
        "panel.attempts_done": "{count} attempt(s) in {seconds:.0f}s",
        "target.box": "Target — stop when this shows up",
        "target.slot": "Slot",
        "target.slot_all": "All",
        "target.slot_tip": "Filters affixes by the slot you are enchanting.",
        "target.affix": "Affix",
        "target.search_placeholder": "type part of the name — resist, dodge, life…",
        "target.condition": "Condition",
        "target.value": "Value",
        "target.min_roll": "Minimum roll",
        "target.min_roll_suffix": " % of max",
        "target.min_roll_ignore": "ignore",
        "target.min_roll_tip": "Needs min/max filled in the Catalog.",
        "target.climb": "Climb: take the affix at any value, then only swap for higher ones",
        "target.climb_tip": (
            "While the item lacks the affix, any value is taken. After that, "
            "only a higher value is accepted, up to the goal."
        ),
        "target.save": "Save target",
        "target.saved": "Target: {rule}",
        "target.none": "No target set",
        "target.no_range": "range not set",
        "target.range": "range {vmin:g} to {vmax:g}",
        "target.off_catalog": "not in catalog",
        "target.unit_flat": "points",
        "target.unit_percent": "%",
        "target.unit_rank": "ranks",
        "catalog.hint": (
            "Fill min/max to use the roll criterion. Slots separated by commas; "
            "empty means every slot."
        ),
        "catalog.affix": "Affix",
        "catalog.unit": "Unit",
        "catalog.min": "Min roll",
        "catalog.max": "Max roll",
        "catalog.slots": "Slots",
        "catalog.add": "Add",
        "catalog.remove": "Remove",
        "catalog.save": "Save catalog",
        "catalog.saved": "Catalog saved — {count} affixes",
        "catalog.new_affix": "New affix",
        "catalog.count": "{count} affixes",
        "catalog.unknown_slot": "Unknown slot ignored: {slot}",
        "unknown.box": "Affixes seen that are not in the catalog",
        "unknown.add": "Add",
        "unknown.added": "{count} affix(es) added — review unit and range in the Catalog",
        "msg.no_target": "Set a target in the Target tab before starting.",
        "msg.no_target_title": "No target",
        "msg.monitor_off": "Watcher turned off to free up CPU.",
        "msg.purged": "Removed from the catalog as misreads: {names}",
        "msg.ocr_ready": "Reader ready ({ms:.0f} ms)",
        "msg.catalog_loaded": "Catalog with {count} affixes",
        "eng.window": "window {w}x{h} at ({x},{y}) — scale {scale:.2f}x",
        "eng.widescreen": (
            "screen {w}x{h} is not 16:9. Regions were placed by model (panel on "
            "the left, dialog centered), not measured at this aspect ratio. "
            "Watch the first round before leaving it running."
        ),
        "eng.limits": "limits: {limits}",
        "eng.rules": "rules: {count} active",
        "eng.priority": "process priority raised",
        "eng.focusing": "bringing Diablo IV to the front",
        "eng.focus_failed": "could not focus the game; switch with Alt+Tab",
        "eng.countdown": "starting in {seconds:.0f}s… keep the game focused",
        "eng.screen": "screen: {state}",
        "eng.click": "clicked {label} ({x},{y})",
        "eng.click_sim": "[simulated] would click {label}",
        "eng.click_retry": "screen did not change after {label}; clicking again",
        "eng.sim_manual": "[simulated] the screen will not advance on its own",
        "eng.frame_saved": "frame saved to captures/{name}",
        "eng.captures_cleared": "captures/ emptied ({count} file(s) from the last session)",
        "eng.current": "current: {affix}",
        "eng.option": "option {index}: {affix}",
        "eng.option_doubt": "option {index}: {affix}  (doubtful)",
        "eng.keeping": "keeping: {reason}",
        "eng.option_confirmed": "option {index} confirmed on screen",
        "eng.option_unconfirmed": "picked option {index} but the screen did not confirm; aborting",
        "eng.orb_samples": "orb read across samples: {samples}",
        "eng.orb_unread": "could not identify the selected orb; carrying on",
        "eng.attempt": "#{index}: {options}  →  {reason}",
        "eng.found": "affix found in {count} attempt(s): {reason}",
        "eng.already_ok": "the item already has {affix}, which satisfies '{rule}'",
        "eng.error": "unexpected error: {error}",
        "stop.cancelled": "cancelled by the user",
        "stop.no_window": "Diablo IV window not found",
        "stop.capture_failed": "screen capture failed",
        "stop.not_foreground": (
            "Diablo IV is not in the foreground. Switch back with Alt+Tab and "
            "press F9, or raise the start delay."
        ),
        "stop.unknown_screen": (
            "I do not recognize this screen. Open the Occultist on the enchant tab."
        ),
        "stop.screen_stuck": (
            "after {what}, the screen stayed on '{state}' for {seconds:g}s. "
            "The click may have missed its target."
        ),
        "stop.click_lost": (
            "clicked {label} {attempts}x and the screen stayed on '{state}'. "
            "Check the calibration or whether the game froze."
        ),
        "stop.no_selection": (
            "no affix is selected. Pick the affix to reroll in game before starting."
        ),
        "stop.unconfirmed": "could not confirm the selected option",
        "stop.kill_key": "stop key pressed",
        "stop.max_attempts": "reached the limit of {count} attempts",
        "stop.max_gold": "gold limit reached",
        "stop.max_time": "time limit reached ({minutes:g} min)",
        "stop.window_gone": "the Diablo IV window disappeared",
        "stop.lost_focus": "the game lost focus",
        "stop.mouse_moved": "mouse moving — safety stop",
        "decision.no_rules": "no active rule",
        "decision.no_match": "no option qualifies",
        "decision.doubtful": "doubtful reading on {count} option(s)",
        "decision.goal": "option {index} satisfies '{rule}'",
        "decision.climb_first": "option {index} — swaps '{held}' for the target",
        "decision.climb_up": "option {index} — climbs from {current:g} to {value:g}",
        "temper.goal": "goal: {goal}",
        "temper.goal_ga": "Greater Affix",
        "temper.goal_fraction": "{pct:.0f}% of the range",
        "temper.goal_value": "value >= {value:g}",
        "temper.goal_any": "any result",
        "temper.attempt": "#{index}: {affix}  →  {reason}",
        "temper.got_ga": "Greater Affix: {value:g}",
        "temper.got_value": "{value:g} meets the requested value",
        "temper.got_fraction": "{value:g} — {pct:.0f}% of the range",
        "temper.got_any": "{value:g}",
        "temper.keep_rolling": "{affix} — keep going",
        "temper.other_affix": "not the requested affix ('{want}')",
        "temper.unreadable": "doubtful reading",
        "temper.recharged": "recharged the rerolls ({count}x)",
        "temper.unknown_screen": "I do not recognize this screen. Open the Blacksmith on the Tempering tab.",
        "temper.recipes_open": (
            "the recipe list is open. Pick the recipe and do the first Temper "
            "by hand; after that I repeat the cycle."
        ),
        "temper.no_recipe": (
            "no recipe selected on this item. Pick the category and the recipe "
            "in game before starting."
        ),
        "temper.out_of_rerolls": (
            "Temper Rerolls ran out. Recharging spends Scrolls — turn on "
            "automatic recharge if you want me to do it."
        ),
        "temper.no_scrolls": (
            "Temper Rerolls ran out and recharging is not possible: either the "
            "item is at its limit, or the Scrolls ran out."
        ),
        "temper.recharge_limit": "reached the session cap of {count} recharge(s)",
        "temper.recharge_runaway": (
            "I clicked recharge {count}x and the item did not fill. Stopped so "
            "as not to keep spending Scrolls: check whether the recharge button "
            "is where it should be on screen."
        ),
        "temper.unreadable_stop": (
            "I could not read the result ({raw!r}) and I will not roll over it. "
            "Check the item in game."
        ),
        "tab.temper": "Tempering",
        "temper.col_affix": "Rolled affix",
        "temper.col_done": "stopped here",
        "temper.col_ga": "GA",
        "temper.col_rolled": "rolled",
        "temper.hint": (
            "Open the Blacksmith on the Tempering tab, pick the category and "
            "the recipe, and do the first Temper by hand. Then press F10."
        ),
        "temper.goal_box": "Stop when",
        "temper.mode_ga": "a Greater Affix comes up",
        "temper.mode_ga_tip": (
            "On a GA the game shows only the value, without the bracketed "
            "range. That is why it can be recognised with no range data at all."
        ),
        "temper.mode_fraction": "the roll reaches",
        "temper.mode_fraction_suffix": "% of the range",
        "temper.mode_value": "the value reaches",
        "temper.affix_filter": "and the affix contains",
        "temper.affix_filter_ph": "leave empty to accept any affix",
        "temper.affix_filter_tip": (
            "Some recipes roll among several affixes. Without this, the cycle "
            "would stop on a GA of the wrong one."
        ),
        "temper.rerolls_box": "When Temper Rerolls run out",
        "temper.recharge_stop": "stop and tell me",
        "temper.recharge_one": "recharge one at a time",
        "temper.recharge_full": "fill up to the item's maximum",
        "temper.recharge_cap": "at most",
        "temper.recharge_no_cap": "no limit",
        "temper.recharge_cap_suffix": " recharge(s) this session",
        "temper.recharge_warn": (
            "Recharging spends Scrolls. Each item has its own Temper Reroll "
            "limit, and the circular button greys out when it is reached — or "
            "when the Scrolls run out."
        ),
        "temper.start": "Start Tempering",
        "temper.hotkey_hint": "F10 starts and stops; F12 only stops.",
        "temper.done": "{count} attempt(s) in {seconds:.0f}s",
        "temper.idle": "Ready. Open the Blacksmith on Tempering and press F10.",
        "temper.running": "Running…",
        "progress.title": "Progress",
        "progress.attempts": "Attempts",
        "progress.elapsed": "Elapsed",
        "progress.rate": "Rate",
        "progress.current": "Current affix",
        "progress.col_n": "#",
        "progress.col_opt1": "Option 1",
        "progress.col_opt2": "Option 2",
        "progress.col_result": "Result",
        "progress.kept": "kept",
        "progress.took": "took",
        "progress.none": "—",
        "progress.details": "Technical details",
        "progress.empty": "Attempts show up here once the cycle starts.",
        "progress.took_n": "took option {index}",
        "speed.humano": "human",
        "speed.rápido": "fast",
        "speed.instantâneo": "instant",
        "progress.goal": "goal reached",
        "progress.rate_unit": "{seconds:.1f} s",
    },
}

_current = DEFAULT


def set_language(code: str) -> str:
    """Troca o idioma corrente. Devolve o que ficou valendo."""
    global _current
    _current = code if code in STRINGS else DEFAULT
    return _current


def current_language() -> str:
    return _current


def t(key: str, **kwargs) -> str:
    """Texto da chave no idioma corrente, formatado com os argumentos."""
    texto = STRINGS.get(_current, {}).get(key)
    if texto is None:
        texto = STRINGS[DEFAULT].get(key, key)
    if kwargs:
        try:
            return texto.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return texto
    return texto
