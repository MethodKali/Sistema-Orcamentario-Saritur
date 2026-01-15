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

def safe_load(df):
    df = df.copy()
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
    except: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    def load_sheet_as_df(sheet_name):
        try:
            data = sh.worksheet(sheet_name).get_all_values()
            if len(data) < 2: return pd.DataFrame()
            
            raw_headers = [h.strip().upper() for h in data[1]]
            final_headers = []
            counts = {}
            for h in raw_headers:
                name = h if h else "VAZIO"
                if name in counts:
                    counts[name] += 1
                    final_headers.append(f"{name}_{counts[name]}")
                else:
                    counts[name] = 0
                    final_headers.append(name)
            
            df = pd.DataFrame(data[2:], columns=final_headers)
            return safe_load(df)
        except: return pd.DataFrame()

    # Retorna agora 5 DataFrames (2026, 2025, EMERG, BACKUP, GERAL_EMERG)
    return load_sheet_as_df("2026"), load_sheet_as_df("2025"), load_sheet_as_df("EMERGENCIAL"), load_sheet_as_df(calculate_backup_sheet_name()), load_sheet_as_df("GERAL_EMERGENCIAL")

def show_result(row, sheet_name):
    st.write(f"📁 **Origem:** {sheet_name}") 
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

# Recebendo as 5 abas
df_2026, df_2025, df_emerg, df_backup, df_geral_emerg = load_sheets(today_date_tz.isoformat())

# SIDEBAR
st.sidebar.image("saritur1.png")
if st.sidebar.button("🔄 Recarregar Dados"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.header("📊 Filtro por período")
start_date = st.sidebar.date_input("Início", date.today() - timedelta(days=30))
end_date = st.sidebar.date_input("Fim", date.today())

# Cálculos de totais filtrados para a Sidebar
df_alta_total = pd.concat([df_2026, df_2025], ignore_index=True)
total_alta = df_alta_total[(df_alta_total[COL_DATA] >= pd.to_datetime(start_date)) & (df_alta_total[COL_DATA] <= pd.to_datetime(end_date))][COL_VALOR].sum()

total_emerg_combinado = pd.concat([df_emerg, df_geral_emerg], ignore_index=True)
total_emerg = total_emerg_combinado[(total_emerg_combinado[COL_DATA] >= pd.to_datetime(start_date)) & (total_emerg_combinado[COL_DATA] <= pd.to_datetime(end_date))][COL_VALOR].sum()

st.sidebar.success(f"TOTAL ALTA (2025/26): {br_money(total_alta)}")
st.sidebar.success(f"EMERGENCIAL TOTAL: {br_money(total_emerg)}")

# CORPO PRINCIPAL
st.title("Sistema de Consulta de Pedidos – Saritur")
BACKUP_NAME = calculate_backup_sheet_name()
st.info(f"Bases: 2026, 2025, EMERGENCIAL, GERAL_EMERGENCIAL e BACKUP ({BACKUP_NAME})")

st.subheader("🔍 Situação da Solicitação/Pedido")
current_key = f"input_{st.session_state.input_reset_counter}"
pedido_input = st.text_input("Digite o número do pedido:", key=current_key)

if pedido_input:
    pid = pedido_input.strip().upper()
    found = False
    
    # Lista de bases atualizada com 2025
    bases_busca = [
        (df_2026, "2026"), 
        (df_2025, "2025"), 
        (df_emerg, "EMERGENCIAL"), 
        (df_geral_emerg, "GERAL_EMERGENCIAL"), 
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
        st.warning(f"❌ Pedido '{pedido_input}' não encontrado em nenhuma aba.")
        
    if st.button("Limpar Busca"):
        st.session_state.input_reset_counter += 1
        st.rerun()

# PESQUISA POR DATA E GRÁFICOS
st.divider()
st.subheader("📅 Relatório Diário")
data_busca = st.date_input("Selecione a data:", value=today_date_tz)

if data_busca:
    dt = pd.to_datetime(data_busca).normalize()
    
    # Filtra 2025 e 2026 para a data selecionada
    alta_26_f = df_2026[df_2026[COL_DATA] == dt] if not df_2026.empty else pd.DataFrame()
    alta_25_f = df_2025[df_2025[COL_DATA] == dt] if not df_2025.empty else pd.DataFrame()
    alta_total_f = pd.concat([alta_26_f, alta_25_f], ignore_index=True)
    
    emerg_f = pd.concat([df_emerg, df_geral_emerg], ignore_index=True)
    emerg_f = emerg_f[emerg_f[COL_DATA] == dt] if not emerg_f.empty else pd.DataFrame()
    
    c1, c2 = st.columns(2)
    c1.metric("ALTA (2025/26)", br_money(alta_total_f[COL_VALOR].sum()), delta="Limite 180k" if alta_total_f[COL_VALOR].sum() > 180000 else None)
    c2.metric("EMERGENCIAL", br_money(emerg_f[COL_VALOR].sum()), delta="Limite 15k" if emerg_f[COL_VALOR].sum() > 15000 else None)

    # Gráficos ajustados para mostrar o consolidado da Alta
    for df_graf, titulo, cor in [(alta_total_f, "🟦 Top 10 ALTA (Consolidado)", "blue"), (emerg_f, "🟥 Top 10 EMERGENCIAL", "red")]:
        if not df_graf.empty:
            st.write(f"### {titulo}")
            top = df_graf.sort_values(by=COL_VALOR, ascending=False).head(10).copy()
            top['VALOR_TEXTO'] = top[COL_VALOR].apply(br_money)
            
            chart = alt.Chart(top).mark_bar(color=cor).encode(
                x=alt.X(COL_VALOR, axis=None), 
                y=alt.Y(COL_PEDIDO, sort='-x', title="Pedido"),
                tooltip=[COL_PEDIDO, 'VALOR_TEXTO']
            )
            text = chart.mark_text(align='left', dx=5).encode(text='VALOR_TEXTO')
            st.altair_chart((chart + text).properties(height=300), use_container_width=True)
            st.dataframe(df_graf[[COL_PEDIDO, COL_VALOR, COL_STATUS, COL_UNIDADE, COL_CARRO]], hide_index=True)

    # Gasto por Unidade (Tabela Estruturada)
    df_comb = pd.concat([alta_total_f, emerg_f], ignore_index=True)
    if not df_comb.empty:
        st.write("---")
        st.subheader(f"🏢 Gasto por Unidade (Status: PEDIDO)")
        
        df_p = df_comb[df_comb[COL_STATUS].astype(str).str.strip().str.upper() == "PEDIDO"].copy()
        
        if not df_p.empty:
            df_p[COL_UNIDADE] = df_p[COL_UNIDADE].astype(str).str.strip().str.upper()
            df_p[COL_UNIDADE] = df_p[COL_UNIDADE].str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8')
            gastos = df_p.groupby(COL_UNIDADE)[COL_VALOR].sum().sort_values(ascending=False).reset_index()
            gastos_tabela = gastos.copy()
            gastos_tabela.columns = ["UNIDADE", "TOTAL (R$)"]
            gastos_tabela["TOTAL (R$)"] = gastos_tabela["TOTAL (R$)"].apply(br_money)
            
            st.dataframe(gastos_tabela, hide_index=True, use_container_width=True)
        else:
            st.info("Nenhum gasto com status 'PEDIDO' encontrado para esta data.")