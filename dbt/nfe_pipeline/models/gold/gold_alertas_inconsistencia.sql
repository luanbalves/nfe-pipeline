/*
  GOLD — Alertas priorizados de inconsistências fiscais
  Responde: "Quais notas o contador precisa revisar agora?"
*/

WITH itens_problema AS (
    SELECT
        chave_acesso,
        num_item,
        descricao_produto,
        cfop,
        cfop_descricao,
        ncm,
        ncm_categoria,
        valor_produto,

        icms_aliquota,
        icms_valor_declarado,
        icms_valor_calculado,
        icms_divergencia,
        flag_icms_inconsistente,

        pis_aliquota,
        pis_valor_declarado,
        pis_valor_calculado,
        pis_divergencia,
        flag_pis_inconsistente,

        cofins_aliquota,
        cofins_valor_declarado,
        cofins_valor_calculado,
        cofins_divergencia,
        flag_cofins_inconsistente,

        emit_cnpj,
        emit_nome,
        dest_cnpj,
        dest_nome,
        data_emissao

    FROM {{ ref('silver_nfe_itens_calculado') }}
    WHERE flag_item_inconsistente = true
      AND flag_nota_homologacao = false
),

com_severidade AS (
    SELECT
        *,
        -- Divergência absoluta total (todos os impostos)
        ROUND(
            ABS(icms_divergencia)
            + ABS(pis_divergencia)
            + ABS(cofins_divergencia)
        , 2) AS divergencia_total_abs,

        -- Severidade baseada no valor da divergência
        CASE
            WHEN ABS(icms_divergencia) > 50
              OR ABS(pis_divergencia)  > 20
              OR ABS(cofins_divergencia) > 20  THEN 'ALTA'
            WHEN ABS(icms_divergencia) > 10
              OR ABS(pis_divergencia)  > 5
              OR ABS(cofins_divergencia) > 5   THEN 'MÉDIA'
            ELSE                                    'BAIXA'
        END AS severidade,

        -- Descrição textual do problema para o contador
        CONCAT_WS(' | ',
            CASE WHEN flag_icms_inconsistente
                THEN 'ICMS: declarado R$' || icms_valor_declarado
                  || ' vs calculado R$' || icms_valor_calculado
                  || ' (dif: R$' || icms_divergencia || ')'
            END,
            CASE WHEN flag_pis_inconsistente
                THEN 'PIS: declarado R$' || pis_valor_declarado
                  || ' vs calculado R$' || pis_valor_calculado
                  || ' (dif: R$' || pis_divergencia || ')'
            END,
            CASE WHEN flag_cofins_inconsistente
                THEN 'COFINS: declarado R$' || cofins_valor_declarado
                  || ' vs calculado R$' || cofins_valor_calculado
                  || ' (dif: R$' || cofins_divergencia || ')'
            END
        ) AS descricao_problema

    FROM itens_problema
)

SELECT
    -- Prioridade de revisão (maior divergência primeiro)
    ROW_NUMBER() OVER (ORDER BY divergencia_total_abs DESC) AS prioridade,
    severidade,
    chave_acesso,
    num_item,
    emit_nome,
    dest_nome,
    data_emissao,
    descricao_produto,
    ncm_categoria,
    cfop_descricao,
    valor_produto,
    divergencia_total_abs,
    descricao_problema,
    -- Detalhes por imposto
    flag_icms_inconsistente,
    icms_divergencia,
    flag_pis_inconsistente,
    pis_divergencia,
    flag_cofins_inconsistente,
    cofins_divergencia,
    CURRENT_TIMESTAMP AS atualizado_em

FROM com_severidade
ORDER BY
    CASE severidade WHEN 'ALTA' THEN 1 WHEN 'MÉDIA' THEN 2 ELSE 3 END,
    divergencia_total_abs DESC