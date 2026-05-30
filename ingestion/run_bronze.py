"""
Ponto de entrada da camada BRONZE.
Roda manualmente ou chamado pela DAG do Airflow.
"""

from ingestion.loader import carregar_diretorio
from pathlib import Path

SAMPLES_DIR = Path("data/samples")
RAW_DIR     = Path("data/raw")

if __name__ == "__main__":
    # Processa samples (desenvolvimento)
    print("\n🚀 Iniciando carga BRONZE — amostras de desenvolvimento\n")
    resumo = carregar_diretorio(SAMPLES_DIR)

    print(f"\n📊 Resumo:")
    print(f"   ✅ Sucesso:  {resumo['sucesso']}")
    print(f"   ⏭️  Ignorado: {resumo['ignorado']}")
    print(f"   ❌ Erro:     {resumo['erro']}")