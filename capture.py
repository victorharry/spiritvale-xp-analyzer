"""Junta tudo: da placa de rede ate o level e o XP do character.

    UDP -> LiteNetLib -> FishNet -> CharacterData -> Progress

Roda numa thread propria e so publica o latest progress lido; quem usa
consulta quando quiser, sem travar a interface.

Isto e capture PASSIVA: le o que ja esta passando na placa, em modo nao
promiscuo (so o trafego desta maquina). Nada e enviado, nada e injetado, nada
e modificado — inclusive nada e escrito no processo do jogo.
"""

from __future__ import annotations

import threading
import time

import rawsocket
import fishnet
import ip
import litenetlib
import pcap
import ports as portas_mod
from character import Progress

PORT_REFRESH_SECONDS = 1.0          # com que frequencia pergunto as ports ao Windows
PROCESS_NAME = "SpiritVale.exe"


class NoCaptureAvailable(pcap.PcapError):
    """Nenhum dos dois caminhos esta available — e o usuario tem que pick."""


def open_capture_backend():
    """Abre a capture pelo caminho que estiver available.

    Sao dois, com friccoes opostas, e por isso os dois existem:

      Npcap        instala um driver uma vez, e depois o app abre normal
      raw socket   nao instala nada, mas exige administrador toda vez

    O Npcap vem primeiro de proposito: quem ja o tem nunca ve uma tela de UAC.
    """
    if pcap.available():
        return pcap.open_capture()
    if rawsocket.available():
        return rawsocket.open_capture()
    # Sem jargao: "Npcap" e "raw socket" nao querem dizer nada pra quem so
    # quer ver o XP. A message diz o que FAZER, e o LEIA-ME explica o resto.
    raise NoCaptureAvailable("can't read the game — right-click the shortcut and pick "
                     "\"Run as administrator\"")


class Monitor:
    """Thread de capture. `latest` guarda o progress mais recente."""

    def __init__(self, process_name: str = PROCESS_NAME, ao_avisar=None):
        self.process_name = process_name
        self._notify = ao_avisar or (lambda _: None)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: Progress | None = None
        self._received_at = 0.0
        self._thread: threading.Thread | None = None
        self._session: pcap.Session | None = None
        self.state = "parado"
        self.packets = 0
        # latest notice, pra janela poder mostrar. Antes isso so ia pro print()
        # e o .exe nao tem console — quando a capture falhava, o usuario via
        # apenas "waiting for the game" e nao tinha como descobrir por que.
        self.notice = ""

    # -- consulta ---------------------------------------------------------

    @property
    def latest(self) -> Progress | None:
        with self._lock:
            return self._latest

    @property
    def age(self) -> float:
        """Segundos desde a ultima reading boa (infinito se nunca houve)."""
        with self._lock:
            if not self._received_at:
                return float("inf")
            return time.time() - self._received_at

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- ciclo ------------------------------------------------------------

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        # o next_packet() pode estar bloqueado esperando packet; isso o solta
        if self._session is not None:
            try:
                self._session.interrupt()
            except Exception:
                pass

    def _report(self, text: str) -> None:
        self.notice = text
        self._notify(text)

    def _publish(self, progress: Progress) -> None:
        with self._lock:
            self._latest = progress
            self._received_at = time.time()

    def _run(self) -> None:
        try:
            session = open_capture_backend()
        except NoCaptureAvailable as erro:
            self.state = "sem capture"
            self._report(str(erro))
            return
        except pcap.PcapError as erro:
            self.state = "falhou"
            self._report(f"capture indisponivel: {erro}")
            return

        self._session = session
        self.state = "esperando o jogo"
        self._report("connected — waiting for the game")

        reassembler = litenetlib.Reassembler()
        splits = fishnet.SplitReassembler()
        hunter = fishnet.Hunter()
        known_ports: set[int] = set()
        next_lookup = 0.0

        try:
            while not self._stop.is_set():
                agora = time.time()
                if agora >= next_lookup:
                    next_lookup = agora + PORT_REFRESH_SECONDS
                    fresh = portas_mod.game_ports(self.process_name)
                    if fresh != known_ports:
                        # jogo reaberto ou character trocado: o que estava
                        # pela metade nao serve mais, e o name travado tambem nao
                        if not (fresh & known_ports):
                            reassembler = litenetlib.Reassembler()
                            splits = fishnet.SplitReassembler()
                            hunter.forget()
                        known_ports = fresh
                        self.state = "lendo" if fresh else "esperando o jogo"

                frame = session.next_packet()
                if frame is None or not known_ports:
                    continue
                self._process(frame, session.link_type, known_ports,
                                reassembler, splits, hunter)
        except pcap.PcapError as erro:
            self.state = "falhou"
            self._report(f"capture interrompida: {erro}")
        finally:
            self._session = None
            session.close()
            if self.state not in ("falhou", "sem capture"):
                self.state = "parado"

    def _process(self, frame: bytes, link_type: int, ports: set[int],
                   reassembler, splits, hunter) -> None:
        # NAO chamar de `rawsocket`: sombrearia o modulo de capture por raw socket
        strip_link_layer = pcap.strip_link_layer(frame, link_type)
        if not strip_link_layer:
            return
        datagram = ip.parse(strip_link_layer)
        if datagram is None or not datagram.involves(ports):
            return
        self.packets += 1

        for packet in litenetlib.decode(datagram.data):
            for message in reassembler.feed(packet):
                channel = packet.channel or 0
                for payload in splits.feed(message, channel, packet.sequence):
                    progress = hunter.feed(payload)
                    if progress is not None:
                        self._publish(progress)


def diagnose() -> list[str]:
    """O que checar quando nada aparece — na ordem em que costuma falhar."""
    linhas = []
    try:
        linhas.append(f"Npcap: {pcap.version()}")
    except pcap.PcapError:
        linhas.append("Npcap: nao instalado")
        if rawsocket.is_elevated():
            linhas.append("raw socket: DISPONIVEL (rodando como administrador)")
        else:
            linhas.append("raw socket: indisponivel (precisa de administrador)")
            linhas.append("  -> instale o Npcap OU rode como administrador")
        return linhas
    try:
        escolhida = pcap.pick()
        for device in pcap.devices():
            marca = "->" if escolhida and device.name == escolhida.name else "  "
            linhas.append(f" {marca} {device}")
    except pcap.PcapError as erro:
        linhas.append(f"placas: erro — {erro}")
    processes = portas_mod.pids(PROCESS_NAME)
    if not processes:
        linhas.append(f"processo: {PROCESS_NAME} nao esta aberto")
    else:
        found_ports = sorted(portas_mod.ports_of(processes))
        linhas.append(f"processo: pid {sorted(processes)} — ports UDP {found_ports}")
    return linhas
