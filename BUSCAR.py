import streamlit as st
import pandas as pd
import datetime
import re
import altair as alt
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, timedelta
import calendar 
import json

# --- CONFIGURAÇÃO DE ACESSO E LIMITES ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
CREDS_FILE = "acesso.json" 
SPREADSHEET_ID = "1X9trwwqVCwPXY2_O667WJcOR4CHNYbBjJDVsrYNZSgc"     
LIMITE_ALTA_DIARIO = 180000.00
LIMITE_EMERG_DIARIO = 15000.00

# MAPA DE COLUNAS
COL_PEDIDO = "PEDIDO"
COL_STATUS = "STATUS"
COL_DATA = "DATA"
COL_VALOR = "VALOR"
COL_UNIDADE = "UNIDADE"
COL_CARRO = "CARRO | UTILIZAÇÃO"
COL_FORNECEDOR = "FORNECEDOR"

# -----------------------
# FUNÇÕES DE VALOR E FORMATAÇÃO
# -----------------------

def valor_brasileiro(valor):
    if pd.isna(valor) or valor is None:
        return 0.0
    s = str(valor).strip()
    s = re.sub(r"[R$\s\.]", "", s)
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

def br_money(valor):
    if pd.isna(valor):
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def safe_load(df):
    df = df.copy()
    date_cols_to_process = [c for c in [COL_DATA] if c in df.columns]
    for col in date_cols_to_process:
        df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce") 
        df[col] = df[col].dt.normalize()  
    if COL_VALOR in df.columns:
        df[COL_VALOR] = df[COL_VALOR].apply(valor_brasileiro)
    if COL_DATA in df.columns:
        df = df[pd.notna(df[COL_DATA])].copy()
    return df

def calculate_backup_sheet_name() -> str:
    today = date.today()
    monday_last_week = today - timedelta(days=today.weekday() + 7)
    friday_last_week = monday_last_week + timedelta(days=4)
    return f"{monday_last_week.strftime('%d.%m')} a {friday_last_week.strftime('%d.%m')}"

# -----------------------
# FUNÇÃO DE CARREGAMENTO DE DADOS
# -----------------------

@st.cache_data(ttl=300)
def load_sheets(today_str):
    try:
        creds_json = st.secrets.get("google_sheets_service_account")
        if creds_json:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(creds_json), SCOPE)
            gc = gspread.authorize(creds)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
            gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    def load_sheet_as_df(sheet_name):
        try:
            data = sh.worksheet(sheet_name).get_all_values() 
            if len(data) < 2: return pd.DataFrame()
            raw_headers = [h.strip().upper() for h in data[1]]
            df = pd.DataFrame(data[2:], columns=raw_headers)
            df.columns = [c if c else f"COL_{i}" for i, c in enumerate(df.columns)]
            df.replace('', pd.NA, inplace=True)
            df.dropna(how='all', inplace=True) 
            return safe_load(df) 
        except:
            return pd.DataFrame()

    df_alta = load_sheet_as_df("ALTA")
    df_emerg = load_sheet_as_df("EMERGENCIAL")
    df_geral_emerg = load_sheet_as_df("GERAL_EMERGENCIAL")
    df_backup = load_sheet_as_df(calculate_backup_sheet_name())

    return df_alta, df_emerg, df_backup, df_geral_emerg

def sum_between(df, start, end):
    if df.empty or COL_DATA not in df.columns or COL_VALOR not in df.columns:
        return 0.0
    mask = (df[COL_DATA] >= pd.to_datetime(start).normalize()) & (df[COL_DATA] <= pd.to_datetime(end).normalize())
    return df.loc[mask, COL_VALOR].sum()

# -----------------------
# SIDEBAR E CARREGAMENTO
# -----------------------
st.sidebar.image("saritur1.png")
SAO_PAULO_TZ = pytz.timezone('America/Sao_Paulo')
today_date_tz = datetime.datetime.now(SAO_PAULO_TZ).date()

if 'input_reset_counter' not in st.session_state:
    st.session_state.input_reset_counter = 0

df_alta, df_emerg, df_backup, df_geral_emerg = load_sheets(today_date_tz.isoformat())

# FILTROS
st.sidebar.markdown("---") 
st.sidebar.header("📊 Filtro por período")
start_date = st.sidebar.date_input("Data inicial", date.today() - timedelta(days=30))
end_date = st.sidebar.date_input("Data final", date.today())

total_alta = sum_between(df_alta, start_date, end_date)
total_emerg = sum_between(df_emerg, start_date, end_date) + sum_between(df_geral_emerg, start_date, end_date)

st.sidebar.markdown("### 💵 Totais filtrados:")
st.sidebar.success(f"ALTA: {br_money(total_alta)}") 
st.sidebar.success(f"EMERGENCIAIS: {br_money(total_emerg)}")

# -----------------------
# CORPO PRINCIPAL
# -----------------------

st.title("Sistema de Consulta de Pedidos – Saritur")

BACKUP_SHEET_NAME = calculate_backup_sheet_name()
st.info(f"Rastreando: ALTA, EMERGENCIAL, GERAL_EMERGENCIAL e BACKUP ({BACKUP_SHEET_NAME})")

st.subheader("🔍 Situação da Solicitação/Pedido")

# APLICAÇÃO DA LÓGICA DE RESET (Igual ao Backlog)
current_search_key = f"pedido_input_{st.session_state.input_reset_counter}"
col_search, col_btn = st.columns([0.8, 0.2])

with col_search:
    pedido_input = st.text_input("Digite o número do pedido:", key=current_search_key)

def show_result(row, sheet_name):
    with st.expander(f"Ver detalhes - {sheet_name}", expanded=True):
        st.write(f"📁 **Origem:** {sheet_name}") 
        st.write(f"📅 **Previsão:** {row.get(COL_DATA).strftime('%d/%m/%Y') if pd.notna(row.get(COL_DATA)) else 'N/A'}") 
        st.write(f"📌 **Status:** {row.get(COL_STATUS)}")
        st.write(f"💰 **Valor:** {br_money(row.get(COL_VALOR))}")
        st.write(f"🚌 **Carro:** {row.get(COL_CARRO)}")
        st.write("---")

if pedido_input:
    pid = pedido_input.strip().upper() 
    
    def search_df(df, pid):
        if not df.empty and COL_PEDIDO in df.columns:
            return df[df[COL_PEDIDO].astype(str).str.strip().str.upper() == pid]
        return pd.DataFrame()

    res_alta = search_df(df_alta, pid)
    res_emerg = search_df(df_emerg, pid)
    res_geral = search_df(df_geral_emerg, pid)
    res_backup = search_df(df_backup, pid) 

    found = False
    for res, label in [(res_alta, "ALTA"), (res_emerg, "EMERGENCIAL"), (res_geral, "GERAL_EMERGENCIAL"), (res_backup, f"BACKUP {BACKUP_SHEET_NAME}")]:
        if not res.empty:
            st.success(f"✅ Pedido encontrado na aba {label}")
            show_result(res.iloc[0], label)
            found = True
    
    if not found:
        st.error(f"❌ Pedido '{pid}' não encontrado.")

    if st.button("Limpar Busca"):
        st.session_state.input_reset_counter += 1
        st.rerun()

# --- CONTINUAÇÃO DA LÓGICA DE DATAS (MANTIDA E ADAPTADA) ---
st.markdown("---")
st.subheader("📅 Buscar pedidos por data")
data_busca = st.date_input("Selecione a data:", key="data_busca_relatorio")  

if data_busca:
    dt = pd.to_datetime(data_busca).normalize()
    
    # Soma Emergencial + Geral Emergencial para o gráfico diário
    emerg_dia = pd.concat([df_emerg, df_geral_emerg])
    alta_dia = df_alta[df_alta[COL_DATA] == dt] if not df_alta.empty else pd.DataFrame()
    emerg_dia_filt = emerg_dia[emerg_dia[COL_DATA] == dt] if not emerg_dia.empty else pd.DataFrame()

    col_a, col_b = st.columns(2)
    col_a.metric("Gasto ALTA", br_money(alta_dia[COL_VALOR].sum()))
    col_b.metric("Gasto EMERGENCIAL", br_money(emerg_dia_filt[COL_VALOR].sum()))