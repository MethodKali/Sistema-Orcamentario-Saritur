import streamlit as st
import re
import pandas as pd
import gspread 
from typing import List, Dict, Union
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, timedelta

# --- CONFIGURAÇÃO ---
PLANILHA_NOME = "Controle Orçamentário Diário V2" 
COLUNA_CARRO = 'CARRO | UTILIZAÇÃO' 

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

def calculate_backup_sheet_name():
    """Calcula o nome da aba de backup da semana anterior (Ex: 06.01 a 10.01)"""
    today = date.today()
    monday_last_week = today - timedelta(days=today.weekday() + 7)
    friday_last_week = monday_last_week + timedelta(days=4)
    return f"{monday_last_week.strftime('%d.%m')} a {friday_last_week.strftime('%d.%m')}"

def fix_col_names(df):
    """Remove duplicados e padroniza nomes de colunas"""
    if df.empty: return df
    df.columns = [str(c).strip().upper() for c in df.columns]
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique():
        cols[cols == dup] = [f"{dup}_{i}" if i != 0 else dup for i in range(sum(cols == dup))]
    df.columns = cols
    return df

def parse_pedidos(text: str) -> List[str]:
    if not text: return []
    text_cleaned = re.sub(r'[^\d]', ' ', text)
    raw_list = re.split(r'\s+', text_cleaned.strip())
    pedidos_limpos = {p for p in raw_list if p.isdigit() and len(p) > 0}
    return sorted(list(pedidos_limpos))

@st.cache_data(ttl=600)
def load_data(sheet_name: str) -> Dict[str, pd.DataFrame]:
    data = {}
    aba_backup = calculate_backup_sheet_name()
    # Apenas as abas que existem de fato
    abas_reais = ['PROGRAMAÇÃO DIÁRIA', 'EMERGENCIAL', aba_backup]
    
    try:
        creds_json = st.secrets.get("google_sheets_service_account")
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, GOOGLE_SHEET_SCOPES)
        gc = gspread.authorize(creds)
        sh = gc.open(sheet_name)
        
        for tab in abas_reais:
            try:
                worksheet = sh.worksheet(tab)
                list_of_lists = worksheet.get_all_values()
                if len(list_of_lists) < 2: continue
                
                # Cabeçalho na linha 2
                headers = [h.strip().upper() for h in list_of_lists[1]]
                
                # Fallback se a linha 2 estiver vazia
                if not any(h in headers for h in ["PEDIDO", "DATA", "STATUS"]):
                    headers = [h.strip().upper() for h in list_of_lists[0]]
                    df = pd.DataFrame(list_of_lists[1:], columns=headers)
                else:
                    df = pd.DataFrame(list_of_lists[2:], columns=headers)
                
                df = fix_col_names(df)
                if 'PEDIDO' in df.columns:
                    df['PEDIDO'] = df['PEDIDO'].astype(str).str.strip()
                data[tab] = df
            except:
                continue
        return data
    except Exception as e:
        st.error(f"Erro ao acessar planilha: {e}")
        return None

# ----------------------------------------------------
# 2. LÓGICA DE BUSCA
# ----------------------------------------------------

def search_pedido(pedido: str, data: Dict[str, pd.DataFrame], carro_selecionado: str) -> Dict[str, str]:
    res = {
        "Pedido": pedido, "Origem": "-", "Data": "-", 
        "Carro/Unidade": "-", "Status": "Pedido Não Encontrado", 
        "Carro Foco": carro_selecionado
    }

    for sheet_name, df in data.items():
        if 'PEDIDO' not in df.columns: continue
        match = df[df['PEDIDO'] == pedido]
        if not match.empty:
            row = match.iloc[0]
            # Busca por colunas que identifiquem o carro ou unidade
            col_carro_real = next((c for c in df.columns if any(x in c for x in ["CARRO", "UNIDADE"])), "CARRO")
            
            res.update({
                "Origem": sheet_name,
                "Data": row.get('DATA', '-'),
                "Carro/Unidade": row.get(col_carro_real, '-'),
                "Status": str(row.get('STATUS', '-')).strip()
            })
            return res
    return res

# ----------------------------------------------------
# 3. INTERFACE (APP)
# ----------------------------------------------------

def app():
    if 'search_history' not in st.session_state:
        st.session_state['search_history'] = []
    if 'input_reset_counter' not in st.session_state:
        st.session_state.input_reset_counter = 0

    st.title("🔍 Pesquisa em Backlog e Operacional")
    
    with st.spinner("Carregando bases vigentes..."):
        data_frames = load_data(PLANILHA_NOME)
    
    if not data_frames: st.stop()

    current_key = f"txt_{st.session_state.input_reset_counter}"
    col1, col2 = st.columns([0.6, 0.4])
    
    with col1:
        texto = st.text_area("Cole os pedidos aqui:", height=130, key=current_key)
    
    with col2:
        carro_sel = st.selectbox("Vincular ao Carro:", options=LISTA_CARROS_CADASTRO)
        if st.button("EXECUTAR BUSCA", type="primary", use_container_width=True):
            pedidos = parse_pedidos(texto)
            if not pedidos:
                st.error("Nenhum pedido detectado.")
            elif carro_sel == LISTA_CARROS_CADASTRO[0]:
                st.error("Selecione um carro.")
            else:
                resultados = [search_pedido(p, data_frames, carro_sel) for p in pedidos]
                new_df = pd.DataFrame(resultados)
                
                # Atualiza histórico
                hist = st.session_state['search_history']
                idx = next((i for i, d in enumerate(hist) if d['Carro Foco'].iloc[0] == carro_sel), None)
                if idx is not None: hist[idx] = new_df
                else: hist.append(new_df)
                
                st.session_state['search_history'] = hist
                st.session_state.input_reset_counter += 1
                st.rerun()

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("⬅️ REMOVER ÚLTIMA"):
        if st.session_state['search_history']: st.session_state['search_history'].pop()
        st.rerun()
    if c2.button("❌ LIMPAR TUDO"):
        st.session_state['search_history'] = []
        st.rerun()

    for df in reversed(st.session_state['search_history']):
        carro_foco = df['Carro Foco'].iloc[0]
        st.markdown(f"### 🚗 CRITÉRIO: {carro_foco}")
        
        def color_status(val):
            if val == "Pedido Não Encontrado": return 'color: #FF4B4B; font-weight: bold'
            return 'color: #008000; font-weight: bold'

        display_df = df.drop(columns=['Carro Foco'])
        st.dataframe(
            display_df.style.map(color_status, subset=['Status']),
            use_container_width=True,
            hide_index=True
        )

if __name__ == '__main__':
    app()