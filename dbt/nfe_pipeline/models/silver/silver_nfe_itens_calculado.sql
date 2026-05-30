/*
  SILVER — Itens com impostos recalculados e validações fiscais
  
  Para cada item da NF-e:
  - Recalcula ICMS, PIS e COFINS matematicamente
  - Compara com o valor declarado no XML
  - Sinaliza divergências acima da tolerância
  - Classifica o CFOP em categoria legível
*/

WITH itens AS (
    SELECT * FROM {{ ref('bronze_nfe_itens') }}
),

cabecalho AS (
    SELECT * FROM {{ ref('bronze_nfe_cabecalho') }}
),

calculos AS (
    SELECT
        i.chave_acesso,
        i.num_item,
        i.codigo_produto,
        i.descricao_produto,
        i.ncm,
        i.cfop,
        i.unidade,
        i.quantidade,
        i.valor_unitario,
        i.valor_produto,

        -- ── ICMS ────────────────────────────────────────────────────────
        i.icms_aliquota,
        i.icms_valor_declarado,
        ROUND(i.valor_produto * i.icms_aliquota / 100, 2)  AS icms_valor_calculado,
        ROUND(
            i.icms_valor_declarado
            - ROUND(i.valor_produto * i.icms_aliquota / 100, 2)
        , 2)                                                AS icms_divergencia,

        -- ── PIS ─────────────────────────────────────────────────────────
        i.pis_aliquota,
        i.pis_valor_declarado,
        ROUND(i.valor_produto * i.pis_aliquota / 100, 2)   AS pis_valor_calculado,
        ROUND(
            i.pis_valor_declarado
            - ROUND(i.valor_produto * i.pis_aliquota / 100, 2)
        , 2)                                                AS pis_divergencia,

        -- ── COFINS ──────────────────────────────────────────────────────
        i.cofins_aliquota,
        i.cofins_valor_declarado,
        ROUND(i.valor_produto * i.cofins_aliquota / 100, 2) AS cofins_valor_calculado,
        ROUND(
            i.cofins_valor_declarado
            - ROUND(i.valor_produto * i.cofins_aliquota / 100, 2)
        , 2)                                                 AS cofins_divergencia,

        -- ── Classificação CFOP ──────────────────────────────────────────
        CASE
            WHEN i.cfop LIKE '1%' THEN 'Entrada Estadual'
            WHEN i.cfop LIKE '2%' THEN 'Entrada Interestadual'
            WHEN i.cfop LIKE '3%' THEN 'Entrada Exterior'
            WHEN i.cfop LIKE '5%' THEN 'Saída Estadual'
            WHEN i.cfop LIKE '6%' THEN 'Saída Interestadual'
            WHEN i.cfop LIKE '7%' THEN 'Saída Exterior'
            ELSE 'CFOP Desconhecido'
        END AS cfop_categoria,

        CASE
            WHEN i.cfop IN ('5101','6101') THEN 'Venda de Produção Própria'
            WHEN i.cfop IN ('5102','6102') THEN 'Venda de Mercadoria Adquirida'
            WHEN i.cfop IN ('5201','6201') THEN 'Devolução de Compra'
            WHEN i.cfop IN ('5202','6202') THEN 'Devolução de Venda'
            WHEN i.cfop IN ('5411','6411') THEN 'Devolução c/ Substituição Tributária'
            WHEN i.cfop IN ('5910','6910') THEN 'Remessa para Demonstração'
            WHEN i.cfop IN ('5949','6949') THEN 'Outras Saídas'
            ELSE 'Operação não mapeada: ' || i.cfop
        END AS cfop_descricao,

        -- ── Classificação NCM (primeiros 2 dígitos = capítulo) ──────────
        CASE LEFT(i.ncm, 2)
            WHEN '84' THEN 'Máquinas e Equipamentos'
            WHEN '85' THEN 'Equipamentos Elétricos/Eletrônicos'
            WHEN '94' THEN 'Móveis e Mobiliário'
            WHEN '48' THEN 'Papel e Papelão'
            WHEN '39' THEN 'Plásticos'
            WHEN '73' THEN 'Obras de Ferro ou Aço'
            WHEN '90' THEN 'Instrumentos de Precisão'
            ELSE 'Outros (NCM ' || LEFT(i.ncm, 2) || ')'
        END AS ncm_categoria,

        -- Dados do emitente para enriquecer o item
        c.emit_cnpj,
        c.emit_nome,
        c.dest_cnpj,
        c.dest_nome,
        c.data_emissao,
        c.ambiente

    FROM itens i
    LEFT JOIN cabecalho c ON i.chave_acesso = c.chave_acesso
)

SELECT
    *,
    -- ── Flags de inconsistência ─────────────────────────────────────────
    -- Tolerância de R$ 0,02 para evitar falso positivo por arredondamento
    ABS(icms_divergencia)    > 0.02 AS flag_icms_inconsistente,
    ABS(pis_divergencia)     > 0.02 AS flag_pis_inconsistente,
    ABS(cofins_divergencia)  > 0.02 AS flag_cofins_inconsistente,

    -- Flag geral: qualquer imposto com problema
    (
        ABS(icms_divergencia)   > 0.02
        OR ABS(pis_divergencia) > 0.02
        OR ABS(cofins_divergencia) > 0.02
    ) AS flag_item_inconsistente,

    -- Ambiente: notas de homologação não devem ir para produção
    ambiente = '2' AS flag_nota_homologacao,

    CURRENT_TIMESTAMP AS processado_em

FROM calculos