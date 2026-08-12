"""Junta tudo: da placa de rede ate o nivel e o XP do personagem.

    UDP -> LiteNetLib -> FishNet -> CharacterData -> Progresso

Roda numa thread propria e so publica o ultimo progresso lido; quem usa
consulta quando quiser, sem travar a interface.

Isto e captura PASSIVA: le o que ja esta passando na placa, em modo nao
promiscuo (so o trafego desta maquina). Nada e enviado, nada e injetado, nada
e modificado — inclusive nada e escrito no processo do jogo.
"""

from __future__ import annotations

import threading
import time

import bruto
import fishnet
import ip
import litenetlib
import pcap
import portas as portas_mod
from personagem import Progresso

INTERVALO_PORTAS = 1.0          # com que frequencia pergunto as portas ao Windows
NOME_PROCESSO = "SpiritVale.exe"


class SemCaptura(pcap.ErroPcap):
    """Nenhum dos dois caminhos esta disponivel — e o usuario tem que escolher."""


def abrir_captura():
    """Abre a captura pelo caminho que estiver disponivel.

    Sao dois, com friccoes opostas, e por isso os dois existem:

      Npcap        instala um driver uma vez, e depois o app abre normal
      raw socket   nao instala nada, mas exige administrador toda vez

    O Npcap vem primeiro de proposito: quem ja o tem nunca ve uma tela de UAC.
    """
    if pcap.disponivel():
        return pcap.abrir()
    if bruto.disponivel():
        return bruto.abrir()
    raise SemCaptura(
        "para ler o progresso e preciso capturar a rede desta maquina, e ha "
        "dois jeitos: instalar o Npcap (https://npcap.com, uma vez so) ou "
        "abrir o XP Analyzer como administrador.")


class Monitor:
    """Thread de captura. `ultimo` guarda o progresso mais recente."""

    def __init__(self, nome_processo: str = NOME_PROCESSO, ao_avisar=None):
        self.nome_processo = nome_processo
        self._avisar = ao_avisar or (lambda _: None)
        self._parar = threading.Event()
        self._trava = threading.Lock()
        self._ultimo: Progresso | None = None
        self._recebido_em = 0.0
        self._thread: threading.Thread | None = None
        self._sessao: pcap.Sessao | None = None
        self.estado = "parado"
        self.pacotes = 0

    # -- consulta ---------------------------------------------------------

    @property
    def ultimo(self) -> Progresso | None:
        with self._trava:
            return self._ultimo

    @property
    def idade(self) -> float:
        """Segundos desde a ultima leitura boa (infinito se nunca houve)."""
        with self._trava:
            if not self._recebido_em:
                return float("inf")
            return time.time() - self._recebido_em

    @property
    def ativo(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- ciclo ------------------------------------------------------------

    def iniciar(self) -> None:
        if self.ativo:
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._rodar, daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        # o proximo() pode estar bloqueado esperando pacote; isso o solta
        if self._sessao is not None:
            try:
                self._sessao.interromper()
            except Exception:
                pass

    def _publicar(self, progresso: Progresso) -> None:
        with self._trava:
            self._ultimo = progresso
            self._recebido_em = time.time()

    def _rodar(self) -> None:
        try:
            sessao = abrir_captura()
        except SemCaptura as erro:
            self.estado = "sem captura"
            self._avisar(str(erro))
            return
        except pcap.ErroPcap as erro:
            self.estado = "falhou"
            self._avisar(f"captura indisponivel: {erro}")
            return

        self._sessao = sessao
        self.estado = "esperando o jogo"
        self._avisar(f"capturando em {sessao.dispositivo}")

        remontador = litenetlib.Remontador()
        splits = fishnet.RemontadorSplit()
        cacador = fishnet.Cacador()
        conhecidas: set[int] = set()
        proxima_consulta = 0.0

        try:
            while not self._parar.is_set():
                agora = time.time()
                if agora >= proxima_consulta:
                    proxima_consulta = agora + INTERVALO_PORTAS
                    novas = portas_mod.portas_do_jogo(self.nome_processo)
                    if novas != conhecidas:
                        # jogo reaberto ou personagem trocado: o que estava
                        # pela metade nao serve mais, e o nome travado tambem nao
                        if not (novas & conhecidas):
                            remontador = litenetlib.Remontador()
                            splits = fishnet.RemontadorSplit()
                            cacador.esquecer()
                        conhecidas = novas
                        self.estado = "lendo" if novas else "esperando o jogo"

                quadro = sessao.proximo()
                if quadro is None or not conhecidas:
                    continue
                self._processar(quadro, sessao.enlace, conhecidas,
                                remontador, splits, cacador)
        except pcap.ErroPcap as erro:
            self.estado = "falhou"
            self._avisar(f"captura interrompida: {erro}")
        finally:
            self._sessao = None
            sessao.fechar()
            if self.estado not in ("falhou", "sem captura"):
                self.estado = "parado"

    def _processar(self, quadro: bytes, enlace: int, portas: set[int],
                   remontador, splits, cacador) -> None:
        # NAO chamar de `bruto`: sombrearia o modulo de captura por raw socket
        pacote_ip = pcap.pacote_ip(quadro, enlace)
        if not pacote_ip:
            return
        datagrama = ip.analisar(pacote_ip)
        if datagrama is None or not datagrama.envolve(portas):
            return
        self.pacotes += 1

        for pacote in litenetlib.decodificar(datagrama.dados):
            for mensagem in remontador.alimentar(pacote):
                canal = pacote.canal or 0
                for conteudo in splits.alimentar(mensagem, canal, pacote.sequencia):
                    progresso = cacador.alimentar(conteudo)
                    if progresso is not None:
                        self._publicar(progresso)


def diagnostico() -> list[str]:
    """O que checar quando nada aparece — na ordem em que costuma falhar."""
    linhas = []
    try:
        linhas.append(f"Npcap: {pcap.versao()}")
    except pcap.ErroPcap:
        linhas.append("Npcap: nao instalado")
        if bruto.elevado():
            linhas.append("raw socket: DISPONIVEL (rodando como administrador)")
        else:
            linhas.append("raw socket: indisponivel (precisa de administrador)")
            linhas.append("  -> instale o Npcap OU rode como administrador")
        return linhas
    try:
        escolhida = pcap.escolher()
        for dispositivo in pcap.dispositivos():
            marca = "->" if escolhida and dispositivo.nome == escolhida.nome else "  "
            linhas.append(f" {marca} {dispositivo}")
    except pcap.ErroPcap as erro:
        linhas.append(f"placas: erro — {erro}")
    processos = portas_mod.pids(NOME_PROCESSO)
    if not processos:
        linhas.append(f"processo: {NOME_PROCESSO} nao esta aberto")
    else:
        achadas = sorted(portas_mod.portas_de(processos))
        linhas.append(f"processo: pid {sorted(processos)} — portas UDP {achadas}")
    return linhas
