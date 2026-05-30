"""
Sincroniza as tabelas GOLD do DuckDB para o PostgreSQL.
Chamado pela DAG após o dbt run.
"""

import duckdb
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path

DB_PATH = Path("/opt/airflow/data/nfe_pipeline.duckdb")

PG_CONFIG = {
    "host":     "postgres-analytics",
    "port":     5432,
    "dbname":   "nfe_analytics",
    "user":     "analytics",
    "password": "analytics",
}

# Tabelas GOLD para sincronizar
TABELAS_GOLD = [
    "gold_impostos_por_fornecedor",
    "gold_alertas_inconsistencia",
    "gold_evolucao_mensal",
    "gold_analise_cfop",
]


def sincronizar(db_path: Path = DB_PATH) -> dict:
    duck = duckdb.connect(str(db_path))
    pg   = psycopg2.connect(**PG_CONFIG)
    cur  = pg.cursor()

    resumo = {}

    for tabela in TABELAS_GOLD:
        print(f"\n🔄 Sincronizando {tabela}...")

        # Lê do DuckDB como DataFrame
        df = duck.execute(f"SELECT * FROM main.{tabela}").df()

        if df.empty:
            print(f"   ⚠️  Tabela vazia — pulando")
            resumo[tabela] = 0
            continue

        # Recria a tabela no PostgreSQL (truncate + insert)
        # Inferência de tipos simples: tudo como TEXT ou NUMERIC
        colunas = df.columns.tolist()

        col_defs = []
        for col in colunas:
            dtype = str(df[col].dtype)
            if "int" in dtype:
                col_defs.append(f'"{col}" BIGINT')
            elif "float" in dtype:
                col_defs.append(f'"{col}" NUMERIC')
            elif "bool" in dtype:
                col_defs.append(f'"{col}" BOOLEAN')
            elif "datetime" in dtype or "timestamp" in dtype:
                col_defs.append(f'"{col}" TIMESTAMP')
            else:
                col_defs.append(f'"{col}" TEXT')

        # Recria a tabela
        cur.execute(f'DROP TABLE IF EXISTS "{tabela}"')
        cur.execute(f'CREATE TABLE "{tabela}" ({", ".join(col_defs)})')

        # Insere os dados
        cols_str = ", ".join(f'"{c}"' for c in colunas)
        rows = [tuple(row) for row in df.itertuples(index=False, name=None)]

        execute_values(
            cur,
            f'INSERT INTO "{tabela}" ({cols_str}) VALUES %s',
            rows,
            page_size=500
        )

        pg.commit()
        print(f"   ✅ {len(rows)} linhas inseridas")
        resumo[tabela] = len(rows)

    cur.close()
    pg.close()
    duck.close()

    return resumo