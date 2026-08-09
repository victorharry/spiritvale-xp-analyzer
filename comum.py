"""Funcoes compartilhadas: config, DPI, OCR e agrupamento de palavras."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytesseract
from PIL import Image, ImageChops, ImageFilter, ImageOps

# Empacotado (.exe), __file__ aponta pra uma pasta temporaria que some ao
# fechar — o config e a calibracao precisam morar em algum lugar que dure.
if getattr(sys, "frozen", False):
    RAIZ = Path(os.environ.get("APPDATA") or Path.home()) / "XP Analyzer"
    RAIZ.mkdir(parents=True, exist_ok=True)
else:
    RAIZ = Path(__file__).resolve().parent
CAMINHO_CONFIG = RAIZ / "config.json"

TESSERACT_PADRAO = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

CONFIG_PADRAO = {
    "tesseract": TESSERACT_PADRAO,
    "tela": None,            # [largura, altura] no momento da calibracao
    "campo_busca": None,     # [x, y, w, h] do campo Search do mercado
    "area_resultados": None, # [x, y, w, h] da lista de ofertas
    "botao_mercado": None,   # icone do mercado no HUD do jogo
    # titulo da janela do jogo: ele e escolhido sozinho na abertura, se estiver
    # aberto. Se um dia o titulo mudar, e so ajustar aqui
    "janela_jogo": "SpiritVale",
    "abrir_mercado": True,   # clicar no icone sozinho antes de comecar
    "espera_abertura": 1.5,  # segundos pra tela do mercado aparecer
    # impressao digital da area de resultados, gravada na calibracao da busca.
    # E assim que ele sabe se o mercado esta na tela: sem isso, clicaria no
    # icone com o mercado ja aberto (fechando) ou digitaria sobre o cenario
    "assinatura_mercado": None,
    "limiar_assinatura": 20,        # distancia maxima pra considerar aberto
    "minimo_palavras_mercado": 15,  # so usado se nao houver assinatura gravada
    # como a BARRA DE BUSCA e o ICONE da loja se parecem, gravados na
    # calibracao. Servem pra distinguir tres estados ao abrir a loja:
    # loja aberta (barra visivel) x fechada (icone visivel) x loading (nenhum)
    "assinatura_busca": None,
    "assinatura_icone": None,
    "abertura_max_tentativas": 8,   # voltas de abrir/esperar antes de desistir
    "abertura_espera_loading": 1.5, # espera quando nao ha icone nem loja (loading)
    "espera_busca": 1.2,     # segundos de espera depois de digitar
    "metodo_digitar": "colar",  # "colar" (ctrl+v) ou "teclar"
    "similaridade_minima": 0.8,
    # de onde comeca a coluna de preco, em fracao da largura da area de
    # resultados. Serve pra nunca confundir a quantidade (na esquerda) com o
    # preco (na direita). Baixe se o preco estiver mais pra esquerda na sua tela.
    "inicio_coluna_preco": 0.7,
    # --- venda (calibrar.py --modo venda) ---
    "venda_botao_listar": None,   # botao azul "List Items for Sale"
    # a fileira inteira de abas de categoria. As abas sao igualmente espacadas,
    # entao o programa divide essa faixa pelo numero de categorias e sabe onde
    # clicar em cada uma - sem precisar calibrar uma por uma
    "venda_abas": None,
    "venda_categorias": ["Consumíveis", "Equipamentos", "Cartas", "Artefatos",
                         "Gemas", "Livros", "Materiais", "Cosméticos"],
    "venda_categoria": "Cartas",  # a ultima escolhida na interface
    # categorias em que item repetido NAO empilha: cada unidade ocupa uma linha
    # propria da lista de venda. Gema tem nivel/atributo proprio, entao duas
    # iguais sao duas linhas - ja duas cartas iguais viram uma linha com "2"
    "venda_categorias_sem_pilha": ["Gemas"],
    "venda_busca": None,          # campo de busca do painel de venda
    "venda_resultado": None,      # primeira linha do resultado da busca
    "venda_preco1": None,         # campo de preco da 1a linha da lista
    "venda_preco2": None,         # campo de preco da 2a linha (da o espacamento)
    "venda_lista": None,          # a lista da direita inteira
    "venda_botao_vender": None,   # botao laranja "Sell Items"
    # --- vigilancia (calibrar.py --modo compra) ---
    # a primeira linha da lista de ofertas, calibrada na mao. Calcular essa
    # posicao pelo OCR errava por poucos pixels e o duplo clique caia no vao
    # entre a busca e a 1a linha, sem abrir modal nenhum
    "vigilancia_primeira_linha": None,
    "vigilancia_intervalo_clique": 0.12,  # pausa entre os dois cliques
    "vigilancia_modal": None,        # texto "Purchase X x1 for Y?"
    "vigilancia_botao_ok": None,
    "vigilancia_botao_close": None,
    "vigilancia_desconto": 20,       # % abaixo da 2a oferta pra virar pechincha
    "vigilancia_minimo_ofertas": 4,  # menos que isso nao da pra julgar
    "vigilancia_preco_maximo": 0,    # teto por compra; 0 = sem teto
    "vigilancia_comprar": False,     # False = so avisa, nao compra
    "vigilancia_escopo": "Só cartas de boss",
    "vigilancia_espera_modal": 0.8,
    # quanto tempo (s) esperar o modal aparecer depois de CADA tentativa de
    # clique, lendo a tela em polling — nao e uma espera cega
    "vigilancia_espera_max_modal": 2.5,
    # quanto tempo (s) esperar a 1a linha mostrar o item procurado antes de
    # clicar (a lista demora um instante pra filtrar depois da busca)
    "vigilancia_espera_linha": 2.0,
    # o modal de compra e centralizado e CRESCE com o texto (nome longo ou
    # preco de 7 digitos quebram em 2 linhas), afastando Close/Ok do centro.
    # Por isso os botoes sao procurados por OCR em vez de usar so o ponto fixo.
    "vigilancia_achar_botao": True,
    "vigilancia_margem_botao": 0.6,  # folga em volta das regioes calibradas
    # --- revender na hora: coleta na Delivery Box e ja anuncia o que comprou,
    # antes de voltar pras buscas. Comeca DESLIGADO: anunciar paga 5% e nao tem
    # desfazer, entao e opt-in.
    # --- liquidez: desconto sem saida e dinheiro parado. Antes de comprar, rola
    # a lista pra contar quantos vendedores existem. Mercado cheio = fila longa
    # pra vender, entao so vale a pena com desconto grande.
    "vigilancia_medir_profundidade": True,
    "vigilancia_scrolls": 3,          # quantas rolagens pra baixo
    "vigilancia_scroll_passo": -5,    # cliques de roda por rolagem (negativo = desce)
    "vigilancia_mercado_cheio": 15,   # a partir de N ofertas, considera saturado
    "vigilancia_desconto_cheio": 50,  # % abaixo do valor exigido em mercado cheio
    "vigilancia_vender_apos_comprar": False,
    "vigilancia_botao_collect": [],   # botao Collect da Delivery Box
    "vigilancia_categoria_venda": 2,  # indice da aba (2 = Cartas)
    "vigilancia_espera_collect": 1.2,
    # vazio = <Area de Trabalho>/evidencias-preco, resolvida pelo Windows
    "vigilancia_pasta_evidencias": "",
    # filtros salvos: {nome: {"preco_minimo": int, "ignorados": [...]}}
    "vigilancia_filtros": {},
    "vigilancia_ultimo_filtro": "",
    # busca que nao devolve NENHUMA oferta e repetida antes de desistir;
    # se continuar vazia, a carta sai da rodagem (nao deve existir no mercado)
    "vigilancia_tentativas_vazio": 3,
    "vigilancia_espera_vazio": 10,
    # --- modo flip: compra gap menor que o do snipe, se sobrar lucro apos as
    # taxas do mercado (5% de listagem + 10% na venda = fica 85% do preco)
    "vigilancia_flip": False,
    "vigilancia_flip_gap": 18,        # % minimo abaixo da 2a oferta
    "vigilancia_flip_lucro": 5000,    # lucro liquido minimo por flip
    "vigilancia_orcamento": 0,        # teto de gasto da sessao (0 = sem)
    # fila de revenda: cada compra entra aqui com o preco sugerido de anuncio
    "vigilancia_arquivo_revenda": "",  # vazio = revenda.json na pasta
    # espera propria da vigilancia entre digitar e ler (0 = usa a espera geral).
    # Na watchlist quente vale baixar: menos espera = mais voltas por hora
    "vigilancia_espera": 0,
    # toda leitura de preco vira uma linha aqui (vazio = historico-precos.csv
    # na pasta do programa). E a materia-prima pra saber o que gira no mercado
    "vigilancia_arquivo_historico": "",
    # carta cuja media de preco fica abaixo disso sai da rodagem ate voce
    # limpar o filtro. 0 = nao filtra nada
    "vigilancia_preco_minimo": 0,
    "vigilancia_ofertas_media": 10,  # quantas ofertas entram na media do filtro
    "vigilancia_ignorados": [],      # cartas ja descartadas pelo filtro
    "vigilancia_pausa_volta": 0,     # segundos entre uma volta e a seguinte
    # atraso aleatorio (em milesimos) entre uma pesquisa e a seguinte, pra
    # nao ficar robotico. 0 a este valor, sorteado a cada carta
    "vigilancia_jitter_ms": 500,
    # --- reconexao automatica (o server desconecta todo mundo nos saves) ---
    "reconectar_ativo": True,
    # regiao + assinatura da BARRA "Select Server": e como sabemos que caimos
    # pra tela de login. Sem isso calibrado, a reconexao fica desligada.
    "reconectar_deteccao": [],
    "reconectar_assinatura": [],
    "reconectar_ok": [],          # botao Ok do aviso "You have disconnected" (opcional)
    "reconectar_connect": [],     # botao Connect (SA ja vem selecionado)
    # regiao + assinatura da tela de escolher personagem
    "reconectar_play_deteccao": [],
    "reconectar_play_assinatura": [],
    "reconectar_play": [],        # botao Play Character (ultimo char ja pre-selecionado)
    "reconectar_limiar": 22,      # tolerancia da assinatura pra dizer "e essa tela"
    "reconectar_espera_ok": 1.0,
    "reconectar_espera_connect": 6.0,   # Connect -> tela de personagem
    "reconectar_espera_play": 12.0,     # Play -> mundo carregado
    "reconectar_max_tentativas": 6,
    # --- medidor de XP: sobreposicao arrastavel com o ritmo e o tempo restante
    "xp_regiao": [],              # a barra inteira (nivel, %, %, nivel)
    "xp_intervalo": 10,           # segundos entre leituras por OCR (caro)
    # lendo da memoria custa ~3 microssegundos, entao da pra atualizar quase
    # ao vivo sem pesar em nada
    "xp_intervalo_memoria": 0.25,
    "xp_janela_minutos": 15,      # janela recente que define o ritmo
    "xp_overlay_pos": [],         # [x, y] onde voce largou a janelinha
    # "auto" tenta a memoria e cai no OCR se nao achar; "ocr" forca so a tela;
    # "memoria" exige a memoria e avisa se nao conseguir
    "xp_fonte": "auto",
    # de quantos em quantos ciclos tentar a memoria de novo, depois de falhar
    "xp_retentar_memoria": 30,
    "abatimento_venda": 0,        # valor fixo tirado de cada unidade ao anunciar
    "venda_espera": 0.8,          # espera depois de cada clique/busca na venda
    # espera depois de abrir o painel de venda, antes de clicar na aba: o
    # painel reabre com animacao e engole clique que chega cedo demais
    "venda_espera_painel": 1.5,
    "venda_max_linhas": 30,       # teto do jogo ("Items: n / 30")
    # quantos ITENS DIFERENTES por lote (item repetido empilha numa linha so).
    # Fica limitado pelo que cabe na tela, senao haveria linha sem como
    # preencher o preco
    "venda_itens_por_lote": 10,
    # do 2o lote em diante, clicar no botao azul reabre o painel? Se ele fechar
    # em vez de abrir, ponha false: dai so a aba e clicada entre um lote e outro
    "venda_reabrir_painel": True,
}


# --------------------------------------------------------------------------
# ambiente
# --------------------------------------------------------------------------

def preparar_console() -> None:
    """Evita UnicodeEncodeError quando a saida e redirecionada para arquivo."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def ativar_dpi() -> None:
    """Faz o processo enxergar pixels fisicos.

    Sem isso, com escala do Windows diferente de 100%, o clique do pyautogui
    cai num lugar e a captura de tela mostra outro.
    """
    if os.name != "nt":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

def carregar_config() -> dict:
    cfg = dict(CONFIG_PADRAO)
    if CAMINHO_CONFIG.exists():
        cfg.update(json.loads(CAMINHO_CONFIG.read_text(encoding="utf-8")))
    return cfg


def salvar_config(cfg: dict) -> None:
    CAMINHO_CONFIG.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def configurar_tesseract(cfg: dict | None = None) -> None:
    cfg = cfg or carregar_config()
    caminho = cfg.get("tesseract") or TESSERACT_PADRAO
    if not os.path.exists(caminho):
        raise SystemExit(
            f"Tesseract nao encontrado em: {caminho}\n"
            "Instale com:  winget install UB-Mannheim.TesseractOCR\n"
            "ou corrija o campo 'tesseract' no config.json."
        )
    pytesseract.pytesseract.tesseract_cmd = caminho


# --------------------------------------------------------------------------
# OCR
# --------------------------------------------------------------------------

def preparar_imagem(img: Image.Image, escala: int = 2, limiar: int | None = None) -> Image.Image:
    """Deixa a imagem no formato que o Tesseract gosta.

    As telas do jogo sao texto claro sobre fundo escuro; o Tesseract espera o
    contrario, entao invertemos. Ampliar 2x melhora muito fonte pequena.
    """
    g = img.convert("L")
    if escala != 1:
        g = g.resize((g.width * escala, g.height * escala), Image.LANCZOS)
    g = ImageOps.invert(g)
    g = ImageOps.autocontrast(g)
    if limiar is not None:
        g = g.point(lambda p: 255 if p > limiar else 0)
    return g


def isolar_texto_claro(img: Image.Image, escala: int = 3, limiar: int = 210) -> Image.Image:
    """Mantem so o que e quase branco, virando texto preto em fundo branco.

    A etiqueta de item do jogo e texto BRANCO sobre um fundo CLARO. Inverter e
    esticar o contraste (o caminho normal) deixa os dois cinza e o OCR erra;
    recortar pelo branco separa a letra de tudo o mais.
    """
    cinza = img.convert("L")
    if escala != 1:
        cinza = cinza.resize((cinza.width * escala, cinza.height * escala), Image.LANCZOS)
    return cinza.point(lambda p: 0 if p >= limiar else 255)


def isolar_texto_branco(img: Image.Image, escala: int = 3, v_minimo: int = 205,
                        s_maximo: int = 45, mancha: int = 9) -> Image.Image:
    """Isola texto BRANCO sobre fundo qualquer (inclusive claro e colorido).

    Serve pra HUD translucido, onde o cenario do jogo aparece por tras: pedra
    marrom, folhagem verde, ceu claro. Dois criterios, porque um so nao basta:

    1. **Cor**: branco tem valor alto e saturacao quase zero. Isso ja derruba
       folha verde, pedra marrom, barra azul e hexagono amarelo — todos
       saturados. Converter pra cinza (o caminho antigo) perdia justamente essa
       informacao, e ai flor branca virava igual a letra branca.

    2. **Espessura**: o que sobra de branco no cenario sao manchas gordas
       (flores, nuvens, reflexos), enquanto letra e traco fino. Uma abertura
       morfologica (erode + dilate) guarda so o que e mais grosso que `mancha`
       px — e esse resultado e subtraido. Traco fino sobrevive; mancha some.

    Devolve texto preto em fundo branco, do jeito que o Tesseract gosta.
    """
    hsv = img.convert("HSV")
    saturacao = hsv.getchannel("S").point(lambda p: 255 if p <= s_maximo else 0)
    brilho = hsv.getchannel("V").point(lambda p: 255 if p >= v_minimo else 0)
    mascara = ImageChops.multiply(saturacao, brilho)   # 0/255: um E logico

    if mancha and mancha >= 3:
        tamanho = mancha if mancha % 2 else mancha + 1   # o filtro exige impar
        nucleo = mascara.filter(ImageFilter.MinFilter(tamanho))    # erode
        gordas = nucleo.filter(ImageFilter.MaxFilter(tamanho))     # dilate
        mascara = ImageChops.subtract(mascara, gordas)

    if escala != 1:
        mascara = mascara.resize(
            (mascara.width * escala, mascara.height * escala), Image.LANCZOS)
        mascara = mascara.point(lambda p: 255 if p >= 128 else 0)
    return ImageChops.invert(mascara)


def palavras_ocr(img: Image.Image, psm: int = 11, escala: int = 2,
                 limiar: int | None = None, conf_minima: float = 30.0,
                 extra: str = "", texto_claro: int | None = None,
                 texto_branco: dict | None = None) -> list[dict]:
    """Roda o OCR e devolve palavras com caixa delimitadora na escala original.

    `texto_branco` (dict com v_minimo/s_maximo/mancha) usa o filtro por cor +
    espessura, pra texto branco sobre fundo qualquer — HUD translucido.
    """
    if texto_branco is not None:
        preparada = isolar_texto_branco(img, escala=escala, **texto_branco)
    elif texto_claro is not None:
        preparada = isolar_texto_claro(img, escala=escala, limiar=texto_claro)
    else:
        preparada = preparar_imagem(img, escala=escala, limiar=limiar)
    dados = pytesseract.image_to_data(
        preparada,
        config=f"--oem 3 --psm {psm} {extra}".strip(),
        output_type=pytesseract.Output.DICT,
    )
    saida = []
    for i, bruto in enumerate(dados["text"]):
        texto = bruto.strip()
        if not texto:
            continue
        try:
            conf = float(dados["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < conf_minima:
            continue
        saida.append(
            {
                "texto": texto,
                "conf": conf,
                "x": dados["left"][i] / escala,
                "y": dados["top"][i] / escala,
                "w": dados["width"][i] / escala,
                "h": dados["height"][i] / escala,
            }
        )
    for p in saida:
        p["cx"] = p["x"] + p["w"] / 2
        p["cy"] = p["y"] + p["h"] / 2
    return saida


# --------------------------------------------------------------------------
# agrupamento
# --------------------------------------------------------------------------

def pasta_area_de_trabalho() -> Path:
    """Onde fica a Area de Trabalho de verdade.

    Nao da pra chutar ~/Desktop: com OneDrive e Windows em portugues ela vira
    algo como "OneDrive/Area de Trabalho". Quem sabe o caminho certo e o
    proprio Windows.
    """
    if os.name == "nt":
        import ctypes
        import ctypes.wintypes

        CSIDL_DESKTOPDIRECTORY = 0x0010
        buffer = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        try:
            if ctypes.windll.shell32.SHGetFolderPathW(
                    None, CSIDL_DESKTOPDIRECTORY, None, 0, buffer) == 0 and buffer.value:
                return Path(buffer.value)
        except Exception:
            pass
    for tentativa in (Path.home() / "Desktop",
                      Path.home() / "OneDrive" / "Desktop",
                      Path.home() / "OneDrive" / "Área de Trabalho"):
        if tentativa.exists():
            return tentativa
    return Path.home()


def capturar(regiao: list[int]) -> Image.Image:
    """Print de um retangulo da tela (x, y, largura, altura)."""
    import mss

    x, y, largura, altura = regiao
    with mss.mss() as sct:
        bruto = sct.grab({"left": x, "top": y, "width": largura,
                          "height": altura})
    return Image.frombytes("RGB", bruto.size, bruto.bgra, "raw", "BGRX")


def tamanho_tela() -> tuple[int, int]:
    """Resolucao real do monitor principal, em pixels fisicos."""
    import mss

    with mss.mss() as sct:
        monitor = sct.monitors[1]
    return monitor["width"], monitor["height"]


LADO_ASSINATURA = 8


def assinatura(img: Image.Image) -> list[int]:
    """Reduz a regiao a uma impressao digital de brilho + cor.

    Serve pra responder "essa regiao ainda e a tela do mercado?". O conteudo
    muda a cada busca, mas o fundo e a grade de linhas continuam no mesmo
    lugar - ja o cenario 3D do jogo nao se parece em nada com isso.
    """
    pequena = img.convert("RGB").resize((LADO_ASSINATURA, LADO_ASSINATURA), Image.BILINEAR)
    hsv = pequena.convert("HSV")
    brilho = list(hsv.getchannel("V").getdata())
    cor = list(hsv.getchannel("S").getdata())
    return [int(v) for v in brilho + cor]


def distancia_assinatura(a: list[int], b: list[int]) -> float:
    """Diferenca media por celula, de 0 (identico) a 255."""
    if not a or not b or len(a) != len(b):
        return 255.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def mediana(valores: list[float]) -> float:
    if not valores:
        return 0.0
    v = sorted(valores)
    meio = len(v) // 2
    if len(v) % 2:
        return v[meio]
    return (v[meio - 1] + v[meio]) / 2


def agrupar_por(itens: list[dict], chave: str, folga: float) -> list[list[dict]]:
    """Agrupa itens ordenados por uma coordenada, cortando onde o vao e grande."""
    if not itens:
        return []
    ordenados = sorted(itens, key=lambda p: p[chave])
    grupos = [[ordenados[0]]]
    for atual in ordenados[1:]:
        anterior = grupos[-1][-1]
        if atual[chave] - anterior[chave] > folga:
            grupos.append([atual])
        else:
            grupos[-1].append(atual)
    return grupos


def agrupar_horizontal(itens: list[dict], folga: float) -> list[list[dict]]:
    """Como agrupar_por, mas medindo o vao real entre uma caixa e a seguinte.

    Precisa disso pra remontar numero cuja virgula o OCR comeu: "22 222" sao
    duas caixas quase encostadas, enquanto quantidade e preco ficam a centenas
    de pixels de distancia.
    """
    if not itens:
        return []
    ordenados = sorted(itens, key=lambda p: p["x"])
    grupos = [[ordenados[0]]]
    for atual in ordenados[1:]:
        anterior = grupos[-1][-1]
        if atual["x"] - (anterior["x"] + anterior["w"]) > folga:
            grupos.append([atual])
        else:
            grupos[-1].append(atual)
    return grupos


PADRAO_NUMERO = re.compile(r"^[\d][\d.,]*$")


def eh_numero(texto: str) -> bool:
    return bool(PADRAO_NUMERO.match(texto)) and any(c.isdigit() for c in texto)


def tem_letra(texto: str) -> bool:
    return any(c.isalpha() for c in texto)


def para_inteiro(texto: str) -> int | None:
    """'2,002,500' -> 2002500. Devolve None se nao for numero."""
    limpo = re.sub(r"[^\d]", "", texto)
    return int(limpo) if limpo else None
