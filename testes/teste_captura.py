"""Prova que os dois caminhos de captura sao tratados como equivalentes.

Existe porque isso quebrou de verdade: o app perguntava so `pcap.disponivel()`
antes de iniciar o monitor. Com o Npcap desinstalado, o monitor nunca iniciava
— e ai rodar como administrador nao adiantava nada, porque o raw socket so e
tentado dentro do monitor. A janela dizia "waiting for the game" pra sempre.
"""
import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import bruto
import captura
import pcap

falhas = []


def conferir(rotulo, obtido, esperado):
    ok = obtido == esperado
    if not ok:
        falhas.append(rotulo)
    print(f"  {'ok ' if ok else 'ERRO'} {rotulo:<52} {obtido!r}"
          + ("" if ok else f"  (esperado {esperado!r})"))


fonte = (RAIZ / "xp_analyzer.py").read_text(encoding="utf-8")

print("o app nao pode condicionar a captura ao Npcap:")
conferir("considera os dois caminhos",
         "pcap.disponivel() or bruto.disponivel()" in fonte, True)
conferir("e inicia o monitor sem condicao",
         "if self.rede_disponivel:\n            self.monitor.iniciar()" in fonte,
         False)

print("\nquem escolhe o caminho e uma funcao so, com ordem definida:")
conferir("abrir_captura existe", hasattr(captura, "abrir_captura"), True)
arvore = ast.parse((RAIZ / "captura.py").read_text(encoding="utf-8"))
escolha = next(n for n in ast.walk(arvore)
               if isinstance(n, ast.FunctionDef) and n.name == "abrir_captura")
# qual modulo aparece primeiro no corpo decide quem e tentado antes
citados = [n.value.id for n in ast.walk(escolha)
           if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
           and n.value.id in ("pcap", "bruto")]
conferir("Npcap primeiro (quem ja tem nunca ve UAC)", citados[0], "pcap")
conferir("e o raw socket vem depois", "bruto" in citados, True)

print("\nsem nenhum dos dois, a falha e explicita:")
try:
    if not pcap.disponivel() and not bruto.disponivel():
        captura.abrir_captura()
        conferir("levanta SemCaptura", False, True)
    else:
        print("  --  pulado: ha captura disponivel nesta maquina")
except captura.SemCaptura as erro:
    conferir("levanta SemCaptura", True, True)
    # o rodape quebra linha (wraplength), entao o limite e legibilidade, nao
    # largura: uma frase, sem jargao, dizendo o que fazer
    conferir("cabe no rodape em duas linhas", len(str(erro)) <= 110, True)
    conferir("sem jargao tecnico",
             not any(p in str(erro).lower() for p in ("npcap", "socket", "pcap")),
             True)

print("\no monitor guarda o aviso pra janela poder mostrar:")
conferir("tem o campo aviso", hasattr(captura.Monitor(), "aviso"), True)

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
