/*
  SILVER — Uma linha por NF-e com resumo fiscal e flags consolidadas
  Útil para dashboards de visão geral
*/

WITH itens_calc AS (
    SELECT * FROM {{ ref('silver_nfe_itens_calculado') }}
),

por_nota AS (
    SELECT
        chave_acesso,
        emit_cnpj,
        emit_nome,
        dest_cnpj,
        dest_nome,
        data_emissao,

        COUNT(*)                                AS qtd_itens,
        SUM(valor_produto)                      AS total_produtos,

        SUM(icms_valor_declarado)               AS icms_declarado,
        SUM(icms_valor_calculado)               AS icms_calculado,
        SUM(icms_divergencia)                   AS icms_divergencia_total,

        SUM(pis_valor_declarado)                AS pis_declarado,
        SUM(pis_valor_calculado)                AS pis_calculado,

        SUM(cofins_valor_declarado)             AS cofins_declarado,
        SUM(cofins_valor_calculado)             AS cofins_calculado,

        -- Flags consolidadas da nota
        BOOL_OR(flag_icms_inconsistente)        AS tem_icms_inconsistente,
        BOOL_OR(flag_pis_inconsistente)         AS tem_pis_inconsistente,
        BOOL_OR(flag_cofins_inconsistente)      AS tem_cofins_inconsistente,
        BOOL_OR(flag_item_inconsistente)        AS nota_tem_inconsistencia,
        MAX(flag_nota_homologacao::INT)::BOOL   AS nota_homologacao,

        -- Quantos itens têm problema
        SUM(flag_item_inconsistente::INT)       AS qtd_itens_inconsistentes

    FROM itens_calc
    GROUP BY 1,2,3,4,5,6
)

SELECT
    *,
    -- Percentual de itens com problema
    ROUND(qtd_itens_inconsistentes * 100.0 / qtd_itens, 1) AS pct_itens_inconsistentes,
    CURRENT_TIMESTAMP AS processado_em
FROM por_nota