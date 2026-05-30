-- Expõe a tabela bronze como view para o dbt referenciar
-- Sem transformação — dados exatamente como vieram do XML

SELECT
    chave_acesso,
    numero_nf,
    serie,
    data_emissao,
    natureza_operacao,
    tipo_nf,
    ambiente,
    emit_cnpj,
    emit_nome,
    emit_ie,
    dest_cnpj,
    dest_nome,
    dest_ie,
    arquivo_origem,
    carregado_em
FROM bronze.nfe_cabecalho