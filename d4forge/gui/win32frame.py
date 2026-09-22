"""Moldura nativa do Windows por baixo de uma janela sem barra de título.

A barra de título do app é desenhada pelo Qt, mas quem manda na JANELA continua
sendo o Windows. É essa a diferença entre "parece um app" e "é um app": arrastar
para a borda encaixa (Aero Snap), Win+Seta funciona, o Snap Layouts aparece ao
pousar no botão de maximizar, sacudir minimiza o resto, as bordas redimensionam
com o cursor certo, a sombra é a mesma das outras janelas e Alt+Espaço abre o
menu do sistema.

A implementação anterior reimplementava arrastar e redimensionar na mão, com
`mouseMoveEvent`. Funciona para mover a janela e para nada mais: o Windows não
sabe que aquilo é um arrasto de título, então não oferece encaixe; não sabe que
aquilo é uma borda, então não mostra o cursor certo nem deixa puxar de fora.

A receita daqui é a que Chrome, VS Code e o Terminal do Windows usam: MANTER
`WS_THICKFRAME | WS_CAPTION` — é deles que vêm todos os comportamentos acima — e
devolver zero em `WM_NCCALCSIZE`, que apaga o DESENHO da moldura sem tirar a
moldura. O resto é `WM_NCHITTEST` respondendo ao Windows o que é borda, o que é
título e o que é conteúdo.

Referência: WM_NCCALCSIZE, WM_NCHITTEST e DwmExtendFrameIntoClientArea na
documentação da Microsoft.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger(__name__)

# Mensagens da área não-cliente.
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCACTIVATE = 0x0086
WM_NCMOUSEMOVE = 0x00A0
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCMOUSELEAVE = 0x02A2
WM_DWMCOMPOSITIONCHANGED = 0x031E

# Resultados de WM_NCHITTEST.
HTCLIENT = 1
HTCAPTION = 2
HTMAXBUTTON = 9
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

# Estilos de janela. WS_CAPTION e WS_THICKFRAME são o coração disto: sem eles o
# Windows trata a janela como um popup e nenhum gesto de janela funciona.
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_NOOWNERZORDER = 0x0200

SM_CXSIZEFRAME = 32
SM_CYSIZEFRAME = 33
SM_CXPADDEDBORDER = 92

MONITOR_DEFAULTTONEAREST = 2

# Barra de tarefas que se esconde sozinha.
ABM_GETSTATE = 0x00000004
ABM_GETAUTOHIDEBAREX = 0x0000000B
ABS_AUTOHIDE = 0x00000001
ABE_LEFT, ABE_TOP, ABE_RIGHT, ABE_BOTTOM = 0, 1, 2, 3

# Cantos arredondados e cor da borda: Windows 11. Em versões anteriores as
# chamadas falham em silêncio, que é o comportamento desejado.
DWMWA_BORDER_COLOR = 34
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

DISPONIVEL = sys.platform == "win32"


def _int_do_ponteiro(valor) -> int:
    """Endereço inteiro a partir do que o PySide entrega em `nativeEvent`."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return int(getattr(valor, "__int__", lambda: 0)())


if DISPONIVEL:  # pragma: no branch - o app é Windows-only
    LRESULT = ctypes.c_ssize_t

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    class MARGINS(ctypes.Structure):
        _fields_ = [
            ("cxLeftWidth", ctypes.c_int),
            ("cxRightWidth", ctypes.c_int),
            ("cyTopHeight", ctypes.c_int),
            ("cyBottomHeight", ctypes.c_int),
        ]

    class NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    class APPBARDATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uCallbackMessage", wintypes.UINT),
            ("uEdge", wintypes.UINT),
            ("rc", wintypes.RECT),
            ("lParam", wintypes.LPARAM),
        ]

    # GetWindowLongPtrW só existe no Python de 64 bits; no de 32 o nome é o
    # antigo e a largura do inteiro basta.
    _ler_estilo = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
    _gravar_estilo = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
    _ler_estilo.argtypes = [wintypes.HWND, ctypes.c_int]
    _ler_estilo.restype = ctypes.c_ssize_t
    _gravar_estilo.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _gravar_estilo.restype = ctypes.c_ssize_t

    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    _user32.ScreenToClient.restype = wintypes.BOOL
    _user32.IsZoomed.argtypes = [wintypes.HWND]
    _user32.IsZoomed.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    _user32.DefWindowProcW.restype = LRESULT
    _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.MonitorFromWindow.restype = wintypes.HANDLE
    _user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
    _user32.GetMonitorInfoW.restype = wintypes.BOOL
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetSystemMetrics.restype = ctypes.c_int

    _shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
    _shell32.SHAppBarMessage.restype = ctypes.c_ssize_t

    _dwmapi.DwmExtendFrameIntoClientArea.argtypes = [
        wintypes.HWND, ctypes.POINTER(MARGINS),
    ]
    _dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
    _dwmapi.DwmSetWindowAttribute.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    ]
    _dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long

    # Windows 10 1607 em diante. Sem elas o app ainda roda, só perde precisão
    # em telas com escala diferente de 100%.
    _metrica_por_dpi = getattr(_user32, "GetSystemMetricsForDpi", None)
    if _metrica_por_dpi is not None:
        _metrica_por_dpi.argtypes = [ctypes.c_int, wintypes.UINT]
        _metrica_por_dpi.restype = ctypes.c_int
    _dpi_da_janela = getattr(_user32, "GetDpiForWindow", None)
    if _dpi_da_janela is not None:
        _dpi_da_janela.argtypes = [wintypes.HWND]
        _dpi_da_janela.restype = wintypes.UINT


def _coordenada(lparam: int, alto: bool) -> int:
    """Metade de um LPARAM como inteiro COM SINAL.

    Monitor à esquerda do principal tem x negativo, e ler os 16 bits sem sinal
    punha o cursor a 65 mil pixels de distância — a janela lá não redimensionava
    por borda nenhuma.
    """
    bruto = (lparam >> 16) if alto else lparam
    return ctypes.c_short(bruto & 0xFFFF).value


class MolduraNativa:
    """Faz a ponte entre as mensagens do Windows e a janela do Qt.

    A janela só precisa dizer, por `regiao`, o que há sob o cursor: borda de
    redimensionamento o próprio objeto resolve; "é título" e "é o botão de
    maximizar" só ela sabe.
    """

    # Faixa que redimensiona, em pixels lógicos. As janelas nativas escondem
    # essa faixa FORA da moldura; aqui ela mora dentro, então um valor grande
    # roubaria cliques do conteúdo. Seis é o que o olho aceita e a mão acerta.
    BORDA = 6
    # Canto com área maior que a borda, como nas janelas do sistema: puxar a
    # diagonal é o gesto mais difícil de acertar dos quatro.
    CANTO = 16

    def __init__(self, janela) -> None:
        self.janela = janela
        self.hwnd: int = 0
        self._sobre_maximizar = False

    # ------------------------------------------------------------ instalação
    def instalar(self, hwnd: int) -> bool:
        """Devolve o Windows ao comando da janela. Idempotente."""
        if not DISPONIVEL or not hwnd:
            return False
        self.hwnd = int(hwnd)
        try:
            estilo = _ler_estilo(self.hwnd, GWL_STYLE)
            _gravar_estilo(
                self.hwnd,
                GWL_STYLE,
                estilo
                | WS_CAPTION
                | WS_THICKFRAME
                | WS_SYSMENU
                | WS_MINIMIZEBOX
                # Sem WS_MAXIMIZEBOX o Windows trata a janela como popup e
                # maximiza POR CIMA da barra de tarefas.
                | WS_MAXIMIZEBOX,
            )
            self._pedir_sombra()
            self._pedir_visual_do_sistema()
            # Sem SWP_FRAMECHANGED o estilo novo só valeria no próximo
            # redimensionamento: é este aviso que dispara o WM_NCCALCSIZE que
            # apaga a moldura.
            _user32.SetWindowPos(
                self.hwnd, None, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                | SWP_NOOWNERZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
        except OSError:
            log.exception("nao consegui instalar a moldura nativa")
            self.hwnd = 0
            return False
        return True

    def _pedir_sombra(self) -> None:
        """A sombra e a linha fina em volta vêm do DWM, não de nós.

        Estender um pixel de moldura para dentro basta: o DWM volta a tratar a
        janela como emoldurada — e portanto a desenhar sombra — sem que sobre
        nada visível, porque os widgets do Qt pintam por cima.
        """
        margens = MARGINS(0, 0, 1, 0)
        _dwmapi.DwmExtendFrameIntoClientArea(self.hwnd, ctypes.byref(margens))

    def _pedir_visual_do_sistema(self) -> None:
        """Cantos arredondados e borda na cor da janela, no Windows 11.

        Em Windows 10 as duas chamadas devolvem erro e não fazem nada, que é
        exatamente o que se quer: lá o visual certo é o de cantos retos.
        """
        preferencia = ctypes.c_int(DWMWCP_ROUND)
        _dwmapi.DwmSetWindowAttribute(
            self.hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preferencia), ctypes.sizeof(preferencia),
        )
        cor = getattr(self.janela, "cor_da_borda", None)
        if cor is not None:
            # COLORREF é 0x00BBGGRR, ao contrário do hex de sempre.
            valor = ctypes.c_uint(
                (cor.blue() << 16) | (cor.green() << 8) | cor.red()
            )
            _dwmapi.DwmSetWindowAttribute(
                self.hwnd, DWMWA_BORDER_COLOR,
                ctypes.byref(valor), ctypes.sizeof(valor),
            )

    # --------------------------------------------------------------- estado
    def maximizada(self) -> bool:
        return bool(DISPONIVEL and self.hwnd and _user32.IsZoomed(self.hwnd))

    def _dpi(self) -> int:
        if _dpi_da_janela is not None:
            return _dpi_da_janela(self.hwnd) or 96
        return 96

    def _espessura_da_moldura(self) -> tuple[int, int]:
        """Quanto a moldura invisível avança para fora, em pixels físicos."""
        dpi = self._dpi()
        if _metrica_por_dpi is not None:
            sobra = _metrica_por_dpi(SM_CXPADDEDBORDER, dpi)
            return (
                _metrica_por_dpi(SM_CXSIZEFRAME, dpi) + sobra,
                _metrica_por_dpi(SM_CYSIZEFRAME, dpi) + sobra,
            )
        sobra = _user32.GetSystemMetrics(SM_CXPADDEDBORDER)
        return (
            _user32.GetSystemMetrics(SM_CXSIZEFRAME) + sobra,
            _user32.GetSystemMetrics(SM_CYSIZEFRAME) + sobra,
        )

    def _info_do_monitor(self) -> MONITORINFO | None:
        monitor = _user32.MonitorFromWindow(self.hwnd, MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return None
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        return info

    def _borda_com_barra_escondida(self) -> int | None:
        """Em que lado mora uma barra de tarefas que se esconde sozinha.

        Uma janela maximizada que cubra o último pixel daquele lado impede a
        barra de reaparecer — o Windows usa essa sobreposição como sinal.
        """
        dados = APPBARDATA()
        dados.cbSize = ctypes.sizeof(APPBARDATA)
        estado = _shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(dados))
        if not estado & ABS_AUTOHIDE:
            return None

        info = self._info_do_monitor()
        if info is None:
            return None
        for lado in (ABE_BOTTOM, ABE_TOP, ABE_LEFT, ABE_RIGHT):
            consulta = APPBARDATA()
            consulta.cbSize = ctypes.sizeof(APPBARDATA)
            consulta.uEdge = lado
            consulta.rc = info.rcMonitor
            if _shell32.SHAppBarMessage(
                ABM_GETAUTOHIDEBAREX, ctypes.byref(consulta)
            ):
                return lado
        return None

    # ------------------------------------------------------------- mensagens
    def processar(self, endereco: int) -> tuple[bool, int]:
        """(tratei?, resposta) para uma MSG do Windows."""
        if not self.hwnd:
            return False, 0
        msg = wintypes.MSG.from_address(endereco)
        # O mesmo gancho vê mensagens de menus e popups do Qt, que são janelas
        # próprias: mexer nelas apagaria a moldura delas também.
        if msg.hWnd != self.hwnd:
            return False, 0

        if msg.message == WM_NCCALCSIZE:
            return self._sem_moldura(msg)
        if msg.message == WM_NCHITTEST:
            return self._onde_esta_o_cursor(msg)
        if msg.message == WM_NCACTIVATE:
            # Sem moldura não há o que repintar, e o padrão do Windows pisca
            # uma faixa clara ao perder o foco. O -1 é o "não repinte".
            if _user32.IsIconic(self.hwnd):
                return False, 0
            return True, _user32.DefWindowProcW(
                self.hwnd, WM_NCACTIVATE, msg.wParam, -1
            )
        if msg.message == WM_DWMCOMPOSITIONCHANGED:
            self._pedir_sombra()
            return False, 0
        if msg.message in (WM_NCLBUTTONDOWN, WM_NCLBUTTONUP):
            return self._clique_no_botao_de_maximizar(msg)
        if msg.message == WM_NCMOUSELEAVE:
            self._destacar_maximizar(False)
            return False, 0
        return False, 0

    def _sem_moldura(self, msg) -> tuple[bool, int]:
        """Apaga o desenho da moldura mantendo a moldura.

        Devolver zero com o retângulo intacto faz a área do cliente ocupar a
        janela inteira: a barra de título nativa some e sobra o que o Qt pinta.
        """
        if not msg.wParam:
            return False, 0

        if not self.maximizada():
            return True, 0

        # Maximizada, o Windows estica a janela para FORA da tela pela
        # espessura da moldura — ela seria invisível, se houvesse moldura.
        # Sem descontar isso aqui, a interface vaza pelas quatro bordas do
        # monitor e ainda invade o monitor vizinho.
        params = NCCALCSIZE_PARAMS.from_address(msg.lParam)
        area = params.rgrc[0]
        largura, altura = self._espessura_da_moldura()
        area.left += largura
        area.top += altura
        area.right -= largura
        area.bottom -= altura

        lado = self._borda_com_barra_escondida()
        if lado == ABE_BOTTOM:
            area.bottom -= 1
        elif lado == ABE_TOP:
            area.top += 1
        elif lado == ABE_LEFT:
            area.left += 1
        elif lado == ABE_RIGHT:
            area.right -= 1
        return True, 0

    def _onde_esta_o_cursor(self, msg) -> tuple[bool, int]:
        borda, canto = self._faixas()
        janela = wintypes.RECT()
        if not _user32.GetWindowRect(self.hwnd, ctypes.byref(janela)):
            return False, 0

        na_tela = wintypes.POINT(
            _coordenada(msg.lParam, alto=False),
            _coordenada(msg.lParam, alto=True),
        )
        x = na_tela.x - janela.left
        y = na_tela.y - janela.top
        largura = janela.right - janela.left
        altura = janela.bottom - janela.top

        # Maximizada não se redimensiona, e manter a faixa ativa roubaria os
        # cliques da primeira linha de botões — justo a que encosta na borda.
        if not self.maximizada() and not self.janela.isFullScreen():
            esquerda = x < borda
            direita = x >= largura - borda
            topo = y < borda
            base = y >= altura - borda
            c_esq = x < canto
            c_dir = x >= largura - canto
            c_topo = y < canto
            c_base = y >= altura - canto

            if (topo and c_esq) or (esquerda and c_topo):
                return True, HTTOPLEFT
            if (topo and c_dir) or (direita and c_topo):
                return True, HTTOPRIGHT
            if (base and c_esq) or (esquerda and c_base):
                return True, HTBOTTOMLEFT
            if (base and c_dir) or (direita and c_base):
                return True, HTBOTTOMRIGHT
            if topo:
                return True, HTTOP
            if base:
                return True, HTBOTTOM
            if esquerda:
                return True, HTLEFT
            if direita:
                return True, HTRIGHT

        # Maximizada, a área do cliente NÃO começa no canto da janela: o
        # desconto da moldura em `_sem_moldura` a desloca. Perguntar em
        # coordenadas do cliente é o que mantém a barra de título no lugar
        # certo nos dois estados.
        no_cliente = wintypes.POINT(na_tela.x, na_tela.y)
        _user32.ScreenToClient(self.hwnd, ctypes.byref(no_cliente))
        regiao = self.janela.regiao_da_barra(no_cliente.x, no_cliente.y)
        if regiao == "maximizar":
            # HTMAXBUTTON é o que acende o Snap Layouts do Windows 11 ao pousar
            # o cursor. O preço é que o botão deixa de receber eventos do Qt:
            # o brilho do hover e o clique passam a vir daqui.
            self._destacar_maximizar(True)
            return True, HTMAXBUTTON
        self._destacar_maximizar(False)
        if regiao == "titulo":
            # Uma palavra só, e o Windows entrega arrastar com encaixe, duplo
            # clique para maximizar, Alt+Espaço, sacudir e o menu do botão
            # direito. Era isso que faltava.
            return True, HTCAPTION
        return True, HTCLIENT

    def _faixas(self) -> tuple[int, int]:
        """Borda e canto em pixels FÍSICOS, que é a régua do WM_NCHITTEST."""
        escala = self._dpi() / 96
        return round(self.BORDA * escala), round(self.CANTO * escala)

    def _clique_no_botao_de_maximizar(self, msg) -> tuple[bool, int]:
        if msg.wParam != HTMAXBUTTON:
            return False, 0
        if msg.message == WM_NCLBUTTONUP:
            self.janela.toggle_maximize()
        # Engolido nos dois casos: deixar o padrão do Windows ver o aperto faz
        # ele desenhar o botão de maximizar DELE por cima do nosso.
        return True, 0

    def _destacar_maximizar(self, aceso: bool) -> None:
        if aceso == self._sobre_maximizar:
            return
        self._sobre_maximizar = aceso
        self.janela.destacar_maximizar(aceso)
