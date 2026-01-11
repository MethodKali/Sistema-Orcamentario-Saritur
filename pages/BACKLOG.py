import streamlit as st
import re
import pandas as pd
import gspread 
from typing import List, Dict, Union
from oauth2client.service_account import ServiceAccountCredentials
import os 

# --- CONFIGURAÇÃO ---
PLANILHA_NOME = "Controle Orçamentário Diário V2" 
COLUNAS_DADOS = ['PEDIDO', 'DATA', 'CARRO | UTILIZAÇÃO', 'STATUS']
COLUNA_CARRO = 'CARRO | UTILIZAÇÃO' 

ABAS_A_BUSCAR = ['ALTA', 'EMERGENCIAL', 'GERAL_EMERGENCIAL']

GOOGLE_SHEET_SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

LISTA_CARROS_CADASTRO = [
    "- SELECIONE UM CRITÉRIO -",
    "BACKLOG",
    "24600", "23900", "23880", "23400", "13770", "26220", "30030", 
    "32990", "21400", "23600", "24000", "14400", "20330", "24300", "32220",
]

# ----------------------------------------------------
# 1. FUNÇÕES DE UTILIDADE
# ----------------------------------------------------

def parse_pedidos(text: str) -> List[str]:
    if not text:
        return []
    text_cleaned = re.sub(r'[^\d]', ' ', text)
    raw_list = re.split(r'\s+', text_cleaned.strip())
    pedidos_limpos = {p for p in raw_list if p.isdigit() and len(p) > 0}
    return sorted(list(pedidos_limpos))

@st.cache_data(ttl=600)
def load_data(sheet_name: str) -> Dict[str, pd.DataFrame]:
    data = {}
    try:
        creds_json = st.secrets.get("google_sheets_service_account")
        if creds_json:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, GOOGLE_SHEET_SCOPES)
            gc = gspread.authorize(creds)
        else:
            gc = gspread.service_account(filename="acesso.json")
    except Exception as e:
        st.error(f"Erro ao autenticar: {e}")
        return None
    
    try:
        sh = gc.open(sheet_name)
        for tab in ABAS_A_BUSCAR:
            try:
                worksheet = sh.worksheet(tab)
                list_of_lists = worksheet.get_all_values()
                if len(list_of_lists) < 2: continue
                header = [h.strip().upper() for h in list_of_lists[1]]
                data_rows = list_of_lists[2:] 
                df = pd.DataFrame(data_rows, columns=header)
                df.columns = [c.strip().upper() for c in df.columns]
                if 'PEDIDO' in df.columns:
                    df['PEDIDO'] = df['PEDIDO'].astype(str).str.strip()
                data[tab] = df
            except gspread.WorksheetNotFound: 
                st.error(f"Erro: Aba '{tab}' não encontrada.")
                continue
        return data
    except Exception as e:
        st.error(f"Erro inesperado: {e}")
        return None

# ----------------------------------------------------
# 2. FUNÇÕES DE BUSCA E CONTROLE DE ESTADO
# ----------------------------------------------------

def initialize_state():
    if 'search_history' not in st.session_state:
        st.session_state['search_history'] = []
    if 'feedback_message' not in st.session_state:
        st.session_state['feedback_message'] = None

def search_pedido(pedido: str, data: Dict[str, pd.DataFrame], carro_selecionado: str) -> Dict[str, str]:
    found_data = {
        "Pedido": pedido, "Origem": "", "Data": "", COLUNA_CARRO: "", 
        "Status": "Pedido Não Encontrado", "Carro Foco": carro_selecionado
    }
    for sheet_name, df in data.items():
        if 'PEDIDO' not in df.columns: continue
        match = df[df['PEDIDO'] == pedido]
        if not match.empty:
            row = match.iloc[0]
            found_data.update({
                "Origem": sheet_name, "Data": row.get('DATA', ''), 
                COLUNA_CARRO: row.get(COLUNA_CARRO, ''), "Status": row.get('STATUS', '')
            })
            return found_data
    return found_data

def perform_search(pedidos: List[str], data: Dict[str, pd.DataFrame], carro_selecionado: str) -> List[Dict[str, str]]:
    if not pedidos or data is None: return []
    return [search_pedido(p, data, carro_selecionado) for p in pedidos]

def handle_search(data_frames: Dict[str, pd.DataFrame]):
    # Pega o valor dos widgets via session_state
    input_text = st.session_state.backlog_input_text
    carro_selecionado = st.session_state.carro_select
    parsed_pedidos = parse_pedidos(input_text)
    
    if carro_selecionado == LISTA_CARROS_CADASTRO[0]:
        st.session_state['feedback_message'] = "⚠️ ERRO: Selecione um critério de carro."
        return

    if not parsed_pedidos:
        st.session_state['feedback_message'] = "⚠️ ERRO: Nenhum número de pedido válido identificado."
        return 
        
    search_results = perform_search(parsed_pedidos, data_frames, carro_selecionado)
    
    if search_results:
        new_df = pd.DataFrame(search_results)
        substituted = False
        new_history = []
        for existing_df in st.session_state['search_history']:
            if existing_df['Carro Foco'].iloc[0] == carro_selecionado:
                new_history.append(new_df)
                substituted = True
            else:
                new_history.append(existing_df)
        if not substituted:
            new_history.append(new_df)
        st.session_state['search_history'] = new_history
        st.session_state['feedback_message'] = f"✅ Critério '{carro_selecionado}' atualizado."
    
    # A limpeza do campo agora é feita via callback ou reset no app() para evitar o erro de API

def remove_last_search():
    if st.session_state['search_history']:
        st.session_state['search_history'].pop()

def clear_search_history():
    st.session_state['search_history'] = []

# ----------------------------------------------------
# 3. FUNÇÕES DE ESTILO E EXIBIÇÃO
# ----------------------------------------------------

def apply_text_color_by_status(row):
    style_list = []
    is_error = row['Status'] == "Pedido Não Encontrado"
    for col in row.index:
        if is_error:
            style_list.append('color: #FF4B4B; font-weight: bold;' if col in ['Pedido', 'Status'] else 'color: #808495;') 
        else:
            style_list.append('color: #008000; font-weight: bold;' if col in ['Pedido', 'Status'] else None)
    return style_list

def display_search_history():
    history = st.session_state['search_history']
    if not history:
        st.info("Nenhuma busca realizada no momento.")
        return
    for df in history:
        carro_foco = df['Carro Foco'].iloc[0]
        df['Sort_Key'] = df['Status'].apply(lambda x: 1 if x == "Pedido Não Encontrado" else 0)
        df_sorted = df.sort_values(by='Sort_Key').drop(columns=['Sort_Key'])
        df_display = df_sorted.rename(columns={COLUNA_CARRO: 'Carro Planilha'}).drop(columns=['Carro Foco'])
        column_order = ['Pedido', 'Origem', 'Data', 'Carro Planilha', 'Status']
        st.markdown(f"### 🚗 CRITÉRIO: {carro_foco}")
        st.dataframe(df_display[column_order].style.apply(apply_text_color_by_status, axis=1), use_container_width=True, hide_index=True)
        st.mark
        
def processar_e_limpar(data_frames):
    """Callback para processar a busca e limpar o campo de texto com segurança."""
    handle_search(data_frames)
    # Limpa o valor no session_state de forma que o widget reconheça no próximo ciclo
    st.session_state["backlog_input_text"] = ""
# ----------------------------------------------------
# 4. FUNÇÃO PRINCIPAL (APP)
# ----------------------------------------------------

def app():
    initialize_state()
    st.title("🔍 Pesquisa em Backlog e Geral")

    if st.session_state.get('feedback_message'):
        if "✅" in st.session_state['feedback_message']:
            st.success(st.session_state['feedback_message'])
        else:
            st.error(st.session_state['feedback_message'])
        st.session_state['feedback_message'] = None 

    with st.spinner("Conectando ao banco de dados da planilha..."):
        data_frames = load_data(PLANILHA_NOME)
    
    if data_frames is None: st.stop()
    
    col1, col2 = st.columns([0.6, 0.4])
    with col1:
        st.text_area("Cole o bloco de texto contendo os pedidos:", height=120, key='backlog_input_text')
    
    with col2:
        st.selectbox("Critério de Carro:", options=LISTA_CARROS_CADASTRO, key='carro_select')
        
        # Usamos o parâmetro on_click para processar e limpar antes da renderização
        st.button(
            "BUSCAR DADOS", 
            type="primary", 
            use_container_width=True,
            on_click=processar_e_limpar,
            args=(data_frames,)
        )
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("⬅️ REMOVER ÚLTIMA BUSCA", use_container_width=True):
            remove_last_search()
            st.rerun()
    with c2:
        if st.button("❌ LIMPAR TODO HISTÓRICO", use_container_width=True):
            clear_search_history()
            st.rerun()
    
    display_search_history()

if __name__ == '__main__':
    app()