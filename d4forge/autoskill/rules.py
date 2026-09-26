"""O que o AutoSkill faz, em dados. Nada de tecla ou coordenada no codigo.

Uma decisao de modelagem que vale explicar: **AutoTP e AutoDodge sao a mesma
coisa**. Os dois sao "aperte esta bind de tempos em tempos enquanto estiver
ligado" - nenhum le' a tela. Em vez de duas classes quase iguais, ha' um
`Repetidor` e a configuracao traz uma lista deles. O preco e' zero e o ganho e'
que criar um terceiro (grito de guerra, buff, o que for) nao precisa de codigo
novo.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from ..automation.binds import Bind, botao_mouse, tecla
from .profile import SLOTS


class ModoDoSlot(Enum):
    """O que fazer com um slot de habilidade."""

    COOLDOWN = "cooldown"   # espera sair do cooldown e usa de novo
    SPAM = "spam"           # aperta sem olhar a tela
    MANUAL = "manual"       # nao encosta

    @property
    def rotulo(self) -> str:
        return {
            ModoDoSlot.COOLDOWN: "Manter em cooldown",
            ModoDoSlot.SPAM: "Spam",
            ModoDoSlot.MANUAL: "Manual / ignorar",
        }[self]


class ModoDeAtivacao(Enum):
    TOGGLE = "toggle"       # um toque liga, outro desliga
    SEGURAR = "hold"        # ativo enquanto a tecla estiver pressionada

    @property
    def rotulo(self) -> str:
        return "Toggle" if self is ModoDeAtivacao.TOGGLE else "Segurar"


def _enum(classe, valor, padrao):
    """Enum tolerante: valor desconhecido vira o padrao, nunca excecao."""
    try:
        return classe(valor)
    except ValueError:
        return padrao


@dataclass
class Controle:
    """A hotkey que liga e desliga um recurso."""

    hotkey: Bind = field(default_factory=Bind)
    ativacao: ModoDeAtivacao = ModoDeAtivacao.TOGGLE

    def to_json(self) -> dict:
        return {"hotkey": self.hotkey.to_json(), "ativacao": self.ativacao.value}

    @classmethod
    def from_json(cls, blob) -> "Controle":
        if not isinstance(blob, dict):
            return cls()
        return cls(
            Bind.from_json(blob.get("hotkey")),
            _enum(ModoDeAtivacao, blob.get("ativacao"), ModoDeAtivacao.TOGGLE),
        )


@dataclass
class SlotConfig:
    """Uma posicao da barra de habilidades."""

    bind: Bind = field(default_factory=Bind)
    modo: ModoDoSlot = ModoDoSlot.MANUAL
    # Menor vai primeiro quando mais de uma habilidade esta' pronta no mesmo
    # instante. Empate resolve pela ordem do slot.
    prioridade: int = 0

    @property
    def age_sozinho(self) -> bool:
        return self.modo is not ModoDoSlot.MANUAL and bool(self.bind)

    def to_json(self) -> dict:
        return {
            "bind": self.bind.to_json(),
            "modo": self.modo.value,
            "prioridade": self.prioridade,
        }

    @classmethod
    def from_json(cls, blob) -> "SlotConfig":
        if not isinstance(blob, dict):
            return cls()
        try:
            prioridade = int(blob.get("prioridade", 0))
        except (TypeError, ValueError):
            prioridade = 0
        return cls(
            Bind.from_json(blob.get("bind")),
            _enum(ModoDoSlot, blob.get("modo"), ModoDoSlot.MANUAL),
            prioridade,
        )


@dataclass
class Repetidor:
    """Aperta uma bind de tempos em tempos. E' o AutoTP e o AutoDodge."""

    nome: str = ""
    bind: Bind = field(default_factory=Bind)
    intervalo_ms: int = 250
    controle: Controle = field(default_factory=Controle)

    def to_json(self) -> dict:
        return {
            "nome": self.nome,
            "bind": self.bind.to_json(),
            "intervalo_ms": self.intervalo_ms,
            "controle": self.controle.to_json(),
        }

    @classmethod
    def from_json(cls, blob) -> "Repetidor":
        if not isinstance(blob, dict):
            return cls()
        try:
            intervalo = max(20, int(blob.get("intervalo_ms", 250)))
        except (TypeError, ValueError):
            intervalo = 250
        nome = blob.get("nome")
        return cls(
            nome if isinstance(nome, str) else "",
            Bind.from_json(blob.get("bind")),
            intervalo,
            Controle.from_json(blob.get("controle")),
        )


@dataclass
class AutoPotionConfig:
    bind: Bind = field(default_factory=lambda: tecla(0x51, "Q"))
    # Abaixo disto, bebe. 35% e' baixo o bastante para nao desperdicar carga e
    # alto o bastante para sobrar tempo de reacao.
    limiar_pct: int = 35
    # Cooldown da pocao no jogo. Sem esperar, o ciclo apertaria Q dez vezes por
    # segundo enquanto a vida estivesse baixa e gastaria as quatro cargas de uma
    # vez. Verificado por tempo, e nao pela tela, porque o contador demora a
    # atualizar.
    cooldown_s: float = 5.0
    # O que fazer quando a barreira cobre o orbe e a vida some da tela.
    beber_com_escudo: bool = False
    controle: Controle = field(default_factory=Controle)

    def to_json(self) -> dict:
        return {
            "bind": self.bind.to_json(),
            "limiar_pct": self.limiar_pct,
            "cooldown_s": self.cooldown_s,
            "beber_com_escudo": self.beber_com_escudo,
            "controle": self.controle.to_json(),
        }

    @classmethod
    def from_json(cls, blob) -> "AutoPotionConfig":
        if not isinstance(blob, dict):
            return cls()
        padrao = cls()
        try:
            limiar = min(99, max(1, int(blob.get("limiar_pct", padrao.limiar_pct))))
        except (TypeError, ValueError):
            limiar = padrao.limiar_pct
        try:
            cd = max(0.0, float(blob.get("cooldown_s", padrao.cooldown_s)))
        except (TypeError, ValueError):
            cd = padrao.cooldown_s
        bind = Bind.from_json(blob.get("bind")) or padrao.bind
        return cls(
            bind, limiar, cd,
            bool(blob.get("beber_com_escudo", False)),
            Controle.from_json(blob.get("controle")),
        )


@dataclass
class AutoCastConfig:
    slots: list[SlotConfig] = field(
        default_factory=lambda: [SlotConfig() for _ in range(SLOTS)]
    )
    # Binds que nao estao na barra numerada: botoes do mouse e roda. Ficam
    # numa lista a' parte porque nao tem slot na tela para ler cooldown - so'
    # aceitam SPAM ou MANUAL.
    extras: list[SlotConfig] = field(default_factory=list)
    # Intervalo entre duas acoes. 120 ms e' o padrao: rapido o bastante para
    # nao perder janela de cast e devagar o bastante para o jogo registrar cada
    # tecla (o aperto sintetico ja' segura 30-55 ms por si).
    intervalo_ms: int = 120
    controle: Controle = field(default_factory=Controle)

    def to_json(self) -> dict:
        return {
            "slots": [s.to_json() for s in self.slots],
            "extras": [s.to_json() for s in self.extras],
            "intervalo_ms": self.intervalo_ms,
            "controle": self.controle.to_json(),
        }

    @classmethod
    def from_json(cls, blob) -> "AutoCastConfig":
        if not isinstance(blob, dict):
            return cls()
        padrao = cls()
        crus = blob.get("slots")
        slots = padrao.slots
        if isinstance(crus, list):
            slots = [SlotConfig.from_json(c) for c in crus[:SLOTS]]
            while len(slots) < SLOTS:
                slots.append(SlotConfig())
        extras = blob.get("extras")
        try:
            intervalo = max(30, int(blob.get("intervalo_ms", padrao.intervalo_ms)))
        except (TypeError, ValueError):
            intervalo = padrao.intervalo_ms
        return cls(
            slots,
            [SlotConfig.from_json(c) for c in extras] if isinstance(extras, list) else [],
            intervalo,
            Controle.from_json(blob.get("controle")),
        )

    def ordem_de_cast(self) -> list[tuple[int, SlotConfig]]:
        """Slots que agem sozinhos, na ordem de prioridade.

        `(indice, config)` porque o indice e' o que liga a configuracao ao slot
        LIDO na tela - a prioridade reordena a lista sem mexer nisso.
        """
        numerados = [
            (i, s) for i, s in enumerate(self.slots) if s.age_sozinho
        ]
        numerados.sort(key=lambda par: (par[1].prioridade, par[0]))
        return numerados


def _repetidores_padrao() -> list[Repetidor]:
    return [
        # Espaco e' a esquiva padrao do jogo.
        Repetidor("dodge", tecla(0x20, "Espaço"), 250),
        # Portal nao tem tecla padrao que valha chutar: fica vazio ate' o
        # usuario informar a dele.
        Repetidor("tp", Bind(), 400),
    ]


@dataclass
class AutoSkillConfig:
    cast: AutoCastConfig = field(default_factory=AutoCastConfig)
    potion: AutoPotionConfig = field(default_factory=AutoPotionConfig)
    repetidores: list[Repetidor] = field(default_factory=_repetidores_padrao)

    def to_json(self) -> dict:
        return {
            "cast": self.cast.to_json(),
            "potion": self.potion.to_json(),
            "repetidores": [r.to_json() for r in self.repetidores],
        }

    @classmethod
    def from_json(cls, blob) -> "AutoSkillConfig":
        """Qualquer defeito vira padrao, NUNCA excecao.

        Isto roda na montagem da janela: um valor inesperado aqui nao estraga
        uma preferencia, impede o app de ABRIR.
        """
        if not isinstance(blob, dict):
            return cls()
        crus = blob.get("repetidores")
        if isinstance(crus, list) and crus:
            repetidores = [Repetidor.from_json(c) for c in crus]
        else:
            repetidores = _repetidores_padrao()
        return cls(
            AutoCastConfig.from_json(blob.get("cast")),
            AutoPotionConfig.from_json(blob.get("potion")),
            repetidores,
        )

    def repetidor(self, nome: str) -> Repetidor | None:
        for r in self.repetidores:
            if r.nome == nome:
                return r
        return None


__all__ = [
    "AutoCastConfig",
    "AutoPotionConfig",
    "AutoSkillConfig",
    "Controle",
    "ModoDeAtivacao",
    "ModoDoSlot",
    "Repetidor",
    "SlotConfig",
    "botao_mouse",
    "replace",
]
