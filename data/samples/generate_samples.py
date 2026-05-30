"""
Gerador de NF-e de exemplo.
Gera notas válidas e algumas com inconsistências intencionais.
"""

import random
import string
from datetime import datetime, timedelta
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent

EMITENTES = [
    {"cnpj": "11222333000181", "nome": "FORNECEDOR ALFA LTDA", "ie": "111222333"},
    {"cnpj": "44555666000195", "nome": "DISTRIBUIDORA BETA SA", "ie": "444555666"},
    {"cnpj": "77888999000102", "nome": "INDUSTRIA GAMA EIRELI", "ie": "777888999"},
]

DESTINATARIOS = [
    {"cnpj": "12345678000195", "nome": "EMPRESA CLIENTE XYZ LTDA", "ie": "123456789"},
    {"cnpj": "98765432000188", "nome": "COMERCIO DELTA ME", "ie": "987654321"},
]

PRODUTOS = [
    {"codigo": "PROD001", "descricao": "NOTEBOOK CORE I7", "ncm": "84713012", "cfop": "6102", "un": "UN", "vUnit": 3500.00, "aliq_icms": 12.0, "aliq_pis": 0.65, "aliq_cofins": 3.0},
    {"codigo": "PROD002", "descricao": "MOUSE SEM FIO", "ncm": "84716042", "cfop": "6102", "un": "UN", "vUnit": 120.00, "aliq_icms": 12.0, "aliq_pis": 0.65, "aliq_cofins": 3.0},
    {"codigo": "PROD003", "descricao": "CADEIRA ERGONOMICA", "ncm": "94013000", "cfop": "6102", "un": "UN", "vUnit": 850.00, "aliq_icms": 18.0, "aliq_pis": 1.65, "aliq_cofins": 7.6},
    {"codigo": "PROD004", "descricao": "PAPEL A4 500FLS", "ncm": "48025510", "cfop": "6101", "un": "PT", "vUnit": 25.00, "aliq_icms": 12.0, "aliq_pis": 0.65, "aliq_cofins": 3.0},
    {"codigo": "PROD005", "descricao": "TONER IMPRESSORA", "ncm": "84439910", "cfop": "6102", "un": "UN", "vUnit": 280.00, "aliq_icms": 18.0, "aliq_pis": 1.65, "aliq_cofins": 7.6},
]


def gerar_chave_acesso(uf="35", data="202401", cnpj="11222333000181", mod="55", serie="001", nnf="000000001"):
    """Gera uma chave de acesso fictícia de 44 dígitos."""
    base = f"{uf}{data}{cnpj}{mod}{serie}{nnf}1"
    base = base.ljust(43, "0")[:43]
    digito = str(random.randint(0, 9))
    return base + digito


def calcular_imposto(valor_produto, aliquota, com_inconsistencia=False):
    """Calcula imposto e opcionalmente introduz inconsistência."""
    valor_correto = round(valor_produto * aliquota / 100, 2)
    if com_inconsistencia:
        # Inconsistência: valor declarado diferente do calculado
        erro = round(random.uniform(0.5, 5.0), 2)
        return valor_correto + erro, valor_correto
    return valor_correto, valor_correto


def gerar_xml_nfe(numero: int, com_inconsistencia: bool = False) -> str:
    emit = random.choice(EMITENTES)
    dest = random.choice(DESTINATARIOS)
    data_emissao = datetime.now() - timedelta(days=random.randint(0, 90))
    data_str = data_emissao.strftime("%Y-%m-%dT%H:%M:%S-03:00")

    itens = random.sample(PRODUTOS, k=random.randint(1, 3))
    quantidades = [random.randint(1, 10) for _ in itens]

    chave = gerar_chave_acesso(
        data=data_emissao.strftime("%y%m"),
        cnpj=emit["cnpj"],
        nnf=str(numero).zfill(9)
    )

    # Monta itens e calcula totais
    itens_xml = ""
    total_produtos = 0.0
    total_icms = 0.0
    total_pis = 0.0
    total_cofins = 0.0

    for idx, (prod, qtd) in enumerate(zip(itens, quantidades), start=1):
        v_prod = round(prod["vUnit"] * qtd, 2)
        total_produtos += v_prod

        # Inconsistência só no primeiro item, se solicitado
        inconsistencia_item = com_inconsistencia and idx == 1

        v_icms, v_icms_correto = calcular_imposto(v_prod, prod["aliq_icms"], inconsistencia_item)
        v_pis, _ = calcular_imposto(v_prod, prod["aliq_pis"])
        v_cofins, _ = calcular_imposto(v_prod, prod["aliq_cofins"])

        total_icms += v_icms
        total_pis += v_pis
        total_cofins += v_cofins

        itens_xml += f"""
        <det nItem="{idx}">
            <prod>
                <cProd>{prod['codigo']}</cProd>
                <cEAN>SEM GTIN</cEAN>
                <xProd>{prod['descricao']}</xProd>
                <NCM>{prod['ncm']}</NCM>
                <CFOP>{prod['cfop']}</CFOP>
                <uCom>{prod['un']}</uCom>
                <qCom>{qtd}.0000</qCom>
                <vUnCom>{prod['vUnit']:.2f}</vUnCom>
                <vProd>{v_prod:.2f}</vProd>
            </prod>
            <imposto>
                <ICMS>
                    <ICMS00>
                        <orig>0</orig>
                        <CST>00</CST>
                        <modBC>3</modBC>
                        <vBC>{v_prod:.2f}</vBC>
                        <pICMS>{prod['aliq_icms']:.2f}</pICMS>
                        <vICMS>{v_icms:.2f}</vICMS>
                    </ICMS00>
                </ICMS>
                <PIS>
                    <PISAliq>
                        <CST>01</CST>
                        <vBC>{v_prod:.2f}</vBC>
                        <pPIS>{prod['aliq_pis']:.4f}</pPIS>
                        <vPIS>{v_pis:.2f}</vPIS>
                    </PISAliq>
                </PIS>
                <COFINS>
                    <COFINSAliq>
                        <CST>01</CST>
                        <vBC>{v_prod:.2f}</vBC>
                        <pCOFINS>{prod['aliq_cofins']:.4f}</pCOFINS>
                        <vCOFINS>{v_cofins:.2f}</vCOFINS>
                    </COFINSAliq>
                </COFINS>
            </imposto>
        </det>"""

    total_nf = round(total_produtos + total_icms, 2)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
    <NFe>
        <infNFe Id="NFe{chave}" versao="4.00">
            <ide>
                <cUF>35</cUF>
                <cNF>{str(random.randint(10000000, 99999999))}</cNF>
                <natOp>VENDA DE MERCADORIA</natOp>
                <mod>55</mod>
                <serie>1</serie>
                <nNF>{numero}</nNF>
                <dhEmi>{data_str}</dhEmi>
                <tpNF>1</tpNF>
                <idDest>1</idDest>
                <cMunFG>3550308</cMunFG>
                <tpImp>1</tpImp>
                <tpEmis>1</tpEmis>
                <tpAmb>1</tpAmb>
                <finNFe>1</finNFe>
                <indFinal>0</indFinal>
                <indPres>0</indPres>
            </ide>
            <emit>
                <CNPJ>{emit['cnpj']}</CNPJ>
                <xNome>{emit['nome']}</xNome>
                <IE>{emit['ie']}</IE>
                <CRT>3</CRT>
            </emit>
            <dest>
                <CNPJ>{dest['cnpj']}</CNPJ>
                <xNome>{dest['nome']}</xNome>
                <IE>{dest['ie']}</IE>
                <indIEDest>1</indIEDest>
            </dest>
            {itens_xml}
            <total>
                <ICMSTot>
                    <vBC>{total_produtos:.2f}</vBC>
                    <vICMS>{total_icms:.2f}</vICMS>
                    <vPIS>{total_pis:.2f}</vPIS>
                    <vCOFINS>{total_cofins:.2f}</vCOFINS>
                    <vProd>{total_produtos:.2f}</vProd>
                    <vNF>{total_nf:.2f}</vNF>
                </ICMSTot>
            </total>
        </infNFe>
    </NFe>
</nfeProc>"""


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 15 notas normais
    for i in range(1, 16):
        xml = gerar_xml_nfe(numero=i)
        path = OUTPUT_DIR / f"nfe_{str(i).zfill(3)}_normal.xml"
        path.write_text(xml, encoding="utf-8")

    # 5 notas com inconsistências
    for i in range(16, 21):
        xml = gerar_xml_nfe(numero=i, com_inconsistencia=True)
        path = OUTPUT_DIR / f"nfe_{str(i).zfill(3)}_inconsistente.xml"
        path.write_text(xml, encoding="utf-8")

    print(f"✅ Gerados 20 XMLs em {OUTPUT_DIR}")
    print(f"   → 15 normais")
    print(f"   → 5 com inconsistências de ICMS no primeiro item")


if __name__ == "__main__":
    main()