import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import localizacao
import motor


def unidade_urgencia(nome, dias, horario, endereco="Rua Teste, 10"):
    return {
        "id_local": nome,
        "crs": "SUL",
        "sts": "Parelheiros",
        "nome": nome,
        "dias_atendimento": dias,
        "horario": horario,
        "endereco": endereco,
        "telefone": "1234-5678",
        "municipio": "São Paulo",
        "uf": "SP",
        "servico": "urgencia_odontologica",
        "fonte_arquivo": "fonte.pdf",
        "fonte_pagina": "1",
        "observacoes": "Confirmar com a unidade.",
    }


def situacao_urgencia():
    return {
        "id": "dentista",
        "perguntas": [{"id": "urgencia", "texto": "Urgência?"}],
        "regras": [
            {
                "quando": {"urgencia": True},
                "orientacao": "Procure atendimento odontológico de urgência.",
                "tipos": ["UPA", "PRONTO-SOCORRO"],
                "levar": [],
                "fonte": {
                    "titulo": "Fonte",
                    "url": "https://example.test",
                    "verificado_em": "2026-11-11",
                },
            }
        ],
    }


class UrgenciaOdontologicaTests(unittest.TestCase):
    def setUp(self):
        self.csv_original = motor.URGENCIA_ODONTOLOGICA_PATH
        self.cache_original = localizacao.CACHE_PATH
        self.temp = tempfile.TemporaryDirectory()
        localizacao.CACHE_PATH = Path(self.temp.name) / "cache.json"
        localizacao._CACHE_UNIDADES = None

    def tearDown(self):
        motor.URGENCIA_ODONTOLOGICA_PATH = self.csv_original
        localizacao.CACHE_PATH = self.cache_original
        localizacao._CACHE_UNIDADES = None
        self.temp.cleanup()

    def test_carrega_30_linhas_com_acento_e_telefone(self):
        unidades = motor.carregar_urgencias_odontologicas()
        self.assertEqual(len(unidades), 30)
        self.assertEqual(unidades[0]["NOME"], "UPA Dr. Atualpa Girão Rabelo")
        self.assertEqual(unidades[0]["NU_TELEFONE"], "2562-0270")

    def test_adaptador_preserva_parelheiros_e_dois_periodos(self):
        unidades = motor.carregar_urgencias_odontologicas()
        parelheiros = next(u for u in unidades if "Parelheiros" in u["NOME"])
        self.assertIn("Sábado e domingo", parelheiros["dias_atendimento"])
        self.assertIn("19h às 07h", parelheiros["horario"])

    def test_tipos_da_tabela_nao_filtram_pa_ama_ou_hospital(self):
        unidades = [
            unidade_urgencia("PA Teste", "Segunda", "07h às 19h"),
            unidade_urgencia("AMA Teste", "Terça", "07h às 19h"),
            unidade_urgencia("Hospital Teste", "Quarta", "07h às 19h"),
        ]
        with patch.object(motor, "carregar_urgencias_odontologicas", return_value=[
            motor._adaptar_urgencia_odontologica(u) for u in unidades
        ]):
            with (
                patch.object(localizacao, "api_configurada", return_value=True),
                patch.object(localizacao, "geocodificar_bairro", return_value=(-46.6, -23.6)),
                patch.object(
                    localizacao,
                    "geocodificar_unidade",
                    side_effect=[(-46.61, -23.61), (-46.62, -23.62), (-46.63, -23.63)],
                ),
                patch.object(
                    localizacao,
                    "calcular_rotas",
                    return_value=[(1000, 60), (2000, 120), (3000, 180)],
                ),
            ):
                resultados, modo = motor.achar_urgencias_odontologicas("Parelheiros")
        self.assertEqual(modo, "rota")
        self.assertEqual(len(resultados), 3)

    def test_urgencia_usa_tabela_e_nao_unidades_cnes(self):
        tabela = [motor._adaptar_urgencia_odontologica(
            unidade_urgencia("PA Confirmado", "Todos os dias", "24 horas")
        )]
        with (
            patch.object(motor, "carregar_urgencias_odontologicas", return_value=tabela),
            patch.object(localizacao, "api_configurada", return_value=True),
            patch.object(localizacao, "geocodificar_bairro", return_value=(-46.6, -23.6)),
            patch.object(localizacao, "geocodificar_unidade", return_value=(-46.61, -23.61)),
            patch.object(localizacao, "calcular_rotas", return_value=[(2400, 480)]),
        ):
            resposta, _ = motor.responder(
                situacao_urgencia(), ["urgencia"], "Parelheiros",
                [{"TIPO": "UPA", "NOME": "UPA CNES genérica"}],
            )
        self.assertIn("PA Confirmado", resposta)
        self.assertNotIn("UPA CNES genérica", resposta)
        self.assertIn("Todos os dias", resposta)
        self.assertIn("2,4 km", resposta)

    def test_falha_total_da_api_nao_retorna_unidades(self):
        tabela = [motor._adaptar_urgencia_odontologica(
            unidade_urgencia("UPA Confirmada", "Todos os dias", "24 horas")
        )]
        with (
            patch.object(motor, "carregar_urgencias_odontologicas", return_value=tabela),
            patch.object(localizacao, "api_configurada", return_value=True),
            patch.object(localizacao, "geocodificar_bairro", return_value=None),
        ):
            resposta, _ = motor.responder(
                situacao_urgencia(), ["urgencia"], "Parelheiros", []
            )
        self.assertIn("Não foi possível buscar unidades próximas", resposta)
        self.assertNotIn("UPA Confirmada", resposta)

    def test_falha_parcial_mostra_apenas_rotas_validas(self):
        tabela = [
            motor._adaptar_urgencia_odontologica(
                unidade_urgencia("Válida", "Todos os dias", "24 horas")
            ),
            motor._adaptar_urgencia_odontologica(
                unidade_urgencia("Sem rota", "Todos os dias", "24 horas")
            ),
        ]
        with (
            patch.object(motor, "carregar_urgencias_odontologicas", return_value=tabela),
            patch.object(localizacao, "api_configurada", return_value=True),
            patch.object(localizacao, "geocodificar_bairro", return_value=(-46.6, -23.6)),
            patch.object(
                localizacao,
                "geocodificar_unidade",
                side_effect=[(-46.61, -23.61), (-46.62, -23.62)],
            ),
            patch.object(localizacao, "calcular_rotas", return_value=[(2400, 480), None]),
        ):
            resposta, _ = motor.responder(
                situacao_urgencia(), ["urgencia"], "Parelheiros", []
            )
        self.assertIn("Válida", resposta)
        self.assertNotIn("Sem rota", resposta)

    def test_csv_ausente_nao_faz_fallback_cnes(self):
        caminho = Path(self.temp.name) / "ausente.csv"
        motor.URGENCIA_ODONTOLOGICA_PATH = caminho
        with patch.object(localizacao, "api_configurada", return_value=True):
            resposta, _ = motor.responder(
                situacao_urgencia(), ["urgencia"], "Parelheiros",
                [{"TIPO": "UPA", "NOME": "UPA genérica"}],
            )
        self.assertIn("lista local", resposta)
        self.assertNotIn("UPA genérica", resposta)

    def test_ordena_por_distancia_numerica_e_limita_a_cinco(self):
        tabela = [
            motor._adaptar_urgencia_odontologica(
                unidade_urgencia(f"Unidade {i}", "Todos os dias", "24 horas")
            )
            for i in range(7)
        ]
        with (
            patch.object(motor, "carregar_urgencias_odontologicas", return_value=tabela),
            patch.object(localizacao, "api_configurada", return_value=True),
            patch.object(localizacao, "geocodificar_bairro", return_value=(-46.6, -23.6)),
            patch.object(
                localizacao, "geocodificar_unidade",
                side_effect=[(-46.61, -23.61)] * 7,
            ),
            patch.object(
                localizacao, "calcular_rotas",
                return_value=[(10000, 1), (2400, 1), (900, 1), (12000, 1),
                              (3000, 1), (8000, 1), (1000, 1)],
            ),
        ):
            resultados, _ = motor.achar_urgencias_odontologicas("Parelheiros")
        self.assertEqual(len(resultados), 5)
        self.assertEqual([r[1] for r in resultados], [900, 1000, 2400, 3000, 8000])


if __name__ == "__main__":
    unittest.main()
