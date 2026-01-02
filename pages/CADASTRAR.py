import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import re

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

def limpar_apenas_numeros(texto):
    """Lógica da BACKUP.py: Mantém apenas dígitos."""
    return re.sub(r'\D', '', str(texto))

def get_actual_next_row(ws, col_index):
    """Busca a primeira linha com a célula de Pedido vazia."""
    col_values = ws.col_values(col_index)
    for i, value in enumerate(col_values[2:], start=3):
        if not value.strip():
            return i
    return len(col_values) + 1

def buscar_duplicado_detalhado(sh, numero_procurado):
    """
    Verifica em qual aba o número existe.
    Retorna o nome da aba específica.
    """
    abas_config = {
        "ALTA": 4,        # Coluna E (índice 4)
        "EMERGENCIAL": 3  # Coluna D (índice 3)
    }
    
    for nome_aba, col_idx in abas_config.items():
        ws = sh.worksheet(nome_aba)
        # get_all_values garante que pegamos o dado bruto sem erros de formatação
        data = ws.get_all_values()
        for row in data[2:]:
            if len(row) > col_idx:
                if limpar_apenas_numeros(row[col_idx]) == str(numero_procurado):
                    return nome_aba
    return None

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
            solicitacao_raw = st.text_input("Nº Solicitação")
            pedidos_raw = st.text_area("Nº Pedidos (Separe por vírgula)")

        avaliacao = st.selectbox("Avaliação", ["EXPEDIÇÃO", "FINANCEIRO", "UNIDADE", "CREDITO"]) if aba_selecionada == "ALTA" else ""
        responsavel, num_ad, nf = "", "", ""
        if aba_selecionada == "EMERGENCIAL":
            responsavel = st.text_input("Responsável Coleta/Entrega")
            num_ad = st.text_input("Nº AD")
            nf = st.text_input("NF")

        btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

    if btn_cadastrar:
        # 1. LIMPEZA DOS DADOS
        s_limpa = limpar_apenas_numeros(solicitacao_raw)
        p_limpos = [limpar_apenas_numeros(x) for x in pedidos_raw.split(",") if x.strip()]
        itens = p_limpos if p_limpos else ([s_limpa] if s_limpa else [])

        if not itens:
            st.warning("Por favor, preencha o número do Pedido ou Solicitação.")
            return

        # 2. VALIDAÇÃO CRUZADA COM MENSAGENS DISTINTAS
        encontrados_alta = []
        encontrados_emergencial = []

        for item in itens:
            local = buscar_duplicado_detalhado(sh, item)
            if local == "ALTA":
                encontrados_alta.append(item)
            elif local == "EMERGENCIAL":
                encontrados_emergencial.append(item)

        # Exibe mensagens de erro separadas
        if encontrados_alta:
            st.error(f"⚠️ O(s) seguinte(s) número(s) já existem na aba **ALTA**: {', '.join(encontrados_alta)}")
        
        if encontrados_emergencial:
            st.error(f"🚨 O(s) seguinte(s) número(s) já existem na aba **EMERGENCIAL**: {', '.join(encontrados_emergencial)}")

        # Se houver qualquer erro em qualquer aba, interrompe o processo
        if encontrados_alta or encontrados_emergencial:
            st.stop()

        # 3. CADASTRO SE TUDO ESTIVER OK
        ws_destino = sh.worksheet(aba_selecionada)
        data_formatada = data_cad.strftime("%d/%m/%Y")
        col_ref = 5 if aba_selecionada == "ALTA" else 4
        
        for item in itens:
            proxima_linha = get_actual_next_row(ws_destino, col_ref)
            if aba_selecionada == "ALTA":
                formula_dias = f'=IF(B{proxima_linha}=""; ""; TODAY()-B{proxima_linha})'
                linha = [formula_dias, data_formatada, unidade, carro, item, valor, fornecedor, status, avaliacao]
                ws_destino.update(f"A{proxima_linha}:I{proxima_linha}", [linha], value_input_option='USER_ENTERED')
            else:
                d_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                linha = [unidade, d_hora, carro, item, valor, fornecedor, responsavel, num_ad, "", status]
                ws_destino.update(f"A{proxima_linha}:J{proxima_linha}", [linha], value_input_option='USER_ENTERED')

        st.success(f"Cadastro de {len(itens)} item(s) finalizado com sucesso!")
        st.balloons()

if __name__ == "__main__":
    app()