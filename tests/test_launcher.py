"""O launcher: baixar, conferir, instalar e trocar a si mesmo.

Nada aqui fala com o GitHub. Sobe um servidor HTTP local que responde
`Range` igual ao CDN de releases (medido: **206**), porque é justamente o
comportamento de retomada que precisa ser testado — e testar contra a
internet seria testar a internet.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import sys
import threading
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from launcher import autoupdate, escolha, fonte, instalacao  # noqa: E402

# --------------------------------------------------------------- servidor


class _Servidor(http.server.BaseHTTPRequestHandler):
    """Serve uma pasta e entende `Range` — o resto do stdlib não entende."""

    pasta: Path

    def log_message(self, *_a) -> None:  # silêncio nos testes
        pass

    def _arquivo(self) -> Path:
        return self.pasta / self.path.lstrip("/")

    def do_GET(self) -> None:  # noqa: N802 - assinatura do http.server
        alvo = self._arquivo()
        if not alvo.is_file():
            self.send_error(404)
            return
        dados = alvo.read_bytes()
        faixa = self.headers.get("Range")
        if faixa and faixa.startswith("bytes="):
            inicio = int(faixa.split("=", 1)[1].split("-")[0])
            dados = dados[inicio:]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {inicio}-/*")
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)


@pytest.fixture
def servidor(tmp_path):
    """Devolve (url_base, pasta_servida)."""
    servida = tmp_path / "servidor"
    servida.mkdir()
    manipulador = type("H", (_Servidor,), {"pasta": servida})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manipulador)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", servida
    httpd.shutdown()
    httpd.server_close()


def _zip_de_app(destino: Path, nome_exe: str = "d4forge.exe") -> Path:
    """Um pacote plausível: pasta no topo, um exe e o marcador de edição."""
    with zipfile.ZipFile(destino, "w") as zf:
        zf.writestr(f"d4forge/{nome_exe}", b"MZ executavel de mentira")
        zf.writestr("d4forge/_internal/d4forge/resources/edicao.txt", "completa")
        zf.writestr("d4forge/_internal/base_library.zip", b"x" * 500)
    return destino


# --------------------------------------------------------------- versões
@pytest.mark.parametrize(
    "a, b, esperado",
    [
        ("1.6.3", "1.6.2", 1),
        ("1.6.2", "1.6.2", 0),
        ("1.6.2", "1.6.10", -1),   # 10 é maior que 2, não menor
        ("v1.7.0", "1.6.9", 1),    # o "v" da tag não conta
        ("1.7", "1.7.0", 0),       # campo ausente vale zero
        ("", "1.0.0", -1),
    ],
)
def test_comparar_versoes(a, b, esperado):
    assert fonte.comparar_versoes(a, b) == esperado


def test_uma_edicao_nao_e_um_pacote():
    """`completa` e `forge` saem do MESMO download — o marcador decide."""
    manifesto = fonte.ler_manifesto({
        "versao": "1.6.2",
        "pacotes": {
            "completo": {"arquivo": "c.zip", "edicoes": ["completa", "forge"]},
            "autoskill": {"arquivo": "a.zip", "edicoes": ["autoskill"]},
        },
    })
    assert manifesto.pacote_da_edicao("completa").chave == "completo"
    assert manifesto.pacote_da_edicao("forge").chave == "completo"
    assert manifesto.pacote_da_edicao("autoskill").chave == "autoskill"
    assert manifesto.pacote_da_edicao("inventada") is None


def test_manifesto_aceita_campos_que_ainda_nao_existem():
    """Um launcher antigo não pode quebrar com um manifesto novo."""
    manifesto = fonte.ler_manifesto({"versao": "9.9.9", "novidade": {"a": 1}})
    assert manifesto.versao == "9.9.9"
    assert manifesto.pacotes == {}
    assert manifesto.launcher_versao == ""


def test_manifesto_vem_do_servidor(servidor, tmp_path):
    url, pasta = servidor
    (pasta / fonte.MANIFESTO).write_text(json.dumps({
        "versao": "1.7.0", "tag": "v1.7.0",
        "launcher": {"versao": "1.1.0", "sha256": "abc"},
        "pacotes": {"completo": {"arquivo": "c.zip", "bytes": 10,
                                 "edicoes": ["completa", "forge"]}},
    }), encoding="utf-8")

    manifesto = fonte.buscar_manifesto(url)
    assert manifesto.versao == "1.7.0"
    assert manifesto.launcher_versao == "1.1.0"
    assert manifesto.pacotes["completo"].edicoes == ("completa", "forge")


# --------------------------------------------------------------- download
def test_baixa_e_confere_o_sha256(servidor, tmp_path):
    url, pasta = servidor
    conteudo = os.urandom(300_000)
    (pasta / "app.zip").write_bytes(conteudo)
    soma = hashlib.sha256(conteudo).hexdigest()

    vistos: list[tuple[int, int]] = []
    destino = fonte.baixar(f"{url}/app.zip", tmp_path / "app.zip",
                           sha256=soma, progresso=lambda f, t: vistos.append((f, t)))

    assert destino.read_bytes() == conteudo
    assert vistos and vistos[-1][0] == len(conteudo)
    assert not (tmp_path / "app.zip.parcial").exists()


def test_o_arquivo_corrompido_nao_vira_instalacao(servidor, tmp_path):
    """Regressão de segurança: um zip trocado no meio do caminho não passa."""
    url, pasta = servidor
    (pasta / "app.zip").write_bytes(b"conteudo diferente do anunciado")

    with pytest.raises(fonte.ArquivoCorrompido):
        fonte.baixar(f"{url}/app.zip", tmp_path / "app.zip", sha256="0" * 64)

    # E o lixo não fica: retomar de cima dele repetiria o erro para sempre.
    assert not (tmp_path / "app.zip").exists()
    assert not (tmp_path / "app.zip.parcial").exists()


def test_retoma_de_onde_parou(servidor, tmp_path):
    """O CDN do GitHub responde 206; o launcher tem de aproveitar isso."""
    url, pasta = servidor
    conteudo = os.urandom(200_000)
    (pasta / "app.zip").write_bytes(conteudo)
    soma = hashlib.sha256(conteudo).hexdigest()

    # Simula um download interrompido na metade.
    metade = len(conteudo) // 2
    (tmp_path / "app.zip.parcial").write_bytes(conteudo[:metade])

    baixados: list[int] = []
    destino = fonte.baixar(f"{url}/app.zip", tmp_path / "app.zip", sha256=soma,
                           progresso=lambda f, _t: baixados.append(f))

    assert destino.read_bytes() == conteudo
    # Começou da metade, e não do zero: é isso que o Range compra.
    assert baixados[0] == metade


def test_cancelar_interrompe(servidor, tmp_path):
    url, pasta = servidor
    (pasta / "app.zip").write_bytes(os.urandom(400_000))

    with pytest.raises(InterruptedError):
        fonte.baixar(f"{url}/app.zip", tmp_path / "app.zip",
                     cancelar=lambda: True)


# --------------------------------------------------------------- instalar
def test_instala_e_acha_o_executavel(tmp_path):
    zipado = _zip_de_app(tmp_path / "c.zip")
    pasta = instalacao.extrair(zipado, "completo", tmp_path)

    assert pasta == tmp_path / "d4forge-completo"
    assert instalacao.instalado("completo", tmp_path)
    assert instalacao.executavel_em(pasta).name == "d4forge.exe"
    # Nada de pasta temporária esquecida no disco.
    assert not list(tmp_path.glob("*.novo"))
    assert not list(tmp_path.glob("*.antigo"))


def test_atualizar_preserva_a_pasta_data(tmp_path):
    """Regressão cara: o build já apagou as binds de quem usa isto."""
    instalacao.extrair(_zip_de_app(tmp_path / "c.zip"), "completo", tmp_path)

    dados = tmp_path / "d4forge-completo" / "data"
    dados.mkdir(parents=True, exist_ok=True)
    (dados / "autoskill.json").write_text('{"slot1": "Q"}', encoding="utf-8")

    # Uma versão nova chega, com um `data/` próprio dentro do zip.
    novo = tmp_path / "c2.zip"
    with zipfile.ZipFile(novo, "w") as zf:
        zf.writestr("d4forge/d4forge.exe", b"MZ versao nova")
        zf.writestr("d4forge/data/autoskill.json", '{"slot1": "PADRAO"}')
    instalacao.extrair(novo, "completo", tmp_path)

    assert (dados / "autoskill.json").read_text(encoding="utf-8") == '{"slot1": "Q"}'
    assert (tmp_path / "d4forge-completo" / "d4forge.exe").read_bytes() == b"MZ versao nova"


def test_marcar_edicao_grava_dentro_do_pacote(tmp_path):
    """Quem cria atalho para o .exe não passa variável de ambiente."""
    pasta = instalacao.extrair(_zip_de_app(tmp_path / "c.zip"), "completo", tmp_path)
    instalacao.marcar_edicao(pasta, "forge")
    assert (pasta / instalacao.MARCADOR).read_text(encoding="utf-8") == "forge"


def test_marcar_edicao_nao_estoura_em_pacote_sem_marcador(tmp_path):
    (tmp_path / "vazia").mkdir()
    instalacao.marcar_edicao(tmp_path / "vazia", "forge")  # não pode levantar


def test_limpar_restos_varre_o_que_sobrou(tmp_path):
    (tmp_path / "d4forge-completo.novo").mkdir()
    (tmp_path / "d4forge-completo.antigo").mkdir()
    (tmp_path / "c.zip.parcial").write_bytes(b"x")
    (tmp_path / "d4forge-completo").mkdir()

    assert instalacao.limpar_restos(tmp_path) == 3
    assert (tmp_path / "d4forge-completo").is_dir()   # o bom fica


def test_estado_sobrevive_ao_fechamento(tmp_path):
    estado = instalacao.Estado(instalados={"completo": {"versao": "1.6.2"}},
                               edicao="forge", idioma="en")
    estado.salvar(tmp_path)

    lido = instalacao.Estado.carregar(tmp_path)
    assert lido.versao_de("completo") == "1.6.2"
    assert lido.edicao == "forge"
    assert lido.idioma == "en"


def test_estado_corrompido_nao_derruba_o_launcher(tmp_path):
    (tmp_path / instalacao.ESTADO).write_text("{isto nao e json", encoding="utf-8")
    assert instalacao.Estado.carregar(tmp_path).instalados == {}


# --------------------------------------------------------------- self-update
def test_o_launcher_se_troca_e_guarda_o_antigo(tmp_path):
    """No Windows o exe em uso não se apaga, mas se renomeia — é o truque."""
    atual = tmp_path / "d4forge-launcher.exe"
    atual.write_bytes(b"launcher v1")
    novo = tmp_path / "baixado.exe"
    novo.write_bytes(b"launcher v2")

    aposentado = autoupdate.trocar(novo, atual=atual, reiniciar=False)

    assert atual.read_bytes() == b"launcher v2"
    assert aposentado.read_bytes() == b"launcher v1"
    assert autoupdate.APOSENTADO in aposentado.name
    assert autoupdate.limpar_aposentados(tmp_path) == 1
    assert atual.exists()


def test_o_nome_do_aposentado_nao_e_fixo(tmp_path):
    """Nome fixo trava toda atualização seguinte se uma janela o segurar."""
    atual = tmp_path / "d4forge-launcher.exe"
    atual.write_bytes(b"v1")
    (tmp_path / "novo.exe").write_bytes(b"v2")
    primeiro = autoupdate.trocar(tmp_path / "novo.exe", atual=atual,
                                 reiniciar=False)
    assert str(os.getpid()) in primeiro.name


def test_so_troca_o_launcher_se_a_versao_for_maior():
    from launcher import __version__ as atual

    assert not autoupdate.ha_launcher_mais_novo(
        fonte.ler_manifesto({"launcher": {"versao": atual}}))
    assert not autoupdate.ha_launcher_mais_novo(fonte.ler_manifesto({}))
    assert autoupdate.ha_launcher_mais_novo(
        fonte.ler_manifesto({"launcher": {"versao": "99.0.0"}}))


# --------------------------------------------------------------- contrato
def test_todo_pacote_do_release_atende_alguma_edicao():
    """Se uma edição nova aparecer sem download, isto acusa."""
    empacotar = pytest.importorskip("empacotar_release")
    from d4forge import edicao

    atendidas = [e for _, edicoes in empacotar.PACOTES.values() for e in edicoes]
    assert sorted(atendidas) == sorted(edicao.TODAS)
    assert len(atendidas) == len(set(atendidas)), "uma edição em dois pacotes"


def test_os_textos_do_launcher_existem_nos_dois_idiomas():
    from d4forge import i18n

    pt = {k for k in i18n.STRINGS["pt-BR"] if k.startswith("lan.")}
    en = {k for k in i18n.STRINGS["en"] if k.startswith("lan.")}
    assert pt == en and pt, "os textos do launcher saíram do par"


# --------------------------------------------------------------- escolha
def _manifesto(versao="1.6.2", completo=147_000_000, autoskill=105_000_000):
    return fonte.ler_manifesto({
        "versao": versao, "tag": f"v{versao}",
        "pacotes": {
            "completo": {"arquivo": "c.zip", "bytes": completo,
                         "edicoes": ["completa", "forge"]},
            "autoskill": {"arquivo": "a.zip", "bytes": autoskill,
                          "edicoes": ["autoskill"]},
        },
    })


NADA_INSTALADO = lambda _chave: False          # noqa: E731
TUDO_INSTALADO = lambda _chave: True           # noqa: E731


@pytest.mark.parametrize("qual", ["completa", "forge", "autoskill"])
def test_sem_nada_no_disco_toda_edicao_oferece_baixar(qual):
    situacao = escolha.situacao(qual, _manifesto(), {}, NADA_INSTALADO)
    assert situacao.estado == escolha.NAO_INSTALADO
    assert situacao.precisa_baixar and situacao.clicavel
    assert situacao.bytes > 0


def test_o_tamanho_mostrado_e_o_do_pacote_daquela_edicao():
    """O AutoSkill não pode anunciar o peso do pacote completo."""
    manifesto = _manifesto()
    completa = escolha.situacao("completa", manifesto, {}, NADA_INSTALADO)
    autoskill = escolha.situacao("autoskill", manifesto, {}, NADA_INSTALADO)
    assert completa.bytes == 147_000_000
    assert autoskill.bytes == 105_000_000


def test_instalar_a_completa_ja_deixa_a_forge_pronta():
    """As duas saem do mesmo zip — baixar de novo seria cobrar duas vezes."""
    instalados = {"completo": {"versao": "1.6.2"}}
    so_completo = lambda chave: chave == "completo"   # noqa: E731

    for qual in ("completa", "forge"):
        situacao = escolha.situacao(qual, _manifesto(), instalados, so_completo)
        assert situacao.estado == escolha.PRONTO
        assert not situacao.precisa_baixar

    # E o AutoSkill continua sendo um download à parte.
    autoskill = escolha.situacao("autoskill", _manifesto(), instalados,
                                 so_completo)
    assert autoskill.estado == escolha.NAO_INSTALADO


def test_versao_publicada_maior_vira_atualizacao():
    situacao = escolha.situacao("completa", _manifesto("1.7.0"),
                                {"completo": {"versao": "1.6.2"}},
                                TUDO_INSTALADO)
    assert situacao.estado == escolha.ATUALIZAVEL
    assert situacao.versao == "1.7.0"
    assert situacao.precisa_baixar


def test_versao_igual_nao_inventa_atualizacao():
    situacao = escolha.situacao("completa", _manifesto("1.6.2"),
                                {"completo": {"versao": "1.6.2"}},
                                TUDO_INSTALADO)
    assert situacao.estado == escolha.PRONTO


def test_instalacao_sem_versao_anotada_nao_vira_atualizacao():
    """Estado perdido não pode empurrar 141 MB de download na cara."""
    situacao = escolha.situacao("completa", _manifesto("1.7.0"), {},
                                TUDO_INSTALADO)
    assert situacao.estado == escolha.PRONTO


def test_offline_ainda_abre_o_que_esta_no_disco():
    """Sem GitHub o launcher não pode virar uma tela morta."""
    instalados = {"completo": {"versao": "1.6.2"}}
    so_completo = lambda chave: chave == "completo"   # noqa: E731

    pronta = escolha.situacao("forge", None, instalados, so_completo)
    assert pronta.estado == escolha.PRONTO and pronta.clicavel

    # O que não está no disco não promete o que não pode cumprir: sem
    # manifesto não há nem tamanho nem endereço.
    ausente = escolha.situacao("autoskill", None, instalados, so_completo)
    assert ausente.estado == escolha.INDISPONIVEL
    assert not ausente.clicavel


def test_edicao_que_nenhum_pacote_atende_fica_indisponivel():
    magro = fonte.ler_manifesto({
        "versao": "2.0.0",
        "pacotes": {"autoskill": {"arquivo": "a.zip", "bytes": 1,
                                  "edicoes": ["autoskill"]}},
    })
    situacao = escolha.situacao("completa", magro, {}, NADA_INSTALADO)
    assert situacao.estado == escolha.INDISPONIVEL
    assert situacao.chave is None


# --------------------------------------------------------------- a janela
def test_a_janela_monta_os_tres_cartoes(tmp_path, monkeypatch):
    """Fumaça: a tela existe, mostra as três edições e fecha limpa.

    Uma janela só, e no fim do arquivo: criar e destruir vários `tk.Tk()` no
    mesmo processo falha de forma intermitente no Windows (medido: 1 em 4).
    A regra de verdade está em `escolha`, testada acima sem tela nenhuma.
    """
    tk = pytest.importorskip("tkinter")
    from launcher import ui

    monkeypatch.setattr(fonte, "buscar_manifesto",
                        lambda *_a, **_k: _manifesto())
    try:
        janela = ui.Janela(base=tmp_path)
    except tk.TclError as erro:                  # máquina sem interface
        pytest.skip(f"sem tkinter utilizável: {erro}")

    try:
        janela.withdraw()
        assert list(janela.cartoes) == ["completa", "forge", "autoskill"]
        janela.manifesto = _manifesto()
        janela._pintar_cartoes()
        for qual in janela.cartoes:
            assert janela.cartoes[qual].nome.cget("text")
            assert janela.cartoes[qual].botao.cget("text")

        antes = janela.subtitulo.cget("text")
        janela._trocar_idioma()
        assert janela.subtitulo.cget("text") != antes
        assert instalacao.Estado.carregar(tmp_path).idioma

        # Regressão: a thread de trabalho chamava `after()` direto, e o
        # tkinter recusa isso de fora ("main thread is not in main loop").
        # O recado tem de voltar pela fila, e só a interface o executa.
        def de_fora():
            janela._na_tela(lambda: janela._dizer("recado de outra thread"))

        trabalhadora = threading.Thread(target=de_fora)
        trabalhadora.start()
        trabalhadora.join()
        assert janela.recado.cget("text") != "recado de outra thread"
        janela._bombear()
        assert janela.recado.cget("text") == "recado de outra thread"
    finally:
        janela.destroy()
