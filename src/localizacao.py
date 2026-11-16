import json
import math
import os
import tempfile
import threading
import unicodedata
from pathlib import Path

import requests
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
CACHE_PATH = RAIZ / "data" / "geocodificacao_unidades.json"
RELACIONAMENTOS_PATH = RAIZ / "data" / "relacionamentos_bairros.json"
ARCGIS_GEOCODE_URL = (
    "https://geocode-api.arcgis.com/arcgis/rest/services/World/"
    "GeocodeServer/findAddressCandidates"
)
ARCGIS_ROUTE_URL = (
    "https://route-api.arcgis.com/arcgis/rest/services/World/Route/"
    "NAServer/Route_World/solve"
)
HTTP_TIMEOUT = 10
MAX_CANDIDATAS = 20
MAX_RESULTADOS = 5
MAX_BAIRRO = 10
_CACHE_BAIRROS = {}
_CACHE_UNIDADES = None
_LOCK = threading.RLock()


def _chave_api():
    load_dotenv(RAIZ / ".env")
    return os.getenv("ARCGIS_TOKEN", "").strip()


def api_configurada():
    return bool(_chave_api())


def _texto(valor):
    if valor is None:
        return ""
    texto = str(valor).strip()
    if not texto or texto.casefold() in {"nan", "none"}:
        return ""
    return texto


def _normalizar(texto):
    normalizado = unicodedata.normalize("NFKD", _texto(texto))
    return "".join(
        caractere
        for caractere in normalizado
        if unicodedata.category(caractere) != "Mn"
    ).casefold()


def validar_coordenadas(coordenadas):
    """Valida e retorna uma tupla (longitude, latitude)."""
    if not isinstance(coordenadas, (list, tuple)) or len(coordenadas) != 2:
        return None
    try:
        longitude, latitude = map(float, coordenadas)
    except (TypeError, ValueError):
        return None
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        return None
    return longitude, latitude


def _consultar_endereco(params):
    chave = _chave_api()
    if not chave:
        return None, "temporary"
    try:
        resposta = requests.get(
            ARCGIS_GEOCODE_URL,
            params={
                **params,
                "f": "json",
                "token": chave,
                "outSr": "4326",
            },
            timeout=HTTP_TIMEOUT,
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except (requests.RequestException, ValueError):
        return None, "temporary"
    if isinstance(dados, dict) and dados.get("error"):
        return None, "temporary"
    candidates = dados.get("candidates") if isinstance(dados, dict) else None
    if not isinstance(candidates, list) or not candidates:
        return None, "not_found"
    location = candidates[0].get("location")
    if not isinstance(location, dict):
        return None, "not_found"
    coordenadas = validar_coordenadas((location.get("x"), location.get("y")))
    return (coordenadas, "ok") if coordenadas else (None, "not_found")


def geocodificar_bairro(bairro):
    consulta = f"{_texto(bairro)}, São Paulo, SP, Brasil"
    chave = _normalizar(consulta)
    if not api_configurada() or not _texto(bairro):
        return None
    with _LOCK:
        if chave not in _CACHE_BAIRROS:
            _CACHE_BAIRROS[chave] = _consultar_endereco(
                {"address": _texto(bairro), "city": "São Paulo"}
            )[0]
        return _CACHE_BAIRROS[chave]


def montar_endereco_unidade(unidade):
    logradouro = _texto(unidade.get("NO_LOGRADOURO"))
    numero = _texto(unidade.get("NU_ENDERECO"))
    bairro = _texto(unidade.get("NO_BAIRRO"))
    nome = _texto(unidade.get("NOME"))
    cep = _texto(unidade.get("CO_CEP")) or _texto(unidade.get("cep"))
    municipio = _texto(unidade.get("municipio")) or "São Paulo"
    uf = _texto(unidade.get("uf")) or "SP"

    partes = []
    if logradouro:
        partes.append(f"{logradouro}, {numero}" if numero else logradouro)
    if bairro:
        partes.append(bairro)
    if nome and not logradouro:
        partes.insert(0, nome)
    if cep:
        partes.append(cep)
    partes.extend([municipio, uf, "Brasil"])
    return ", ".join(partes)


def _chave_unidade(unidade):
    cnes = _texto(unidade.get("CO_CNES"))
    if cnes:
        return cnes
    namespace = _texto(unidade.get("cache_namespace")) or "unidade"
    identificador = _texto(unidade.get("id_local"))
    base = identificador or montar_endereco_unidade(unidade)
    return f"{namespace}:{_normalizar(base)}"


def _carregar_cache():
    global _CACHE_UNIDADES
    if _CACHE_UNIDADES is not None:
        return _CACHE_UNIDADES
    try:
        with CACHE_PATH.open(encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except (OSError, json.JSONDecodeError):
        dados = {}
    _CACHE_UNIDADES = dados if isinstance(dados, dict) else {}
    return _CACHE_UNIDADES


def _salvar_cache():
    cache = _CACHE_UNIDADES or {}
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, caminho = tempfile.mkstemp(
        prefix=f"{CACHE_PATH.name}.", suffix=".tmp", dir=CACHE_PATH.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            json.dump(cache, arquivo, ensure_ascii=False, indent=2)
        os.replace(caminho, CACHE_PATH)
    except OSError:
        try:
            os.unlink(caminho)
        except OSError:
            pass


def geocodificar_unidade(unidade):
    global _CACHE_UNIDADES
    if not api_configurada():
        return None
    endereco = montar_endereco_unidade(unidade)
    cep = _texto(unidade.get("CO_CEP")) or _texto(unidade.get("cep"))
    chave = _chave_unidade(unidade)
    with _LOCK:
        cache = _carregar_cache()
        registro = cache.get(chave)
        if isinstance(registro, dict) and registro.get("status") == "nao_encontrado":
            return None
        if isinstance(registro, dict) and registro.get("status") == "ok":
            if registro.get("provedor") != "arcgis":
                registro = None
        if isinstance(registro, dict) and registro.get("status") == "ok":
            coordenadas = validar_coordenadas(
                (registro.get("longitude"), registro.get("latitude"))
            )
            if coordenadas is not None:
                return coordenadas

        consulta = {"postal": cep} if cep else {
            "address": endereco,
            "city": "São Paulo",
        }
        coordenadas, status = _consultar_endereco(consulta)
        cache_alterado = False
        if coordenadas is None and status != "temporary":
            cache[chave] = {
                "endereco_consultado": endereco,
                "provedor": "arcgis",
                "status": "nao_encontrado",
            }
            cache_alterado = True
        elif coordenadas is not None:
            cache[chave] = {
                "endereco_consultado": endereco,
                "longitude": coordenadas[0],
                "latitude": coordenadas[1],
                "provedor": "arcgis",
                "status": "ok",
            }
            cache_alterado = True
        _CACHE_UNIDADES = cache
        if cache_alterado:
            _salvar_cache()
        return coordenadas


def calcular_rotas(origem, destinos):
    """Retorna (distância_metros, duração_minutos) na ordem dos destinos."""
    origem = validar_coordenadas(origem)
    destinos = [validar_coordenadas(destino) for destino in destinos]
    if not _chave_api() or origem is None or not destinos or any(
        destino is None for destino in destinos
    ):
        return None
    resultados = []
    for destino in destinos:
        try:
            resposta = requests.get(
                ARCGIS_ROUTE_URL,
                params={
                    "f": "json",
                    "token": _chave_api(),
                    "stops": f"{origem[0]},{origem[1]};{destino[0]},{destino[1]}",
                },
                timeout=HTTP_TIMEOUT,
            )
            resposta.raise_for_status()
            dados = resposta.json()
            atributos = dados["routes"]["features"][0]["attributes"]
            resultados.append((
                float(atributos["Total_Kilometers"]) * 1000,
                float(atributos["Total_TravelTime"]),
            ))
        except (KeyError, TypeError, ValueError, requests.RequestException):
            resultados.append(None)
    return resultados if any(resultado is not None for resultado in resultados) else None
