import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime

# --- CONFIGURAÇÕES BÁSICAS ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_ID = "1n5I4U7siMsRB-eeAcWr56zNqudlcVbK7T2OImIjnMWs"

# --- OPÇÕES PARA SELEÇÃO ---
OPCOES_UNIDADE = [
    "INDÚSTRIA", "JARDIM MONTANHÊS", "SÃO MARCOS", "NOVA LIMA", "ITAÚNA", 
    "LAGOA SANTA", "DURVAL DE BARROS", "MONTES CLAROS", "VARGINHA", "NEVES", 
    "LAVRAS", "IPATINGA", "VESPASIANO", "GARANTIA", "VENDA DE VEÍCULOS", 
    "ADMINISTRATIVO", "PREDIO ADM", "EXPEDIÇÃO", "CEL. FABRICIANO", "OLIVEIRA", 
    "MORRO ALTO", "TRANSNORTE", "TIMOTEO", "ADMINISTRAÇÃO"
]
OPCOES_STATUS = ["NÃO APROVADA", "APROVADA", "COTAÇÃO", "PEDIDO"]
OPCOES_AVALIACAO = ["EXPEDIÇÃO", "FINANCEIRO", "UNIDADE", "CREDITO"]

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

def get_first_empty_row(ws, col_index):
    """Encontra a primeira linha realmente vazia baseada em uma coluna essencial (ex: PEDIDO)"""
    # col_values traz apenas as células que possuem conteúdo
    values = ws.col_values(col_index)
    return len(values) + 1

def find_number_in_sheets(client, number):
    sh = client.open_by_key(SPREADSHEET_ID)
    for aba_name in ["ALTA", "EMERGENCIAL"]:
        ws = sh.worksheet(aba_name)
        col_idx = 6 if aba_name == "ALTA" else 4
        all_values = ws.col_values(col_idx)
        if str(number) in all_values:
            return aba_name, all_values.index(str(number)) + 1
    return None, None

def delete_row_by_request(client, request_number):
    aba, linha = find_number_in_sheets(client, request_number)
    if aba and linha:
        sh = client.open_by_key(SPREADSHEET_ID)
        sh.worksheet(aba).delete_rows(linha)
        return True
    return False

def app():
    st.title("📝 Cadastro de Pedidos e Solicitações")
    client = get_gspread_client()
    if not client: return

    sh = client.open_by_key(SPREADSHEET_ID)
    aba_selecionada = st.selectbox("Selecione a Aba de Destino", ["ALTA", "EMERGENCIAL"])

    with st.form("form_cadastro", clear_on_submit=False):
        st.subheader(f"Dados para {aba_selecionada}")
        col1, col2 = st.columns(2)
        
        with col1:
            data_cad = st.date_input("Data *", datetime.now())
            unidade = st.selectbox("Unidade *", OPCOES_UNIDADE)
            carro = st.text_input("Carro | Utilização")
            fornecedor = st.text_input("Fornecedor")
            
        with col2:
            valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
            status = st.selectbox("Status *", OPCOES_STATUS)
            solicitacao = st.text_input("Nº Solicitação")
            pedidos_input = st.text_area("Nº Pedidos - Separe por vírgula")

        avaliacao = st.selectbox("Avaliação", OPCOES_AVALIACAO) if aba_selecionada == "ALTA" else ""
        responsavel, num_ad, nf = ("", "", "")
        if aba_selecionada == "EMERGENCIAL":
            responsavel = st.text_input("Responsável Coleta/Entrega")
            num_ad = st.text_input("Nº AD")
            nf = st.text_input("NF")

        btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

    if btn_cadastrar:
        lista_pedidos = [p.strip() for p in pedidos_input.split(",") if p.strip()]
        if solicitacao and lista_pedidos and status == "PEDIDO":
            delete_row_by_request(client, solicitacao)

        ws_destino = sh.worksheet(aba_selecionada)
        data_formatada = data_cad.strftime("%d/%m/%Y")
        itens_para_cadastrar = lista_pedidos if lista_pedidos else [solicitacao]
        
        # Define a coluna de referência para achar o pé da tabela (Coluna PEDIDO)
        col_ref = 6 if aba_selecionada == "ALTA" else 4
        
        sucesso_count = 0
        for item in itens_para_cadastrar:
            aba_dup, lin_dup = find_number_in_sheets(client, item)
            if aba_dup:
                st.warning(f"O número {item} já existe na aba {aba_dup}, linha {lin_dup}.")
                continue
            
            # 1. Encontrar a próxima linha disponível
            proxima_linha = get_first_empty_row(ws_destino, col_ref)
            
            # 2. Montar a linha SEM o "" inicial para não deslocar (Item 1)
            if aba_selecionada == "ALTA":
                # Estrutura baseada na imagem: A:DIAS, B:DATA, C:UNIDADE, D:CARRO, E:PEDIDO...
                formula_dias = f'=IF(B{proxima_linha}="";"";TODAY()-B{proxima_linha})'
                nova_linha = [formula_dias, data_formatada, unidade, carro, item, valor, fornecedor, status, avaliacao]
                range_update = f"A{proxima_linha}:I{proxima_linha}"
            else:
                # EMERGENCIAL: A:UNIDADE, B:DATA, C:CARRO, D:PEDIDO, E:VALOR, F:FORNECEDOR, G:RESP, H:AD, I:DATA_PGTO, J:STATUS
                data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                nova_linha = [unidade, data_hora, carro, item, valor, fornecedor, responsavel, num_ad, "", status]
                range_update = f"A{proxima_linha}:J{proxima_linha}"

            # 3. Usar 'update' em vez de 'append_row' para preencher os templates formatados (Item 2)
            ws_destino.update(range_update, [nova_linha], value_input_option='USER_ENTERED')
            sucesso_count += 1

        if sucesso_count > 0:
            st.success(f"Sucesso! {sucesso_count} itens cadastrados no pé real da tabela.")
            st.balloons()

if __name__ == "__main__":
    app()