"""
Loader — Camada BRONZE
Recebe os dados parseados e persiste no DuckDB.
Cria as tabelas se não existirem (idempotente).
"""

import duckdb
from pathlib import Path
from typing import Optional
from datetime import datetime

# Caminho padrão do banco
DB_PATH = Path(__file__).parent.parent / "data" / "nfe_pipeline.duckdb"


def get_connection(db_path: str | Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    """Retorna uma conexão com o DuckDB, criando o arquivo se necessário."""
    return duckdb.connect(str(db_path))


def criar_schema_bronze(conn: duckdb.DuckDBPyConnection) -> None:
    """
    Cria as tabelas da camada BRONZE se não existirem.
    Idempotente: pode ser chamado várias vezes sem problema.
    """
    conn.execute("CREATE SCHEMA IF NOT EXISTS bronze")

    # Tabela de cabeçalhos das notas
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bronze.nfe_cabecalho (
            chave_acesso        VARCHAR PRIMARY KEY,
            numero_nf           VARCHAR,
            serie               VARCHAR,
            data_emissao        VARCHAR,
            natureza_operacao   VARCHAR,
            tipo_nf             VARCHAR,
            ambiente            VARCHAR,
            emit_cnpj           VARCHAR,
            emit_nome           VARCHAR,
            emit_ie             VARCHAR,
            dest_cnpj           VARCHAR,
            dest_nome           VARCHAR,
            dest_ie             VARCHAR,
            arquivo_origem      VARCHAR,
            carregado_em        TIMESTAMP DEFAULT current_timestamp
        )
    """)

    # Tabela de itens (um registro por produto por nota)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bronze.nfe_itens (
            id                      INTEGER PRIMARY KEY,
            chave_acesso            VARCHAR,
            num_item                INTEGER,
            codigo_produto          VARCHAR,
            descricao_produto       VARCHAR,
            ncm                     VARCHAR,
            cfop                    VARCHAR,
            unidade                 VARCHAR,
            quantidade              DOUBLE,
            valor_unitario          DOUBLE,
            valor_produto           DOUBLE,
            icms_bc                 DOUBLE,
            icms_aliquota           DOUBLE,
            icms_valor_declarado    DOUBLE,
            pis_aliquota            DOUBLE,
            pis_valor_declarado     DOUBLE,
            cofins_aliquota         DOUBLE,
            cofins_valor_declarado  DOUBLE,
            carregado_em            TIMESTAMP DEFAULT current_timestamp
        )
    """)

    # Tabela de totais por nota
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bronze.nfe_totais (
            chave_acesso    VARCHAR PRIMARY KEY,
            vbc_total       DOUBLE,
            icms_total      DOUBLE,
            pis_total       DOUBLE,
            cofins_total    DOUBLE,
            vprod_total     DOUBLE,
            vnf_total       DOUBLE,
            carregado_em    TIMESTAMP DEFAULT current_timestamp
        )
    """)

    # Tabela de controle de arquivos processados
    # Evita reprocessar o mesmo XML duas vezes
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bronze.arquivos_processados (
            arquivo         VARCHAR PRIMARY KEY,
            status          VARCHAR,   -- 'sucesso' ou 'erro'
            detalhes        VARCHAR,
            processado_em   TIMESTAMP DEFAULT current_timestamp
        )
    """)


def ja_foi_processado(conn: duckdb.DuckDBPyConnection, arquivo: str) -> bool:
    """Verifica se um arquivo já foi processado com sucesso anteriormente."""
    resultado = conn.execute("""
        SELECT COUNT(*) FROM bronze.arquivos_processados
        WHERE arquivo = ? AND status = 'sucesso'
    """, [arquivo]).fetchone()
    return resultado[0] > 0


def carregar_nfe(conn: duckdb.DuckDBPyConnection, dado_parseado: dict) -> None:
    """
    Carrega uma NF-e parseada no DuckDB.
    Usa INSERT OR REPLACE para ser idempotente.
    """
    cab = dado_parseado["cabecalho"]
    totais = dado_parseado["totais"]
    itens = dado_parseado["itens"]

    # Cabeçalho
    conn.execute("""
        INSERT OR REPLACE INTO bronze.nfe_cabecalho VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp
        )
    """, [
        cab["chave_acesso"], cab["numero_nf"], cab["serie"],
        cab["data_emissao"], cab["natureza_operacao"], cab["tipo_nf"],
        cab["ambiente"], cab["emit_cnpj"], cab["emit_nome"], cab["emit_ie"],
        cab["dest_cnpj"], cab["dest_nome"], cab["dest_ie"], cab["arquivo_origem"]
    ])

    # Totais
    conn.execute("""
        INSERT OR REPLACE INTO bronze.nfe_totais VALUES (
            ?, ?, ?, ?, ?, ?, ?, current_timestamp
        )
    """, [
        totais["chave_acesso"], totais["vbc_total"], totais["icms_total"],
        totais["pis_total"], totais["cofins_total"],
        totais["vprod_total"], totais["vnf_total"]
    ])

    # Itens — deleta os anteriores da mesma chave antes de inserir
    # (garante idempotência sem precisar de PK composta complexa)
    conn.execute(
        "DELETE FROM bronze.nfe_itens WHERE chave_acesso = ?",
        [cab["chave_acesso"]]
    )

    for item in itens:
        # Gera ID único combinando chave + num_item
        id_item = hash(f"{item['chave_acesso']}_{item['num_item']}") % (10**9)

        conn.execute("""
            INSERT INTO bronze.nfe_itens VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, current_timestamp
            )
        """, [
            id_item, item["chave_acesso"], item["num_item"],
            item["codigo_produto"], item["descricao_produto"],
            item["ncm"], item["cfop"], item["unidade"],
            item["quantidade"], item["valor_unitario"], item["valor_produto"],
            item["icms_bc"], item["icms_aliquota"], item["icms_valor_declarado"],
            item["pis_aliquota"], item["pis_valor_declarado"],
            item["cofins_aliquota"], item["cofins_valor_declarado"]
        ])


def registrar_processamento(
    conn: duckdb.DuckDBPyConnection,
    arquivo: str,
    status: str,
    detalhes: Optional[str] = None
) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO bronze.arquivos_processados VALUES (
            ?, ?, ?, current_timestamp
        )
    """, [arquivo, status, detalhes])


def carregar_diretorio(diretorio: str | Path, db_path: str | Path = DB_PATH) -> dict:
    """
    Pipeline completo: lê todos os XMLs de uma pasta e carrega no DuckDB.
    Retorna um resumo do processamento.
    """
    from ingestion.xml_parser import parse_diretorio, parse_nfe
    from pathlib import Path

    diretorio = Path(diretorio)
    conn = get_connection(db_path)
    criar_schema_bronze(conn)

    resumo = {"sucesso": 0, "ignorado": 0, "erro": 0}
    arquivos = sorted(diretorio.glob("*.xml"))

    for arquivo in arquivos:
        nome = arquivo.name

        # Pula arquivos já processados
        if ja_foi_processado(conn, nome):
            print(f"  ⏭️  Ignorado (já processado): {nome}")
            resumo["ignorado"] += 1
            continue

        try:
            dado = parse_nfe(arquivo)
            if dado is None:
                raise ValueError("Parser retornou None — XML inválido")

            carregar_nfe(conn, dado)
            registrar_processamento(conn, nome, "sucesso")
            print(f"  ✅ Carregado: {nome}")
            resumo["sucesso"] += 1

        except Exception as e:
            registrar_processamento(conn, nome, "erro", str(e))
            print(f"  ❌ Erro em {nome}: {e}")
            resumo["erro"] += 1

    conn.close()
    return resumo