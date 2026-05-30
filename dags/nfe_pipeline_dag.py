"""
DAG principal do pipeline NF-e

Fluxo:
  1. Sensor detecta novos XMLs em data/raw/
  2. Ingestão: parse + carga na camada BRONZE
  3. dbt run: transforma BRONZE → SILVER → GOLD
  4. dbt test: valida a qualidade dos dados
  5. Relatório: imprime resumo no log

Agendamento: a cada 30 minutos
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.operators.bash import BashOperator
from airflow.sensors.filesystem import FileSensor

# ── Configurações ──────────────────────────────────────────────────────────────

BASE_DIR  = Path("/opt/airflow")
DATA_DIR  = BASE_DIR / "data"
RAW_DIR   = DATA_DIR / "raw"
DB_PATH   = DATA_DIR / "nfe_pipeline.duckdb"
DBT_DIR   = BASE_DIR / "dbt" / "nfe_pipeline"

DEFAULT_ARGS = {
    "owner":            "luan",
    "retries":          2,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
}

# ── Funções das tasks ──────────────────────────────────────────────────────────
# Adiciona junto com as outras funções

def executar_sync_postgres(**context) -> None:
    import sys
    sys.path.insert(0, str(BASE_DIR))

    from ingestion.sync_to_postgres import sincronizar

    print("🔄 Sincronizando GOLD → PostgreSQL...")
    resumo = sincronizar(DB_PATH)

    print("\n📊 Resumo da sincronização:")
    for tabela, qtd in resumo.items():
        print(f"   • {tabela}: {qtd} linhas")

def verificar_xmls_pendentes(**context) -> bool:
    """
    ShortCircuit: retorna False se não houver XMLs novos.
    Evita rodar o pipeline desnecessariamente.
    """
    import duckdb

    xmls_disponiveis = list(RAW_DIR.glob("*.xml"))
    if not xmls_disponiveis:
        print("ℹ️  Nenhum XML encontrado em data/raw/ — pipeline encerrado")
        return False

    conn = duckdb.connect(str(DB_PATH))

    # Verifica se há XMLs ainda não processados
    processados = conn.execute(
        "SELECT arquivo FROM bronze.arquivos_processados WHERE status = 'sucesso'"
    ).fetchall()
    conn.close()

    nomes_processados = {row[0] for row in processados}
    pendentes = [x for x in xmls_disponiveis if x.name not in nomes_processados]

    if not pendentes:
        print(f"ℹ️  Todos os {len(xmls_disponiveis)} XMLs já foram processados")
        return False

    print(f"✅ {len(pendentes)} XMLs pendentes para processar")

    # Passa a lista para a próxima task via XCom
    context["ti"].xcom_push(key="xmls_pendentes", value=[str(x) for x in pendentes])
    return True


def executar_ingestao_bronze(**context) -> dict:
    """
    Task de ingestão: processa XMLs pendentes e carrega no DuckDB.
    """
    import sys
    sys.path.insert(0, str(BASE_DIR))

    from ingestion.loader import carregar_diretorio

    print("🚀 Iniciando ingestão BRONZE...")
    resumo = carregar_diretorio(RAW_DIR, DB_PATH)

    print(f"\n📊 Resumo da ingestão:")
    print(f"   ✅ Sucesso:  {resumo['sucesso']}")
    print(f"   ⏭️  Ignorado: {resumo['ignorado']}")
    print(f"   ❌ Erro:     {resumo['erro']}")

    if resumo["erro"] > 0:
        raise ValueError(f"Ingestão concluída com {resumo['erro']} erro(s)")

    # Passa resumo para tasks seguintes via XCom
    context["ti"].xcom_push(key="resumo_bronze", value=resumo)
    return resumo


def gerar_relatorio_final(**context) -> None:
    """
    Task final: consulta as tabelas GOLD e imprime resumo no log do Airflow.
    """
    import duckdb

    ti = context["ti"]
    resumo_bronze = ti.xcom_pull(task_ids="ingestao_bronze", key="resumo_bronze")

    conn = duckdb.connect(str(DB_PATH))

    print("\n" + "="*60)
    print("📋 RELATÓRIO DO PIPELINE NF-e")
    print("="*60)

    if resumo_bronze:
        print(f"\n📥 Ingestão:")
        print(f"   Notas processadas: {resumo_bronze.get('sucesso', 0)}")
        print(f"   Erros:             {resumo_bronze.get('erro', 0)}")

    # Resumo de inconsistências
    alertas = conn.execute("""
        SELECT
            severidade,
            COUNT(*) as qtd
        FROM main.gold_alertas_inconsistencia
        GROUP BY severidade
        ORDER BY CASE severidade
            WHEN 'ALTA'  THEN 1
            WHEN 'MÉDIA' THEN 2
            ELSE 3
        END
    """).fetchall()

    print(f"\n🚨 Alertas de inconsistência:")
    if alertas:
        for severidade, qtd in alertas:
            emoji = "🔴" if severidade == "ALTA" else "🟡" if severidade == "MÉDIA" else "🟢"
            print(f"   {emoji} {severidade}: {qtd} item(ns)")
    else:
        print("   ✅ Nenhuma inconsistência encontrada")

    # Top fornecedores
    fornecedores = conn.execute("""
        SELECT emit_nome, qtd_notas, total_mercadorias, carga_tributaria_total
        FROM main.gold_impostos_por_fornecedor
        ORDER BY total_mercadorias DESC
        LIMIT 3
    """).fetchall()

    print(f"\n🏭 Top fornecedores por volume:")
    for nome, qtd_notas, total, carga in fornecedores:
        print(f"   • {nome}: R$ {total:,.2f} ({qtd_notas} notas) | Tributos: R$ {carga:,.2f}")

    conn.close()
    print("\n" + "="*60)


# ── Definição da DAG ───────────────────────────────────────────────────────────

with DAG(
    dag_id="nfe_pipeline",
    description="Pipeline completo de NF-e: ingestão, transformação e validação",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule_interval="*/30 * * * *",   # a cada 30 minutos
    catchup=False,
    tags=["nfe", "fiscal", "bronze", "silver", "gold"],
) as dag:

    # ── Task 1: verifica se há XMLs para processar ─────────────────────────────
    verificar = ShortCircuitOperator(
        task_id="verificar_xmls_pendentes",
        python_callable=verificar_xmls_pendentes,
        provide_context=True,
    )

    # ── Task 2: ingestão BRONZE ────────────────────────────────────────────────
    bronze = PythonOperator(
        task_id="ingestao_bronze",
        python_callable=executar_ingestao_bronze,
        provide_context=True,
    )

    # ── Task 3: dbt run (SILVER + GOLD) ───────────────────────────────────────
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {DBT_DIR} && dbt run --profiles-dir /home/airflow/.dbt",
    )

    # ── Task 4: dbt test ───────────────────────────────────────────────────────
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {DBT_DIR} && dbt test --profiles-dir /home/airflow/.dbt",
    )

    # ── Task 5: relatório final ────────────────────────────────────────────────
    relatorio = PythonOperator(
        task_id="relatorio_final",
        python_callable=gerar_relatorio_final,
        provide_context=True,
    )

    # ── Task 6: sincroniza GOLD → PostgreSQL ──────────────────────────
    sync_postgres = PythonOperator(
        task_id="sync_postgres",
        python_callable=executar_sync_postgres,
        provide_context=True,
    )

    # Atualiza a cadeia de dependências
    verificar >> bronze >> dbt_run >> dbt_test >> sync_postgres >> relatorio