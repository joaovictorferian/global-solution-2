"""Limpa o CSV bruto do CNES e gera data/unidades.csv.

Uso: coloque o arquivo como cnes_bruto.csv nesta pasta e rode: python tratar_cnes.py
"""
import pandas as pd

ENTRADA = "cnes_bruto.csv"
SAIDA = "data/unidades.csv"
MUNICIPIO = "355030"  # código IBGE do município, exatamente como aparece na coluna CO_IBGE

MANTER = [
    "CO_CNES", "NO_FANTASIA", "NO_RAZAO_SOCIAL", "CO_IBGE", "TP_UNIDADE",
    "DS_ESFERA_ADMINISTRATIVA", "NO_LOGRADOURO", "NU_ENDERECO", "NO_BAIRRO",
    "CO_CEP", "NU_TELEFONE", "NU_LATITUDE", "NU_LONGITUDE",
    "DS_TURNO_ATENDIMENTO",
    "CO_AMBULATORIAL_SUS", "CO_MOTIVO_DESAB",
]

# CONFIRME estes códigos na tabela oficial de tipos de unidade do CNES.
# Os rótulos da direita são os que o regras.json usa em "tipos".
TIPOS = {
    "1": "POSTO",
    "2": "UBS",
    "5": "HOSPITAL",
    "15": "UNIDADE MISTA",
    "20": "PRONTO-SOCORRO",
    "36": "ESPECIALIDADES",
    "70": "CAPS",
    "73": "UPA",
    "85": "IMUNIZACAO",
}

# A fonte CNES pode misturar bytes legados em registros posteriores ao
# cabeçalho; latin-1 permite ler o arquivo inteiro sem carregar seus dados.
codificacao = "latin-1"

leitor = pd.read_csv(
    ENTRADA,
    sep=None,
    engine="python",
    dtype=str,
    encoding=codificacao,
    usecols=MANTER,
    chunksize=100000,
)

partes = []
linhas_lidas = 0
for parte in leitor:
    linhas_lidas += len(parte)
    parte = parte[parte["CO_IBGE"] == MUNICIPIO]
    if not parte.empty:
        partes.append(parte)
df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=MANTER)
df = df.fillna("")
print("Linhas na entrada:", linhas_lidas)

if not MUNICIPIO:
    print("\nDefina MUNICIPIO no topo do script. Códigos mais frequentes:")
    print(df["CO_IBGE"].value_counts().head(10))
    raise SystemExit
print(f"Linhas do município {MUNICIPIO}:", len(df))

# Confira estes valores antes de confiar nos filtros abaixo
for col in ["TP_UNIDADE", "CO_AMBULATORIAL_SUS", "CO_MOTIVO_DESAB", "DS_ESFERA_ADMINISTRATIVA"]:
    print(f"\n{col}:\n{df[col].value_counts().head(15)}")

df = df[df["TP_UNIDADE"].isin(TIPOS)]
df = df[~df["DS_ESFERA_ADMINISTRATIVA"].str.upper().str.contains("PRIVAD")]
df = df[df["CO_MOTIVO_DESAB"].isin(["", "0", "00"])]

df["TIPO"] = df["TP_UNIDADE"].map(TIPOS)
df["NOME"] = df["NO_FANTASIA"].where(df["NO_FANTASIA"] != "", df["NO_RAZAO_SOCIAL"])
df["NO_BAIRRO"] = df["NO_BAIRRO"].str.strip().str.upper()

df.to_csv(SAIDA, index=False, encoding="utf-8")
print("\nLinhas na saída:", len(df))
print(df["TIPO"].value_counts())
