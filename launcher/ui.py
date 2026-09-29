"""A janela do launcher.

tkinter, e não PySide6, por um motivo medido: o mesmo launcher empacotado dá
**10,4 MB** com tkinter e passaria de 90 MB com Qt. Um launcher que pesa o
mesmo que o aplicativo não é um launcher.

O desenho segue a paleta do app (`d4forge/gui/style.py`) para que as duas
janelas pareçam a mesma coisa, mesmo sendo dois programas diferentes.

Regra de thread: tkinter **não é seguro entre threads**, e nem mesmo
`after()` pode ser chamado de fora — ele registra um comando no Tcl e estoura
com `RuntimeError: main thread is not in main loop`. Rede e disco rodam numa
thread de trabalho e devolvem o resultado por uma **fila**, que a thread da
interface esvazia periodicamente. Nenhum widget é tocado de fora.
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from d4forge import edicao, i18n
from d4forge.i18n import t

from . import __version__, autoupdate, escolha, fonte, instalacao

log = logging.getLogger(__name__)

# A paleta do aplicativo, para as duas janelas serem a mesma família.
FUNDO = "#14110d"
CARTAO = "#1c1813"
CARTAO_ATIVO = "#221c15"
BORDA = "#3a3128"
TEXTO = "#ddd3c2"
TEXTO_FRACO = "#8a8073"
DOURADO = "#c9a463"
VERMELHO = "#a83c31"
VERDE = "#5f7d4a"

FONTE = "Segoe UI"

# A ordem em que as edições aparecem. A completa primeiro: é o que a maioria
# quer, e a primeira linha é a que mais recebe clique.
ORDEM = (edicao.COMPLETA, edicao.FORGE, edicao.AUTOSKILL)


def tamanho_legivel(n: int) -> str:
    """142000000 -> "135 MB". Sem casas decimais: ninguém lê o terceiro dígito."""
    if n <= 0:
        return "—"
    for unidade, limite in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= limite:
            return f"{n / limite:.0f} {unidade}" if n / limite >= 10 \
                else f"{n / limite:.1f} {unidade}"
    return f"{n} B"


class Cartao(tk.Frame):
    """Uma edição: nome, o que ela tem, em que estado está, e um botão."""

    def __init__(self, pai: tk.Misc, qual: str, aoclicar) -> None:
        super().__init__(pai, bg=CARTAO, highlightbackground=BORDA,
                         highlightthickness=1)
        self.qual = qual
        self._aoclicar = aoclicar

        esquerda = tk.Frame(self, bg=CARTAO)
        esquerda.pack(side="left", fill="both", expand=True, padx=14, pady=11)

        self.nome = tk.Label(esquerda, text="", bg=CARTAO, fg=TEXTO,
                             font=(FONTE, 11, "bold"), anchor="w")
        self.nome.pack(fill="x")
        self.descricao = tk.Label(esquerda, text="", bg=CARTAO, fg=TEXTO_FRACO,
                                  font=(FONTE, 8), anchor="w", justify="left",
                                  wraplength=340)
        self.descricao.pack(fill="x", pady=(1, 3))
        self.estado = tk.Label(esquerda, text="", bg=CARTAO, fg=TEXTO_FRACO,
                               font=(FONTE, 8), anchor="w")
        self.estado.pack(fill="x")

        self.botao = tk.Button(
            self, text="", command=self._clique, relief="flat", bd=0,
            bg="#2a231b", fg=TEXTO, activebackground="#362d22",
            activeforeground=TEXTO, font=(FONTE, 9), cursor="hand2",
            padx=14, pady=7, highlightthickness=1, highlightbackground=BORDA,
        )
        self.botao.pack(side="right", padx=(0, 14))

        for widget in (self, esquerda, self.nome, self.descricao, self.estado):
            widget.bind("<Enter>", self._entrou)
            widget.bind("<Leave>", self._saiu)
            widget.bind("<Button-1>", lambda _e: self._clique())

    def _entrou(self, _evento=None) -> None:
        self._pintar(CARTAO_ATIVO)

    def _saiu(self, _evento=None) -> None:
        self._pintar(CARTAO)

    def _pintar(self, cor: str) -> None:
        self.configure(bg=cor)
        for filho in self.winfo_children():
            if isinstance(filho, tk.Button):
                continue
            filho.configure(bg=cor)
            for neto in filho.winfo_children():
                neto.configure(bg=cor)

    def _clique(self) -> None:
        if str(self.botao["state"]) != "disabled":
            self._aoclicar(self.qual)

    def mostrar(self, titulo: str, descricao: str, estado: str, cor_estado: str,
                acao: str, ligado: bool) -> None:
        self.nome.configure(text=titulo)
        self.descricao.configure(text=descricao)
        self.estado.configure(text=estado, fg=cor_estado)
        self.botao.configure(text=acao, state="normal" if ligado else "disabled",
                             fg=TEXTO if ligado else "#5c5449")


class Janela(tk.Tk):
    """O launcher inteiro: três cartões, uma barra e uma thread de trabalho."""

    def __init__(self, base: Path | None = None) -> None:
        super().__init__()
        self.base = base or instalacao.raiz()
        self.estado = instalacao.Estado.carregar(self.base)
        i18n.set_language(self.estado.idioma)

        self.manifesto: fonte.Manifesto | None = None
        self._cancelar = threading.Event()
        self._trabalhando = False
        # O correio de volta das threads de trabalho: elas põem funções aqui e
        # quem executa é sempre a thread da interface.
        self._fila: queue.Queue = queue.Queue()

        self.configure(bg=FUNDO)
        self.resizable(False, False)
        self._montar()
        self._centralizar(560, 520)
        self._icone()
        self.retranslate()

        # Sobras de uma atualização interrompida somem antes de qualquer
        # coisa: elas confundiriam a leitura do que está instalado.
        instalacao.limpar_restos(self.base)
        autoupdate.limpar_aposentados(self.base)

        self._bombeando = self.after(80, self._bombear)
        self._agendado = self.after(60, self._checar_versao)

    # ------------------------------------------------------------- threads
    def _na_tela(self, funcao) -> None:
        """Agenda algo para rodar na thread da interface. Seguro de fora."""
        self._fila.put(funcao)

    def _bombear(self) -> None:
        """Esvazia a fila. Roda a cada 80 ms na thread da interface."""
        while True:
            try:
                funcao = self._fila.get_nowait()
            except queue.Empty:
                break
            try:
                funcao()
            except Exception:  # noqa: BLE001 - um recado não derruba a janela
                log.exception("falha ao atualizar a tela")
        self._bombeando = self.after(80, self._bombear)

    def destroy(self) -> None:
        """Cancela o que estava agendado antes de derrubar a janela."""
        for atributo in ("_agendado", "_bombeando"):
            agendado = getattr(self, atributo, None)
            if agendado is not None:
                try:
                    self.after_cancel(agendado)
                except tk.TclError:
                    pass
                setattr(self, atributo, None)
        super().destroy()

    # ------------------------------------------------------------- montagem
    def _icone(self) -> None:
        empacotado = Path(getattr(sys, "_MEIPASS", ""))
        for candidato in (
            empacotado / "d4forge.ico",
            Path(__file__).resolve().parent.parent
            / "d4forge" / "resources" / "d4forge.ico",
        ):
            try:
                if candidato.is_file():
                    self.iconbitmap(str(candidato))
                    return
            except tk.TclError:
                pass

    def _centralizar(self, largura: int, altura: int) -> None:
        x = (self.winfo_screenwidth() - largura) // 2
        y = (self.winfo_screenheight() - altura) // 3
        self.geometry(f"{largura}x{altura}+{max(x, 0)}+{max(y, 0)}")

    def _montar(self) -> None:
        cabecalho = tk.Frame(self, bg=FUNDO)
        cabecalho.pack(fill="x", padx=18, pady=(16, 4))

        self.titulo = tk.Label(cabecalho, text="d4forge", bg=FUNDO, fg=DOURADO,
                               font=(FONTE, 20, "bold"))
        self.titulo.pack(side="left")

        self.idioma = tk.Button(
            cabecalho, text=i18n.LANGUAGE_SHORT.get(i18n.current_language(), "PT"),
            command=self._trocar_idioma, relief="flat", bd=0, bg=FUNDO,
            fg=TEXTO_FRACO, activebackground=FUNDO, activeforeground=DOURADO,
            font=(FONTE, 9), cursor="hand2", padx=8,
        )
        self.idioma.pack(side="right")

        self.subtitulo = tk.Label(self, text="", bg=FUNDO, fg=TEXTO_FRACO,
                                  font=(FONTE, 9), anchor="w")
        self.subtitulo.pack(fill="x", padx=18, pady=(0, 12))

        self.cartoes: dict[str, Cartao] = {}
        for qual in ORDEM:
            cartao = Cartao(self, qual, self._agir)
            cartao.pack(fill="x", padx=18, pady=5)
            self.cartoes[qual] = cartao

        rodape = tk.Frame(self, bg=FUNDO)
        rodape.pack(side="bottom", fill="x", padx=18, pady=(8, 14))

        estilo = ttk.Style(self)
        # "clam" é o único tema do ttk que aceita cor na barra no Windows;
        # o padrão ignora `background` e a barra sairia azul de sistema.
        if "clam" in estilo.theme_names():
            estilo.theme_use("clam")
        estilo.configure("d4.Horizontal.TProgressbar", troughcolor="#0d0b08",
                         background=DOURADO, bordercolor=BORDA,
                         lightcolor=DOURADO, darkcolor=DOURADO, thickness=6)
        self.barra = ttk.Progressbar(rodape, style="d4.Horizontal.TProgressbar",
                                     maximum=1000)

        self.recado = tk.Label(rodape, text="", bg=FUNDO, fg=TEXTO_FRACO,
                               font=(FONTE, 8), anchor="w")
        self.recado.pack(fill="x")

        self.guardar = tk.Label(rodape, text="", bg=FUNDO, fg="#5c5449",
                                font=(FONTE, 8), anchor="w")
        self.guardar.pack(fill="x", pady=(2, 0))

        self.versao = tk.Label(rodape, text=f"launcher {__version__}", bg=FUNDO,
                               fg="#4a443c", font=(FONTE, 8), anchor="e")
        self.versao.pack(fill="x")

    # ------------------------------------------------------------- idiomas
    def _trocar_idioma(self) -> None:
        atual = i18n.current_language()
        codigos = list(i18n.STRINGS)
        novo = codigos[(codigos.index(atual) + 1) % len(codigos)]
        i18n.set_language(novo)
        self.estado.idioma = novo
        self.estado.salvar(self.base)
        self.idioma.configure(text=i18n.LANGUAGE_SHORT.get(novo, novo))
        self.retranslate()

    def retranslate(self) -> None:
        self.title(t("lan.title"))
        self.subtitulo.configure(text=t("lan.subtitle"))
        self.guardar.configure(text=t("lan.keep"))
        self._pintar_cartoes()

    # ------------------------------------------------------------- estado
    def _situacao(self, qual: str) -> escolha.Situacao:
        return escolha.situacao(
            qual, self.manifesto, self.estado.instalados,
            lambda chave: instalacao.instalado(chave, self.base),
        )

    def _pintar_cartoes(self) -> None:
        """Traduz o veredito de `escolha` em texto, cor e rótulo de botão."""
        for qual, cartao in self.cartoes.items():
            situacao = self._situacao(qual)

            if situacao.estado == escolha.NAO_INSTALADO:
                texto = t("lan.state.missing",
                          size=tamanho_legivel(situacao.bytes))
                cor, acao = TEXTO_FRACO, t("lan.action.install")
            elif situacao.estado == escolha.ATUALIZAVEL:
                texto = t("lan.state.update", version=situacao.versao)
                cor, acao = DOURADO, t("lan.action.update")
            elif situacao.estado == escolha.PRONTO:
                texto = t("lan.state.ready", version=situacao.versao or "?")
                cor, acao = VERDE, t("lan.action.open")
            else:
                texto = t("lan.msg.nopackage")
                cor, acao = TEXTO_FRACO, t("lan.action.install")

            cartao.mostrar(
                titulo=t(f"lan.edition.{qual}"),
                descricao=t(f"lan.edition.{qual}.desc"),
                estado=texto, cor_estado=cor, acao=acao,
                ligado=situacao.clicavel and not self._trabalhando,
            )

    def _dizer(self, texto: str, cor: str = TEXTO_FRACO) -> None:
        self.recado.configure(text=texto, fg=cor)

    def _mostrar_barra(self, ligada: bool) -> None:
        if ligada and not self.barra.winfo_ismapped():
            self.barra.pack(fill="x", pady=(0, 6), before=self.recado)
        elif not ligada and self.barra.winfo_ismapped():
            self.barra.pack_forget()

    # ------------------------------------------------------------- trabalho
    def _em_thread(self, funcao) -> None:
        self._trabalhando = True
        self._pintar_cartoes()
        threading.Thread(target=funcao, daemon=True).start()

    def _terminou(self) -> None:
        self._trabalhando = False
        self._mostrar_barra(False)
        self._pintar_cartoes()

    def _checar_versao(self) -> None:
        self._dizer(t("lan.busy.checking"))

        def trabalho() -> None:
            try:
                manifesto = fonte.buscar_manifesto()
            except fonte.FalhaDeRede as erro:
                log.info("sem manifesto: %s", erro)
                self._na_tela(lambda: (self._dizer(t("lan.msg.offline")),
                                       self._terminou()))
                return
            self._na_tela(lambda: self._chegou_manifesto(manifesto))

        self._em_thread(trabalho)

    def _chegou_manifesto(self, manifesto: fonte.Manifesto) -> None:
        self.manifesto = manifesto
        self._terminou()
        alguma_desatualizada = any(
            self.estado.versao_de(chave)
            and fonte.comparar_versoes(manifesto.versao,
                                       self.estado.versao_de(chave)) > 0
            for chave in self.estado.instalados
        )
        if autoupdate.ha_launcher_mais_novo(manifesto):
            # Não troca sozinho: trocar o executável que a pessoa acabou de
            # abrir, sem ela pedir, é o tipo de susto que faz desinstalar.
            self._dizer(
                t("lan.msg.available", version=manifesto.launcher_versao)
                + "  ·  launcher", DOURADO,
            )
            self.recado.configure(cursor="hand2")
            self.recado.bind("<Button-1>", lambda _e: self._trocar_launcher())
        elif alguma_desatualizada:
            self._dizer(t("lan.msg.available", version=manifesto.versao), DOURADO)
        elif self.estado.instalados:
            self._dizer(t("lan.msg.uptodate", version=manifesto.versao))
        else:
            # Nada instalado: dizer "tudo na versão mais nova" seria dar
            # notícia sobre um conjunto vazio.
            self._dizer(t("lan.msg.pick", version=manifesto.versao))

    def _trocar_launcher(self) -> None:
        """Baixa o launcher novo e se aposenta no lugar dele."""
        if self._trabalhando or self.manifesto is None:
            return
        self.recado.unbind("<Button-1>")
        self.recado.configure(cursor="")
        self._dizer(t("lan.busy.self"))
        self._mostrar_barra(True)
        manifesto = self.manifesto

        def andamento(feito: int, total: int) -> None:
            self._na_tela(lambda: self.barra.configure(
                value=(feito / total * 1000) if total else 0))

        def trabalho() -> None:
            novo = self.base / (fonte.LAUNCHER + ".novo")
            try:
                fonte.baixar(
                    fonte.url_do_asset(fonte.LAUNCHER, manifesto.tag or None),
                    novo, sha256=manifesto.launcher_sha256,
                    progresso=andamento, cancelar=self._cancelar.is_set,
                )
                autoupdate.trocar(novo)
            except Exception as erro:  # noqa: BLE001 - nada aqui pode matar a janela
                recado = str(erro)
                novo.unlink(missing_ok=True)
                self._na_tela(lambda: (
                    self._dizer(t("lan.msg.failed", reason=recado), VERMELHO),
                    self._terminou()))
                return
            self._na_tela(self.destroy)

        self._em_thread(trabalho)

    def _agir(self, qual: str) -> None:
        """O clique. O que ele faz é o que o cartão prometeu — a mesma conta."""
        if self._trabalhando:
            return
        situacao = self._situacao(qual)
        if situacao.chave is None:
            self._dizer(t("lan.msg.nopackage"), VERMELHO)
            return
        if situacao.precisa_baixar:
            self._baixar_e_abrir(qual, situacao.chave)
        else:
            self._abrir(qual, situacao.chave)

    def _abrir(self, qual: str, chave: str) -> None:
        self._dizer(t("lan.busy.opening"))
        try:
            instalacao.abrir(chave, qual, self.base)
        except OSError as erro:
            self._dizer(t("lan.msg.failed", reason=str(erro)), VERMELHO)
            return
        self.estado.edicao = qual
        self.estado.salvar(self.base)
        # O launcher sai de cena: ele já fez o que tinha para fazer, e duas
        # janelas do mesmo programa na barra de tarefas só atrapalham.
        self.after(400, self.destroy)

    def _baixar_e_abrir(self, qual: str, chave: str) -> None:
        pacote = self.manifesto.pacotes.get(chave) if self.manifesto else None
        if pacote is None:
            self._dizer(t("lan.msg.nopackage"), VERMELHO)
            return

        self._cancelar.clear()
        self._mostrar_barra(True)
        alvo = self.base / pacote.arquivo
        marca = {"quando": time.monotonic(), "bytes": 0}

        def andamento(feito: int, total: int) -> None:
            agora = time.monotonic()
            if agora - marca["quando"] < 0.2 and feito < total:
                return
            velocidade = (feito - marca["bytes"]) / max(agora - marca["quando"], 1e-6)
            marca.update(quando=agora, bytes=feito)
            fracao = (feito / total * 1000) if total else 0
            self._na_tela(lambda: (
                self.barra.configure(value=fracao),
                self._dizer(t("lan.busy.downloading",
                              done=tamanho_legivel(feito),
                              total=tamanho_legivel(total),
                              speed=tamanho_legivel(int(velocidade)))),
            ))

        def extraindo(feito: int, total: int) -> None:
            if feito % 25 and feito != total:
                return
            self._na_tela(lambda: (
                self.barra.configure(value=feito / max(total, 1) * 1000),
                self._dizer(t("lan.busy.extracting",
                              percent=int(feito / max(total, 1) * 100))),
            ))

        def trabalho() -> None:
            try:
                fonte.baixar(
                    fonte.url_do_asset(pacote.arquivo, self.manifesto.tag or None),
                    alvo, sha256=pacote.sha256, total_esperado=pacote.bytes,
                    progresso=andamento, cancelar=self._cancelar.is_set,
                )
                self._na_tela(lambda: self._dizer(t("lan.busy.verifying")))
                instalacao.extrair(alvo, chave, self.base, progresso=extraindo)
            except InterruptedError:
                self._na_tela(lambda: (self._dizer(t("lan.msg.cancelled")),
                                       self._terminou()))
                return
            except fonte.ArquivoCorrompido:
                self._na_tela(lambda: (self._dizer(t("lan.msg.corrupt"), VERMELHO),
                                       self._terminou()))
                return
            except instalacao.InstalacaoOcupada:
                self._na_tela(lambda: (self._dizer(t("lan.msg.running"), VERMELHO),
                                       self._terminou()))
                return
            except (OSError, fonte.FalhaDeRede) as erro:
                recado = str(erro)
                self._na_tela(lambda: (
                    self._dizer(t("lan.msg.failed", reason=recado), VERMELHO),
                    self._terminou()))
                return
            finally:
                # O zip já virou pasta instalada: guardá-lo dobraria o espaço
                # em disco por nada.
                try:
                    alvo.unlink(missing_ok=True)
                except OSError:
                    pass

            versao = self.manifesto.versao if self.manifesto else ""
            self._na_tela(lambda: self._instalou(qual, chave, versao))

        self._em_thread(trabalho)

    def _instalou(self, qual: str, chave: str, versao: str) -> None:
        self.estado.instalados[chave] = {"versao": versao}
        self.estado.edicao = qual
        self.estado.salvar(self.base)
        self._terminou()
        self._dizer(t("lan.msg.installed", version=versao), VERDE)
        self._abrir(qual, chave)


def executar() -> int:
    """Abre o launcher. Devolve o código de saída do processo."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    Janela().mainloop()
    return 0
