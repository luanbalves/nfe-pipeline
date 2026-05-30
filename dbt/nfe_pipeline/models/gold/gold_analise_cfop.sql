/*
  GOLD — Distribuição de operações por CFOP
  Responde: "Qual o perfil fiscal das operações?"
*/

WITH base AS (
    SELECT * FROM {{ ref('silver_nfe_itens_calculado') }}
    WHERE flag_nota_homologacao = false
)

SELECT
    cfop,
    cfop_categoria,
    cfop_descricao,

    COUNT(DISTINCT chave_acesso)            AS qtd_notas,
    COUNT(*)                                AS qtd_itens,

    ROUND(SUM(valor_produto), 2)            AS valor_total,
    ROUND(AVG(valor_produto), 2)            AS valor_medio_item,

    ROUND(SUM(icms_valor_declarado), 2)     AS icms_total,
    ROUND(AVG(icms_aliquota), 2)            AS aliquota_icms_media,

    SUM(flag_item_inconsistente::INT)       AS itens_inconsistentes,

    -- Participação no volume total
    ROUND(
        SUM(valor_produto) * 100.0
        / SUM(SUM(valor_produto)) OVER ()
    , 2)                                    AS pct_volume_total,

    CURRENT_TIMESTAMP AS atualizado_em

FROM base
GROUP BY cfop, cfop_categoria, cfop_descricao
ORDER BY valor_total DESC