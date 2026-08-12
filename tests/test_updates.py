"""Proves the update check answers correctly and never breaks the app.

Two things are worth guarding here.

The first is the comparison. It runs on a tag somebody typed by hand at release
time, and getting it wrong is invisible in the good case and permanent in the
bad one: either nobody is ever told about a new build, or everybody is told
forever about the one they already have.

The second is failure. This code runs at startup on machines that are offline,
behind a corporate proxy, or throttled by GitHub. It must return "no answer"
and let the program open — never raise, never hang.

No network is touched: the HTTP call is replaced by a fake.
"""
import io
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import updates

falhas = []


def conferir(label, obtido, esperado):
    ok = obtido == esperado
    if not ok:
        falhas.append(label)
    print(f"  {'ok ' if ok else 'ERRO'} {label:<52} {obtido!r}"
          + ("" if ok else f"  (esperado {esperado!r})"))


print("lendo a tag, com e sem 'v', com e sem sufixo:")
conferir("v2.1.0", updates._numbers("v2.1.0"), (2, 1, 0))
conferir("2.1.0", updates._numbers("2.1.0"), (2, 1, 0))
conferir("V2.1.0-beta.2", updates._numbers("V2.1.0-beta.2"), (2, 1, 0))
conferir("espaco em volta", updates._numbers("  v3.0  "), (3, 0))
conferir("tag sem numero", updates._numbers("latest"), ())

print("\ncomparando versoes (a de cima e mais nova?):")
conferir("2.1.0 > 2.0.0", updates.is_newer("2.1.0", "2.0.0"), True)
conferir("2.0.1 > 2.0.0", updates.is_newer("2.0.1", "2.0.0"), True)
conferir("10.0.0 > 9.9.9", updates.is_newer("10.0.0", "9.9.9"), True)
conferir("2.0.0 > 2.0.0", updates.is_newer("2.0.0", "2.0.0"), False)
conferir("1.9.0 > 2.0.0", updates.is_newer("1.9.0", "2.0.0"), False)
# "2.1" e "2.1.0" sao a mesma coisa: sem o preenchimento com zeros, a tupla
# mais curta perderia a comparacao e o aviso apareceria pra sempre
conferir("2.1 > 2.1.0", updates.is_newer("2.1", "2.1.0"), False)
conferir("2.1.0 > 2.1", updates.is_newer("2.1.0", "2.1"), False)
conferir("tag sem numero nunca e mais nova",
         updates.is_newer("latest", "2.0.0"), False)


class RespostaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def responder(payload):
    """Troca a chamada HTTP por uma resposta pronta."""
    def falsa(_request, timeout=None):
        return RespostaFalsa(json.dumps(payload).encode("utf-8"))
    return falsa


def falhar(erro):
    def falsa(_request, timeout=None):
        raise erro
    return falsa


original = urllib.request.urlopen
print("\nlendo a resposta da API:")
try:
    urllib.request.urlopen = responder(
        {"tag_name": "v2.4.0", "html_url": "https://example/releases/v2.4.0"})
    conferir("versao vem sem o 'v'", updates.latest().version, "2.4.0")
    conferir("url e a da release",
             updates.latest().url, "https://example/releases/v2.4.0")

    urllib.request.urlopen = responder({"tag_name": "v9.9.9", "draft": True})
    conferir("rascunho nao conta", updates.latest(), None)

    urllib.request.urlopen = responder({"tag_name": "  "})
    conferir("tag vazia nao conta", updates.latest(), None)

    urllib.request.urlopen = responder(["isto nao e um objeto"])
    conferir("resposta em formato inesperado", updates.latest(), None)

    print("\nsem resposta e um caso normal, nao um erro:")
    for nome, erro in (("sem internet", urllib.error.URLError("offline")),
                       ("proxy recusou", OSError("connection reset")),
                       ("tempo esgotado", TimeoutError())):
        urllib.request.urlopen = falhar(erro)
        conferir(nome, updates.latest(), None)

    urllib.request.urlopen = responder({"tag_name": "nao-e-json-valido"})
    urllib.request.urlopen = falhar(ValueError("json quebrado"))
    conferir("json quebrado", updates.latest(), None)

    print("\navisando (ou nao) em segundo plano:")

    def esperar(payload_ou_erro, **kwargs):
        """Roda o check e devolve a Release avisada, ou None."""
        recebido = []
        pronto = threading.Event()
        urllib.request.urlopen = (
            falhar(payload_ou_erro) if isinstance(payload_ou_erro, Exception)
            else responder(payload_ou_erro))
        updates.check_in_background(
            lambda r: (recebido.append(r), pronto.set()), **kwargs)
        pronto.wait(timeout=5)
        return recebido[0] if recebido else None

    nova = {"tag_name": "v99.0.0", "html_url": "https://example/new"}
    aviso = esperar(nova)
    conferir("versao mais nova avisa", aviso and aviso.version, "99.0.0")
    conferir("versao igual a atual nao avisa",
             esperar({"tag_name": updates.VERSION}), None)
    conferir("versao antiga nao avisa",
             esperar({"tag_name": "v0.0.1"}), None)
    # fechar o aviso guarda a versao no config; ela nao pode voltar no proximo
    # arranque, senao o botao de fechar nao serve pra nada
    conferir("versao dispensada nao volta",
             esperar(nova, skipped="99.0.0"), None)
    conferir("outra versao ainda avisa",
             bool(esperar(nova, skipped="98.0.0")), True)
    conferir("sem internet nao avisa nada",
             esperar(urllib.error.URLError("offline")), None)

    # a thread e daemon: se ela travasse, o programa nao poderia fechar
    conferir("a checagem nao segura o programa",
             all(t.daemon for t in threading.enumerate()
                 if t.name == "update-check"), True)
finally:
    urllib.request.urlopen = original

print("\na versao anunciada e a mesma que o instalador publica:")
iss = (Path(__file__).resolve().parent.parent / "installer.iss")
if iss.exists():
    import re
    achado = re.search(r'#define\s+AppVersion\s+"([^"]+)"',
                       iss.read_text(encoding="utf-8", errors="replace"))
    conferir("installer.iss x updates.VERSION",
             achado and achado.group(1), updates.VERSION)
else:
    print("  (installer.iss nao encontrado, pulando)")

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
