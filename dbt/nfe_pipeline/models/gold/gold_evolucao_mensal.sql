/*
  GOLD — Evolução mensal de volume e impostos
  Responde: "Como está a tendência fiscal mês a mês?"
*/

WITH base AS (
    SELECT
        *,
        -- Extrai ano-mês da data de emissão (formato ISO: 2024-01-15T...)
        STRFTIME(CAST(data_emissao AS TIMESTAMP), '%Y-%m') AS ano_mes
    FROM {{ ref('silver_nfe_resumo') }}
    WHERE nota_homologacao = false OR {{ var('filtrar_homologacao') }} = false
)

SELECT
    ano_mes,

    COUNT(*)                                AS qtd_notas,
    COUNT(DISTINCT emit_cnpj)               AS qtd_fornecedores_ativos,

    ROUND(SUM(total_produtos), 2)           AS total_mercadorias,
    ROUND(SUM(icms_declarado), 2)           AS icms_total,
    ROUND(SUM(pis_declarado), 2)            AS pis_total,
    ROUND(SUM(cofins_declarado), 2)         AS cofins_total,
    ROUND(
        SUM(icms_declarado)
        + SUM(pis_declarado)
        + SUM(cofins_declarado), 2
    )                                       AS carga_tributaria_total,

    -- Ticket médio por nota
    ROUND(SUM(total_produtos) / COUNT(*), 2) AS ticket_medio,

    -- Notas com problema no mês
    SUM(nota_tem_inconsistencia::INT)       AS notas_inconsistentes,
    ROUND(
        SUM(nota_tem_inconsistencia::INT) * 100.0 / COUNT(*)
    , 1)                                    AS pct_inconsistentes

FROM base
GROUP BY ano_mes
ORDER BY ano_mes