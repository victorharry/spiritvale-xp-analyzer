"""Quanto XP cada nivel pede — a tabela do jogo, nao uma estimativa.

Extraida de `SpiritVale_Data/sharedassets0.assets`. A tabela ESTA no cliente
porque tem que estar: o servidor manda XP absoluto, e quem desenha a barra em
porcentagem e o cliente, entao ele precisa do denominador.

Achar valor solto no arquivo nao provava nada — a faixa medida do nivel 114 tem
100 mil de largura, e dado binario aleatorio caia nela 177 mil vezes. O que
identificou a tabela foi a ESTRUTURA: num array indexado por nivel, o 22 fica
um elemento depois do 21, o 25 tres depois do 22, o 33 oito depois do 25.
Exigindo os acertos nas distancias certas, sobrou exatamente um candidato, com
6 de 6 niveis batendo.

Confere com as 18 medicoes independentes que o Victor registrou: todas caem
dentro. E uma tabela so serve para classe e job — o que explica os dois terem
batido em 0,08% quando medidos no mesmo nivel.

O jogo satura em 2^31 a partir do nivel 162; aqui vai ate 161, e o maximo
jogavel e 150.
"""

from __future__ import annotations

# indice 0 = nivel 1
NECESSARIO = (
               40,           196,           500,           970,         1_620,   # 1-5
            2_464,         3_513,         4_777,         6_263,         7_981,   # 6-10
           10_007,        12_534,        15_683,        19_544,        24_193,   # 11-15
           29_698,        36_120,        43_516,        51_939,        61_439,   # 16-20
           72_062,        83_854,        96_858,       111_114,       126_662,   # 21-25
          143_541,       161_788,       181_439,       202_528,       225_090,   # 26-30
          249_218,       275_153,       303_103,       333_247,       365_747,   # 31-35
          400_756,       438_418,       478_873,       522_253,       568_688,   # 36-40
          618_302,       671_218,       727_553,       787_424,       850_945,   # 41-45
          918_226,       989_378,     1_064_507,     1_143_718,     1_227_117,   # 46-50
        1_314_864,     1_407_330,     1_504_900,     1_607_946,     1_716_827,   # 51-55
        1_831_894,     1_953_495,     2_081_968,     2_217_650,     2_360_872,   # 56-60
        2_511_963,     2_671_247,     2_839_047,     3_015_681,     3_201_466,   # 61-65
        3_396_716,     3_601_743,     3_816_857,     4_042_364,     4_278_572,   # 66-70
        4_525_844,     4_784_816,     5_056_234,     5_340_867,     5_639_499,   # 71-75
        5_952_924,     6_281_947,     6_627_379,     6_990_037,     7_370_743,   # 76-80
        7_770_326,     8_189_616,     8_629_450,     9_090_666,     9_574_106,   # 81-85
       10_080_615,    10_611_042,    11_166_236,    11_747_051,    12_354_341,   # 86-90
       12_989_023,    13_652_368,    14_345_896,    15_071_245,    15_830_142,   # 91-95
       16_624_379,    17_455_812,    18_326_346,    19_237_936,    20_192_578,   # 96-100
       21_192_310,    22_239_204,    23_335_366,    24_482_938,    25_684_090,   # 101-105
       26_941_022,    28_255_960,    29_631_160,    31_068_902,    32_571_490,   # 106-110
       34_141_312,    35_781_216,    37_494_524,    39_284_872,    41_156_140,   # 111-115
       43_112_432,    45_158_048,    47_297_468,    49_535_336,    51_876_460,   # 116-120
       54_325_792,    56_888_432,    59_569_604,    62_374_676,    65_309_128,   # 121-125
       68_378_576,    71_588_736,    74_945_448,    78_454_672,    82_122_456,   # 126-130
       85_955_016,    89_960_368,    94_153_872,    98_565_376,   103_246_448,   # 131-135
      108_277_536,   113_775_176,   119_899_208,   126_859_944,   134_925_408,   # 136-140
      144_428_464,   155_774_096,   169_446_576,   186_016_640,   206_148_704,   # 141-145
      230_608_064,   260_268_096,   296_117_472,   339_267_296,   390_958_368,   # 146-150
      452_568_384,   525_619_104,   611_783_488,   712_893_184,   830_945_152,   # 151-155
      968_109_568, 1_126_736_512, 1_309_363_200, 1_518_721_664, 1_757_745_408,   # 156-160
    2_029_576_832,   # 161-161
)

MAXIMO_NA_TABELA = len(NECESSARIO)


def xp_do_nivel(nivel: int) -> int | None:
    """XP que o nivel pede, ou None se estiver fora da tabela."""
    if 1 <= nivel <= MAXIMO_NA_TABELA:
        return NECESSARIO[nivel - 1]
    return None
