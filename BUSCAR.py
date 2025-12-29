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

# ----------------------------------------------------------------------
# MAPA DE COLUNAS
# ----------------------------------------------------------------------
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
    gc = None
    try:
        creds_json = st.secrets.get("google_sheets_service_account")
        if creds_json:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(creds_json), SCOPE)
            gc = gspread.authorize(creds)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
            gc = gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro ao autenticar credenciais. Erro: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error(f"Erro ao abrir a planilha. Verifique o ID e as credenciais. Erro: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    def load_sheet_as_df(sheet_name):
        try:
            data = sh.worksheet(sheet_name).get_all_values() 
            raw_headers = [h.strip().upper() for h in data[1]]
            seen_headers = {}
            unique_headers = []
            for header in raw_headers:
                clean_header = header if header else ""
                if clean_header in seen_headers:
                    seen_headers[clean_header] += 1
                    unique_headers.append(f"{clean_header}_{seen_headers[clean_header]}") 
                else:
                    seen_headers[clean_header] = 0
                    unique_headers.append(clean_header)
            df = pd.DataFrame(data[2:], columns=unique_headers)
            df.replace('', pd.NA, inplace=True)
            df.dropna(how='all', inplace=True) 
            return safe_load(df) 
        except gspread.WorksheetNotFound:
            return pd.DataFrame()
        except Exception as e:
            st.error(f"Erro ao carregar aba {sheet_name}. Erro: {e}")
            return pd.DataFrame()

    df_alta = load_sheet_as_df("ALTA")
    df_emerg = load_sheet_as_df("EMERGENCIAL")
    BACKUP_SHEET_NAME = calculate_backup_sheet_name()
    df_backup = load_sheet_as_df(BACKUP_SHEET_NAME)
    return df_alta, df_emerg, df_backup

# --- FUNÇÃO DE SOMA ATUALIZADA COM FILTRO DE STATUS ---
def sum_between(df, start, end, status_filtro=None):
    if df.empty or COL_DATA not in df.columns or COL_VALOR not in df.columns:
        return 0.0
    
    end_date_normalized = pd.to_datetime(end).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    mask = (df[COL_DATA] >= pd.to_datetime(start).normalize()) & (df[COL_DATA] <= end_date_normalized)
    
    df_temp = df.loc[mask].copy()
    
    # Se status_filtro for fornecido, filtra apenas os registros correspondentes
    if status_filtro and COL_STATUS in df_temp.columns:
        df_temp = df_temp[df_temp[COL_STATUS].astype(str).str.strip().str.upper() == status_filtro.upper()]
        
    return df_temp[COL_VALOR].sum()

# -----------------------
# SIDEBAR
# -----------------------
st.sidebar.image("saritur1.png")

SAO_PAULO_TZ = pytz.timezone('America/Sao_Paulo')
today_date_tz = datetime.datetime.now(SAO_PAULO_TZ).date()
today_date_str = today_date_tz.isoformat() 

if st.sidebar.button("🔄 Recarregar Dados"):
    st.cache_data.clear()
    st.success("Cache limpo! Recarregando dados...")
    
df_alta, df_emerg, df_backup = load_sheets(today_date_str)

st.sidebar.markdown("---") 
st.sidebar.header("📊 Filtro por período")

start_date = st.sidebar.date_input("Data inicial", datetime.date.today() - datetime.timedelta(days=30))
end_date = st.sidebar.date_input("Data final", datetime.date.today())

# APLICAÇÃO DA REGRA: ALTA apenas 'PEDIDO' | EMERGENCIAL soma tudo
total_alta = sum_between(df_alta, start_date, end_date, status_filtro="PEDIDO")
total_emerg = sum_between(df_emerg, start_date, end_date)

st.sidebar.markdown("### 💵 Totais filtrados:")
st.sidebar.success(f"ALTA (Status: PEDIDO): {br_money(total_alta)}") 
st.sidebar.success(f"EMERGENCIAL: {br_money(total_emerg)}")

# -----------------------
# ALERTAS DE STATUS (ALTA)
# -----------------------
st.sidebar.markdown("---") 
st.sidebar.markdown("### 🔔 Alertas de Status - ALTA")

hoje = pd.to_datetime(today_date_tz).normalize() 
data_amanha = hoje + datetime.timedelta(days=1)
data_amanha_br = data_amanha.strftime('%d/%m') 

if COL_STATUS in df_alta.columns and COL_DATA in df_alta.columns:
    df_alta["STATUS_CLEAN"] = df_alta[COL_STATUS].astype(str).str.strip().str.upper()
    df_alta['DATA_ONLY'] = df_alta[COL_DATA].dt.normalize()

    df_base_amanha = df_alta[(df_alta['DATA_ONLY'] == data_amanha) & (pd.notna(df_alta['DATA_ONLY']))].copy()
    df_base_total = df_alta[(df_alta['DATA_ONLY'] >= data_amanha) & (pd.notna(df_alta['DATA_ONLY']))].copy()
    
    qtde_nao_aprovada_amanha = df_base_amanha[df_base_amanha["STATUS_CLEAN"] == "NÃO APROVADA"].shape[0]
    qtde_nao_aprovada_total = df_base_total[df_base_total["STATUS_CLEAN"] == "NÃO APROVADA"].shape[0] 
    qtde_aprovada_amanha = df_base_amanha[df_base_amanha["STATUS_CLEAN"] == "APROVADA"].shape[0]
    qtde_aprovada_total = df_base_total[df_base_total["STATUS_CLEAN"] == "APROVADA"].shape[0] 

    st.sidebar.error(f"Existem **{qtde_nao_aprovada_total}** solicitações NÃO APROVADAS futuras, sendo **{qtde_nao_aprovada_amanha}** para amanhã ({data_amanha_br}).", icon="🚨")
    st.sidebar.warning(f"Existem **{qtde_aprovada_total}** solicitações APROVADAS futuras, sendo **{qtde_aprovada_amanha}** para amanhã ({data_amanha_br}).", icon="⚠️")

# -----------------------
# CORPO PRINCIPAL
# -----------------------
st.title("Sistema de Consulta de Pedidos – *ALTA*, *EMERGENCIAL* e *BACKUP*")

try:
    BACKUP_SHEET_NAME = calculate_backup_sheet_name()
    st.info(f"Aba de Backup de Emergencial sendo rastreada: **{BACKUP_SHEET_NAME}**")
except Exception: pass 

## 1) Pesquisa por Número de Pedido
st.subheader("🔍 Situação da Solicitação/Pedido")
pedido_input = st.text_input("Digite o número do pedido:")

def show_result(row, sheet_name):
    st.write(f"📁 **Origem:** {sheet_name}") 
    st.write(f"📅 **Previsão de pagamento:** {row.get(COL_DATA).strftime('%d/%m/%Y')}") 
    st.write(f"📌 **Status:** {row.get(COL_STATUS)}")
    st.write(f"💰 **Valor:** {br_money(row.get(COL_VALOR))}")
    st.write(f"🏢 **Unidade solicitante:** {row.get(COL_UNIDADE)}")
    st.write(f"🚌 **Carro/Utilização:** {row.get(COL_CARRO)}")
    st.write(f"📦 **Fornecedor:** {row.get(COL_FORNECEDOR)}")
    st.write("---")

if pedido_input:
    pid = pedido_input.strip().upper() 
    def search_df(df, pid):
        if COL_PEDIDO in df.columns and not df.empty:
            return df[df[COL_PEDIDO].astype(str).str.strip().str.upper() == pid]
        return pd.DataFrame()

    res_alta = search_df(df_alta, pid)
    res_emerg = search_df(df_emerg, pid)
    res_backup = search_df(df_backup, pid) 

    if res_alta.empty and res_emerg.empty and res_backup.empty:
        st.warning(f"❌ Pedido '{pedido_input}' não encontrado.")
    else:
        if not res_alta.empty: show_result(res_alta.iloc[0], "ALTA")
        if not res_emerg.empty: show_result(res_emerg.iloc[0], "EMERGENCIAL")
        if not res_backup.empty: show_result(res_backup.iloc[0], BACKUP_SHEET_NAME)

## 2) Pesquisa por Data
st.subheader("📅 Buscar pedidos por data")
data_busca = st.date_input("Selecione a data do pedido:", key="data_busca_2")  

if data_busca:
    data_busca_dt = pd.to_datetime(data_busca).normalize()  

    mask_alta = pd.notna(df_alta[COL_DATA]) & (df_alta[COL_DATA] == data_busca_dt)
    alta_filtrado = df_alta[mask_alta].copy()
    
    mask_emerg = pd.notna(df_emerg[COL_DATA]) & (df_emerg[COL_DATA] == data_busca_dt)
    emerg_filtrado = df_emerg[mask_emerg].copy()
    
    # --- CÁLCULO DOS TOTAIS DO DIA COM A NOVA REGRA ---
    if not alta_filtrado.empty and COL_STATUS in alta_filtrado.columns:
        total_valor_dia_alta = alta_filtrado[
            alta_filtrado[COL_STATUS].astype(str).str.strip().str.upper() == "PEDIDO"
        ][COL_VALOR].sum()
    else:
        total_valor_dia_alta = 0.0

    total_valor_dia_emerg = emerg_filtrado[COL_VALOR].sum()
    total_geral = total_valor_dia_alta + total_valor_dia_emerg

    st.markdown(f"### 💰 Gastos Diários em {data_busca_dt.strftime('%d/%m/%Y')}")
    st.caption("Nota: O valor da ALTA contabiliza apenas registros com status 'PEDIDO'.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**🟦 ALTA** (Limite: {br_money(LIMITE_ALTA_DIARIO)})")
        st.metric(label="Gasto (PEDIDO)", value=br_money(total_valor_dia_alta))
        if total_valor_dia_alta > LIMITE_ALTA_DIARIO: st.warning("🚨 **Limite excedido.**")
        st.info(f"Total registros: {len(alta_filtrado)}")

    with col2:
        st.markdown(f"**🟥 EMERGENCIAL** (Limite: {br_money(LIMITE_EMERG_DIARIO)})")
        st.metric(label="Gasto EMERGENCIAL", value=br_money(total_valor_dia_emerg))
        if total_valor_dia_emerg > LIMITE_EMERG_DIARIO: st.warning("🚨 **Limite excedido.**")
        st.info(f"Pedidos encontrados: {len(emerg_filtrado)}")
        
    st.metric(label="💰 TOTAL GERAL DO DIA", value=br_money(total_geral))
    st.markdown("---")

    # Exibição das Tabelas e Gráficos (Mantidos conforme original)
    COLS_BASE = [COL_PEDIDO, COL_STATUS, COL_UNIDADE, COL_CARRO, COL_FORNECEDOR]

    if not alta_filtrado.empty:
        st.write("### 🟦 Pedidos da ALTA")
        alta_show = alta_filtrado.copy()
        alta_show[COL_VALOR] = alta_show[COL_VALOR].apply(br_money)
        st.dataframe(alta_show[[COL_PEDIDO, COL_VALOR] + [c for c in COLS_BASE if c != COL_PEDIDO]], hide_index=True)

    if not emerg_filtrado.empty:
        st.write("### 🟥 Pedidos da EMERGENCIAL")
        emerg_show = emerg_filtrado.copy()
        emerg_show[COL_VALOR] = emerg_show[COL_VALOR].apply(br_money)
        st.dataframe(emerg_show[[COL_PEDIDO, COL_VALOR] + [c for c in COLS_BASE if c != COL_PEDIDO]], hide_index=True)

    # Gasto por Unidade (Apenas Status PEDIDO)
    df_combinado = pd.concat([alta_filtrado, emerg_filtrado], ignore_index=True)
    if not df_combinado.empty:
        df_unid = df_combinado[df_combinado[COL_STATUS].astype(str).str.strip().str.upper() == "PEDIDO"].copy()
        if not df_unid.empty:
            st.markdown("---")
            st.subheader(f"🏢 Gasto por Unidade (Status: PEDIDO) em {data_busca_dt.strftime('%d/%m/%Y')}")
            gastos_unid = df_unid.groupby(COL_UNIDADE)[COL_VALOR].sum().reset_index().sort_values(by=COL_VALOR, ascending=False)
            for _, row in gastos_unid.iterrows():
                st.markdown(f"<div style='display: flex; justify-content: space-between;'><span>{row[COL_UNIDADE]}</span><b>{br_money(row[COL_VALOR])}</b></div>", unsafe_allow_html=True)
                st.markdown(
                    f"""<div style="display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #282828;">
                        <span style='font-size: 15px; font-weight: 500; color: white;'>{row[COL_UNIDADE]}</span>
                        <span style='font-size: 15px; font-weight: 500; color: #AAAAAA;'>{br_money(row[COL_VALOR])}</span>
                    </div>""", unsafe_allow_html=True
                ) 
        else:
            st.info(f"Nenhum pedido com status 'PEDIDO' encontrado para calcular gastos por unidade em {data_busca_dt.strftime('%d/%m/%Y')}.")


    else:
        st.info(f"Nenhum pedido encontrado para calcular gastos por unidade em {data_busca_dt.strftime('%d/%m/%Y')}.")