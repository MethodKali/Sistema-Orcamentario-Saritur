import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- CONFIGURAÇÕES ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_ID = "1n5I4U7siMsRB-eeAcWr56zNqudlcVbK7T2OImIjnMWs"

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
    """Encontra a primeira linha com a coluna 'Pedido' vazia dentro da tabela"""
    col_values = ws.col_values(col_index)
    # Ignora os cabeçalhos (linhas 1 e 2)
    for i, value in enumerate(col_values[2:], start=3):
        if not value.strip():
            return i
    return len(col_values) + 1

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
            unidade = st.selectbox("Unidade *", ["INDÚSTRIA", "JARDIM MONTANHÊS", "SÃO MARCOS", "NOVA LIMA", "ITAÚNA", "LAGOA SANTA", "DURVAL DE BARROS", "MONTES CLAROS", "VARGINHA", "NEVES", "LAVRAS", "IPATINGA", "VESPASIANO", "GARANTIA", "VENDA DE VEÍCULOS", "ADMINISTRATIVO", "PREDIO ADM", "EXPEDIÇÃO", "CEL. FABRICIANO", "OLIVEIRA", "MORRO ALTO", "TRANSNORTE", "TIMOTEO", "ADMINISTRAÇÃO"])
            carro = st.text_input("Carro | Utilização")
            fornecedor = st.text_input("Fornecedor")
        with col2:
            valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
            status = st.selectbox("Status *", ["NÃO APROVADA", "APROVADA", "COTAÇÃO", "PEDIDO"])
            solicitacao = st.text_input("Nº Solicitação")
            pedidos_input = st.text_area("Nº Pedidos - Separe por vírgula")

        avaliacao = st.selectbox("Avaliação", ["EXPEDIÇÃO", "FINANCEIRO", "UNIDADE", "CREDITO"]) if aba_selecionada == "ALTA" else ""
        responsavel, num_ad, nf = "", "", ""
        if aba_selecionada == "EMERGENCIAL":
            responsavel = st.text_input("Responsável Coleta/Entrega")
            num_ad = st.text_input("Nº AD")
            nf = st.text_input("NF")

        btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

    if btn_cadastrar:
        ws_destino = sh.worksheet(aba_selecionada)
        data_formatada = data_cad.strftime("%d/%m/%Y")
        itens = [p.strip() for p in pedidos_input.split(",") if p.strip()] or [solicitacao]
        
        # REFERÊNCIA DE COLUNA PARA 'PEDIDO':
        # Na ALTA é E (5). Na EMERGENCIAL é D (4).
        col_ref = 5 if aba_selecionada == "ALTA" else 4
        
        sucesso_count = 0
        for item in itens:
            proxima_linha = get_actual_next_row(ws_destino, col_ref)
            
            if aba_selecionada == "ALTA":
                # A:DIAS, B:DATA, C:UNIDADE, D:CARRO, E:PEDIDO, F:VALOR, G:FORNECEDOR, H:STATUS, I:AVALIAÇÃO
                # Note que a fórmula agora aponta para a coluna B (Data)
                formula_dias = f'=IF(B{proxima_linha}=""; ""; TODAY()-B{proxima_linha})'
                nova_linha = [formula_dias, data_formatada, unidade, carro, item, valor, fornecedor, status, avaliacao]
                range_target = f"A{proxima_linha}:I{proxima_linha}"
            else:
                # EMERGENCIAL: A:UNIDADE, B:DATA, C:CARRO, D:PEDIDO, E:VALOR, F:FORNECEDOR, G:RESP, H:AD, I:VAZIO, J:STATUS
                data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                nova_linha = [unidade, data_hora, carro, item, valor, fornecedor, responsavel, num_ad, "", status]
                range_target = f"A{proxima_linha}:J{proxima_linha}"

            ws_destino.update(range_target, [nova_linha], value_input_option='USER_ENTERED')
            sucesso_count += 1

        if sucesso_count > 0:
            st.success(f"Cadastrado com sucesso na linha {proxima_linha}!")
            st.balloons()

if __name__ == "__main__":
    app()