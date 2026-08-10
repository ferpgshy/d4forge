"""Aparência da janela.

Paleta tirada da própria interface do jogo: pergaminho escuro, dourado
envelhecido nos títulos, vermelho seco nas ações. Nada de cinza de sistema — a
janela fica lado a lado com o Diablo IV e destoar cansa a vista.
"""

from __future__ import annotations

FUNDO = "#14110d"
FUNDO_CARTAO = "#1c1813"
FUNDO_CAMPO = "#0d0b08"
BORDA = "#3a3128"
BORDA_CLARA = "#4e4235"
TEXTO = "#ddd3c2"
TEXTO_FRACO = "#8a8073"
DOURADO = "#c9a463"
DOURADO_FRACO = "#8d7442"
VERMELHO = "#8c2f26"
VERMELHO_CLARO = "#a83c31"
VERDE = "#5f7d4a"

QSS = f"""
QWidget {{
    background: {FUNDO};
    color: {TEXTO};
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}}

/* Rótulos e caixas de marcar herdavam o fundo da JANELA e apareciam como
   faixas escuras dentro dos cartões, que são mais claros. */
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
QLabel[role="hint"] {{ color: {TEXTO_FRACO}; }}
QLabel[role="accent"] {{ color: {DOURADO}; }}
QLabel[role="error"] {{ color: {VERMELHO_CLARO}; }}

/* -------------------------------------------------- moldura própria */
QWidget#shell {{
    background: {FUNDO};
    border: 1px solid {BORDA_CLARA};
}}

/* Cor chapada, e nao gradiente: entre #1f1a13 e #262019 ha' sete niveis de
   diferenca, e espalha-los por mil pixels rendia degraus visiveis - parecia um
   retangulo mais claro colado no meio do cabecalho. */
QFrame#header {{
    background: #221c15;
    border: none;
    border-bottom: 1px solid {DOURADO_FRACO};
}}
QLabel#brand {{
    color: {DOURADO};
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 3px;
    background: transparent;
}}
QLabel#brandSub {{
    color: {TEXTO_FRACO};
    font-size: 11px;
    letter-spacing: 1px;
    background: transparent;
}}

/* Botões da barra de título */
QPushButton[titlebar="true"] {{
    background: transparent;
    border: none;
    border-radius: 0;
    color: {TEXTO_FRACO};
    font-size: 15px;
    font-family: "Segoe MDL2 Assets", "Segoe UI Symbol", sans-serif;
    padding: 0;
    min-width: 44px;
    max-width: 44px;
    min-height: 34px;
    max-height: 34px;
}}
QPushButton[titlebar="true"]:hover {{ background: #33291f; color: {TEXTO}; }}
QPushButton#btnClose:hover {{ background: {VERMELHO}; color: #ffffff; }}

/* -------------------------------------------------- abas */
QTabWidget::pane {{ border: none; background: {FUNDO}; }}
QTabBar::tab {{
    background: transparent;
    color: {TEXTO_FRACO};
    padding: 10px 22px;
    margin-right: 4px;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}}
QTabBar::tab:hover {{ color: {TEXTO}; }}
QTabBar::tab:selected {{
    color: {DOURADO};
    border-bottom: 2px solid {DOURADO};
}}

/* -------------------------------------------------- cartões */
QGroupBox {{
    background: {FUNDO_CARTAO};
    border: 1px solid {BORDA};
    border-radius: 6px;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {DOURADO};
    letter-spacing: 1px;
}}

/* -------------------------------------------------- botões */
QPushButton {{
    background: #2a231b;
    border: 1px solid {BORDA_CLARA};
    border-radius: 4px;
    padding: 8px 16px;
    color: {TEXTO};
}}
QPushButton:hover {{ background: #362d22; border-color: {DOURADO_FRACO}; }}
QPushButton:pressed {{ background: #221c15; }}
QPushButton:disabled {{ color: #5c5449; border-color: #2a241d; background: #1a1610; }}

QPushButton#start {{
    background: {VERMELHO};
    border: 1px solid {VERMELHO_CLARO};
    font-size: 15px;
    font-weight: 600;
    padding: 12px 20px;
    letter-spacing: 1px;
}}
QPushButton#start:hover {{ background: {VERMELHO_CLARO}; }}
QPushButton#stop {{
    background: #3a3118;
    border: 1px solid {DOURADO_FRACO};
    font-size: 15px;
    font-weight: 600;
    padding: 12px 20px;
    letter-spacing: 1px;
}}
QPushButton#stop:hover {{ background: #4a3f1f; }}
QPushButton#globe {{
    background: transparent;
    border: 1px solid {BORDA};
    border-radius: 14px;
    padding: 0 12px;
    color: {TEXTO_FRACO};
    font-size: 12px;
    text-align: center;
}}
/* Nao usamos setMenu(), mas garantimos que nenhuma seta nativa apareca. */
QPushButton#globe::menu-indicator {{ image: none; width: 0; }}
QPushButton#globe:hover {{ color: {DOURADO}; border-color: {DOURADO_FRACO}; }}

/* -------------------------------------------------- campos */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {FUNDO_CAMPO};
    border: 1px solid {BORDA};
    border-radius: 4px;
    padding: 6px 8px;
    selection-background-color: {DOURADO_FRACO};
}}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border-color: {DOURADO_FRACO};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {FUNDO_CAMPO};
    border: 1px solid {BORDA_CLARA};
    selection-background-color: #3a3126;
    selection-color: {DOURADO};
    outline: none;
}}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {BORDA_CLARA};
    background: {FUNDO_CAMPO};
}}
QCheckBox::indicator {{ border-radius: 3px; }}
/* Metade da largura: o quadrado vira circulo. */
QRadioButton::indicator {{ border-radius: 8px; }}
/* Sem estas duas regras o indicador MARCADO some. Basta a folha de estilo
   tocar o widget para o Qt parar de desenhar a versao nativa, e ai um estado
   sem regra nao e' desenhado por ninguem - o radio selecionado ficava
   invisivel, que e' justamente o unico que precisa aparecer. */
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {DOURADO_FRACO};
    border-color: {DOURADO};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {DOURADO_FRACO};
}}
QCheckBox:disabled, QRadioButton:disabled {{ color: {TEXTO_FRACO}; }}

/* -------------------------------------------------- tabelas e log */
QPlainTextEdit {{
    background: {FUNDO_CAMPO};
    border: 1px solid {BORDA};
    border-radius: 4px;
    padding: 6px;
    font-family: Consolas, monospace;
    font-size: 12px;
}}
QTableWidget {{
    background: {FUNDO_CAMPO};
    border: 1px solid {BORDA};
    border-radius: 4px;
    gridline-color: #241e18;
    selection-background-color: #3a3126;
    selection-color: {DOURADO};
}}
QHeaderView::section {{
    background: #241e18;
    color: {TEXTO_FRACO};
    padding: 6px;
    border: none;
    border-right: 1px solid {FUNDO};
}}

QScrollBar:vertical {{ background: {FUNDO}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {BORDA_CLARA}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {DOURADO_FRACO}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: {FUNDO}; height: 10px; }}
QScrollBar::handle:horizontal {{
    background: {BORDA_CLARA}; border-radius: 5px; min-width: 30px;
}}

/* -------------------------------------------------- menus */
QMenu {{
    background: {FUNDO_CARTAO};
    border: 1px solid {BORDA_CLARA};
    border-radius: 4px;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 24px 8px 16px;
    border-radius: 3px;
    color: {TEXTO};
}}
QMenu::item:selected {{
    background: #3a3126;
    color: {DOURADO};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDA};
    margin: 4px 8px;
}}

/* ------------------------------------------- painel de progresso */
QFrame#metric {{
    background: {FUNDO_CAMPO};
    border: 1px solid {BORDA};
    border-radius: 5px;
}}
QTableWidget#attempts {{
    alternate-background-color: #171310;
    font-size: 12px;
}}
QTableWidget#attempts::item {{ padding: 5px 8px; }}
/* Botao que parece link: abre os detalhes tecnicos sem pedir destaque. */
QToolButton[role="link"] {{
    background: transparent;
    border: none;
    color: {TEXTO_FRACO};
    padding: 2px 4px;
    font-size: 12px;
}}
QToolButton[role="link"]:hover {{ color: {DOURADO}; }}
QToolButton[role="link"]:checked {{ color: {DOURADO}; }}

QToolTip {{
    background: #241e18;
    color: {TEXTO};
    border: 1px solid {DOURADO_FRACO};
    padding: 6px;
}}
"""

# Cores do estado no painel, para não espalhar hex pelo código.
COR_ESTADO = {
    "idle": TEXTO_FRACO,
    "running": DOURADO,
    "stopping": TEXTO_FRACO,
    "found": VERDE,
}
