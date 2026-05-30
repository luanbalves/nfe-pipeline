"""
Parser de XML de NF-e — Camada BRONZE
Extrai dados estruturados do XML e retorna como dicionários prontos
para serem carregados no DuckDB.
"""

from lxml import etree
from pathlib import Path
from typing import Optional
import re

# Namespace padrão da NF-e — necessário para localizar tags com lxml
NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}


def _texto(elemento, xpath: str) -> Optional[str]:
    """Extrai texto de um elemento via XPath. Retorna None se não encontrar."""
    resultado = elemento.xpath(f"{xpath}/text()", namespaces=NS)
    return resultado[0].strip() if resultado else None


def _decimal(elemento, xpath: str) -> Optional[float]:
    """Extrai valor decimal. Retorna None se não encontrar ou não for número."""
    valor = _texto(elemento, xpath)
    if valor is None:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def parse_nfe(caminho_xml: str | Path) -> Optional[dict]:
    """
    Faz o parse completo de um XML de NF-e.

    Retorna um dicionário com:
      - cabecalho: dados da nota (chave, número, emitente, destinatário)
      - itens: lista de produtos com impostos declarados
      - totais: totais da nota conforme declarado no XML

    Retorna None se o arquivo não for um XML de NF-e válido.
    """
    caminho_xml = Path(caminho_xml)

    try:
        tree = etree.parse(caminho_xml)
        root = tree.getroot()
    except etree.XMLSyntaxError as e:
        print(f"⚠️  XML inválido: {caminho_xml.name} — {e}")
        return None

    # Localiza o nó principal infNFe
    inf_nfe = root.find(".//nfe:infNFe", NS)
    if inf_nfe is None:
        print(f"⚠️  Não é uma NF-e válida: {caminho_xml.name}")
        return None

    # ── Chave de acesso ────────────────────────────────────────────────
    id_attr = inf_nfe.get("Id", "")
    chave_acesso = id_attr.replace("NFe", "") if id_attr else None

    # ── Cabeçalho ──────────────────────────────────────────────────────
    ide = inf_nfe.find("nfe:ide", NS)
    emit = inf_nfe.find("nfe:emit", NS)
    dest = inf_nfe.find("nfe:dest", NS)

    cabecalho = {
        "chave_acesso":      chave_acesso,
        "numero_nf":         _texto(ide, "nfe:nNF"),
        "serie":             _texto(ide, "nfe:serie"),
        "data_emissao":      _texto(ide, "nfe:dhEmi"),
        "natureza_operacao": _texto(ide, "nfe:natOp"),
        "tipo_nf":           _texto(ide, "nfe:tpNF"),      # 0=entrada, 1=saída
        "ambiente":          _texto(ide, "nfe:tpAmb"),     # 1=produção, 2=homologação
        # Emitente
        "emit_cnpj":         _texto(emit, "nfe:CNPJ"),
        "emit_nome":         _texto(emit, "nfe:xNome"),
        "emit_ie":           _texto(emit, "nfe:IE"),
        # Destinatário
        "dest_cnpj":         _texto(dest, "nfe:CNPJ"),
        "dest_nome":         _texto(dest, "nfe:xNome"),
        "dest_ie":           _texto(dest, "nfe:IE"),
        # Metadados
        "arquivo_origem":    caminho_xml.name,
    }

    # ── Itens ──────────────────────────────────────────────────────────
    itens = []
    for det in inf_nfe.findall("nfe:det", NS):
        num_item = det.get("nItem")
        prod = det.find("nfe:prod", NS)
        imposto = det.find("nfe:imposto", NS)

        v_prod = _decimal(prod, "nfe:vProd")
        qtd = _decimal(prod, "nfe:qCom")
        v_unit = _decimal(prod, "nfe:vUnCom")

        # ICMS — pode estar em ICMS00, ICMS10, ICMS20, etc.
        icms_node = imposto.find(".//nfe:ICMS/nfe:*", NS) if imposto is not None else None
        v_icms_declarado = _decimal(icms_node, "nfe:vICMS") if icms_node is not None else None
        aliq_icms = _decimal(icms_node, "nfe:pICMS") if icms_node is not None else None
        bc_icms = _decimal(icms_node, "nfe:vBC") if icms_node is not None else None

        # PIS
        pis_node = imposto.find(".//nfe:PIS/nfe:*", NS) if imposto is not None else None
        v_pis_declarado = _decimal(pis_node, "nfe:vPIS") if pis_node is not None else None
        aliq_pis = _decimal(pis_node, "nfe:pPIS") if pis_node is not None else None

        # COFINS
        cofins_node = imposto.find(".//nfe:COFINS/nfe:*", NS) if imposto is not None else None
        v_cofins_declarado = _decimal(cofins_node, "nfe:vCOFINS") if cofins_node is not None else None
        aliq_cofins = _decimal(cofins_node, "nfe:pCOFINS") if cofins_node is not None else None

        itens.append({
            "chave_acesso":       chave_acesso,
            "num_item":           int(num_item) if num_item else None,
            "codigo_produto":     _texto(prod, "nfe:cProd"),
            "descricao_produto":  _texto(prod, "nfe:xProd"),
            "ncm":                _texto(prod, "nfe:NCM"),
            "cfop":               _texto(prod, "nfe:CFOP"),
            "unidade":            _texto(prod, "nfe:uCom"),
            "quantidade":         qtd,
            "valor_unitario":     v_unit,
            "valor_produto":      v_prod,
            # ICMS
            "icms_bc":            bc_icms,
            "icms_aliquota":      aliq_icms,
            "icms_valor_declarado": v_icms_declarado,
            # PIS
            "pis_aliquota":       aliq_pis,
            "pis_valor_declarado": v_pis_declarado,
            # COFINS
            "cofins_aliquota":    aliq_cofins,
            "cofins_valor_declarado": v_cofins_declarado,
        })

    # ── Totais declarados ──────────────────────────────────────────────
    tot = inf_nfe.find(".//nfe:ICMSTot", NS)
    totais = {
        "chave_acesso":   chave_acesso,
        "vbc_total":      _decimal(tot, "nfe:vBC"),
        "icms_total":     _decimal(tot, "nfe:vICMS"),
        "pis_total":      _decimal(tot, "nfe:vPIS"),
        "cofins_total":   _decimal(tot, "nfe:vCOFINS"),
        "vprod_total":    _decimal(tot, "nfe:vProd"),
        "vnf_total":      _decimal(tot, "nfe:vNF"),
    }

    return {
        "cabecalho": cabecalho,
        "itens":     itens,
        "totais":    totais,
    }


def parse_diretorio(diretorio: str | Path) -> list[dict]:
    """Faz o parse de todos os XMLs de uma pasta. Ignora arquivos inválidos."""
    diretorio = Path(diretorio)
    resultados = []
    arquivos = sorted(diretorio.glob("*.xml"))

    print(f"📂 Encontrados {len(arquivos)} XMLs em {diretorio}")

    for arquivo in arquivos:
        resultado = parse_nfe(arquivo)
        if resultado:
            resultados.append(resultado)

    print(f"✅ Parseados com sucesso: {len(resultados)}/{len(arquivos)}")
    return resultados