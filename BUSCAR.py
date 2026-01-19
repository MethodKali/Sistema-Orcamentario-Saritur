import streamlit as st
import pandas as pd
import datetime
import re
import altair as alt
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, timedelta

# --- CONFIGURAÇÃO DE ACESSO E LIMITES ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = "acesso.json" 
SPREADSHEET_ID = "1X9trwwqVCwPXY2_O667WJcOR4CHNYbBjJDVsrYNZSgc"      
LIMITE_ALTA_DIARIO = 180000.00
LIMITE_EMERG_DIARIO = 15000.00

# MAPA DE COLUNAS
COL_PEDIDO, COL_STATUS, COL_DATA = "PEDIDO", "STATUS", "DATA"
COL_VALOR, COL_UNIDADE, COL_CARRO = "VALOR", "UNIDADE", "CARRO | UTILIZAÇÃO"
COL_FORNECEDOR = "FORNECEDOR"
COL_AVALIACAO = "AVALIAÇÃO" 

# --- FUNÇÕES DE UTILIDADE ---
def valor_brasileiro(valor):
    if pd.isna(valor) or valor is None: return 0.0
    s = str(valor).strip()
    # Remove R$, espaços e pontos de milhar, troca vírgula por ponto
    s = re.sub(r"[R$\s\.]", "", s).replace(",", ".")
    try: return float(s)
    except: return 0.0

def br_money(valor):
    if pd.isna(valor): return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def safe_load(df):
    df = df.copy()
    # Limpeza de nomes de colunas para garantir compatibilidade
    df.columns = [c.strip().upper() for c in df.columns]
    
    if COL_DATA in df.columns:
        df[COL_DATA] = pd.to_datetime(df[COL_DATA], dayfirst=True, errors="coerce").dt.normalize()
        df = df[pd.notna(df[COL_DATA])].copy()
    if COL_VALOR in df.columns:
        df[COL_VALOR] = df[COL_VALOR].apply(valor_brasileiro)
    return df

def calculate_backup_sheet_name():
    today = date.today()
    monday_last_week = today - timedelta(days=today.weekday() + 7)
    friday_last_week = monday_last_week + timedelta(days=4)
    return f"{monday_last_week.strftime('%d.%m')} a {friday_last_week.strftime('%d.%m')}"

@st.cache_data(ttl=300)
def load_sheets(today_str):
    try:
        creds_json = st.secrets.get("google_sheets_service_account")
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(creds_json), SCOPE) if creds_json else ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
    except: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    def load_sheet_as_df(sheet_name):
        try:
            data = sh.worksheet(sheet_name).get_all_values()
            if len(data) < 2: return pd.DataFrame()
            
            # Pega o cabeçalho da SEGUNDA linha (índice 1) conforme sua nova estrutura
            raw_headers = [h.strip().upper() for h in data[1]]
            df = pd.DataFrame(data[2:], columns=raw_headers)
            return safe_load(df)
        except: return pd.DataFrame()

    return load_sheet_as_df("PROGRAMAÇÃO DIÁRIA"), load_sheet_as_df("EMERGENCIAL"), load_sheet_as_df(calculate_backup_sheet_name())

def show_result(row, sheet_name):
    st.write(f"📁 **Origem:** {sheet_name}") 
    
    # Lógica de Alerta Vermelho para EMERGENCIAL
    avaliacao = str(row.get(COL_AVALIACAO, "")).strip().upper()
    if avaliacao == "EMERGENCIAL":
        st.error(f"🚨 **AVALIAÇÃO: EMERGENCIAL**")
    elif avaliacao != "" and avaliacao != "NAN":
        st.info(f"⚖️ **Avaliação:** {avaliacao}")
        
    st.write(f"📅 **Previsão de pagamento:** {row.get(COL_DATA).strftime('%d/%m/%Y') if pd.notna(row.get(COL_DATA)) else 'N/A'}") 
    st.write(f"📌 **Status:** {row.get(COL_STATUS)}")
    st.write(f"💰 **Valor:** {br_money(row.get(COL_VALOR))}")
    st.write(f"🏢 **Unidade solicitante:** {row.get(COL_UNIDADE)}")
    st.write(f"🚌 **Carro/Utilização:** {row.get(COL_CARRO)}")
    st.write(f"📦 **Fornecedor:** {row.get(COL_FORNECEDOR)}")
    st.write("---")

# --- INÍCIO DO APP ---
SAO_PAULO_TZ = pytz.timezone('America/Sao_Paulo')
today_date_tz = datetime.datetime.now(SAO_PAULO_TZ).date()

if 'input_reset_counter' not in st.session_state:
    st.session_state.input_reset_counter = 0

df_programacao, df_emerg, df_backup = load_sheets(today_date_tz.isoformat())

# SIDEBAR
st.sidebar.image("saritur1.png")
if st.sidebar.button("🔄 Recarregar Dados"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.header("📊 Filtro por período")
start_date = st.sidebar.date_input("Início", date.today() - timedelta(days=30))
end_date = st.sidebar.date_input("Fim", date.today())

# Cálculos Totais
total_prog = df_programacao[(df_programacao[COL_DATA] >= pd.to_datetime(start_date)) & (df_programacao[COL_DATA] <= pd.to_datetime(end_date))][COL_VALOR].sum()
total_emerg = df_emerg[(df_emerg[COL_DATA] >= pd.to_datetime(start_date)) & (df_emerg[COL_DATA] <= pd.to_datetime(end_date))][COL_VALOR].sum()

st.sidebar.success(f"TOTAL PROGRAMAÇÃO: {br_money(total_prog)}")
st.sidebar.success(f"TOTAL EMERGENCIAL: {br_money(total_emerg)}")

st.title("Sistema de Consulta de Pedidos – Saritur")
BACKUP_NAME = calculate_backup_sheet_name()

st.subheader("🔍 Situação da Solicitação/Pedido")
current_key = f"input_{st.session_state.input_reset_counter}"
pedido_input = st.text_input("Digite o número do pedido:", key=current_key)

if pedido_input:
    pid = pedido_input.strip().upper()
    found = False
    
    bases_busca = [
        (df_programacao, "PROGRAMAÇÃO DIÁRIA"), 
        (df_emerg, "EMERGENCIAL"), 
        (df_backup, f"BACKUP {BACKUP_NAME}")
    ]
    
    for df, label in bases_busca:
        if not df.empty and COL_PEDIDO in df.columns:
            res = df[df[COL_PEDIDO].astype(str).str.strip().str.upper() == pid]
            if not res.empty:
                st.success(f"✅ Pedido encontrado na aba {label}")
                show_result(res.iloc[0], label)
                found = True
    
    if not found:
        st.warning(f"❌ Pedido '{pedido_input}' não encontrado.")
        
    if st.button("Limpar Busca"):
        st.session_state.input_reset_counter += 1
        st.rerun()

# RELATÓRIO DIÁRIO E GRÁFICOS
st.divider()
st.subheader("📅 Relatório Diário")
data_busca = st.date_input("Selecione a data:", value=today_date_tz)

if data_busca:
    dt = pd.to_datetime(data_busca).normalize()
    
    prog_f = df_programacao[df_programacao[COL_DATA] == dt] if not df_programacao.empty else pd.DataFrame()
    emerg_f = df_emerg[df_emerg[COL_DATA] == dt] if not df_emerg.empty else pd.DataFrame()
    
    c1, c2 = st.columns(2)
    c1.metric("PROGRAMAÇÃO", br_money(prog_f[COL_VALOR].sum()), delta="Limite 180k" if prog_f[COL_VALOR].sum() > 180000 else None, delta_color="inverse")
    c2.metric("EMERGENCIAL", br_money(emerg_f[COL_VALOR].sum()), delta="Limite 15k" if emerg_f[COL_VALOR].sum() > 15000 else None, delta_color="inverse")

    # Gráficos e Tabelas
    for df_graf, titulo, cor in [(prog_f, "🟦 Top 10 Programação", "blue"), (emerg_f, "🟥 Top 10 Emergencial", "red")]:
        if not df_graf.empty:
            st.write(f"### {titulo}")
            # Garante que VALOR é numérico antes de ordenar
            top = df_graf.sort_values(by=COL_VALOR, ascending=False).head(10).copy()
            top['VALOR_TEXTO'] = top[COL_VALOR].apply(br_money)
            
            chart = alt.Chart(top).mark_bar(color=cor).encode(
                x=alt.X(COL_VALOR, title="Valor Total"), 
                y=alt.Y(COL_PEDIDO, sort='-x', title="Pedido"),
                tooltip=[COL_PEDIDO, 'VALOR_TEXTO', COL_UNIDADE]
            )
            text = chart.mark_text(align='left', dx=5).encode(text='VALOR_TEXTO')
            st.altair_chart((chart + text).properties(height=300), use_container_width=True)
            
            # Tabela detalhada
            cols_disponiveis = [c for c in [COL_PEDIDO, COL_VALOR, COL_AVALIACAO, COL_STATUS, COL_UNIDADE, COL_CARRO] if c in df_graf.columns]
            st.dataframe(df_graf[cols_disponiveis], hide_index=True)

    # Gasto por Unidade
    df_comb = pd.concat([prog_f, emerg_f], ignore_index=True)
    if not df_comb.empty:
        st.write("---")
        st.subheader(f"🏢 Gasto por Unidade (Status: PEDIDO)")
        
        df_p = df_comb[df_comb[COL_STATUS].astype(str).str.strip().str.upper() == "PEDIDO"].copy()
        
        if not df_p.empty:
            df_p[COL_UNIDADE] = df_p[COL_UNIDADE].astype(str).str.strip().str.upper()
            gastos = df_p.groupby(COL_UNIDADE)[COL_VALOR].sum().sort_values(ascending=False).reset_index()
            gastos.columns = ["UNIDADE", "TOTAL (R$)"]
            # Formatação para exibição
            gastos_view = gastos.copy()
            gastos_view["TOTAL (R$)"] = gastos_view["TOTAL (R$)"].apply(br_money)
            st.dataframe(gastos_view, hide_index=True, use_container_width=True)