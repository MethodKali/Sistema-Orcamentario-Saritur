import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime

# --- CONFIGURAÇÕES BÁSICAS ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_ID = "1n5I4U7siMsRB-eeAcWr56zNqudlcVbK7T2OImIjnMWs"

# --- OPÇÕES PARA SELEÇÃO (ITEM 6) ---
OPCOES_UNIDADE = ["INDÚSTRIA",
    "JARDIM MONTANHÊS",
    "SÃO MARCOS",
    "NOVA LIMA",
    "ITAÚNA",
    "LAGOA SANTA",
    "DURVAL DE BARROS",
    "MONTES CLAROS",
    "VARGINHA",
    "NEVES",
    "LAVRAS",
    "IPATINGA",
    "VESPASIANO",
    "GARANTIA",
    "VENDA DE VEÍCULOS",
    "ADMINISTRATIVO",
    "PREDIO ADM",
    "EXPEDIÇÃO",
    "CEL. FABRICIANO",
    "OLIVEIRA",
    "MORRO ALTO",
    "TRANSNORTE",
    "TIMOTEO",
    "ADMINISTRAÇÃO"] # Adicione suas unidades aqui
OPCOES_STATUS = ["NÃO APROVADA", "APROVADA", "COTAÇÃO", "PEDIDO"]
OPCOES_AVALIACAO = ["EXPEDIÇÃO", "FINANCEIRO", "UNIDADE", "CREDITO"]

# --- FUNÇÕES DE CONEXÃO ---
def get_gspread_client():
    try:
        creds_json = st.secrets.get("google_sheets_service_account")
        if creds_json:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(creds_json), SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("acesso.json", SCOPE)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro de autenticação: {e}")
        return None

def find_number_in_sheets(client, number):
    """Busca um número de pedido/solicitação em ambas as abas (Item 3)"""
    sh = client.open_by_key(SPREADSHEET_ID)
    for aba_name in ["ALTA", "EMERGENCIAL"]:
        ws = sh.worksheet(aba_name)
        # Busca na coluna F (6) na ALTA ou D (4) na EMERGENCIAL
        col_idx = 6 if aba_name == "ALTA" else 4
        all_values = ws.col_values(col_idx)
        if str(number) in all_values:
            return aba_name, all_values.index(str(number)) + 1
    return None, None

def delete_row_by_request(client, request_number):
    """Remove a linha de uma solicitação quando ela vira pedido (Item 2 - PEDIDO)"""
    aba, linha = find_number_in_sheets(client, request_number)
    if aba and linha:
        sh = client.open_by_key(SPREADSHEET_ID)
        sh.worksheet(aba).delete_rows(linha)
        return True
    return False

# --- INTERFACE STREAMLIT ---
def app():
    st.title("📝 Cadastro de Pedidos e Solicitações")
    client = get_gspread_client()
    if not client: return

    sh = client.open_by_key(SPREADSHEET_ID)
    
    aba_selecionada = st.selectbox("Selecione a Aba de Destino", ["ALTA", "EMERGENCIAL"])

    with st.form("form_cadastro", clear_on_submit=False):
        st.subheader(f"Dados para {aba_selecionada}")
        
        col1, col2 = st.columns(2)
        
        # Campos Comuns
        with col1:
            data_cad = st.date_input("Data *", datetime.now())
            unidade = st.selectbox("Unidade *", OPCOES_UNIDADE)
            carro = st.text_input("Carro | Utilização")
            fornecedor = st.text_input("Fornecedor")
            
        with col2:
            valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
            status = st.selectbox("Status *", OPCOES_STATUS)
            solicitacao = st.text_input("Nº Solicitação (300k - 400k)")
            pedidos_input = st.text_area("Nº Pedidos (1.1M - 1.3M) - Separe por vírgula para vários")

        # Campos Específicos ALTA
        avaliacao = ""
        if aba_selecionada == "ALTA":
            avaliacao = st.selectbox("Avaliação", OPCOES_AVALIACAO)
        
        # Campos Específicos EMERGENCIAL
        responsavel, num_ad, nf = "", "", ""
        if aba_selecionada == "EMERGENCIAL":
            responsavel = st.text_input("Responsável Coleta/Entrega")
            num_ad = st.text_input("Nº AD")
            nf = st.text_input("NF")

        btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

    if btn_cadastrar:
        # 1. Validação de Campos Obrigatórios
        if not unidade or not pedidos_input and not solicitacao:
            st.error("Campos com * são obrigatórios.")
            return

        # 2. Tratamento de Números (Intervalos)
        lista_pedidos = [p.strip() for p in pedidos_input.split(",") if p.strip()]
        
        # Validação de Intervalos (Item 3)
        if solicitacao:
            s_int = int(solicitacao)
            if not (300000 <= s_int <= 400000):
                st.error("Número de Solicitação fora do intervalo (300.000 - 400.000)")
                return

        for p in lista_pedidos:
            p_int = int(p)
            if not (1100000 <= p_int <= 1300000):
                st.error(f"Pedido {p} fora do intervalo (1.100.000 - 1.300.000)")
                return

        # 3. Lógica de Status (Item 2)
        if solicitacao and lista_pedidos:
            if status in ["NÃO APROVADA", "APROVADA"]:
                st.error(f"Apenas solicitações podem ser {status}. Verifique o cadastro!")
                return
            
            if status == "PEDIDO":
                delete_row_by_request(client, solicitacao)
                st.info(f"Solicitação {solicitacao} removida para inclusão dos pedidos.")

        # 4. Verificação de Duplicatas e Cadastro
        ws_destino = sh.worksheet(aba_selecionada)
        
        # Garantir que não há filtros ativos (Item 5)
        try:
            ws_destino.clear_basic_filter()
        except:
            pass

        data_formatada = data_cad.strftime("%d.%m.%Y")
        
        # Se for COTAÇÃO ou PEDIDO com lista, iteramos os pedidos
        itens_para_cadastrar = lista_pedidos if lista_pedidos else [solicitacao]
        
        sucesso_count = 0
        for item in itens_para_cadastrar:
            aba_duplicada, linha_duplicada = find_number_in_sheets(client, item)
            
            if aba_duplicada:
                st.warning(f"O número {item} já existe na aba {aba_duplicada}, linha {linha_duplicada}. Ignorado.")
                continue
            
            # Montagem da linha conforme estrutura (Item 1)
            if aba_selecionada == "ALTA":
                # Colunas: B:DIAS(formula), C:DATA, D:UNIDADE, E:CARRO, F:PEDIDO, G:VALOR, H:FORNECEDOR, I:STATUS, J:AVALIAÇÃO...
                nova_linha = ["", "", data_formatada, unidade, carro, item, valor, fornecedor, status, avaliacao]
            else:
                # EMERGENCIAL: A:UNIDADE, B:DATA, C:CARRO, D:PEDIDO, E:VALOR, F:FORNECEDOR, G:RESP, H:AD, I:STATUS, J:NF
                data_hora = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                nova_linha = [unidade, data_hora, carro, item, valor, fornecedor, responsavel, num_ad, status, nf]

            ws_destino.append_row(nova_linha, table_range="A2")
            sucesso_count += 1

        if sucesso_count > 0:
            st.success(f"Cadastro de {sucesso_count} item(ns) realizado com sucesso no pé da planilha!")
            st.balloons()

if __name__ == "__main__":
    app()