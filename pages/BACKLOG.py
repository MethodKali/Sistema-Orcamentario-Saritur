# BACKLOG.py
import streamlit as st
import re
import pandas as pd
import gspread 
from typing import List, Dict, Union
from datetime import date, timedelta
import calendar 
import json 
from oauth2client.service_account import ServiceAccountCredentials
import os 

# --- CONFIGURAÇÃO ---
PLANILHA_NOME = "Controle Orçamentário Diário V2" 
COLUNAS_DADOS = ['PEDIDO', 'DATA', 'CARRO | UTILIZAÇÃO', 'STATUS']
COLUNA_CARRO = 'CARRO | UTILIZAÇÃO' 

# LISTA DAS ABAS A SEREM CARREGADAS
ABAS_PRINCIPAIS = ['ALTA', 'EMERGENCIAL']

# DEFINIÇÃO DO SCOPE DE PERMISSÃO
GOOGLE_SHEET_SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# LISTA DOS CARROS CADASTRADOS
LISTA_CARROS_CADASTRO = [
    "- SELECIONE UM CRITÉRIO -",
    "BACKLOG",
    "24600", "23900", "23880", "23400", "13770", "26220", "30030", 
    "32990", "21400", "23600", "24000", "14400", "20330", "24300", "32220",
]

# ----------------------------------------------------
# 1. FUNÇÕES DE UTILIDADE E CÁLCULO DE DATA (CORRIGIDO)
# ----------------------------------------------------

def parse_pedidos(text: str) -> List[str]:
    """Trata a string de anotação e retorna apenas uma lista de números de pedidos (strings)."""
    if not text:
        return []
    
    text_cleaned = re.sub(r'[^\d]', ' ', text)
    raw_list = re.split(r'\s+', text_cleaned.strip())
    
    pedidos_limpos = {p for p in raw_list if p.isdigit() and len(p) > 0}
    
    return sorted(list(pedidos_limpos))


def calculate_backup_sheet_name() -> str:
    """
    Calcula o nome da aba da semana passada completa (Segunda a Sexta).
    Lógica idêntica ao arquivo principal para manter sincronia.
    """
    today = date.today()
    # Encontra a segunda-feira da semana anterior à atual
    monday_last_week = today - timedelta(days=today.weekday() + 7)
    # Encontra a sexta-feira daquela mesma semana
    friday_last_week = monday_last_week + timedelta(days=4)
    
    return f"{monday_last_week.strftime('%d.%m')} a {friday_last_week.strftime('%d.%m')}"


@st.cache_data
def load_data(sheet_name: str) -> Dict[str, pd.DataFrame]:
    """
    Conecta ao Google Sheets e carrega os dados das abas ALTA, EMERGENCIAL,
    e a aba de Backup calculada dinamicamente.
    """
    data = {}
    
    # 1. Calcula o nome da aba de backup
    BACKUP_SHEET_NAME = calculate_backup_sheet_name()
    ABAS_A_BUSCAR = ABAS_PRINCIPAIS + [BACKUP_SHEET_NAME]
    
    try:
        creds_json = st.secrets.get("google_sheets_service_account")
        
        if creds_json:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, GOOGLE_SHEET_SCOPES)
            gc = gspread.authorize(creds)
        else:
            gc = gspread.service_account(filename="acesso.json")
            
    except Exception as e:
        st.error(f"Erro ao autenticar no Google Sheets. Erro: {e}")
        return None
    
    try:
        sh = gc.open(sheet_name)
        
        for tab in ABAS_A_BUSCAR:
            try:
                worksheet = sh.worksheet(tab)
                list_of_lists = worksheet.get_all_values()
                
                if len(list_of_lists) < 2:
                    continue

                header = [h.strip().upper() for h in list_of_lists[1]]
                data_rows = list_of_lists[2:] 
                df = pd.DataFrame(data_rows, columns=header)
                
                # Normaliza nomes de colunas para busca
                df.columns = [c.strip().upper() for c in df.columns]
                
                df['PEDIDO'] = df['PEDIDO'].astype(str).str.strip()
                data[tab] = df
                
            except gspread.WorksheetNotFound: 
                if tab == BACKUP_SHEET_NAME:
                    st.warning(f"Aviso: Aba de Backup '{BACKUP_SHEET_NAME}' não encontrada.")
                    continue
                st.error(f"Erro: Aba '{tab}' não encontrada.")
                return None
        
        if BACKUP_SHEET_NAME not in LISTA_CARROS_CADASTRO:
             LISTA_CARROS_CADASTRO.insert(1, BACKUP_SHEET_NAME) 
        
        return data
        
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado: {e}")
        return None


# ----------------------------------------------------
# 2. FUNÇÕES DE BUSCA E CONTROLE DE ESTADO (MANTIDAS)
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
    if not pedidos or data is None:
        return []

    results = []
    for pedido in pedidos:
        result = search_pedido(pedido, data, carro_selecionado)
        results.append(result)
        
    return results


def handle_search(data_frames: Dict[str, pd.DataFrame]):
    input_text = st.session_state.backlog_input_text
    carro_selecionado = st.session_state.carro_select
    parsed_pedidos = parse_pedidos(input_text)
    
    if carro_selecionado == LISTA_CARROS_CADASTRO[0]:
        st.session_state['feedback_message'] = "ERRO: Selecione um critério."
        st.rerun()
        return

    if not parsed_pedidos:
        st.session_state['feedback_message'] = "ERRO: Nenhum pedido válido."
        st.rerun()
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
        st.session_state['feedback_message'] = f"✅ Tabela '{carro_selecionado}' processada."
        
    st.session_state.backlog_input_text = ""
    st.rerun()


def remove_last_search():
    if st.session_state['search_history']:
        st.session_state['search_history'].pop()
    st.rerun()


def clear_search_history():
    st.session_state['search_history'] = []
    st.rerun()


# ----------------------------------------------------
# 3. FUNÇÕES DE ESTILO E EXIBIÇÃO (MANTIDAS)
# ----------------------------------------------------

def apply_text_color_by_status(row):
    style_list = []
    is_error = row['Status'] == "Pedido Não Encontrado"
    for col in row.index:
        if is_error:
            style_list.append('color: red; font-weight: bold;' if col in ['Pedido', 'Status'] else 'color: grey;') 
        else:
            style_list.append('color: green; font-weight: bold;' if col in ['Pedido', 'Status'] else None)
    return style_list


def display_search_history():
    history = st.session_state['search_history']
    if not history:
        st.info("Histórico vazio.")
        return

    for df in history:
        carro_foco = df['Carro Foco'].iloc[0]
        df['Sort_Key'] = df['Status'].apply(lambda x: 1 if x == "Pedido Não Encontrado" else 0)
        df_sorted = df.sort_values(by='Sort_Key').drop(columns=['Sort_Key'])
        
        df_display = df_sorted.rename(columns={COLUNA_CARRO: 'Carro Planilha'}).drop(columns=['Carro Foco'])
        column_order = ['Pedido', 'Origem', 'Data', 'Carro Planilha', 'Status']
        
        st.markdown(f"### 🚗 CRITÉRIO: {carro_foco}")
        st.dataframe(df_display[column_order].style.apply(apply_text_color_by_status, axis=1), use_container_width=True, hide_index=True)
        st.markdown("---")


# ----------------------------------------------------
# 4. FUNÇÃO PRINCIPAL (APP)
# ----------------------------------------------------

def app():
    initialize_state()
    st.title("🔍 BACKLOG: Pesquisa Rápida de Pedidos")

    try:
        BACKUP_SHEET_NAME = calculate_backup_sheet_name()
        st.info(f"Aba de Backup sendo rastreada: **{BACKUP_SHEET_NAME}**")
    except Exception:
        pass 
        
    if st.session_state.get('feedback_message'):
        st.write(st.session_state['feedback_message'])
        st.session_state['feedback_message'] = None 

    with st.spinner("Carregando dados..."):
        data_frames = load_data(PLANILHA_NOME)
    
    if data_frames is None: st.stop()
    
    col1, col2 = st.columns([0.6, 0.4])
    with col1:
        st.text_area("Cole os pedidos:", height=100, key='backlog_input_text')
    
    with col2:
        st.selectbox("Selecione o Critério:", options=LISTA_CARROS_CADASTRO, key='carro_select')
        st.button("BUSCAR INFORMAÇÕES", type="primary", use_container_width=True, on_click=handle_search, args=(data_frames,))
    
    st.divider()
    c1, c2 = st.columns(2)
    c1.button("⬅️ REMOVER ÚLTIMA", use_container_width=True, on_click=remove_last_search)
    c2.button("❌ LIMPAR TUDO", use_container_width=True, on_click=clear_search_history)
    
    display_search_history()

if __name__ == '__main__':
    app()