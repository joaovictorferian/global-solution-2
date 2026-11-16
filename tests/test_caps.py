import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import localizacao
import motor


def caps_row(nome, modalidade, cep="01000-000", observacoes=""):
    return {
        "id_local": nome,
        "regiao": "CENTRO",
        "nome": nome,
        "modalidade": modalidade,
        "nivel": "III",
        "endereco": "Rua Teste, 10",
        "cep": cep,
        "territorio_informado": "Centro",
        "telefone": "(11) 0000-0000",
        "municipio": "São Paulo",
        "uf": "SP",
        "fonte_url": "https://example.test/caps",
        "verificado_em": "2026-11-11",
        "observacoes": observacoes,
    }


def situacao_caps():
    return {
        "id": "saude_mental",
        "perguntas": [],
        "regras": [
            {
                "quando": {},
                "orientacao": "Orientação geral.",
                "tipos": ["UBS", "CAPS"],
                "levar": [],
                "fonte": {
                    "titulo": "Fonte geral",
                    "url": "https://example.test",
                    "verificado_em": "2026-11-11",
                },
            }
        ],
    }


class CapsTests(unittest.TestCase):
    def setUp(self):
        self.path_original = motor.CAPS_PATH
        self.cache_original = localizacao.CACHE_PATH
        self.temp = tempfile.TemporaryDirectory()
        localizacao.CACHE_PATH = Path(self.temp.name) / "cache.json"
        localizacao._CACHE_UNIDADES = None

    def tearDown(self):
        motor.CAPS_PATH = self.path_original
        localizacao.CACHE_PATH = self.cache_original
        localizacao._CACHE_UNIDADES = None
        self.temp.cleanup()

    def test_base_real_tem_modalidades_e_sem_duplicatas(self):
        unidades = motor.carregar_caps()
        self.assertEqual(len(unidades), 104)
        self.assertEqual({u["modalidade"] for u in unidades}, {"AD", "ADULTO", "IJ"})
        self.assertEqual(len({u["id_local"] for u in unidades}), 104)

    def test_modalidade_tem_igualdade_exata(self):
        rows = [caps_row("AD", "AD"), caps_row("ADULTO", "ADULTO")]
        with patch.object(motor, "carregar_caps", return_value=[
            motor._adaptar_caps(row) for row in rows
        ]):
            with (
                patch.object(localizacao, "api_configurada", return_value=True),
                patch.object(localizacao, "geocodificar_bairro", return_value=None),
            ):
                _, modo = motor.achar_caps("AD", "Centro")
        self.assertEqual(modo, "api_indisponivel")

    def test_endereco_caps_inclui_cep_e_namespace(self):
        unidade = motor._adaptar_caps(caps_row("CAPS Teste", "AD"))
        self.assertIn("01000-000", localizacao.montar_endereco_unidade(unidade))
        self.assertTrue(localizacao._chave_unidade(unidade).startswith("caps:"))

    def test_cep_com_alerta_nao_e_usado_na_consulta(self):
        unidade = motor._adaptar_caps(
            caps_row("CAPS Teste", "AD", observacoes="CEP a conferir")
        )
        self.assertNotIn("01000-000", localizacao.montar_endereco_unidade(unidade))
        self.assertIn("Rua Teste, 10", unidade["endereco_sem_cep"])

    def test_cache_caps_reutiliza_endereco(self):
        unidade = motor._adaptar_caps(caps_row("CAPS Teste", "AD"))
        with (
            patch.object(localizacao, "api_configurada", return_value=True),
            patch.object(
                localizacao,
                "_consultar_endereco",
                return_value=((-46.6, -23.6), "ok"),
            ) as consultar,
        ):
            primeira = localizacao.geocodificar_unidade(unidade)
            segunda = localizacao.geocodificar_unidade(unidade)
        self.assertEqual(primeira, segunda)
        consultar.assert_called_once()

    def test_falha_temporaria_nao_grava_nao_encontrado(self):
        unidade = motor._adaptar_caps(caps_row("CAPS Teste", "AD"))
        with (
            patch.object(localizacao, "api_configurada", return_value=True),
            patch.object(
                localizacao,
                "_consultar_endereco",
                return_value=(None, "temporary"),
            ),
        ):
            self.assertIsNone(localizacao.geocodificar_unidade(unidade))
        self.assertFalse(localizacao.CACHE_PATH.exists())

    def test_caps_ordena_limita_e_ignora_unidades_sem_rota(self):
        rows = [motor._adaptar_caps(caps_row(f"CAPS {i}", "AD")) for i in range(7)]
        with (
            patch.object(motor, "carregar_caps", return_value=rows),
            patch.object(localizacao, "api_configurada", return_value=True),
            patch.object(localizacao, "geocodificar_bairro", return_value=(-46.6, -23.6)),
            patch.object(
                localizacao,
                "geocodificar_unidade",
                side_effect=[(-46.6, -23.6)] * 7,
            ),
            patch.object(
                localizacao,
                "calcular_rotas",
                return_value=[(9000, 1), (1000, 1), None, (3000, 1), (2000, 1), (7000, 1), (4000, 1)],
            ),
        ):
            resultados, modo = motor.achar_caps("AD", "Centro")
        self.assertEqual(modo, "rota")
        self.assertEqual(len(resultados), 5)
        self.assertEqual([item[1] for item in resultados], [1000, 2000, 3000, 4000, 7000])

    def test_caps_falha_total_nao_entrega_unidades(self):
        with (
            patch.object(motor, "carregar_caps", return_value=[
                motor._adaptar_caps(caps_row("CAPS AD", "AD"))
            ]),
            patch.object(localizacao, "api_configurada", return_value=True),
            patch.object(localizacao, "geocodificar_bairro", return_value=None),
        ):
            resposta, _ = motor.responder(
                situacao_caps(), [], "Centro", [], modalidade_caps="AD"
            )
        self.assertIn("Não foi possível buscar unidades próximas", resposta)
        self.assertNotIn("CAPS AD", resposta)

    def test_nao_sei_usa_ubs_e_nao_afirma_caps_de_referencia(self):
        with (
            patch.object(
                motor,
                "achar_unidades",
                return_value=([], "api_falha"),
            ),
        ):
            resposta, _ = motor.responder(
                situacao_caps(), [], "Centro", [], modalidade_caps="NAO_SEI"
            )
        self.assertIn("acolhimento e orientação", resposta)
        self.assertNotIn("referência", resposta.casefold())

    def test_regra_odontologica_sem_urgencia_tem_novo_texto(self):
        regras = motor.carregar_regras()
        dentista = next(s for s in regras if s["id"] == "dentista")
        regra = next(r for r in dentista["regras"] if not r["quando"])
        self.assertIn("UBS indicada", regra["orientacao"])
        self.assertIn("encaminhamento para atendimento especializado", regra["orientacao"])


if __name__ == "__main__":
    unittest.main()
