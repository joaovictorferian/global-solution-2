"""Servidor do Orientação SUS.

Aqui ficam só as rotas e a validação dos dados que chegam do navegador.
A interface está em static/ (index.html, css/style.css, js/app.js) e as
regras de orientação continuam no motor.py.
"""
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import motor

PASTA_STATIC = Path(__file__).resolve().parent / "static"

app = Flask(__name__, static_folder=str(PASTA_STATIC), static_url_path="/static")

REGRAS = motor.carregar_regras()
UNIDADES = motor.carregar_unidades()
POR_ID = {s["id"]: s for s in REGRAS}
# Ignora valores que são códigos e não nomes de bairro (ex.: "355030").
BAIRROS = [b for b in motor.bairros(UNIDADES) if any(c.isalpha() for c in b)]
BAIRROS_VALIDOS = set(BAIRROS)

MODALIDADES_SAUDE_MENTAL = [
    {"id": "ADULTO", "texto": "Saúde mental para adulto"},
    {"id": "IJ", "texto": "Saúde mental para criança ou adolescente"},
    {"id": "AD", "texto": "Atendimento relacionado ao uso de álcool ou outras drogas"},
    {"id": "NAO_SEI", "texto": "Não sei qual escolher"},
]
IDS_MODALIDADE = {m["id"] for m in MODALIDADES_SAUDE_MENTAL}

ERRO_GERAL = (
    "Não foi possível gerar a orientação agora. Tente novamente em instantes. "
    "Em caso de emergência, ligue 192 (SAMU)."
)


def _situacao_para_json(situacao):
    exige_modalidade = situacao["id"] == "saude_mental"
    return {
        "id": situacao["id"],
        "titulo": situacao["titulo"],
        "perguntas": [
            {"id": p["id"], "texto": p["texto"]}
            for p in situacao.get("perguntas", [])
        ],
        "modalidades": MODALIDADES_SAUDE_MENTAL if exige_modalidade else [],
    }


def _erro(mensagem, codigo=400):
    return jsonify({"erro": mensagem}), codigo


@app.after_request
def cabecalhos_de_seguranca(resposta):
    resposta.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    )
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    return resposta


@app.get("/")
def pagina_inicial():
    return send_from_directory(PASTA_STATIC, "index.html")


@app.get("/api/opcoes")
def opcoes():
    return jsonify(
        {
            "aviso": motor.AVISO,
            "bairros": BAIRROS,
            "situacoes": [_situacao_para_json(s) for s in REGRAS],
        }
    )


@app.post("/api/sugerir")
def sugerir():
    dados = request.get_json(silent=True) or {}
    texto = str(dados.get("texto", ""))[:1000]
    situacao, _confianca = motor.sugerir_situacao(texto, REGRAS)
    return jsonify({"situacao": situacao["id"] if situacao else None})


@app.post("/api/orientar")
def orientar():
    dados = request.get_json(silent=True) or {}
    bairro = dados.get("bairro")
    sit_id = dados.get("situacao")
    marcadas = dados.get("marcadas") or []
    modalidade = dados.get("modalidade") or None

    if bairro not in BAIRROS_VALIDOS:
        return _erro("Escolha um bairro da lista.")
    if sit_id not in POR_ID:
        return _erro("Escolha o que você precisa.")
    situacao = POR_ID[sit_id]

    ids_perguntas = {p["id"] for p in situacao.get("perguntas", [])}
    if not isinstance(marcadas, list) or not set(marcadas) <= ids_perguntas:
        return _erro("Resposta inválida. Atualize a página e tente de novo.")

    if situacao["id"] == "saude_mental":
        if modalidade not in IDS_MODALIDADE:
            return _erro("Escolha o tipo de atendimento de saúde mental.")
    else:
        modalidade = None

    try:
        resposta, confianca = motor.responder(
            situacao, marcadas, bairro, UNIDADES, modalidade_caps=modalidade
        )
        motor.registrar(sit_id, confianca)
    except Exception:
        app.logger.exception("Falha ao gerar orientação")
        return _erro(ERRO_GERAL, 500)

    return jsonify({"orientacao": resposta})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
