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
    col_values = ws.col_values(col_index)
    for i, value in enumerate(col_values[2:], start=3):
        if not value.strip():
            return i
    return len(col_values) + 1

# --- FUNÇÕES DE BUSCA E SCANNER ---

def buscar_em_todas_as_abas(sh, itens_validar):
    """Verifica os itens em ambas as abas e retorna dicionários com os achados."""
    encontrados_alta = []
    encontrados_emergencial = []
    
    # Cache dos dados para performance
    dados_alta = sh.worksheet("ALTA").get_all_values()
    dados_emerg = sh.worksheet("EMERGENCIAL").get_all_values()
    
    for item in itens_validar:
        num_limpo = str(item)
        if not num_limpo: continue
        
        # Busca na ALTA (Coluna E = índice 4)
        for row in dados_alta[2:]:
            if len(row) > 4 and limpar_apenas_numeros(row[4]) == num_limpo:
                encontrados_alta.append(num_limpo)
                break # Para de procurar este item na aba atual
        
        # Busca na EMERGENCIAL (Coluna D = índice 3)
        for row in dados_emerg[2:]:
            if len(row) > 3 and limpar_apenas_numeros(row[3]) == num_limpo:
                encontrados_emergencial.append(num_limpo)
                break
                
    return list(set(encontrados_alta)), list(set(encontrados_emergencial))

def scanner_duplicatas_globais(sh):
    """Cruza a aba ALTA com a EMERGENCIAL em busca de números repetidos."""
    # Coluna E da ALTA (índice 4)
    pedidos_alta = [limpar_apenas_numeros(row[4]) for row in sh.worksheet("ALTA").get_all_values()[2:] if len(row) > 4]
    # Coluna D da EMERGENCIAL (índice 3)
    pedidos_emerg = [limpar_apenas_numeros(row[3]) for row in sh.worksheet("EMERGENCIAL").get_all_values()[2:] if len(row) > 3]
    
    # Remove vazios
    pedidos_alta = set([p for p in pedidos_alta if p])
    pedidos_emerg = set([p for p in pedidos_emerg if p])
    
    # Interseção: números que estão em ambas
    duplicatas = pedidos_alta.intersection(pedidos_emerg)
    return sorted(list(duplicatas))

def app():
    st.title("📝 Cadastro de Pedidos e Solicitações")
    client = get_gspread_client()
    if not client: return
    sh = client.open_by_key(SPREADSHEET_ID)

    # --- SIDEBAR: SCANNER DE DUPLICATAS ---
    st.sidebar.title("🔍 Scanner de Duplicatas")
    duplicas_globais = scanner_duplicatas_globais(sh)
    
    if duplicas_globais:
        st.sidebar.warning("Existem duplicatas de pedidos/solicitações na aba ALTA e EMERGENCIAL!")
        if st.sidebar.button("Mostrar"):
            st.sidebar.write(duplicas_globais)
    else:
        st.sidebar.success("A planilha não possui dados duplicados")

    # --- FORMULÁRIO PRINCIPAL ---
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
        # Limpeza
        s_limpa = limpar_apenas_numeros(solicitacao_raw)
        p_limpos = [limpar_apenas_numeros(x) for x in pedidos_raw.split(",") if x.strip()]
        itens = p_limpos if p_limpos else ([s_limpa] if s_limpa else [])

        if not itens:
            st.warning("Preencha o número do Pedido ou Solicitação.")
            return

        # Validação Cruzada (Garante que verifica as duas abas)
        na_alta, na_emerg = buscar_em_todas_as_abas(sh, itens)

        # Mostra mensagens de erro se houver duplicatas
        if na_alta:
            st.error(f"⚠️ O(s) seguinte(s) número(s) já existem na aba **ALTA**: {', '.join(na_alta)}")
        
        if na_emerg:
            st.error(f"🚨 O(s) seguinte(s) número(s) já existem na aba **EMERGENCIAL**: {', '.join(na_emerg)}")

        if na_alta or na_emerg:
            st.stop()

        # Cadastro
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

        st.success("Cadastrado com sucesso!")
        st.rerun() # Recarrega para atualizar o scanner na sidebar

if __name__ == "__main__":
    app()