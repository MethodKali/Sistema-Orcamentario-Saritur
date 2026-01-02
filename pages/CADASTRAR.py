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
    """Remove letras e símbolos, mantendo apenas números."""
    return re.sub(r'\D', '', str(texto))

def get_actual_next_row(ws, col_index):
    """Encontra a primeira linha com a coluna 'Pedido' vazia."""
    col_values = ws.col_values(col_index)
    for i, value in enumerate(col_values[2:], start=3):
        if not value.strip():
            return i
    return len(col_values) + 1

def buscar_duplicado_nas_abas(sh, numero_procurado):
    """
    Busca o número em todas as linhas das colunas de Pedido/Solicitação.
    Retorna o nome da aba se encontrar, ou None.
    """
    # Mapeamento: Nome da Aba -> Índice da Coluna (começando em 0)
    config_abas = {
        "ALTA": 4,        # Coluna E é índice 4
        "EMERGENCIAL": 3  # Coluna D é índice 3
    }
    
    for nome_aba, col_idx in config_abas.items():
        ws = sh.worksheet(nome_aba)
        # Pega todos os dados da aba de uma vez (mais rápido e seguro)
        all_data = ws.get_all_values()
        
        for row in all_data[2:]:  # Pula os cabeçalhos
            if len(row) > col_idx:
                valor_celula = limpar_apenas_numeros(row[col_idx])
                if valor_celula == str(numero_procurado) and valor_celula != "":
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
        
        # Campos emergenciais
        responsavel, num_ad, nf = "", "", ""
        if aba_selecionada == "EMERGENCIAL":
            responsavel = st.text_input("Responsável Coleta/Entrega")
            num_ad = st.text_input("Nº AD")
            nf = st.text_input("NF")

        btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

    if btn_cadastrar:
        # 1. TRATAMENTO E LIMPEZA
        solic_limpa = limpar_apenas_numeros(solicitacao_raw)
        pedidos_sujos = [p.strip() for p in pedidos_raw.split(",") if p.strip()]
        pedidos_limpos = [limpar_apenas_numeros(p) for p in pedidos_sujos]
        
        # Consolida itens para validar
        itens_validar = pedidos_limpos if pedidos_limpos else ([solic_limpa] if solic_limpa else [])

        if not itens_validar:
            st.warning("Insira um número de Pedido ou Solicitação.")
            return

        # 2. VERIFICAÇÃO DE DUPLICATAS (O CORAÇÃO DO ERRO ANTERIOR)
        com_erro = False
        for item in itens_validar:
            aba_onde_existe = buscar_duplicado_nas_abas(sh, item)
            if aba_onde_existe:
                st.error(f"❌ O número **{item}** já está cadastrado na aba **{aba_onde_existe}**!")
                com_erro = True
        
        if com_erro:
            st.stop() # Interrompe tudo se achar qualquer duplicata

        # 3. CADASTRO
        ws_destino = sh.worksheet(aba_selecionada)
        data_formatada = data_cad.strftime("%d/%m/%Y")
        col_ref = 5 if aba_selecionada == "ALTA" else 4
        
        for item in itens_validar:
            proxima_linha = get_actual_next_row(ws_destino, col_ref)
            
            if aba_selecionada == "ALTA":
                formula_dias = f'=IF(B{proxima_linha}=""; ""; TODAY()-B{proxima_linha})'
                nova_linha = [formula_dias, data_formatada, unidade, carro, item, valor, fornecedor, status, avaliacao]
                ws_destino.update(f"A{proxima_linha}:I{proxima_linha}", [nova_linha], value_input_option='USER_ENTERED')
            else:
                data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                nova_linha = [unidade, data_hora, carro, item, valor, fornecedor, responsavel, num_ad, "", status]
                ws_destino.update(f"A{proxima_linha}:J{proxima_linha}", [nova_linha], value_input_option='USER_ENTERED')

        st.success(f"Cadastro realizado com sucesso!")
        st.balloons()

if __name__ == "__main__":
    app()