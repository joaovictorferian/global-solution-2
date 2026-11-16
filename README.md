# Orientação SUS

Aplicação web informativa para ajudar moradores de São Paulo a encontrar
orientações e unidades de atendimento do SUS a partir do bairro e da
necessidade informada.

> **Aviso:** o sistema é informativo, não substitui avaliação profissional e
> não é um canal oficial de atendimento. Em caso de emergência, ligue 192
> (SAMU). Para outras dúvidas de saúde, ligue 136 (Disque Saúde).

## Integrantes - 1CCPO

| Nome | RM |
| --- | --- |
| Gustavo Melo dos Santos | 573562 |
| João Victor Canello Ferian | 573295 |
| João Pedro Costenari Silva | 572260 |

## Funcionalidades

- Seleção do bairro por lista de bairros presentes na base local.
- Escolha da necessidade, com sugestão a partir de texto livre.
- Orientações configuradas em `data/regras.json`.
- Indicação de unidades compatíveis, priorizando o bairro informado.
- Busca opcional de geocodificação e rotas para ordenar unidades por
  proximidade.
- Fluxos específicos para:
  - UBS e outros serviços do SUS;
  - medicamentos e farmácia do SUS;
  - vacinação;
  - saúde mental e modalidades de CAPS;
  - urgência odontológica.
- Registro anônimo de situação e confiança em `logs/indicadores.csv`.

## Requisitos

- Python 3.10 ou superior.
- Dependências listadas em `requirements.txt`.
- Token do ArcGIS opcional para calcular coordenadas e rotas.

## Instalação

No PowerShell, a partir da pasta do projeto:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 -m pip install -r requirements.txt
```

Se a política de execução do PowerShell impedir a ativação do ambiente,
execute os comandos diretamente pelo interpretador do ambiente virtual:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Configuração opcional de localização

Crie um arquivo `.env` na raiz do projeto:

```dotenv
ARCGIS_TOKEN=seu_token_do_arcgis
```

Sem esse token, a aplicação continua funcionando usando o fallback por bairro,
mas não calcula distâncias e tempos de rota.
Para gerar o token, siga as orientações presentes em: https://developers.arcgis.com/documentation/security-and-authentication/api-key-authentication/tutorials/create-an-api-key/location-platform/

## Executando a aplicação

```powershell
py -3 src\app.py
```

Depois, abra <http://127.0.0.1:5000> no navegador.

O servidor disponibiliza:

- `GET /` — interface web;
- `GET /api/opcoes` — aviso, bairros e situações disponíveis;
- `POST /api/sugerir` — sugere uma situação a partir de texto livre;
- `POST /api/orientar` — gera a orientação para o bairro e a situação
  selecionados.

Exemplo de requisição para orientação:

```json
{
  "bairro": "VILA MARIANA",
  "situacao": "medicamentos",
  "marcadas": [],
  "modalidade": null
}
```

## Executando os testes

```powershell
py -3 -m unittest discover -s tests -v
```

Os testes cobrem regras de orientação, seleção de unidades, geocodificação,
cache, serviços CAPS e urgência odontológica.

## Preparando a base CNES

O script `tratar_cnes.py` transforma um arquivo bruto do CNES em
`data/unidades.csv`, filtrando os registros do município de São Paulo e
unidades públicas.

1. Coloque o arquivo bruto com o nome `cnes_bruto.csv` na raiz.
2. Instale o pandas, caso necessário:

   ```powershell
   py -3 -m pip install pandas
   ```

3. Execute:

   ```powershell
   py -3 tratar_cnes.py
   ```

Antes de usar os dados em produção, confira no script os códigos de tipos de
unidade definidos em `TIPOS`.

## Estrutura do projeto

```text
.
├── data/
│   ├── regras.json                    # Regras e fontes das orientações
│   ├── unidades.csv                   # Unidades usadas na busca
│   ├── caps_servicos.csv              # Base de serviços CAPS
│   ├── urgencia_odontologica.csv      # Serviços odontológicos de urgência
│   ├── geocodificacao_unidades.json   # Cache de geocodificação
│   └── relacionamentos_bairros.json   # Cache de rotas
├── logs/
│   └── indicadores.csv                # Registro anônimo de uso
├── src/
│   ├── app.py                         # Rotas Flask e validação de entrada
│   ├── motor.py                       # Regras e montagem das respostas
│   ├── localizacao.py                 # Geocodificação, rotas e cache
│   └── static/                        # HTML, CSS e JavaScript da interface
├── tests/                             # Testes automatizados
├── requirements.txt
└── tratar_cnes.py
```

## Fontes e atualização dos dados

As fontes, URLs e datas de verificação das orientações ficam em
`data/regras.json`. As tabelas de CAPS e urgência odontológica possuem seus
próprios campos de fonte e data de verificação. Confirme as informações com a
unidade antes de utilizá-las.
