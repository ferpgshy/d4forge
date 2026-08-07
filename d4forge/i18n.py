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

STRINGS: dict[str, dict[str, str]] = {
    "pt-BR": {
        # -- janela e cabeçalho
        "app.title": "d4forge",
        "app.subtitle": "Encantamento — Diablo IV",
        "app.window": "d4forge",
        # -- abas
        "tab.panel": "Painel",
        "tab.target": "Alvo",
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
        "panel.start_delay_tip": "Tempo para voltar ao jogo depois de apertar Iniciar.",
        "panel.safety": "Parar quando",
        "panel.abort_focus": "o jogo sair do foco",
        "panel.abort_mouse": "eu mexer no mouse",
        "panel.focus_game": "trazer o jogo para frente",
        "panel.mouse_speed": "Velocidade do mouse",
        "panel.mouse_speed_tip": (
            "Instantâneo vai direto ao alvo. Os outros imitam movimento humano "
            "e custam até 0,8 s por rodada."
        ),
        "panel.log": "Registro",
        "panel.rate": "{seconds:.2f} s por tentativa",
        "panel.attempts_done": "{count} tentativa(s) em {seconds:.0f}s",
        # -- alvo
        "target.box": "Parar quando aparecer",
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
        "target.hint": "O Occultist troca um afixo por vez, então o alvo é um só.",
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
        "msg.no_target": "Defina um alvo na aba Alvo antes de iniciar.",
        "msg.no_target_title": "Sem alvo",
        "msg.monitor_off": "Observador desligado para não disputar CPU.",
        "msg.purged": "Removidos do catálogo por serem erro de leitura: {names}",
        "msg.ocr_ready": "Leitor pronto ({ms:.0f} ms)",
        "msg.catalog_loaded": "Catálogo com {count} afixos",
    },
    "en": {
        "app.title": "d4forge",
        "app.subtitle": "Enchanting — Diablo IV",
        "app.window": "d4forge",
        "tab.panel": "Panel",
        "tab.target": "Target",
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
        "panel.start_delay_tip": "Time to switch back to the game after pressing Start.",
        "panel.safety": "Stop when",
        "panel.abort_focus": "the game loses focus",
        "panel.abort_mouse": "I move the mouse",
        "panel.focus_game": "bring the game to front",
        "panel.mouse_speed": "Mouse speed",
        "panel.mouse_speed_tip": (
            "Instant jumps straight to the target. The others mimic human "
            "movement and cost up to 0.8 s per round."
        ),
        "panel.log": "Log",
        "panel.rate": "{seconds:.2f} s per attempt",
        "panel.attempts_done": "{count} attempt(s) in {seconds:.0f}s",
        "target.box": "Stop when this shows up",
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
        "target.hint": "The Occultist rerolls one affix at a time, so there is a single target.",
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
