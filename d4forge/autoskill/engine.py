"""O laco do AutoSkill.

Tres coisas moram aqui e vale dizer por que sao uma so' e nao tres:

* **as hotkeys sao lidas SEMPRE**, mesmo com tudo desligado - e' assim que se
  liga alguma coisa. Por isso o tique e' curto (25 ms) e quem espera nao e' o
  laco, e sim cada acao, com o seu proprio relogio.
* **a captura acontece no maximo UMA vez por tique**, e so' se houver alguem
  que precise dela. Cast e pocao leem o mesmo quadro; esquiva e portal nao leem
  nada.
* **UMA acao por tique, e a pocao na frente.** Cada aperto sintetico segura a
  tecla 30-55 ms para o jogo registrar; deixar cast, esquiva e portal sairem no
  MESMO tique fazia o tique passar de 150 ms, e a vida so' era relida depois
  disso. Numa vida que cai, essa e' a diferenca entre beber a 30% e beber a
  10%. Com uma acao por tique a leitura volta a ~18 Hz, e a pocao tem
  precedencia sobre tudo.

O portao de tudo e' o jogo estar em primeiro plano. Fora disso o laco continua
girando - para ouvir as hotkeys - mas nao aperta nada.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from ..automation import binds
from ..capture import ScreenCapture
from ..engine import EngineEvent, EventKind
from ..profile import ResolvedProfile
from ..window import find_game_window
from .profile import DEFAULT_AUTOSKILL_PROFILE
from .rules import AutoSkillConfig, ModoDeAtivacao, ModoDoSlot
from .vision import LeitorDeCooldown, ler_vida

# Tique do laco. Curto porque e' ele que da' a resposta da hotkey; as acoes em
# si tem cada uma o seu intervalo.
TIQUE_S = 0.025

# Carencia depois de apertar um slot. O jogo leva um ou dois quadros para
# escurecer o icone, entao o tique seguinte ainda le' "pronta" e apertaria a
# mesma tecla de novo. Sem isto, o slot de maior prioridade monopolizava o
# ciclo e os outros nunca chegavam a vez.
GRACA_APOS_DISPARO_S = 0.30

# Ritmo do aviso de estado para a interface. Emitir a cada tique encheria o
# painel com quarenta mensagens por segundo sem dizer nada de novo.
AVISO_S = 0.2

log = logging.getLogger(__name__)


@dataclass
class EstadoAutoSkill:
    """Retrato do que esta' acontecendo, para o indicador da aba."""

    em_foco: bool = False
    ligados: dict = field(default_factory=dict)      # nome -> bool
    vida_pct: int | None = None
    escudo_pct: int = 0
    slots_prontos: list[bool] = field(default_factory=list)
    ultima_acao: str = ""


class _Gatilho:
    """Liga e desliga um recurso a partir de uma hotkey.

    Toggle e "segurar" nao sao dois codigos: os dois viram um booleano aqui, e
    quem consulta nao precisa saber qual modo o usuario escolheu.
    """

    def __init__(self, controle) -> None:
        self.controle = controle
        self.ligado = False
        # O toque que ligou a hotkey nao pode ser lido como o toque que a
        # desliga: `foi_pressionada` devolve True uma vez por aperto, e a
        # primeira leitura poderia trazer um aperto anterior a' vigilancia.
        binds.descarta_toque_pendente(controle.hotkey)

    def apontar_para(self, controle) -> None:
        """Troca o controle sem reiniciar o laco.

        A aba edita a configuracao enquanto o laco roda - ele sobe junto com o
        app e nunca para. Trocar a hotkey aqui e' o que faz a bind nova valer
        na hora, e descartar o toque pendente impede que o proprio aperto que
        acabou de gravar a tecla seja lido como o toque que liga o recurso.
        """
        if controle.hotkey != self.controle.hotkey:
            binds.descarta_toque_pendente(controle.hotkey)
        self.controle = controle

    def atualizar(self) -> bool:
        alvo = self.controle.hotkey
        if not alvo:
            return self.ligado
        if self.controle.ativacao is ModoDeAtivacao.SEGURAR:
            self.ligado = binds.esta_pressionada(alvo)
        elif binds.foi_pressionada(alvo):
            self.ligado = not self.ligado
        return self.ligado


class AutoSkillEngine:
    """Roda ate' mandarem parar. Nao tem `Outcome`: nao ha' o que concluir."""

    def __init__(self, config: AutoSkillConfig, settings=None, listener=None) -> None:
        self.config = config
        self.settings = settings
        self._listener = listener
        self._cancel = False
        self._captura = None
        # De onde a fila recomeca, e quando cada slot disparou pela ultima vez.
        # Os dois existem pelo mesmo motivo: repartir as vezes entre os slots.
        self._ultimo_slot = -1
        self._disparado_em: dict[int, float] = {}
        self._ultimo_aviso = 0.0
        self._leitor = LeitorDeCooldown(len(config.cast.slots))

    # -- controle ---------------------------------------------------------
    def cancel(self) -> None:
        self._cancel = True

    def _emit(self, kind: EventKind, chave: str, **dados) -> None:
        if self._listener is not None:
            self._listener(EngineEvent(kind, chave, dados))

    # -- laco -------------------------------------------------------------
    def run(self) -> EstadoAutoSkill:
        cfg = self.config
        gatilhos = {
            "cast": _Gatilho(cfg.cast.controle),
            "potion": _Gatilho(cfg.potion.controle),
        }
        for rep in cfg.repetidores:
            gatilhos[rep.nome] = _Gatilho(rep.controle)

        agora = time.monotonic()
        proxima = {nome: agora for nome in gatilhos}
        estado = EstadoAutoSkill()
        self._ultimo_aviso = 0.0

        # A captura nasce SO' quando alguem precisar de um quadro. O laco sobe
        # junto com o app e fica no ar a sessao inteira; abrir o dxcam ali
        # tomaria um dispositivo de video de quem talvez nunca ligue o
        # AutoSkill - e, numa configuracao so' de spam, de quem nunca vai
        # precisar dele.
        self._captura = None
        try:
            while not self._cancel:
                try:
                    self._tique(gatilhos, proxima, estado, cfg)
                except Exception:  # noqa: BLE001 - ver o comentario
                    # Uma excecao aqui matava a THREAD, em silencio: o
                    # AutoSkill parava de funcionar e nada na tela dizia isso,
                    # so' reabrir o app resolvia. Anotar e seguir e' melhor -
                    # o que costuma falhar (captura, janela que fechou) volta
                    # sozinho no tique seguinte.
                    log.exception("falha num tique do AutoSkill")
                    self._emit(EventKind.ERROR, "autoskill.erro")
                    time.sleep(0.25)
        finally:
            self._fechar_captura()
        return estado

    def _tique(self, gatilhos, proxima, estado, cfg) -> None:
        """Uma volta do laco. Fora do `while` para poder falhar sem derrubar."""
        agora = time.monotonic()
        self._sincronizar(gatilhos, proxima, agora)
        ligados = {n: g.atualizar() for n, g in gatilhos.items()}
        estado.ligados = dict(ligados)

        janela = find_game_window()
        estado.em_foco = bool(janela and janela.is_foreground)
        if not estado.em_foco:
            # Sem foco o laco continua girando - so' para ouvir as hotkeys -
            # mas nao encosta no teclado.
            self._avisar(estado, agora)
            time.sleep(TIQUE_S)
            return

        precisa_ver = (
            (ligados.get("cast") and self._algum_slot_le_tela())
            or ligados.get("potion")
        )
        quadro = perfil = None
        if precisa_ver:
            perfil = ResolvedProfile(DEFAULT_AUTOSKILL_PROFILE, janela.client)
            quadro = self._olhar(janela.client)

        # A pocao vem PRIMEIRO, e a vida e' lida mesmo quando nao se vai beber:
        # e' essa leitura que alimenta o indicador da aba.
        agiu = False
        if ligados.get("potion") and quadro is not None:
            antes = proxima["potion"]
            proxima["potion"] = self._talvez_beber(
                quadro, perfil, estado, agora, antes
            )
            agiu = proxima["potion"] != antes

        if not agiu and ligados.get("cast") and agora >= proxima["cast"]:
            if self._talvez_castar(quadro, perfil, estado, agora):
                proxima["cast"] = agora + cfg.cast.intervalo_ms / 1000
                agiu = True

        for rep in cfg.repetidores:
            if agiu:
                break
            if ligados.get(rep.nome) and agora >= proxima[rep.nome]:
                if binds.disparar(rep.bind):
                    estado.ultima_acao = rep.nome
                    proxima[rep.nome] = time.monotonic() + rep.intervalo_ms / 1000
                    agiu = True

        self._avisar(estado, agora)
        time.sleep(TIQUE_S)

    def _olhar(self, client):
        """Um quadro da tela, abrindo a captura na primeira vez que precisar."""
        if self._captura is None:
            self._captura = ScreenCapture(
                prefer=getattr(self.settings, "capture_backend", "dxcam")
            )
        return self._captura.grab(client)

    def _fechar_captura(self) -> None:
        if self._captura is not None:
            try:
                self._captura.close()
            finally:
                self._captura = None

    # -- partes -----------------------------------------------------------
    def _sincronizar(self, gatilhos, proxima, agora) -> None:
        """Reflete no laco o que a aba mudou, sem reiniciar nada."""
        cfg = self.config
        gatilhos["cast"].apontar_para(cfg.cast.controle)
        gatilhos["potion"].apontar_para(cfg.potion.controle)
        for rep in cfg.repetidores:
            existente = gatilhos.get(rep.nome)
            if existente is None:
                gatilhos[rep.nome] = _Gatilho(rep.controle)
                proxima[rep.nome] = agora
            else:
                existente.apontar_para(rep.controle)

    def _algum_slot_le_tela(self) -> bool:
        """So' o modo "manter em cooldown" precisa de captura.

        Uma configuracao so' de spam nao custa um unico quadro - e e'
        exatamente o caso de quem so' quer trocar a macro do LGHUB.
        """
        return any(
            s.modo is ModoDoSlot.COOLDOWN and s.bind
            for s in self.config.cast.slots
        )

    def _talvez_castar(self, quadro, perfil, estado, agora) -> bool:
        cfg = self.config.cast
        prontos: list[bool] = []
        if quadro is not None and perfil is not None:
            leitura = self._leitor.ler(quadro, perfil.skill_slots)
            prontos = [not e.em_cooldown for e in leitura]
            estado.slots_prontos = prontos

        for indice, slot in self._rodizio(cfg.ordem_de_cast()):
            if slot.modo is ModoDoSlot.COOLDOWN:
                # Sem leitura nao ha' como saber; nao chuta.
                if indice >= len(prontos) or not prontos[indice]:
                    continue
                # `-inf` e nao zero: zero significaria "disparou no instante
                # zero", e "nunca disparou" tem de ser inequivoco.
                ultimo = self._disparado_em.get(indice, float("-inf"))
                if agora - ultimo < GRACA_APOS_DISPARO_S:
                    continue
            if binds.disparar(slot.bind):
                self._ultimo_slot = indice
                # `agora`, e nao `time.monotonic()` de novo: a carencia e'
                # comparada com o mesmo valor que o tique recebeu, e misturar
                # as duas leituras do relogio deixava a conta sem sentido.
                self._disparado_em[indice] = agora
                estado.ultima_acao = (
                    f"slot {indice + 1}" if indice < len(self.config.cast.slots)
                    else slot.bind.descreve()
                )
                return True
        return False

    def _rodizio(self, fila):
        """A mesma fila, recomecando DEPOIS do ultimo que disparou.

        Sem isto a varredura reiniciava sempre no topo e so' a habilidade de
        maior prioridade era usada: ela disparava, o laco saia, e no tique
        seguinte ela era a primeira a ser testada outra vez. A prioridade
        define a ORDEM do rodizio, nao um monopolio do primeiro - foi
        exatamente o que o pedido descreveu, "quando mais de uma estiver
        disponivel ao mesmo tempo".
        """
        for i, (indice, _slot) in enumerate(fila):
            if indice == self._ultimo_slot:
                return fila[i + 1:] + fila[:i + 1]
        return fila

    def _talvez_beber(self, quadro, perfil, estado, agora, proxima) -> float:
        cfg = self.config.potion
        leitura = ler_vida(quadro, perfil.health_orb)
        estado.escudo_pct = int(round(leitura.barreira * 100))
        estado.vida_pct = leitura.porcentagem() if leitura.confiavel else None

        if agora < proxima:
            return proxima
        if not leitura.confiavel:
            # Orbe coberto pelo escudo: a vida nao esta' na tela. Beber aqui
            # seria chutar, e chutar gasta carga.
            if not cfg.beber_com_escudo:
                return proxima
        elif leitura.porcentagem() > cfg.limiar_pct:
            return proxima

        if binds.disparar(cfg.bind):
            estado.ultima_acao = "poção"
            self._emit(EventKind.INFO, "autoskill.potion",
                       vida=estado.vida_pct if estado.vida_pct is not None else -1)
            return time.monotonic() + cfg.cooldown_s
        return proxima

    def _avisar(self, estado, agora) -> None:
        """Retrato para a interface, no maximo cinco vezes por segundo.

        A cada tique seriam quarenta mensagens por segundo sem nada de novo.
        """
        if agora - self._ultimo_aviso < AVISO_S:
            return
        self._ultimo_aviso = agora
        self._emit(EventKind.STATE, "autoskill.estado", estado=estado)


__all__ = ["AutoSkillEngine", "EstadoAutoSkill", "TIQUE_S"]
