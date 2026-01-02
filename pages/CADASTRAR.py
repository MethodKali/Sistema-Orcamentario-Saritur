import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime

# --- CONFIGURAÇÕES BÁSICAS ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_ID = "1n5I4U7siMsRB-eeAcWr56zNqudlcVbK7T2OImIjnMWs"

# Opções de Unidade, Status e Avaliação permanecem as mesmas...
OPCOES_UNIDADE = ["INDÚSTRIA", "JARDIM MONTANHÊS", "SÃO MARCOS", "NOVA LIMA", "ITAÚNA", "LAGOA SANTA", "DURVAL DE BARROS", "MONTES CLAROS", "VARGINHA", "NEVES", "LAVRAS", "IPATINGA", "VESPASIANO", "GARANTIA", "VENDA DE VEÍCULOS", "ADMINISTRATIVO", "PREDIO ADM", "EXPEDIÇÃO", "CEL. FABRICIANO", "OLIVEIRA", "MORRO ALTO", "TRANSNORTE", "TIMOTEO", "ADMINISTRAÇÃO"]
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

def get_actual_next_row(ws, col_index):
    """
    Encontra a primeira linha realmente disponível ignorando fórmulas e bordas.
    Busca o primeiro espaço vazio na coluna de referência (Pedido).
    """
    col_values = ws.col_values(col_index)
    # Remove o cabeçalho (linhas 1 e 2)
    data_values = col_values[2:] if len(col_values) > 2 else []
    
    for i, value in enumerate(data_values):
        if not value.strip(): # Se encontrar uma célula vazia no meio da tabela
            return i + 3
            
    return len(col_values) + 1

def app():
    st.title("📝 Cadastro de Pedidos e Solicitações")
    
    # DICA: Se ver erros de "TypeError", limpe o cache do navegador (Ctrl+F5)
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
        responsavel, num_ad, nf = "", "", ""
        if aba_selecionada == "EMERGENCIAL":
            responsavel = st.text_input("Responsável Coleta/Entrega")
            num_ad = st.text_input("Nº AD")
            nf = st.text_input("NF")

        btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

    if btn_cadastrar:
        ws_destino = sh.worksheet(aba_selecionada)
        data_formatada = data_cad.strftime("%d/%m/%Y")
        itens_para_cadastrar = [p.strip() for p in pedidos_input.split(",") if p.strip()] or [solicitacao]
        
        # COLUNA DE REFERÊNCIA: F (6) na ALTA, D (4) na EMERGENCIAL
        col_ref = 6 if aba_selecionada == "ALTA" else 4
        
        sucesso_count = 0
        for item in itens_para_cadastrar:
            # 1. ENCONTRAR A LINHA EXATA
            proxima_linha = get_actual_next_row(ws_destino, col_ref)
            
            # 2. MONTAR A LINHA PARA ENCAIXAR NAS BORDAS
            if aba_selecionada == "ALTA":
                # Alinhamento conforme imagem 23-17-24:
                # B:DIAS, C:DATA, D:UNIDADE, E:CARRO, F:PEDIDO, G:VALOR, H:FORNECEDOR, I:STATUS, J:AVALIAÇÃO
                formula_dias = f'=IF(C{proxima_linha}="";"";TODAY()-C{proxima_linha})'
                nova_linha = [formula_dias, data_formatada, unidade, carro, item, valor, fornecedor, status, avaliacao]
                # Inicia na Coluna B (2) até J (10)
                range_target = f"B{proxima_linha}:J{proxima_linha}"
            else:
                # EMERGENCIAL: A:UNIDADE, B:DATA, C:CARRO, D:PEDIDO, E:VALOR, F:FORNECEDOR, G:RESP, H:AD, I:DATA_PGTO, J:STATUS
                data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                nova_linha = [unidade, data_hora, carro, item, valor, fornecedor, responsavel, num_ad, "", status]
                range_target = f"A{proxima_linha}:J{proxima_linha}"

            # 3. ATUALIZAR EM VEZ DE ADICIONAR NOVA LINHA
            ws_destino.update(range_target, [nova_linha], value_input_option='USER_ENTERED')
            sucesso_count += 1

        if sucesso_count > 0:
            st.success(f"Cadastrado na linha {proxima_linha} com sucesso!")
            st.balloons()

if __name__ == "__main__":
    app()