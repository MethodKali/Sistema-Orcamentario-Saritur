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
    s = re.sub(r"[R$\s\.]", "", s).replace(",", ".")
    try: return float(s)
    except: return 0.0

def br_money(valor):
    if pd.isna(valor): return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def safe_load(df, sheet_name):
    # Se o DF vier vazio, cria estrutura mínima para não quebrar filtros
    if df.empty:
        return pd.DataFrame(columns=[COL_DATA, COL_VALOR, COL_PEDIDO, COL_STATUS, COL_UNIDADE, COL_AVALIACAO])
    
    # Padronização de colunas
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    # Garante que a coluna VALOR exista
    if COL_VALOR not in df.columns:
        cols_com_valor = [c for c in df.columns if "VALOR" in c]
        if cols_com_valor:
            df = df.rename(columns={cols_com_valor[0]: COL_VALOR})
        else:
            df[COL_VALOR] = 0.0
    
    # Garante que a coluna AVALIACAO exista (mesmo que vazia)
    if COL_AVALIACAO not in df.columns:
        df[COL_AVALIACAO] = ""

    # Conversão de tipos
    df[COL_VALOR] = df[COL_VALOR].apply(valor_brasileiro)
    if COL_DATA in df.columns:
        df[COL_DATA] = pd.to_datetime(df[COL_DATA], dayfirst=True, errors="coerce").dt.normalize()
    else:
        df[COL_DATA] = pd.NaT
    
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
    except: 
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    def load_sheet_as_df(sheet_name):
        try:
            ws = sh.worksheet(sheet_name)
            data = ws.get_all_values()
            if len(data) < 2: return pd.DataFrame()
            
            # Tenta ler o cabeçalho da linha 2 (índice 1)
            headers = [h.strip().upper() for h in data[1]]
            
            # Se não achar as colunas básicas na linha 2, tenta a linha 1
            if not any(h in headers for h in ["VALOR", "DATA", "PEDIDO"]):
                headers = [h.strip().upper() for h in data[0]]
                df = pd.DataFrame(data[1:], columns=headers)
            else:
                df = pd.DataFrame(data[2:], columns=headers)
            
            return safe_load(df, sheet_name)
        except:
            return pd.DataFrame()

    return load_sheet_as_df("PROGRAMAÇÃO DIÁRIA"), load_sheet_as_df("EMERGENCIAL"), load_sheet_as_df(calculate_backup_sheet_name())

def show_result(row, sheet_name):
    st.write(f"📁 **Origem:** {sheet_name}") 
    
    # Alerta Vermelho para AVALIAÇÃO EMERGENCIAL
    aval = str(row.get(COL_AVALIACAO, "")).strip().upper()
    if aval == "EMERGENCIAL":
        st.error(f"🚨 **AVALIAÇÃO: EMERGENCIAL**")
    elif aval not in ["", "NAN", "NONE"]:
        st.info(f"⚖️ **Avaliação:** {aval}")
        
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

# Cálculos Totais da Sidebar com Verificação de Coluna
def get_sum(df, s_date, e_date):
    if df.empty or COL_DATA not in df.columns or COL_VALOR not in df.columns:
        return 0.0
    mask = (df[COL_DATA] >= pd.to_datetime(s_date)) & (df[COL_DATA] <= pd.to_datetime(e_date))
    return df.loc[mask, COL_VALOR].sum()

t_prog = get_sum(df_programacao, start_date, end_date)
t_emerg = get_sum(df_emerg, start_date, end_date)

st.sidebar.success(f"TOTAL PROGRAMAÇÃO: {br_money(t_prog)}")
st.sidebar.success(f"TOTAL EMERGENCIAL: {br_money(t_emerg)}")

st.title("Sistema de Consulta de Pedidos – Saritur")
BACKUP_NAME = calculate_backup_sheet_name()

st.subheader("🔍 Situação da Solicitação/Pedido")
current_key = f"input_{st.session_state.input_reset_counter}"
pedido_input = st.text_input("Digite o número do pedido:", key=current_key)

if pedido_input:
    pid = pedido_input.strip().upper()
    found = False
    bases_busca = [(df_programacao, "PROGRAMAÇÃO DIÁRIA"), (df_emerg, "EMERGENCIAL"), (df_backup, f"BACKUP {BACKUP_NAME}")]
    
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
    
    # Filtros Seguros
    prog_f = df_programacao[df_programacao[COL_DATA] == dt] if not df_programacao.empty and COL_DATA in df_programacao.columns else pd.DataFrame()
    emerg_f = df_emerg[df_emerg[COL_DATA] == dt] if not df_emerg.empty and COL_DATA in df_emerg.columns else pd.DataFrame()
    
    # Soma Segura para as Métricas
    val_prog_f = prog_f[COL_VALOR].sum() if not prog_f.empty and COL_VALOR in prog_f.columns else 0.0
    val_emerg_f = emerg_f[COL_VALOR].sum() if not emerg_f.empty and COL_VALOR in emerg_f.columns else 0.0
    
    c1, c2 = st.columns(2)
    c1.metric("PROGRAMAÇÃO", br_money(val_prog_f), delta="Limite 180k" if val_prog_f > 180000 else None, delta_color="inverse")
    c2.metric("EMERGENCIAL", br_money(val_emerg_f), delta="Limite 15k" if val_emerg_f > 15000 else None, delta_color="inverse")

    # Gráficos
    for df_graf, titulo, cor in [(prog_f, "🟦 Top 10 Programação", "blue"), (emerg_f, "🟥 Top 10 Emergencial", "red")]:
        if not df_graf.empty and COL_VALOR in df_graf.columns and COL_PEDIDO in df_graf.columns:
            st.write(f"### {titulo}")
            top = df_graf.sort_values(by=COL_VALOR, ascending=False).head(10).copy()
            top['VALOR_TEXTO'] = top[COL_VALOR].apply(br_money)
            
            chart = alt.Chart(top).mark_bar(color=cor).encode(
                x=alt.X(COL_VALOR, title="Valor Total"), 
                y=alt.Y(COL_PEDIDO, sort='-x', title="Pedido"),
                tooltip=[COL_PEDIDO, 'VALOR_TEXTO', COL_UNIDADE]
            )
            text = chart.mark_text(align='left', dx=5).encode(text='VALOR_TEXTO')
            st.altair_chart((chart + text).properties(height=300), use_container_width=True)
            
            cols_show = [c for c in [COL_PEDIDO, COL_VALOR, COL_AVALIACAO, COL_STATUS, COL_UNIDADE, COL_CARRO] if c in df_graf.columns]
            st.dataframe(df_graf[cols_show], hide_index=True)

    # Gasto por Unidade
    df_comb = pd.concat([prog_f, emerg_f], ignore_index=True)
    if not df_comb.empty and COL_STATUS in df_comb.columns:
        st.write("---")
        st.subheader(f"🏢 Gasto por Unidade (Status: PEDIDO)")
        df_p = df_comb[df_comb[COL_STATUS].astype(str).str.strip().str.upper() == "PEDIDO"].copy()
        
        if not df_p.empty and COL_UNIDADE in df_p.columns:
            df_p[COL_UNIDADE] = df_p[COL_UNIDADE].astype(str).str.strip().upper()
            gastos = df_p.groupby(COL_UNIDADE)[COL_VALOR].sum().sort_values(ascending=False).reset_index()
            gastos.columns = ["UNIDADE", "TOTAL (R$)"]
            gastos_view = gastos.copy()
            gastos_view["TOTAL (R$)"] = gastos_view["TOTAL (R$)"].apply(br_money)
            st.dataframe(gastos_view, hide_index=True, use_container_width=True)