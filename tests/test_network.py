"""Prova a pilha de capture inteira sem precisar do jogo aberto.

Monta um packet de verdade de tras pra frente — CharacterData dentro do
FishNet, dentro do LiteNetLib, dentro do UDP, dentro do IP, dentro do Ethernet
— e confere que a pilha desembrulha tudo e chega no level e no XP certos.

Os casos chatos estao aqui de proposito, porque sao os que quebram na pratica:
packet fragmented que chega fora de ordem, mensagens grudadas num datagram
so, VLAN no meio do caminho, e lixo aleatorio que nao pode virar reading.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fishnet
import ip
import litenetlib
import pcap
from test_character import packed, sintetico

falhas = []


def _curto(valor, limit=52):
    text = repr(valor)
    return text if len(text) <= limit else text[:limit] + f"...({len(text)} chars)"


def conferir(label, obtido, esperado):
    ok = obtido == esperado
    if not ok:
        falhas.append(label)
    print(f"  {'ok ' if ok else 'ERRO'} {label:<44} {_curto(obtido)}"
          + ("" if ok else f"  (esperado {_curto(esperado)})"))


# -- construtores de packet ----------------------------------------------

def mensagem_fishnet(payload: bytes, tick=7777, id_pacote=10) -> bytes:
    """Tick de 4 bytes + id do packet de 2, que e o cabecalho de todo bundle."""
    cabecalho = tick.to_bytes(4, "little") + id_pacote.to_bytes(2, "little")
    # framing do targetRpc antes do payload: id do object_marker, flag de spawn,
    # indice do componente e o hash do RPC. A cacada tem que atravessar isso.
    return cabecalho + bytes([0x40, 0x01, 0x00, 57]) + payload


def channel(payload: bytes, sequence=1, canal_id=0) -> bytes:
    return (bytes([1]) + sequence.to_bytes(2, "little")
            + bytes([canal_id]) + payload)


def fragmentos(payload: bytes, parts: int, ident=9, canal_id=0) -> list[bytes]:
    size = (len(payload) + parts - 1) // parts
    out = []
    for i in range(parts):
        pedaco = payload[i * size:(i + 1) * size]
        out.append(bytes([1 | 0x80])
                     + (100 + i).to_bytes(2, "little")
                     + bytes([canal_id])
                     + ident.to_bytes(2, "little")
                     + i.to_bytes(2, "little")
                     + parts.to_bytes(2, "little")
                     + pedaco)
    return out


def unir(*filhos: bytes) -> bytes:
    out = bytearray([12])
    for filho in filhos:
        out += len(filho).to_bytes(2, "little") + filho
    return bytes(out)


def udp(payload: bytes, origem=30000, destino=7777) -> bytes:
    return (origem.to_bytes(2, "big") + destino.to_bytes(2, "big")
            + (8 + len(payload)).to_bytes(2, "big") + b"\x00\x00" + payload)


def ipv4(payload: bytes, fragment=0) -> bytes:
    return (bytes([0x45, 0x00]) + (20 + len(payload)).to_bytes(2, "big")
            + b"\x00\x01" + fragment.to_bytes(2, "big")
            + bytes([64, 17]) + b"\x00\x00"
            + bytes([10, 0, 0, 5]) + bytes([200, 1, 2, 3]) + payload)


def ethernet(payload: bytes, vlan=False) -> bytes:
    cabecalho = b"\x11" * 6 + b"\x22" * 6
    if vlan:
        return cabecalho + b"\x81\x00" + b"\x00\x64" + b"\x08\x00" + payload
    return cabecalho + b"\x08\x00" + payload


# -- link_type ---------------------------------------------------------------

print("link_type (tirar o cabecalho da placa):")
alvo = b"an-ip-packet"
conferir("ethernet simples", pcap.strip_link_layer(ethernet(alvo), 1), alvo)
conferir("ethernet com VLAN", pcap.strip_link_layer(ethernet(alvo, vlan=True), 1), alvo)
conferir("frame nao-IP e ignorado",
         pcap.strip_link_layer(b"\x11" * 6 + b"\x22" * 6 + b"\x08\x06" + alvo, 1), None)

print("\nIP e UDP:")
d = ip.parse(ipv4(udp(b"payload", origem=1234, destino=5678)))
conferir("port de origem", d.source_port if d else None, 1234)
conferir("port de destino", d.dest_port if d else None, 5678)
conferir("payload", d.data if d else None, b"payload")
conferir("casa com a port do jogo", d.involves({5678}) if d else None, True)
conferir("ignora port alheia", d.involves({9999}) if d else None, False)
conferir("fragment do meio e descartado (nao tem cabecalho UDP)",
         ip.parse(ipv4(udp(b"x"), fragment=185)), None)
conferir("packet curto demais", ip.parse(b"\x45\x00\x00"), None)

# -- LiteNetLib -----------------------------------------------------------

print("\nLiteNetLib:")
packets = litenetlib.decode(channel(b"abc", sequence=5, canal_id=1))
conferir("um channel, um packet", len(packets), 1)
conferir("kind", packets[0].kind if packets else None, "channeled")
conferir("sequence", packets[0].sequence if packets else None, 5)
conferir("payload", packets[0].data if packets else None, b"abc")

unidos = litenetlib.decode(unir(channel(b"um"), channel(b"dois"), bytes([0]) + b"tres"))
conferir("merge abre os tres filhos", len(unidos), 3)
conferir("payload dos filhos", [p.data for p in unidos],
         [b"um", b"dois", b"tres"])

grande = bytes(range(256)) * 4
parts = fragmentos(grande, 4)
reassembler = litenetlib.Reassembler()
resultados = []
for part in reversed(parts):          # chega fora de ordem, como na vida real
    for p in litenetlib.decode(part):
        resultados += reassembler.feed(p)
conferir("fragment remontado fora de ordem", resultados, [grande])

parcial = litenetlib.Reassembler()
soltos = []
for part in fragmentos(grande, 4)[:3]:
    for p in litenetlib.decode(part):
        soltos += parcial.feed(p)
conferir("fragment incompleto nao entrega nada", soltos, [])
conferir("merge vazio nao explode", litenetlib.decode(bytes([12])), [])
conferir("datagram vazio nao explode", litenetlib.decode(b""), [])

# -- FishNet --------------------------------------------------------------

print("\nFishNet:")
splits = fishnet.SplitReassembler()
comum_msg = mensagem_fishnet(b"payload normal")
conferir("a plain message passes straight through",
         splits.feed(comum_msg, 0, 1), [comum_msg])


def split(pedaco: bytes, count: int, tick=555) -> bytes:
    cabecalho = bytearray(tick.to_bytes(4, "little") + (2).to_bytes(2, "little"))
    packed(cabecalho, count)
    return bytes(cabecalho) + pedaco


splits = fishnet.SplitReassembler()
out = splits.feed(split(b"part-A", 3), 0, 10)
out += splits.feed(split(b"part-C", 3), 0, 12)
out += splits.feed(split(b"part-B", 3), 0, 11)
conferir("split remontado na ordem da sequence", out,
         [b"part-Apart-Bpart-C"])

# -- a cacada -------------------------------------------------------------

print("\ncacada do CharacterData:")
# UID em formato de GUID: no jogo real ele e sempre assim, e a cacada usa isso
# como evidencia. Sem o formato, a reading e recusada de proposito — foi o que
# derrubou o falso positivo que acompanhava toda reading boa na capture real.
GUID_EXEMPLO = "5defcee6-0dc8-47bb-a2dd-893784a975e2"
personagem_bytes = sintetico(com_update=True, name="Batato Frito",
                             uid=GUID_EXEMPLO)
recheio = b"\x99\x02\x7f" * 30 + personagem_bytes + b"\x00\x11" * 40
found = fishnet.hunt(recheio)
conferir("acha o character no meio do packet", len(found) >= 1, True)
conferir("name", found[0].name if found else None, "Batato Frito")
conferir("level de classe", found[0].level if found else None, 42)
conferir("XP absoluto", found[0].xp if found else None, 12345)
conferir("level de job", found[0].job_level if found else None, 18)
conferir("XP de job", found[0].job_xp if found else None, 678)

sorteio = random.Random(20260811)
falsos = 0
for _ in range(2000):
    lixo = bytes(sorteio.randrange(256) for _ in range(400))
    falsos += len(fishnet.hunt(lixo))
conferir("2000 packets de lixo nao viram reading", falsos, 0)

hunter = fishnet.Hunter()
conferir("primeiro acerto ainda nao e reliable",
         hunter.feed(recheio), None)
segundo = hunter.feed(recheio)
conferir("segundo acerto trava o name", segundo.name if segundo else None,
         "Batato Frito")
conferir("name travado", hunter.name, "Batato Frito")
outro = fishnet.hunt(sintetico(com_update=True, name="Outra Pessoa",
                                uid=GUID_EXEMPLO),
                      expected_name="Batato Frito")
conferir("bpf_filter por name ignora outro character", outro, [])
conferir("UID que nao e GUID e recusado",
         fishnet.hunt(sintetico(com_update=True, name="Batato Frito")), [])

# na tela de selecao o roster inteiro passa uma vez cada; se isso roubasse o
# travamento, o medidor seguiria o character errado. Trocar custa mais caro.
outra = sintetico(com_update=True, name="Outra Pessoa", uid=GUID_EXEMPLO)
conferir("roster passando nao rouba o travamento",
         [hunter.feed(outra) for _ in range(3)][-1], None)
conferir("continua no character certo", hunter.name, "Batato Frito")
trocou = hunter.feed(outra)
conferir("insistindo, a troca acontece",
         trocou.name if trocou else None, "Outra Pessoa")

# -- pilha inteira --------------------------------------------------------

print("\nda placa de rede ate o XP:")
message = mensagem_fishnet(personagem_bytes)
quadros = [ethernet(ipv4(udp(unir(channel(b"ruido qualquer"), part))))
           for part in fragmentos(message, 3)]

reassembler = litenetlib.Reassembler()
splits = fishnet.SplitReassembler()
hunter = fishnet.Hunter()
hunter.CONFIRMATIONS = 1          # um packet so, no teste
lido = None
for frame in quadros:
    rawsocket = pcap.strip_link_layer(frame, 1)
    datagram = ip.parse(rawsocket)
    if not datagram.involves({7777}):
        continue
    for p in litenetlib.decode(datagram.data):
        for msg in reassembler.feed(p):
            for payload in splits.feed(msg, p.channel or 0, p.sequence):
                achado = hunter.feed(payload)
                if achado:
                    lido = achado

conferir("name", lido.name if lido else None, "Batato Frito")
conferir("level de classe", lido.level if lido else None, 42)
conferir("XP absoluto", lido.xp if lido else None, 12345)
conferir("level de job", lido.job_level if lido else None, 18)
conferir("XP de job", lido.job_xp if lido else None, 678)

# -- o caminho sem Npcap --------------------------------------------------

print("\ncaptura por raw socket — dispensa instalar, mas exige administrador:")
import rawsocket

# aqui nao ha cabecalho Ethernet: o packet ja chega no cabecalho IP
puro = ipv4(udp(b"payload", origem=1234, destino=5678))
conferir("strip_link_layer devolve intacto", pcap.strip_link_layer(puro, rawsocket.LINK_TYPE), puro)
lido_puro = ip.parse(pcap.strip_link_layer(puro, rawsocket.LINK_TYPE))
conferir("e as ports saem certas",
         (lido_puro.source_port, lido_puro.dest_port), (1234, 5678))
conferir("declara link_type CRU, nao Ethernet", rawsocket.LINK_TYPE, pcap.LINK_RAW)
conferir("so se oferece quando ha elevacao", rawsocket.available(), rawsocket.is_elevated())

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
