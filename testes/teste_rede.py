"""Prova a pilha de captura inteira sem precisar do jogo aberto.

Monta um pacote de verdade de tras pra frente — CharacterData dentro do
FishNet, dentro do LiteNetLib, dentro do UDP, dentro do IP, dentro do Ethernet
— e confere que a pilha desembrulha tudo e chega no nivel e no XP certos.

Os casos chatos estao aqui de proposito, porque sao os que quebram na pratica:
pacote fragmentado que chega fora de ordem, mensagens grudadas num datagrama
so, VLAN no meio do caminho, e lixo aleatorio que nao pode virar leitura.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fishnet
import ip
import litenetlib
import pcap
from teste_personagem import packed, sintetico

falhas = []


def _curto(valor, limite=52):
    texto = repr(valor)
    return texto if len(texto) <= limite else texto[:limite] + f"...({len(texto)} chars)"


def conferir(rotulo, obtido, esperado):
    ok = obtido == esperado
    if not ok:
        falhas.append(rotulo)
    print(f"  {'ok ' if ok else 'ERRO'} {rotulo:<44} {_curto(obtido)}"
          + ("" if ok else f"  (esperado {_curto(esperado)})"))


# -- construtores de pacote ----------------------------------------------

def mensagem_fishnet(conteudo: bytes, tick=7777, id_pacote=10) -> bytes:
    """Tick de 4 bytes + id do pacote de 2, que e o cabecalho de todo bundle."""
    cabecalho = tick.to_bytes(4, "little") + id_pacote.to_bytes(2, "little")
    # framing do targetRpc antes do conteudo: id do objeto, flag de spawn,
    # indice do componente e o hash do RPC. A cacada tem que atravessar isso.
    return cabecalho + bytes([0x40, 0x01, 0x00, 57]) + conteudo


def canal(conteudo: bytes, sequencia=1, canal_id=0) -> bytes:
    return (bytes([1]) + sequencia.to_bytes(2, "little")
            + bytes([canal_id]) + conteudo)


def fragmentos(conteudo: bytes, partes: int, ident=9, canal_id=0) -> list[bytes]:
    tamanho = (len(conteudo) + partes - 1) // partes
    saida = []
    for i in range(partes):
        pedaco = conteudo[i * tamanho:(i + 1) * tamanho]
        saida.append(bytes([1 | 0x80])
                     + (100 + i).to_bytes(2, "little")
                     + bytes([canal_id])
                     + ident.to_bytes(2, "little")
                     + i.to_bytes(2, "little")
                     + partes.to_bytes(2, "little")
                     + pedaco)
    return saida


def unir(*filhos: bytes) -> bytes:
    saida = bytearray([12])
    for filho in filhos:
        saida += len(filho).to_bytes(2, "little") + filho
    return bytes(saida)


def udp(conteudo: bytes, origem=30000, destino=7777) -> bytes:
    return (origem.to_bytes(2, "big") + destino.to_bytes(2, "big")
            + (8 + len(conteudo)).to_bytes(2, "big") + b"\x00\x00" + conteudo)


def ipv4(conteudo: bytes, fragmento=0) -> bytes:
    return (bytes([0x45, 0x00]) + (20 + len(conteudo)).to_bytes(2, "big")
            + b"\x00\x01" + fragmento.to_bytes(2, "big")
            + bytes([64, 17]) + b"\x00\x00"
            + bytes([10, 0, 0, 5]) + bytes([200, 1, 2, 3]) + conteudo)


def ethernet(conteudo: bytes, vlan=False) -> bytes:
    cabecalho = b"\x11" * 6 + b"\x22" * 6
    if vlan:
        return cabecalho + b"\x81\x00" + b"\x00\x64" + b"\x08\x00" + conteudo
    return cabecalho + b"\x08\x00" + conteudo


# -- enlace ---------------------------------------------------------------

print("enlace (tirar o cabecalho da placa):")
alvo = b"pacote-ip-aqui"
conferir("ethernet simples", pcap.pacote_ip(ethernet(alvo), 1), alvo)
conferir("ethernet com VLAN", pcap.pacote_ip(ethernet(alvo, vlan=True), 1), alvo)
conferir("quadro nao-IP e ignorado",
         pcap.pacote_ip(b"\x11" * 6 + b"\x22" * 6 + b"\x08\x06" + alvo, 1), None)

print("\nIP e UDP:")
d = ip.analisar(ipv4(udp(b"conteudo", origem=1234, destino=5678)))
conferir("porta de origem", d.porta_origem if d else None, 1234)
conferir("porta de destino", d.porta_destino if d else None, 5678)
conferir("conteudo", d.dados if d else None, b"conteudo")
conferir("casa com a porta do jogo", d.envolve({5678}) if d else None, True)
conferir("ignora porta alheia", d.envolve({9999}) if d else None, False)
conferir("fragmento do meio e descartado (nao tem cabecalho UDP)",
         ip.analisar(ipv4(udp(b"x"), fragmento=185)), None)
conferir("pacote curto demais", ip.analisar(b"\x45\x00\x00"), None)

# -- LiteNetLib -----------------------------------------------------------

print("\nLiteNetLib:")
pacotes = litenetlib.decodificar(canal(b"abc", sequencia=5, canal_id=1))
conferir("um canal, um pacote", len(pacotes), 1)
conferir("tipo", pacotes[0].tipo if pacotes else None, "channeled")
conferir("sequencia", pacotes[0].sequencia if pacotes else None, 5)
conferir("conteudo", pacotes[0].dados if pacotes else None, b"abc")

unidos = litenetlib.decodificar(unir(canal(b"um"), canal(b"dois"), bytes([0]) + b"tres"))
conferir("merge abre os tres filhos", len(unidos), 3)
conferir("conteudo dos filhos", [p.dados for p in unidos],
         [b"um", b"dois", b"tres"])

grande = bytes(range(256)) * 4
partes = fragmentos(grande, 4)
remontador = litenetlib.Remontador()
resultados = []
for parte in reversed(partes):          # chega fora de ordem, como na vida real
    for p in litenetlib.decodificar(parte):
        resultados += remontador.alimentar(p)
conferir("fragmento remontado fora de ordem", resultados, [grande])

parcial = litenetlib.Remontador()
soltos = []
for parte in fragmentos(grande, 4)[:3]:
    for p in litenetlib.decodificar(parte):
        soltos += parcial.alimentar(p)
conferir("fragmento incompleto nao entrega nada", soltos, [])
conferir("merge vazio nao explode", litenetlib.decodificar(bytes([12])), [])
conferir("datagrama vazio nao explode", litenetlib.decodificar(b""), [])

# -- FishNet --------------------------------------------------------------

print("\nFishNet:")
splits = fishnet.RemontadorSplit()
comum_msg = mensagem_fishnet(b"conteudo normal")
conferir("mensagem comum passa direto",
         splits.alimentar(comum_msg, 0, 1), [comum_msg])


def split(pedaco: bytes, quantos: int, tick=555) -> bytes:
    cabecalho = bytearray(tick.to_bytes(4, "little") + (2).to_bytes(2, "little"))
    packed(cabecalho, quantos)
    return bytes(cabecalho) + pedaco


splits = fishnet.RemontadorSplit()
saida = splits.alimentar(split(b"parte-A", 3), 0, 10)
saida += splits.alimentar(split(b"parte-C", 3), 0, 12)
saida += splits.alimentar(split(b"parte-B", 3), 0, 11)
conferir("split remontado na ordem da sequencia", saida,
         [b"parte-Aparte-Bparte-C"])

# -- a cacada -------------------------------------------------------------

print("\ncacada do CharacterData:")
# UID em formato de GUID: no jogo real ele e sempre assim, e a cacada usa isso
# como evidencia. Sem o formato, a leitura e recusada de proposito — foi o que
# derrubou o falso positivo que acompanhava toda leitura boa na captura real.
GUID_EXEMPLO = "5defcee6-0dc8-47bb-a2dd-893784a975e2"
personagem_bytes = sintetico(com_update=True, nome="Batato Frito",
                             uid=GUID_EXEMPLO)
recheio = b"\x99\x02\x7f" * 30 + personagem_bytes + b"\x00\x11" * 40
achados = fishnet.cacar(recheio)
conferir("acha o personagem no meio do pacote", len(achados) >= 1, True)
conferir("nome", achados[0].nome if achados else None, "Batato Frito")
conferir("nivel de classe", achados[0].nivel if achados else None, 42)
conferir("XP absoluto", achados[0].xp if achados else None, 12345)
conferir("nivel de job", achados[0].nivel_job if achados else None, 18)
conferir("XP de job", achados[0].xp_job if achados else None, 678)

sorteio = random.Random(20260811)
falsos = 0
for _ in range(2000):
    lixo = bytes(sorteio.randrange(256) for _ in range(400))
    falsos += len(fishnet.cacar(lixo))
conferir("2000 pacotes de lixo nao viram leitura", falsos, 0)

cacador = fishnet.Cacador()
conferir("primeiro acerto ainda nao e confiavel",
         cacador.alimentar(recheio), None)
segundo = cacador.alimentar(recheio)
conferir("segundo acerto trava o nome", segundo.nome if segundo else None,
         "Batato Frito")
conferir("nome travado", cacador.nome, "Batato Frito")
outro = fishnet.cacar(sintetico(com_update=True, nome="Outra Pessoa",
                                uid=GUID_EXEMPLO),
                      nome_esperado="Batato Frito")
conferir("filtro por nome ignora outro personagem", outro, [])
conferir("UID que nao e GUID e recusado",
         fishnet.cacar(sintetico(com_update=True, nome="Batato Frito")), [])

# na tela de selecao o roster inteiro passa uma vez cada; se isso roubasse o
# travamento, o medidor seguiria o personagem errado. Trocar custa mais caro.
outra = sintetico(com_update=True, nome="Outra Pessoa", uid=GUID_EXEMPLO)
conferir("roster passando nao rouba o travamento",
         [cacador.alimentar(outra) for _ in range(3)][-1], None)
conferir("continua no personagem certo", cacador.nome, "Batato Frito")
trocou = cacador.alimentar(outra)
conferir("insistindo, a troca acontece",
         trocou.nome if trocou else None, "Outra Pessoa")

# -- pilha inteira --------------------------------------------------------

print("\nda placa de rede ate o XP:")
mensagem = mensagem_fishnet(personagem_bytes)
quadros = [ethernet(ipv4(udp(unir(canal(b"ruido qualquer"), parte))))
           for parte in fragmentos(mensagem, 3)]

remontador = litenetlib.Remontador()
splits = fishnet.RemontadorSplit()
cacador = fishnet.Cacador()
cacador.CONFIRMACOES = 1          # um pacote so, no teste
lido = None
for quadro in quadros:
    bruto = pcap.pacote_ip(quadro, 1)
    datagrama = ip.analisar(bruto)
    if not datagrama.envolve({7777}):
        continue
    for p in litenetlib.decodificar(datagrama.dados):
        for msg in remontador.alimentar(p):
            for conteudo in splits.alimentar(msg, p.canal or 0, p.sequencia):
                achado = cacador.alimentar(conteudo)
                if achado:
                    lido = achado

conferir("nome", lido.nome if lido else None, "Batato Frito")
conferir("nivel de classe", lido.nivel if lido else None, 42)
conferir("XP absoluto", lido.xp if lido else None, 12345)
conferir("nivel de job", lido.nivel_job if lido else None, 18)
conferir("XP de job", lido.xp_job if lido else None, 678)

# -- o caminho sem Npcap --------------------------------------------------

print("\ncaptura por raw socket — dispensa instalar, mas exige administrador:")
import bruto

# aqui nao ha cabecalho Ethernet: o pacote ja chega no cabecalho IP
puro = ipv4(udp(b"conteudo", origem=1234, destino=5678))
conferir("pacote_ip devolve intacto", pcap.pacote_ip(puro, bruto.ENLACE), puro)
lido_puro = ip.analisar(pcap.pacote_ip(puro, bruto.ENLACE))
conferir("e as portas saem certas",
         (lido_puro.porta_origem, lido_puro.porta_destino), (1234, 5678))
conferir("declara enlace CRU, nao Ethernet", bruto.ENLACE, pcap.ENLACE_CRU)
conferir("so se oferece quando ha elevacao", bruto.disponivel(), bruto.elevado())

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
