"""Decodifica o CharacterData que o jogo manda no RPC CharacterCallback_T.

E aqui que mora o ganho: o servidor manda NIVEL e XP ABSOLUTO prontos, para
classe e para job. Nada de estimar por porcentagem de barra, nada de pedir pro
usuario digitar o nivel.

A ordem dos campos nao e adivinhavel — ela vem do formato do jogo, e foi
mapeada pelo spirit-vale-tools (MIT). Ler fora de ordem nao "da erro": entrega
numero errado com cara de certo. Por isso a leitura para nos quatro campos que
interessam, em vez de percorrer a estrutura inteira: quanto menos campos eu
atravesso, menos chance de sair do trilho.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from leitor import Leitor, PayloadInvalido, PayloadTruncado

# o UID do personagem e um GUID. O decodificador deles descarta esse campo, mas
# quem procura a estrutura as cegas (fishnet.cacar) precisa de toda evidencia
# disponivel: exigir o formato aqui derrubou um falso positivo que aparecia
# junto de toda leitura boa, com um GUID lido no lugar do nome
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
                  r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# limites do jogo — servem de sanidade: valor fora disso significa que a
# leitura saiu do trilho, nao que o jogador e especial
NIVEL_MAXIMO_CLASSE = 150
NIVEL_MAXIMO_JOB = 70
XP_MAXIMO = 10_000_000_000


@dataclass(frozen=True)
class Progresso:
    """O que interessa pro medidor de XP."""

    nome: str
    nivel: int
    xp: int
    nivel_job: int
    xp_job: int

    def plausivel(self) -> bool:
        return (1 <= self.nivel <= NIVEL_MAXIMO_CLASSE
                and 1 <= self.nivel_job <= NIVEL_MAXIMO_JOB
                and 0 <= self.xp <= XP_MAXIMO
                and 0 <= self.xp_job <= XP_MAXIMO)


def decodificar(payload: bytes, com_tipo_de_update: bool,
                exigir_guid: bool = False) -> Progresso | None:
    """Le o comeco do CharacterData ate os campos de progresso.

    `com_tipo_de_update` = True quando o RPC e o CharacterCallback_T, que
    comeca com um enum a mais antes do objeto.

    `exigir_guid` = True cobra que o UID tenha cara de GUID. Fica desligado por
    padrao pra nao divergir do decodificador original, que so descarta o campo;
    quem procura a estrutura as cegas liga.

    Devolve None se o payload nao casar com o formato — de proposito: e melhor
    admitir que nao entendeu do que entregar um numero inventado.
    """
    try:
        leitor = Leitor(payload)
        if com_tipo_de_update:
            leitor.packed()          # CharacterUpdateType

        leitor.objeto()
        uid = leitor.texto(80)
        if exigir_guid and not (uid and GUID.match(uid)):
            return None
        leitor.texto(80)             # id da conta, descartado
        leitor.packed()
        leitor.texto(80)
        leitor.texto(80)
        nome = leitor.texto(64) or "?"

        leitor.objeto()
        for _ in range(10):
            leitor.packed()
        leitor.objeto()
        leitor.booleanos()
        # lista de titulos/conquistas: cada item tem forma propria
        leitor.lista(lambda: (leitor.objeto(), leitor.packed(),
                              leitor.texto(256), leitor.packed(),
                              leitor.booleano()))
        leitor.texto(256)            # titulo
        leitor.texto(256)
        leitor.texto(256)
        leitor.lista(leitor.packed)  # arquetipos

        # finalmente, o que a gente quer
        nivel = leitor.packed()
        xp = leitor.packed()
        nivel_job = leitor.packed()
        xp_job = leitor.packed()
    except (PayloadTruncado, PayloadInvalido):
        return None

    progresso = Progresso(nome=nome, nivel=nivel, xp=xp,
                          nivel_job=nivel_job, xp_job=xp_job)
    return progresso if progresso.plausivel() else None
