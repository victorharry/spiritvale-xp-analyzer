"""Prova que os dois caminhos de capture sao tratados como equivalentes.

Existe porque isso quebrou de verdade: o app perguntava so `pcap.available()`
antes de start o monitor. Com o Npcap desinstalado, o monitor nunca iniciava
— e ai rodar como administrador nao adiantava nada, porque o raw socket so e
tentado dentro do monitor. A janela dizia "waiting for the game" pra sempre.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import rawsocket
import capture
import pcap

falhas = []


def conferir(label, obtido, esperado):
    ok = obtido == esperado
    if not ok:
        falhas.append(label)
    print(f"  {'ok ' if ok else 'ERRO'} {label:<52} {obtido!r}"
          + ("" if ok else f"  (esperado {esperado!r})"))


fonte = (ROOT / "xp_analyzer.py").read_text(encoding="utf-8")

print("o app nao pode condicionar a capture ao Npcap:")
conferir("considera os dois caminhos",
         "pcap.available() or rawsocket.available()" in fonte, True)
conferir("e inicia o monitor sem condicao",
         "if self.rede_disponivel:\n            self.monitor.start()" in fonte,
         False)

print("\nquem escolhe o caminho e uma funcao so, com ordem definida:")
conferir("open_capture_backend existe", hasattr(capture, "open_capture_backend"), True)
arvore = ast.parse((ROOT / "capture.py").read_text(encoding="utf-8"))
escolha = next(n for n in ast.walk(arvore)
               if isinstance(n, ast.FunctionDef) and n.name == "open_capture_backend")
# qual modulo aparece primeiro no corpo decide quem e tentado antes
citados = [n.value.id for n in ast.walk(escolha)
           if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
           and n.value.id in ("pcap", "rawsocket")]
conferir("Npcap primeiro (quem ja tem nunca ve UAC)", citados[0], "pcap")
conferir("e o raw socket vem depois", "rawsocket" in citados, True)

print("\nsem nenhum dos dois, a falha e explicita:")
try:
    if not pcap.available() and not rawsocket.available():
        capture.open_capture_backend()
        conferir("levanta NoCaptureAvailable", False, True)
    else:
        print("  --  pulado: ha capture available nesta maquina")
except capture.NoCaptureAvailable as erro:
    conferir("levanta NoCaptureAvailable", True, True)
    # o rodape quebra linha (wraplength), entao o limit e legibilidade, nao
    # largura: uma frase, sem jargao, dizendo o que fazer
    conferir("cabe no rodape em duas linhas", len(str(erro)) <= 110, True)
    conferir("sem jargao tecnico",
             not any(p in str(erro).lower() for p in ("npcap", "socket", "pcap")),
             True)

print("\no monitor guarda o notice pra janela poder mostrar:")
conferir("tem o campo notice", hasattr(capture.Monitor(), "notice"), True)

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
