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

# --- CONFIGURAÇÃO DE ACESSO E LIMITES ---
st.set_page_config(page_title="Sistema Saritur", layout="wide")

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = "acesso.json" 
SPREADSHEET_ID = "1X9trwwqVCwPXY2_O667WJcOR4CHNYbBjJDVsrYNZSgc"     
LIMITE_ALTA_DIARIO = 180000.00
LIMITE_EMERG_DIARIO = 15000.00

# MAPA DE COLUNAS
COL_PEDIDO, COL_STATUS, COL_DATA = "PEDIDO", "STATUS", "DATA"
COL_VALOR, COL_UNIDADE = "VALOR", "UNIDADE"
COL_CARRO, COL_FORNECEDOR = "CARRO | UTILIZAÇÃO", "FORNECEDOR"

# --- FUNÇÕES DE FORMATAÇÃO ---
def valor_brasileiro(valor):
    if pd.isna(valor) or valor is None: return 0.0
    s = str(valor).strip()
    s = re.sub(r"[R$\s\.]", "", s).replace(",", ".")
    try: return float(s)
    except: return 0.0

def br_money(valor):
    if pd.isna(valor): return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def safe_load(df):
    df = df.copy()
    if COL_DATA in df.columns:
        df[COL_DATA] = pd.to_datetime(df[COL_DATA], dayfirst=True, errors="coerce").dt.normalize()
    if COL_VALOR in df.columns:
        df[COL_VALOR] = df[COL_VALOR].apply(valor_brasileiro)
    return df[pd.notna(df[COL_DATA])].copy() if COL_DATA in df.columns else df

# --- LÓGICA DE BACKUP (Semana Anterior) ---
def calculate_backup_sheet_name() -> str:
    today = date.today()
    # Volta para a segunda-feira da semana passada
    monday_last_week = today - timedelta(days=today.weekday() + 7)
    friday_last_week = monday_last_week + timedelta(days=4)
    return f"{monday_last_week.strftime('%d.%m')} a {friday_last_week.strftime('%d.%m')}"

# --- CARREGAMENTO DE DADOS ---
@st.cache_data(ttl=300)
def load_sheets(today_str):
    try:
        creds_json = st.secrets.get("google_sheets_service_account")
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(creds_json), SCOPE) if creds_json else ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
        sh = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error(f"Erro de autenticação: {e}"); return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    def get_df(name):
        try:
            data = sh.worksheet(name).get_all_values()
            if len(data) < 2: return pd.DataFrame()
            headers = [h.strip().upper() for h in data[1]]
            df = pd.DataFrame(data[2:], columns=headers)
            return safe_load(df)
        except: return pd.DataFrame()

    return get_df("ALTA"), get_df("EMERGENCIAL"), get_df(calculate_backup_sheet_name())

# --- SIDEBAR E PROCESSAMENTO ---
st.sidebar.image("saritur1.png")
SAO_PAULO_TZ = pytz.timezone('America/Sao_Paulo')
hoje_tz = datetime.datetime.now(SAO_PAULO_TZ).date()

if st.sidebar.button("🔄 Recarregar Dados"):
    st.cache_data.clear(); st.rerun()

df_alta, df_emerg, df_backup = load_sheets(hoje_tz.isoformat())

# Filtro Período
st.sidebar.markdown("---")
st.sidebar.header("📊 Filtro por período")
start_d = st.sidebar.date_input("Início", hoje_tz - timedelta(days=30))
end_d = st.sidebar.date_input("Fim", hoje_tz)

def sum_btn(df, s, e):
    if df.empty: return 0.0
    return df[(df[COL_DATA].dt.date >= s) & (df[COL_DATA].dt.date <= e)][COL_VALOR].sum()

st.sidebar.success(f"ALTA: {br_money(sum_btn(df_alta, start_d, end_d))}")
st.sidebar.success(f"EMERG: {br_money(sum_btn(df_emerg, start_d, end_d))}")

# Alertas Corrigidos
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔔 Alertas de Status - ALTA")
data_amanha = hoje_tz + timedelta(days=1)
if not df_alta.empty:
    df_alta["SC"] = df_alta[COL_STATUS].astype(str).str.strip().str.upper()
    df_f = df_alta[df_alta[COL_DATA].dt.date >= data_amanha]
    df_a = df_alta[df_alta[COL_DATA].dt.date == data_amanha]
    
    for status, msg, icon in [("NÃO APROVADA", "solicitações NÃO APROVADAS", "🚨"), ("APROVADA", "solicitações APROVADAS", "⚠️")]:
        tot, amanha = len(df_f[df_f["SC"] == status]), len(df_a[df_a["SC"] == status])
        if status == "NÃO APROVADA": st.sidebar.error(f"Existem **{tot}** {msg} futuras, sendo **{amanha}** para amanhã.", icon=icon)
        else: st.sidebar.warning(f"Existem **{tot}** {msg} futuras, sendo **{amanha}** para amanhã.", icon=icon)

# --- CORPO PRINCIPAL ---
st.title("Sistema de Consulta de Pedidos")
st.info(f"Aba de Backup: **{calculate_backup_sheet_name()}**")

# 1. Busca por Pedido
st.subheader("🔍 Situação da Solicitação")
p_in = st.text_input("Número do pedido:").strip().upper()
if p_in:
    for df, nome in [(df_alta, "ALTA"), (df_emerg, "EMERGENCIAL"), (df_backup, calculate_backup_sheet_name())]:
        res = df[df[COL_PEDIDO].astype(str).str.upper() == p_in] if not df.empty else pd.DataFrame()
        if not res.empty:
            r = res.iloc[0]
            st.success(f"Encontrado em: {nome}")
            st.write(f"📅 **Data:** {r[COL_DATA].strftime('%d/%m/%Y')} | **Status:** {r[COL_STATUS]} | **Valor:** {br_money(r[COL_VALOR])}")
            st.write(f"🏢 **Unidade:** {r[COL_UNIDADE]} | 🚌 **Carro:** {r[COL_CARRO]} | 📦 **Fornecedor:** {r[COL_FORNECEDOR]}")
            st.divider()

# 2. Busca por Data
st.subheader("📅 Pedidos por data")
d_busca = st.date_input("Selecione a data:", key="db")
if d_busca:
    dt = pd.to_datetime(d_busca).normalize()
    f_alta, f_emerg = df_alta[df_alta[COL_DATA] == dt], df_emerg[df_emerg[COL_DATA] == dt]
    v_a, v_e = f_alta[COL_VALOR].sum(), f_emerg[COL_VALOR].sum()

    col1, col2 = st.columns(2)
    col1.metric("Gasto ALTA", br_money(v_a), delta=f"Limite {br_money(LIMITE_ALTA_DIARIO)}", delta_color="inverse")
    col2.metric("Gasto EMERG", br_money(v_e), delta=f"Limite {br_money(LIMITE_EMERG_DIARIO)}", delta_color="inverse")
    st.metric("💰 TOTAL DO DIA", br_money(v_a + v_e))

    for f_df, t, cor in [(f_alta, "ALTA", "blue"), (f_emerg, "EMERG", "red")]:
        if not f_df.empty:
            st.write(f"### 📋 {t}")
            st.dataframe(f_df[[COL_PEDIDO, COL_VALOR, COL_STATUS, COL_UNIDADE, COL_FORNECEDOR]], hide_index=True)
            top = f_df.sort_values(by=COL_VALOR, ascending=False).head(10)
            st.altair_chart(alt.Chart(top).mark_bar(color=cor).encode(x=alt.X(COL_VALOR, title='Valor'), y=alt.Y(COL_PEDIDO, sort='-x'), tooltip=[COL_PEDIDO, COL_VALOR]), use_container_width=True)

    # Gasto por Unidade (Status PEDIDO)
    comb = pd.concat([f_alta, f_emerg])
    if not comb.empty:
        unid = comb[comb[COL_STATUS].astype(str).str.upper() == "PEDIDO"].groupby(COL_UNIDADE)[COL_VALOR].sum().sort_values(ascending=False).reset_index()
        if not unid.empty:
            st.write("### 🏢 Gasto por Unidade (Status: PEDIDO)")
            for _, r in unid.iterrows(): st.markdown(f"**{r[COL_UNIDADE]}**: {br_money(r[COL_VALOR])}")