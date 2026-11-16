import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import localizacao
import motor


def unidade(nome, bairro="VILA A", cnes="1"):
    return {
        "CO_CNES": cnes,
        "TIPO": "UBS",
        "NOME": nome,
        "NO_BAIRRO": bairro,
        "NO_LOGRADOURO": "Rua Exemplo",
        "NU_ENDERECO": "10",
        "NU_TELEFONE": "",
        "NU_LATITUDE": "valor inválido",
        "NU_LONGITUDE": "valor inválido",
    }


SITUACAO = {
    "perguntas": [],
    "regras": [
        {
            "quando": {},
            "orientacao": "Orientação de teste.",
            "tipos": ["UBS"],
            "levar": [],
            "fonte": {
                "titulo": "Fonte de teste",
                "url": "https://example.test",
                "verificado_em": "2026-11-09",
            },
        }
    ],
}


class Resposta:
    def __init__(self, dados):
        self.dados = dados

    def raise_for_status(self):
        return None

    def json(self):
        return self.dados


class LocalizacaoTests(unittest.TestCase):
    def setUp(self):
        localizacao._CACHE_BAIRROS.clear()
        localizacao._CACHE_UNIDADES = None
        self.cache_temporario = tempfile.TemporaryDirectory()
        self.cache_anterior = localizacao.CACHE_PATH
        self.relacionamentos_anterior = localizacao.RELACIONAMENTOS_PATH
        localizacao.CACHE_PATH = Path(self.cache_temporario.name) / "cache.json"
        localizacao.RELACIONAMENTOS_PATH = (
            Path(self.cache_temporario.name) / "relacionamentos.json"
        )

    def tearDown(self):
        localizacao.CACHE_PATH = self.cache_anterior
        localizacao.RELACIONAMENTOS_PATH = self.relacionamentos_anterior
        localizacao._CACHE_BAIRROS.clear()
        localizacao._CACHE_UNIDADES = None
        self.cache_temporario.cleanup()

    def test_chave_ausente_faz_fallback_sem_requisicao(self):
        with patch.object(localizacao, "api_configurada", return_value=False):
            with patch.object(localizacao.requests, "get") as get:
                self.assertIsNone(localizacao.geocodificar_bairro("VILA A"))
                self.assertIsNone(localizacao.geocodificar_unidade(unidade("UBS")))
            get.assert_not_called()

    def test_api_configurada_mas_indisponivel_mostra_falha_e_fallback(self):
        unidades = [unidade("UBS A")]
        with (
            patch.object(localizacao, "api_configurada", return_value=True),
            patch.object(localizacao, "geocodificar_bairro", return_value=None),
        ):
            resultados, modo = motor.achar_unidades(["UBS"], "VILA A", unidades)

        self.assertEqual(modo, "api_falha")
        self.assertEqual(resultados[0][0]["NOME"], "UBS A")

    def test_bairro_geocodificado_usa_candidato_da_api(self):
        resposta = Resposta(
            {
                "candidates": [
                    {
                        "location": {"x": -46.63, "y": -23.59},
                    }
                ]
            }
        )
        with (
            patch.object(localizacao, "_chave_api", return_value="chave"),
            patch.object(localizacao.requests, "get", return_value=resposta) as get,
        ):
            resultado = localizacao.geocodificar_bairro("VILA A")

        self.assertEqual(resultado, (-46.63, -23.59))
        self.assertEqual(get.call_args.kwargs["params"]["address"], "VILA A")
        self.assertEqual(get.call_args.kwargs["params"]["city"], "São Paulo")

    def test_bairro_usa_o_primeiro_candidato_da_api(self):
        resposta = Resposta(
            {
                "candidates": [
                    {
                        "location": {"x": -46.66, "y": -23.67},
                    },
                ]
            }
        )
        with (
            patch.object(localizacao, "_chave_api", return_value="chave"),
            patch.object(localizacao.requests, "get", return_value=resposta),
        ):
            resultado = localizacao.geocodificar_bairro("Vila Do Castelo")

        self.assertEqual(resultado, (-46.66, -23.67))

    def test_geocode_usa_coordenadas_do_primeiro_candidato(self):
        resposta = Resposta(
            {
                "candidates": [
                    {
                        "location": {"x": -49.88, "y": -22.96},
                    }
                ]
            }
        )
        with (
            patch.object(localizacao, "_chave_api", return_value="chave"),
            patch.object(localizacao.requests, "get", return_value=resposta),
        ):
            self.assertEqual(
                localizacao.geocodificar_bairro("VILA A"),
                (-49.88, -22.96),
            )

    def test_endereco_de_unidade_e_cache_persistente(self):
        resposta = Resposta(
            {"candidates": [{"location": {"x": -46.63, "y": -23.59}}]}
        )
        unidade_teste = unidade("UBS TESTE")
        with (
            patch.object(localizacao, "_chave_api", return_value="chave"),
            patch.object(localizacao.requests, "get", return_value=resposta) as get,
        ):
            primeira = localizacao.geocodificar_unidade(unidade_teste)
            segunda = localizacao.geocodificar_unidade(unidade_teste)

        self.assertEqual(primeira, segunda)
        get.assert_called_once()
        cache = json.loads(localizacao.CACHE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(cache["1"]["status"], "ok")
        self.assertNotIn("NU_LATITUDE", cache["1"])

    def test_cache_de_unidade_fora_do_municipio_e_descartado(self):
        localizacao.CACHE_PATH.write_text(
            json.dumps(
                {
                    "1": {
                        "endereco_consultado": "Rua Exemplo, 10",
                        "longitude": -49.88,
                        "latitude": -22.96,
                        "status": "ok",
                    }
                }
            ),
            encoding="utf-8",
        )
        resposta = Resposta(
            {
                "candidates": [
                    {
                        "location": {"x": -46.63, "y": -23.59},
                    }
                ]
            }
        )
        with (
            patch.object(localizacao, "_chave_api", return_value="chave"),
            patch.object(localizacao.requests, "get", return_value=resposta) as get,
        ):
            resultado = localizacao.geocodificar_unidade(unidade("UBS"))

        self.assertEqual(resultado, (-46.63, -23.59))
        get.assert_called_once()

    def test_cache_nao_encontrado_nao_repete_consulta(self):
        unidade_teste = unidade("UBS SEM ENDEREÇO")
        with (
            patch.object(localizacao, "_chave_api", return_value="chave"),
            patch.object(localizacao.requests, "get", return_value=Resposta({"features": []})) as get,
        ):
            self.assertIsNone(localizacao.geocodificar_unidade(unidade_teste))
            self.assertIsNone(localizacao.geocodificar_unidade(unidade_teste))
        self.assertEqual(get.call_count, 1)

    def test_rotas_convertem_quilometros_e_minutos(self):
        respostas = [
            Resposta(
                {
                    "routes": {
                        "features": [
                            {
                                "attributes": {
                                    "Total_Kilometers": 2.4,
                                    "Total_TravelTime": 8,
                                }
                            }
                        ]
                    }
                }
            ),
            Resposta(
                {
                    "routes": {
                        "features": [
                            {
                                "attributes": {
                                    "Total_Kilometers": 1.3,
                                    "Total_TravelTime": 5,
                                }
                            }
                        ]
                    }
                }
            ),
        ]
        with (
            patch.object(localizacao, "_chave_api", return_value="chave"),
            patch.object(
                localizacao.requests,
                "get",
                side_effect=respostas,
            ) as get,
        ):
            rotas = localizacao.calcular_rotas(
                (-46.63, -23.59), [(-46.64, -23.60), (-46.65, -23.61)]
            )

        self.assertEqual(rotas, [(2400.0, 8.0), (1300.0, 5.0)])
        self.assertEqual(get.call_count, 2)
        self.assertIn(
            "-46.63,-23.59;-46.64,-23.6",
            get.call_args_list[0].kwargs["params"]["stops"],
        )

    def test_rota_invalida_faz_fallback(self):
        with (
            patch.object(localizacao, "_chave_api", return_value="chave"),
            patch.object(localizacao.requests, "get", return_value=Resposta({})),
        ):
            self.assertIsNone(
                localizacao.calcular_rotas((-46.63, -23.59), [(-46.64, -23.60)])
            )

    def test_falha_http_nao_chega_a_interface(self):
        with (
            patch.object(localizacao, "_chave_api", return_value="chave"),
            patch.object(
                localizacao.requests,
                "get",
                side_effect=localizacao.requests.Timeout,
            ),
        ):
            self.assertIsNone(localizacao.geocodificar_bairro("VILA A"))

    def test_selecao_limita_candidatas_e_prioriza_bairro(self):
        unidades = [
            unidade(f"UBS {indice}", "VILA A" if indice < 12 else "VILA B", str(indice))
            for indice in range(30)
        ]
        candidatas = motor.selecionar_candidatas(["UBS"], "VILA A", unidades)
        self.assertEqual(len(candidatas), localizacao.MAX_CANDIDATAS)
        self.assertEqual(sum(u["NO_BAIRRO"] == "VILA A" for u in candidatas), 10)

    def test_rotas_ordenam_e_completam_sem_rota(self):
        unidades = [unidade("UBS A"), unidade("UBS B", "VILA B", "2")]
        with (
            patch.object(localizacao, "geocodificar_bairro", return_value=(-46.63, -23.59)),
            patch.object(
                localizacao,
                "geocodificar_unidade",
                side_effect=[(-46.64, -23.60), (-46.65, -23.61)],
            ),
            patch.object(
                localizacao,
                "calcular_rotas",
                return_value=[(2400, 480), None],
            ),
        ):
            resultados, modo = motor.achar_unidades(["UBS"], "VILA A", unidades)

        self.assertEqual(modo, "rota")
        self.assertEqual(resultados[0][0]["NOME"], "UBS A")
        self.assertIsNone(resultados[1][1])

    def test_rotas_priorizam_bairro_antes_da_distancia(self):
        unidades = [
            unidade("UBS DO BAIRRO", "VILA A", "1"),
            unidade("UBS LONGE", "VILA B", "2"),
            unidade("UBS PERTO", "VILA C", "3"),
        ]
        with (
            patch.object(
                localizacao, "geocodificar_bairro", return_value=(-46.63, -23.59)
            ),
            patch.object(
                localizacao,
                "geocodificar_unidade",
                side_effect=[
                    (-46.70, -23.60),
                    (-46.64, -23.59),
                    (-46.65, -23.59),
                ],
            ),
            patch.object(
                localizacao,
                "calcular_rotas",
                return_value=[(10000, 600), (1000, 60), (2000, 120)],
            ),
        ):
            resultados, modo = motor.achar_unidades(["UBS"], "VILA A", unidades)

        self.assertEqual(modo, "rota")
        self.assertEqual(
            [item[0]["NOME"] for item in resultados],
            ["UBS DO BAIRRO", "UBS LONGE", "UBS PERTO"],
        )

    def test_fallback_sem_api_ordena_por_grupo_e_nao_exibe_distancia(self):
        unidades = [unidade("UBS Z"), unidade("UBS A", "VILA B", "2")]
        with patch.object(localizacao, "geocodificar_bairro", return_value=None):
            resposta, confianca = motor.responder(SITUACAO, [], "VILA A", unidades)
        self.assertIn("Unidades no seu bairro:", resposta)
        self.assertIn("UBS Z", resposta)
        self.assertNotIn("km", resposta)
        self.assertEqual(confianca, "alta")

    def test_classificacao_e_perguntas_continuam_iguais(self):
        situacao = {
            "palavras": ["dente"],
            "perguntas": [{"id": "p1", "texto": "urgência?"}],
            "regras": [],
        }
        encontrada, confianca = motor.sugerir_situacao("dor de dente", [situacao])
        self.assertEqual(encontrada, situacao)
        self.assertEqual(confianca, "média")


if __name__ == "__main__":
    unittest.main()
