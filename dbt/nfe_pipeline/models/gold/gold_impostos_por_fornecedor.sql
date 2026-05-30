/*
  GOLD — Resumo fiscal consolidado por fornecedor (emitente)
  Responde: "Quanto cada fornecedor nos gerou de imposto?"
*/

WITH base AS (
    SELECT * FROM {{ ref('silver_nfe_resumo') }}
    WHERE nota_homologacao = false OR {{ var('filtrar_homologacao') }} = false   -- exclui notas de teste
),

por_fornecedor AS (
    SELECT
        emit_cnpj,
        emit_nome,

        COUNT(*)                            AS qtd_notas,
        SUM(qtd_itens)                      AS qtd_itens_total,

        ROUND(SUM(total_produtos), 2)       AS total_mercadorias,

        ROUND(SUM(icms_declarado), 2)       AS icms_total_declarado,
        ROUND(SUM(icms_calculado), 2)       AS icms_total_calculado,
        ROUND(SUM(icms_declarado)
            - SUM(icms_calculado), 2)       AS icms_divergencia_total,

        ROUND(SUM(pis_declarado), 2)        AS pis_total,
        ROUND(SUM(cofins_declarado), 2)     AS cofins_total,

        ROUND(
            SUM(icms_declarado)
            + SUM(pis_declarado)
            + SUM(cofins_declarado), 2
        )                                   AS carga_tributaria_total,

        -- Percentual de carga tributária sobre mercadorias
        ROUND(
            (SUM(icms_declarado) + SUM(pis_declarado) + SUM(cofins_declarado))
            * 100.0 / NULLIF(SUM(total_produtos), 0)
        , 2)                                AS pct_carga_tributaria,

        SUM(nota_tem_inconsistencia::INT)   AS notas_com_inconsistencia,
        ROUND(
            SUM(nota_tem_inconsistencia::INT) * 100.0 / COUNT(*)
        , 1)                                AS pct_notas_inconsistentes

    FROM base
    GROUP BY emit_cnpj, emit_nome
)

SELECT
    *,
    -- Ranking por volume de mercadorias
    ROW_NUMBER() OVER (ORDER BY total_mercadorias DESC) AS ranking_volume,
    CURRENT_TIMESTAMP AS atualizado_em
FROM por_fornecedor
ORDER BY total_mercadorias DESC