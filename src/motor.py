import csv
import json
import unicodedata
from datetime import datetime
from pathlib import Path

import localizacao

RAIZ = Path(__file__).resolve().parent.parent
MAX_CANDIDATAS = localizacao.MAX_CANDIDATAS
MAX_RESULTADOS = localizacao.MAX_RESULTADOS
MAX_BAIRRO = localizacao.MAX_BAIRRO
URGENCIA_ODONTOLOGICA_PATH = RAIZ / "data" / "urgencia_odontologica.csv"
URGENCIA_ODONTOLOGICA_COLUNAS = {
    "id_local",
    "crs",
    "sts",
    "nome",
    "dias_atendimento",
    "horario",
    "endereco",
    "telefone",
    "municipio",
    "uf",
    "servico",
    "fonte_arquivo",
    "fonte_pagina",
    "observacoes",
}
CAPS_PATH = RAIZ / "data" / "caps_servicos.csv"
CAPS_COLUNAS = {
    "id_local",
    "regiao",
    "nome",
    "modalidade",
    "nivel",
    "endereco",
    "cep",
    "territorio_informado",
    "telefone",
    "municipio",
    "uf",
    "fonte_url",
    "verificado_em",
    "observacoes",
}
CAPS_MODALIDADES = {"AD", "ADULTO", "IJ"}

AVISO = (
    "Orientação informativa: não é canal oficial e não substitui avaliação "
    "profissional. Confirme na unidade. Em emergência, ligue 192 (SAMU)."
)
NAO_SEI = (
    "Não tenho orientação validada para isso. Procure a UBS mais próxima "
    "ou ligue 136 (Disque Saúde)."
)


def norm(texto):
    t = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower().strip()


def carregar_regras():
    with open(RAIZ / "data" / "regras.json", encoding="utf-8") as f:
        return json.load(f)["situacoes"]


def carregar_unidades():
    with open(RAIZ / "data" / "unidades.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def carregar_urgencias_odontologicas():
    """Carrega a fonte local confirmada de serviços odontológicos de urgência."""
    with URGENCIA_ODONTOLOGICA_PATH.open(
        encoding="utf-8-sig", newline=""
    ) as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";")
        if set(leitor.fieldnames or ()) != URGENCIA_ODONTOLOGICA_COLUNAS:
            raise ValueError("Colunas inválidas na tabela de urgência odontológica.")
        linhas = list(leitor)
    if not linhas:
        raise ValueError("Tabela de urgência odontológica vazia.")
    return [_adaptar_urgencia_odontologica(linha) for linha in linhas]


def _adaptar_urgencia_odontologica(linha):
    """Adapta a tabela local para o formato usado pela apresentação e pelo ORS."""
    return {
        "CO_CNES": "",
        "TIPO": linha["nome"].split(maxsplit=1)[0] if linha["nome"] else "",
        "NOME": linha["nome"],
        "NO_BAIRRO": linha["sts"],
        "NO_LOGRADOURO": linha["endereco"],
        "NU_ENDERECO": "",
        "NU_TELEFONE": linha["telefone"],
        "dias_atendimento": linha["dias_atendimento"],
        "horario": linha["horario"],
        "id_local": linha["id_local"],
        "servico": linha["servico"],
        "observacoes": linha["observacoes"],
        "municipio": linha["municipio"],
        "uf": linha["uf"],
    }


def carregar_caps():
    """Carrega e valida a fonte local de serviços CAPS."""
    with CAPS_PATH.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";")
        if set(leitor.fieldnames or ()) != CAPS_COLUNAS:
            raise ValueError("Colunas inválidas na tabela de CAPS.")
        linhas = list(leitor)

    ids = [linha["id_local"] for linha in linhas]
    pares = [(linha["nome"], linha["endereco"]) for linha in linhas]
    if any(not linha["id_local"] or not linha["nome"] or not linha["endereco"]
           for linha in linhas):
        raise ValueError("Há registros CAPS sem identificador, nome ou endereço.")
    if len(ids) != len(set(ids)):
        raise ValueError("Há identificadores CAPS duplicados.")
    if len(pares) != len(set(pares)):
        raise ValueError("Há registros CAPS duplicados por nome e endereço.")
    if any(linha["modalidade"] not in CAPS_MODALIDADES for linha in linhas):
        raise ValueError("Há modalidade CAPS não reconhecida.")
    return [_adaptar_caps(linha) for linha in linhas]


def _adaptar_caps(linha):
    observacoes = linha["observacoes"]
    endereco = ", ".join(
        parte
        for parte in (
            linha["endereco"],
            linha["cep"] if "cep" not in norm(observacoes) else "",
            linha["municipio"],
            linha["uf"],
            "Brasil",
        )
        if parte
    )
    endereco_sem_cep = ", ".join(
        parte
        for parte in (linha["endereco"], linha["municipio"], linha["uf"], "Brasil")
        if parte
    )
    return {
        "CO_CNES": "",
        "TIPO": "CAPS",
        "NOME": linha["nome"],
        "NO_BAIRRO": linha["territorio_informado"],
        "NO_LOGRADOURO": linha["endereco"],
        "NU_ENDERECO": "",
        "NU_TELEFONE": linha["telefone"],
        "municipio": linha["municipio"],
        "uf": linha["uf"],
        "cep": linha["cep"] if "cep" not in norm(observacoes) else "",
        "endereco_completo": endereco,
        "endereco_sem_cep": endereco_sem_cep,
        "cache_namespace": "caps",
        "id_local": linha["id_local"],
        "modalidade": linha["modalidade"],
        "nivel": linha["nivel"],
        "fonte_url": linha["fonte_url"],
        "verificado_em": linha["verificado_em"],
    }


def bairros(unidades):
    return sorted({u["NO_BAIRRO"] for u in unidades if u["NO_BAIRRO"]})


def sugerir_situacao(texto, situacoes):
    """Leva texto livre até uma opção do menu. Nunca decide a orientação."""
    t = norm(texto)
    melhor, pontos = None, 0
    for s in situacoes:
        p = sum(1 for k in s["palavras"] if norm(k) in t)
        if p > pontos:
            melhor, pontos = s, p
    if pontos >= 2:
        return melhor, "alta"
    if pontos == 1:
        return melhor, "média"
    return None, "baixa"


def decidir(situacao, marcadas):
    """Primeira regra cujas condições batem. Pergunta não marcada = não."""
    resp = {p["id"]: p["id"] in marcadas for p in situacao["perguntas"]}
    for regra in situacao["regras"]:
        if all(resp.get(k, False) == v for k, v in regra["quando"].items()):
            return regra
    return None


def validada(regra):
    """Regra com campo PREENCHER ainda não tem fonte oficial: não responde."""
    return "PREENCHER" not in json.dumps(regra, ensure_ascii=False)


def selecionar_candidatas(tipos, bairro, unidades):
    compatíveis = [u for u in unidades if u["TIPO"] in tipos]
    no_bairro = sorted(
        (u for u in compatíveis if norm(u["NO_BAIRRO"]) == norm(bairro)),
        key=lambda u: norm(u["NOME"]),
    )
    outras = sorted(
        (u for u in compatíveis if norm(u["NO_BAIRRO"]) != norm(bairro)),
        key=lambda u: norm(u["NOME"]),
    )
    candidatas = no_bairro[:MAX_BAIRRO]
    restante = MAX_CANDIDATAS - len(candidatas)
    return candidatas + outras[:max(0, restante)]


def _rotas_com_cache(chave, origem, unidades_coordenadas):
    try:
        with localizacao.RELACIONAMENTOS_PATH.open(encoding="utf-8") as arquivo:
            relacionamentos = json.load(arquivo)
    except (OSError, json.JSONDecodeError):
        relacionamentos = {}

    ids = [
        localizacao._chave_unidade(unidade)
        for unidade, _ in unidades_coordenadas
    ]
    cache_rotas = relacionamentos.get(chave, {})
    if all(identificador in cache_rotas for identificador in ids):
        return [
            tuple(cache_rotas[identificador]) if cache_rotas[identificador] else None
            for identificador in ids
        ]

    rotas = localizacao.calcular_rotas(
        origem, [coordenadas for _, coordenadas in unidades_coordenadas]
    )
    if rotas is None:
        return None

    relacionamentos[chave] = {
        identificador: list(rota) if rota else None
        for identificador, rota in zip(ids, rotas)
    }
    localizacao.RELACIONAMENTOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    localizacao.RELACIONAMENTOS_PATH.write_text(
        json.dumps(relacionamentos, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return rotas


def achar_unidades(tipos, bairro, unidades):
    """Busca por rota quando disponível; sem chave, usa o fallback por bairro."""
    candidatas = selecionar_candidatas(tipos, bairro, unidades)
    if not candidatas:
        return [], "vazio"

    origem = localizacao.geocodificar_bairro(bairro)
    if origem is None:
        return [
            (unidade, None, None)
            for unidade in candidatas[:MAX_RESULTADOS]
        ], "api_falha" if localizacao.api_configurada() else "bairro"

    com_coordenadas = []
    sem_coordenadas = []
    for unidade in candidatas:
        coordenadas = localizacao.geocodificar_unidade(unidade)
        if coordenadas is None:
            sem_coordenadas.append(unidade)
        else:
            com_coordenadas.append((unidade, coordenadas))

    chave_relacao = norm(bairro) + "|" + ",".join(sorted(tipos))
    rotas = _rotas_com_cache(chave_relacao, origem, com_coordenadas)
    if rotas is None:
        return [
            (unidade, None, None)
            for unidade in candidatas[:MAX_RESULTADOS]
        ], "api_falha"
    if rotas is None:
        return [
            (unidade, None, None)
            for unidade in candidatas[:MAX_RESULTADOS]
        ], "api_falha"

    com_rota = []
    sem_rota = list(sem_coordenadas)
    for (unidade, _), rota in zip(com_coordenadas, rotas):
        if rota is None:
            sem_rota.append(unidade)
        else:
            com_rota.append((unidade, rota[0], rota[1]))
    bairro_normalizado = norm(bairro)
    com_rota.sort(
        key=lambda item: (
            norm(item[0]["NO_BAIRRO"]) != bairro_normalizado,
            item[1],
        )
    )
    resultados = com_rota[:MAX_RESULTADOS]
    restantes = MAX_RESULTADOS - len(resultados)
    resultados.extend((unidade, None, None) for unidade in sem_rota[:restantes])
    return resultados, "rota"


def achar_urgencias_odontologicas(bairro):
    """Busca somente as unidades confirmadas na tabela odontológica local."""
    try:
        unidades = carregar_urgencias_odontologicas()
    except (OSError, UnicodeError, csv.Error, ValueError):
        return [], "fonte_indisponivel"

    if not localizacao.api_configurada():
        return [], "api_indisponivel"

    origem = localizacao.geocodificar_bairro(bairro)
    if origem is None:
        return [], "api_indisponivel"

    com_coordenadas = []
    for unidade in unidades:
        coordenadas = localizacao.geocodificar_unidade(unidade)
        if coordenadas is not None:
            com_coordenadas.append((unidade, coordenadas))
    if not com_coordenadas:
        return [], "api_indisponivel"

    rotas = _rotas_com_cache(
        norm(bairro) + "|urgencia_odontologica",
        origem,
        com_coordenadas,
    )
    if rotas is None:
        return [], "api_indisponivel"

    resultados = [
        (unidade, distancia, duracao)
        for (unidade, _), rota in zip(com_coordenadas, rotas)
        if rota is not None
        for distancia, duracao in [rota]
    ]
    resultados.sort(key=lambda item: item[1])
    return resultados[:MAX_RESULTADOS], "rota"


def achar_caps(modalidade, bairro):
    """Busca somente CAPS da modalidade escolhida na tabela local."""
    try:
        unidades = [
            unidade
            for unidade in carregar_caps()
            if unidade["modalidade"] == modalidade
        ]
    except (OSError, UnicodeError, csv.Error, ValueError):
        return [], "fonte_indisponivel"
    if not unidades or not localizacao.api_configurada():
        return [], "api_indisponivel"
    origem = localizacao.geocodificar_bairro(bairro)
    if origem is None:
        return [], "api_indisponivel"

    com_coordenadas = []
    for unidade in unidades:
        coordenadas = localizacao.geocodificar_unidade(unidade)
        if coordenadas is not None:
            com_coordenadas.append((unidade, coordenadas))
    if not com_coordenadas:
        return [], "api_indisponivel"
    rotas = _rotas_com_cache(
        norm(bairro) + "|caps_" + modalidade,
        origem,
        com_coordenadas,
    )
    if rotas is None:
        return [], "api_indisponivel"
    resultados = [
        (unidade, distancia, duracao)
        for (unidade, _), rota in zip(com_coordenadas, rotas)
        if rota is not None
        for distancia, duracao in [rota]
    ]
    resultados.sort(key=lambda item: item[1])
    return resultados[:MAX_RESULTADOS], "rota"


def modalidade_caps_em_linguagem_simples(modalidade):
    return {
        "AD": "Álcool e outras drogas",
        "ADULTO": "Saúde mental para adulto",
        "IJ": "Saúde mental para criança ou adolescente",
    }[modalidade]


def formatar_unidade(
    unidade,
    distancia=None,
    duracao=None,
    odontologica=False,
    caps=False,
):
    endereco = (
        ", ".join(
            parte
            for parte in (
                unidade.get("NO_LOGRADOURO", ""),
                unidade.get("NO_BAIRRO", ""),
                unidade.get("municipio", "São Paulo"),
                unidade.get("uf", "SP"),
            )
            if parte
        )
        if odontologica
        else localizacao.montar_endereco_unidade(unidade)
    )
    telefone = (
        f'\n  Tel: {unidade["NU_TELEFONE"]}'
        if unidade.get("NU_TELEFONE")
        else ""
    )
    partes = [f'- **{unidade["NOME"]}** ({unidade["TIPO"]})', endereco + telefone]
    if odontologica:
        partes.append(
            f'**Atendimento odontológico:** {unidade["dias_atendimento"]}; '
            f'{unidade["horario"]}'
        )
    if caps:
        partes.append(
            "**Modalidade:** "
            + modalidade_caps_em_linguagem_simples(unidade["modalidade"])
        )
    if distancia is not None:
        partes.append(f"Distância aproximada: {distancia / 1000:.3g} km".replace(".", ","))
    if duracao is not None:
        partes.append(f"Tempo estimado de carro: {duracao:.0f} min".replace(".", ","))
    return "\n".join(partes)


def responder(situacao, marcadas, bairro, unidades, modalidade_caps=None):
    regra = decidir(situacao, marcadas)
    if regra is None or not validada(regra):
        return f"{NAO_SEI}\n\n{AVISO}", "baixa"

    fonte = regra["fonte"]
    partes = [f'**{regra["orientacao"]}**']
    if regra.get("levar"):
        partes.append("**O que levar:** " + ", ".join(regra["levar"]))

    if situacao.get("id") == "saude_mental":
        if modalidade_caps is None:
            return "Escolha que atendimento de saúde mental você procura.", "baixa"
        if modalidade_caps == "NAO_SEI":
            partes = [
                "**Procure a UBS indicada para acolhimento e orientação sobre "
                "o acesso ao atendimento em saúde mental.**"
            ]
            lista, modo = achar_unidades(["UBS"], bairro, unidades)
            if modo == "api_falha":
                partes = [
                    "**Para acolhimento e orientação sobre o acesso ao "
                    "atendimento em saúde mental, procure uma UBS.**"
                ]
                partes.append(
                    "Não foi possível buscar unidades próximas agora."
                )
            elif lista and modo == "rota":
                partes.append(
                    "Procure a UBS indicada para acolhimento e orientação "
                    "sobre o acesso ao atendimento em saúde mental."
                )
                partes.append("**Unidades próximas ao bairro informado:**")
                partes.extend(formatar_unidade(*item) for item in lista)
            else:
                partes.append(
                    "Procure a UBS indicada para acolhimento e orientação "
                    "sobre o acesso ao atendimento em saúde mental."
                )
            partes.append(
                f'*Fonte: {fonte["titulo"]} — {fonte["url"]} '
                f'(verificado em {fonte["verificado_em"]})*'
            )
            partes.append(AVISO)
            return "\n\n".join(partes), "alta"

        if modalidade_caps not in CAPS_MODALIDADES:
            return "Escolha uma opção válida de atendimento.", "baixa"
        lista, modo = achar_caps(modalidade_caps, bairro)
        if modo == "fonte_indisponivel":
            partes.append("A lista de CAPS não pôde ser carregada.")
        elif modo == "api_indisponivel":
            partes.append("Não foi possível buscar unidades próximas agora.")
        elif lista:
            partes.append("**Opções de CAPS para o atendimento procurado:**")
            partes.extend(
                formatar_unidade(*item, caps=True) for item in lista
            )
            partes.append(
                "*A proximidade não confirma que esta seja sua unidade de "
                "referência. Confirme o atendimento com o serviço.*"
            )
            fonte_caps = lista[0][0]
            partes.append(
                f'*Fonte da tabela de CAPS: {fonte_caps["fonte_url"]} '
                f'(verificado em {fonte_caps["verificado_em"]})*'
            )
        else:
            partes.append("Não foi possível buscar unidades próximas agora.")
        partes.append(
            f'*Fonte: {fonte["titulo"]} — {fonte["url"]} '
            f'(verificado em {fonte["verificado_em"]})*'
        )
        partes.append(AVISO)
        return "\n\n".join(partes), "alta"

    urgencia_odontologica = (
        situacao.get("id") == "dentista"
        and regra.get("quando", {}).get("urgencia") is True
    )
    if urgencia_odontologica:
        lista, modo = achar_urgencias_odontologicas(bairro)
        if modo == "fonte_indisponivel":
            partes.append(
                "A lista local de serviços odontológicos de urgência "
                "não pôde ser carregada."
            )
        elif modo == "api_indisponivel":
            partes.append(
                "Não foi possível buscar unidades próximas com serviço "
                "odontológico de urgência agora."
            )
        elif lista:
            partes.append("**Unidades próximas ao bairro informado:**")
            partes.extend(
                formatar_unidade(
                    unidade,
                    distancia,
                    duracao,
                    odontologica=True,
                )
                for unidade, distancia, duracao in lista
            )
            partes.append(
                "*Os horários são do serviço odontológico e podem sofrer "
                "alterações. Confirme o funcionamento com a unidade.*"
            )
        else:
            partes.append(
                "Não foi possível buscar unidades próximas com serviço "
                "odontológico de urgência agora."
            )
        partes.append(
            f'*Fonte: {fonte["titulo"]} — {fonte["url"]} '
            f'(verificado em {fonte["verificado_em"]})*'
        )
        partes.append(AVISO)
        return "\n\n".join(partes), "alta"

    lista, modo = achar_unidades(regra["tipos"], bairro, unidades)
    com_distancia = [item for item in lista if item[1] is not None]
    sem_distancia = [item for item in lista if item[1] is None]
    if modo == "rota" and com_distancia:
        partes.append("**Unidades próximas ao bairro informado:**")
        partes.extend(formatar_unidade(*item) for item in com_distancia)
        if sem_distancia:
            partes.append("**Outras opções compatíveis:**")
            partes.extend(formatar_unidade(*item) for item in sem_distancia)
    elif modo == "api_falha":
        partes.append(
            "Não consegui calcular as distâncias agora. "
            "Vou mostrar as opções do bairro."
        )
        partes.append(
            "**Unidades no seu bairro:**"
            if any(norm(item[0]["NO_BAIRRO"]) == norm(bairro) for item in lista)
            else "**Não encontrei uma unidade compatível neste bairro. "
            "Veja outras opções:**"
        )
        partes.extend(formatar_unidade(*item) for item in lista)
    elif lista:
        tem_bairro = any(
            norm(item[0]["NO_BAIRRO"]) == norm(bairro) for item in lista
        )
        partes.append(
            "**Unidades no seu bairro:**"
            if tem_bairro
            else "**Não encontrei uma unidade compatível neste bairro. "
            "Veja outras opções:**"
        )
        partes.extend(formatar_unidade(*item) for item in lista)
    else:
        partes.append("Não há unidade deste tipo na base. Veja o site da prefeitura.")

    partes.append(
        f'*Fonte: {fonte["titulo"]} — {fonte["url"]} '
        f'(verificado em {fonte["verificado_em"]})*'
    )
    partes.append(AVISO)
    return "\n\n".join(partes), "alta"


def registrar(situacao_id, confianca):
    """Log anônimo: só situação e confiança. Não guarda localização."""
    arq = RAIZ / "logs" / "indicadores.csv"
    arq.parent.mkdir(exist_ok=True)
    novo = not arq.exists()
    with open(arq, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["quando", "situacao", "confianca"])
        w.writerow(
            [datetime.now().isoformat(timespec="seconds"), situacao_id, confianca]
        )
