import streamlit as st
import pandas as pd
import datetime
import re
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, timedelta
import calendar 
import os

# --- CONFIGURAÇÃO DE ACESSO ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = "acesso.json" 
SPREADSHEET_ID = "1X9trwwqVCwPXY2_O667WJcOR4CHNYbBjJDVsrYNZSgc"     

# MAPA DE COLUNAS
COL_PEDIDO = "PEDIDO"
COL_STATUS = "STATUS"
COL_DATA = "DATA"
COL_VALOR = "VALOR"
COL_UNIDADE = "UNIDADE"
COL_CARRO = "CARRO | UTILIZAÇÃO"
COL_FORNECEDOR = "FORNECEDOR"

# --- FUNÇÕES DE APOIO ---

def valor_brasileiro(valor):
    if pd.isna(valor) or valor is None: return 0.0
    s = str(valor).strip()
    # Remove R$, espaços e pontos de milhar, troca vírgula por ponto
    s = re.sub(r"[R$\s\.]", "", s).replace(",", ".")
    try: return float(s)
    except ValueError: return 0.0

def br_money(valor):
    if pd.isna(valor): return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def safe_load(df):
    df = df.copy()
    if COL_DATA in df.columns:
        df[COL_DATA] = pd.to_datetime(df[COL_DATA], dayfirst=True, errors="coerce").dt.normalize()
    if COL_VALOR in df.columns:
        df[COL_VALOR] = df[COL_VALOR].apply(valor_brasileiro)
    # Filtra linhas sem data para evitar erros de exibição
    return df[pd.notna(df[COL_DATA])].copy() if COL_DATA in df.columns else df

# --- CORREÇÃO DEFINITIVA DA LÓGICA DE DATAS (BACKUP) ---
def calculate_backup_sheet_name() -> str:
    """
    Calcula o nome da aba da semana útil anterior completa (Segunda a Sexta).
    A lógica permanece estática durante a semana atual.
    """
    today = date.today()
    # Retorna o índice da semana (0=Segunda, 1=Terça...)
    weekday_idx = today.weekday()
    
    # monday_last_week: voltamos para a segunda desta semana e subtraímos 7 dias
    monday_last_week = today - timedelta(days=weekday_idx + 7)
    friday_last_week = monday_last_week + timedelta(days=4)
    
    return f"{monday_last_week.strftime('%d.%m')} a {friday_last_week.strftime('%d.%m')}"

@st.cache_data(ttl=300)
def load_sheets(today_str):
    try:
        # Prioriza Segredos do Streamlit Cloud (Deploy)
        creds_json = st.secrets.get("google_sheets_service_account")
        if creds_json:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(creds_json), SCOPE)
        else:
            # Fallback para arquivo local
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
            
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    def load_sheet_as_df(sheet_name):
        try:
            worksheet = sh.worksheet(sheet_name)
            data = worksheet.get_all_values() 
            if len(data) < 2: return pd.DataFrame()
            
            # Limpa cabeçalhos (segunda linha da planilha)
            headers = [h.strip().upper() for h in data[1]]
            df = pd.DataFrame(data[2:], columns=headers)
            return safe_load(df) 
        except: 
            return pd.DataFrame()

    df_alta = load_sheet_as_df("ALTA")
    df_emerg = load_sheet_as_df("EMERGENCIAL")
    df_backup = load_sheet_as_df(calculate_backup_sheet_name())
    
    return df_alta, df_emerg, df_backup

# --- INTERFACE SIDEBAR ---
st.sidebar.image("saritur1.png")
if st.sidebar.button("🔄 Recarregar Dados"):
    st.cache_data.clear()
    st.rerun()

# Carrega os dados usando a data de hoje como chave de cache
df_alta, df_emerg, df_backup = load_sheets(date.today().isoformat())

st.sidebar.markdown("---") 
st.sidebar.markdown(
    """
    <div style='text-align: center;'>
        <p style='font-size: 11px; color: #808489;'>
            Desenvolvido por Kerles Alves - Ass. Suprimentos<br>
            Unidade Jardim Montanhês (BH)<br>
            Saritur Santa Rita Transporte Urbano e Rodoviário
        </p>
    </div>
    """, 
    unsafe_allow_html=True
)

# --- CORPO PRINCIPAL ---
st.title("🔍 Pesquisa de Pedidos")

BACKUP_NAME = calculate_backup_sheet_name()
st.info(f"Rastreando solicitações atuais e histórico de backup: **{BACKUP_NAME}**")

pedido_input = st.text_input("Digite o número do pedido:", placeholder="Ex: 1234/2025").strip().upper()

if pedido_input:
    def search(df, p):
        if not df.empty and COL_PEDIDO in df.columns:
            return df[df[COL_PEDIDO].astype(str).str.strip().str.upper() == p]
        return pd.DataFrame()

    # Dicionário para facilitar o loop de exibição
    fontes = {
        "🟦 Aba ALTA": search(df_alta, pedido_input),
        "🟥 Aba EMERGENCIAL": search(df_emerg, pedido_input),
        f"🗄️ Histórico ({BACKUP_NAME})": search(df_backup, pedido_input)
    }

    found = False
    for local, df_res in fontes.items():
        if not df_res.empty:
            found = True
            row = df_res.iloc[0]
            st.success(f"📍 Pedido localizado em: {local}")
            
            # Organização visual dos dados encontrados
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"📅 **Pagamento:** {row[COL_DATA].strftime('%d/%m/%Y')}")
                st.write(f"💰 **Valor:** {br_money(row[COL_VALOR])}")
                st.write(f"🏢 **Unidade:** {row[COL_UNIDADE]}")
            with col_b:
                st.write(f"📌 **Status:** {row[COL_STATUS]}")
                st.write(f"🚌 **Carro:** {row[COL_CARRO]}")
                st.write(f"📦 **Fornecedor:** {row[COL_FORNECEDOR]}")
            st.divider()
    
    if not found:
        st.warning(f"❌ O pedido '{pedido_input}' não foi encontrado nas bases de dados.")