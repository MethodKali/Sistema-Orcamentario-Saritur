# BUSCAR.py
import streamlit as st
import pandas as pd
import datetime
import re
import altair as alt
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, timedelta
import calendar # Adicionado para manipulação de datas
import json

# --- CONFIGURAÇÃO DE ACESSO E LIMITES ---
# ESTA LISTA DE SCOPE JÁ ESTAVA CORRETA NO BUSCAR.py
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
# Substitua pelo caminho real do seu arquivo de credenciais se ele não for carregado
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
# FUNÇÕES DE VALOR E FORMATAÇÃO (Mantidas)
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

# -----------------------
# FUNÇÃO DE CÁLCULO DO NOME DA ABA DE BACKUP (MANTIDA)
# -----------------------

def calculate_backup_sheet_name() -> str:
    """
    Calcula o nome da aba de backup baseando-se na data atual (dd.mm a dd.mm).
    Regras: 
    1. Se hoje for Segunda-feira, busca a Semana Passada.
    2. Caso contrário, busca a Semana Retrasada.
    """
    today = date.today()
    is_update_day = today.weekday() == calendar.MONDAY

    if is_update_day:
        # É dia de atualização (Segunda): Buscamos a SEMANA PASSADA.
        last_friday = today - timedelta(days=3) 
        end_date = last_friday
        
    else:
        # Não é dia de atualização: Buscamos a SEMANA RETRASADA.
        
        # Encontra a Sexta-feira da semana retrasada
        days_since_last_friday = (today.weekday() - calendar.FRIDAY + 7) % 7 
        
        if today.weekday() in [calendar.SATURDAY, calendar.SUNDAY]:
            last_friday_passada = today - timedelta(days=days_since_last_friday) 
        else:
            last_friday_passada = today - timedelta(days=days_since_last_friday + 7)
            
        end_date = last_friday_passada - timedelta(days=7) 

    
    ultimo_dia_util = end_date
    primeiro_dia_util = ultimo_dia_util - timedelta(days=4)

    return f"{primeiro_dia_util.strftime('%d.%m')} a {ultimo_dia_util.strftime('%d.%m')}"


@st.cache_data(ttl=300)
def load_sheets(today_str): 
    
    gc = None
    # -----------------------------------------------------------------
    # CORREÇÃO AQUI: Prioriza st.secrets para o Cloud
    # -----------------------------------------------------------------
    try:
        # 1. Tenta carregar credenciais do Streamlit Secrets (Cloud)
        creds_json = st.secrets.get("google_sheets_service_account")
        
        if creds_json:
             # Usa a lista SCOPE correta definida no topo
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, SCOPE)
            gc = gspread.authorize(creds)
        else:
            # 2. Fallback para execução local (acesso.json)
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
            gc = gspread.authorize(creds)
            
    except KeyError:
        # Ocorre se 'google_sheets_service_account' não estiver em st.secrets
        st.error("ERRO: As credenciais do Google Sheets não foram configuradas nos segredos do Streamlit.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
    except Exception as e:
        # Captura qualquer erro de autenticação (incluindo FileAccessError/FileNotFound localmente)
        st.error(f"Erro ao autenticar credenciais no Streamlit Cloud. Verifique as Secrets. Erro: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    # -----------------------------------------------------------------
    
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error(f"Erro ao abrir a planilha. Verifique o ID e as credenciais. Erro: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()


    def load_sheet_as_df(sheet_name):
        try:
            data = sh.worksheet(sheet_name).get_all_values() 
            # Lógica para limpar e garantir cabeçalhos únicos
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
            st.warning(f"Aviso: Aba '{sheet_name}' não encontrada. Retornando DataFrame vazio.")
            return pd.DataFrame()
        except Exception as e:
            st.error(f"Erro ao carregar aba {sheet_name}. Erro: {e}")
            return pd.DataFrame()

    df_alta = load_sheet_as_df("ALTA")
    df_emerg = load_sheet_as_df("EMERGENCIAL")
    
    # --- NOVO: Carregar a aba de backup calculada ---
    BACKUP_SHEET_NAME = calculate_backup_sheet_name()
    df_backup = load_sheet_as_df(BACKUP_SHEET_NAME)

    return df_alta, df_emerg, df_backup


def sum_between(df, start, end):
    if df.empty or COL_DATA not in df.columns or COL_VALOR not in df.columns:
        return 0.0
    
    end_date_normalized = pd.to_datetime(end).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    mask = (df[COL_DATA] >= pd.to_datetime(start).normalize()) & (df[COL_DATA] <= end_date_normalized)
    return df.loc[mask, COL_VALOR].sum()


# -----------------------
# APP STREAMLIT (MANTIDO)
# -----------------------
st.sidebar.image("saritur1.png")

SAO_PAULO_TZ = pytz.timezone('America/Sao_Paulo')
today_date_tz = datetime.datetime.now(SAO_PAULO_TZ).date()
today_date_str = today_date_tz.isoformat() 

if st.sidebar.button("🔄 Recarregar Dados"):
    st.cache_data.clear()
    st.success("Cache limpo! Recarregando dados...")
    
df_alta, df_emerg, df_backup = load_sheets(today_date_str)

st.title("Sistema de Consulta de Pedidos – *ALTA*, *EMERGENCIAL* e *BACKUP*")

# Exibe o nome da aba de backup que está sendo rastreada
try:
    BACKUP_SHEET_NAME = calculate_backup_sheet_name()
    st.info(f"Aba de Backup de Emergencial sendo rastreada: **{BACKUP_SHEET_NAME}**")
except Exception:
    pass 


## 1) Pesquisa por Número de Pedido

st.subheader("🔍 Situação da Solicitação/Pedido")
pedido_input = st.text_input("Digite o número do pedido:")

def show_result(row, sheet_name):
    st.write(f"📁 **Origem:** {sheet_name}") # Adiciona a origem
    st.write(f"📅 **Previsão de pagamento:** {row.get(COL_DATA).strftime('%d/%m/%Y')}") 
    st.write(f"📌 **Status:** {row.get(COL_STATUS)}")
    st.write(f"💰 **Valor:** {br_money(row.get(COL_VALOR))}")
    st.write(f"🏢 **Unidade solicitante:** {row.get(COL_UNIDADE)}")
    st.write(f"🚌 **Carro/Utilização:** {row.get(COL_CARRO)}")
    st.write(f"📦 **Fornecedor:** {row.get(COL_FORNECEDOR)}")
    st.write("---")


if pedido_input:
    pid = pedido_input.strip().upper() 
    
    # ----------------------------------------------------
    # ATUALIZADO: Pesquisa em ALTA, EMERGENCIAL e BACKUP
    # ----------------------------------------------------
    
    def search_df(df, pid):
        if COL_PEDIDO in df.columns and not df.empty:
            return df[df[COL_PEDIDO].astype(str).str.strip().str.upper() == pid]
        return pd.DataFrame()

    res_alta = search_df(df_alta, pid)
    res_emerg = search_df(df_emerg, pid)
    res_backup = search_df(df_backup, pid) # NOVO: Pesquisa na aba de backup

    if res_alta.empty and res_emerg.empty and res_backup.empty:
        st.warning(f"❌ Pedido '{pedido_input}' não encontrado em nenhuma aba.")
    else:
        found = False
        if not res_alta.empty:
            st.success("🟦 Pedido encontrado na aba ALTA")
            show_result(res_alta.iloc[0], "ALTA")
            found = True

        if not res_emerg.empty:
            st.success("🟥 Pedido encontrado na aba EMERGENCIAL")
            show_result(res_emerg.iloc[0], "EMERGENCIAL")
            found = True
            
        if not res_backup.empty:
            st.info(f"🗄️ Pedido encontrado na aba de BACKUP: {BACKUP_SHEET_NAME}")
            show_result(res_backup.iloc[0], BACKUP_SHEET_NAME)
            found = True

## 2) Pesquisa por Data

st.subheader("📅 Buscar pedidos por data")
data_busca = st.date_input("Selecione a data do pedido:", key="data_busca_2")  

if data_busca:
    data_busca_dt = pd.to_datetime(data_busca).normalize()  

    mask_alta = pd.notna(df_alta[COL_DATA]) & (df_alta[COL_DATA] == data_busca_dt)
    alta_filtrado = df_alta[mask_alta].copy()
    
    mask_emerg = pd.notna(df_emerg[COL_DATA]) & (df_emerg[COL_DATA] == data_busca_dt)
    emerg_filtrado = df_emerg[mask_emerg].copy()

    total_valor_dia_alta = alta_filtrado[COL_VALOR].sum()
    total_valor_dia_emerg = emerg_filtrado[COL_VALOR].sum()
    total_geral = total_valor_dia_alta + total_valor_dia_emerg

    contagem_alta = len(alta_filtrado)
    contagem_emerg = len(emerg_filtrado)
    
    # ----------------------------------------------------
    # EXIBIÇÃO DE GASTOS, LIMITES E ALERTAS (Mantida)
    # ----------------------------------------------------
    
    st.markdown(f"### 💰 Gastos Diários em {data_busca_dt.strftime('%d/%m/%Y')}")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"**🟦 ALTA** (Limite: {br_money(LIMITE_ALTA_DIARIO)})")
        st.metric(label="Gasto ALTA", value=br_money(total_valor_dia_alta))
        
        if total_valor_dia_alta > LIMITE_ALTA_DIARIO:
            st.warning("⚠️ **Valor diário excedido.** São necessárias precauções!", icon="🚨")
        
        st.info(f"Pedidos encontrados: **{contagem_alta}**")

    with col2:
        st.markdown(f"**🟥 EMERGENCIAL** (Limite: {br_money(LIMITE_EMERG_DIARIO)})")
        st.metric(label="Gasto EMERGENCIAL", value=br_money(total_valor_dia_emerg))
        
        if total_valor_dia_emerg > LIMITE_EMERG_DIARIO:
            st.warning("⚠️ **Valor diário excedido.** São necessárias precauções!", icon="🚨")
        
        st.info(f"Pedidos encontrados: **{contagem_emerg}**")
        
    st.markdown("  \n")
    st.markdown("  \n") 
    st.metric(label="💰 TOTAL GERAL DO DIA", value=br_money(total_geral))
    st.markdown("---")

    COLS_BASE = [COL_PEDIDO, COL_STATUS, COL_UNIDADE, COL_CARRO, COL_FORNECEDOR]

    # =================================================================
    # BLOCO 1: ALTA (Tabela + Gráfico Top 10)
    # =================================================================
    if not alta_filtrado.empty:
        st.write("### 🟦 Pedidos da ALTA")
        
        alta_filtrado_show = alta_filtrado.copy()
        alta_filtrado_show[COL_VALOR] = alta_filtrado_show[COL_VALOR].apply(br_money)
        cols_final_alta = COLS_BASE[:1] + [COL_VALOR] + COLS_BASE[1:]
        st.dataframe(alta_filtrado_show[cols_final_alta], hide_index=True)
        
        st.markdown("#### 📈 ALTA: Top 10 Pedidos por Valor")
        
        top_alta = alta_filtrado.sort_values(by=COL_VALOR, ascending=False).head(10).copy()
        top_alta['VALOR_TEXTO'] = top_alta[COL_VALOR].apply(lambda x: f'R$ {x:,.2f}'.replace(",", "X").replace(".", ",").replace("X", "."))
        
        chart_bar_alta = alt.Chart(top_alta).mark_bar(color='rgb(66, 133, 244)').encode(
            x=alt.X(COL_VALOR, title='', axis=None), 
            y=alt.Y(COL_PEDIDO, 
                    sort='-x', 
                    title='', 
                    axis=alt.Axis(grid=False, titleAnchor='start')), 
            tooltip=[COL_PEDIDO, alt.Tooltip(COL_VALOR, format='$.2f', title='Valor')]
        )
        
        chart_text_alta = alt.Chart(top_alta).mark_text(
            align='left', 
            baseline='middle',
            dx=5 
        ).encode(
            x=alt.X(COL_VALOR, stack=None), 
            y=alt.Y(COL_PEDIDO, sort='-x'),
            text=alt.Text('VALOR_TEXTO'), 
            color=alt.value('#CCCCCC')
        )
        
        chart_alta = (chart_bar_alta + chart_text_alta).properties(
            title=data_busca_dt.strftime('%d/%m/%Y')
        ).interactive() 
        
        st.altair_chart(chart_alta, use_container_width=True)
        st.markdown("---") 

    # =================================================================
    # BLOCO 2: EMERGENCIAL (Tabela + Gráfico Top 10)
    # =================================================================
    if not emerg_filtrado.empty:
        st.write("### 🟥 Pedidos da EMERGENCIAL")
        
        emerg_filtrado_show = emerg_filtrado.copy()
        emerg_filtrado_show[COL_VALOR] = emerg_filtrado_show[COL_VALOR].apply(br_money)
        cols_final_emerg = COLS_BASE[:1] + [COL_VALOR] + COLS_BASE[1:]
        st.dataframe(emerg_filtrado_show[cols_final_emerg], hide_index=True)
        
        st.markdown("#### 📈 EMERGENCIAL: Top 10 Pedidos por Valor")
        
        top_emerg = emerg_filtrado.sort_values(by=COL_VALOR, ascending=False).head(10).copy()
        top_emerg['VALOR_TEXTO'] = top_emerg[COL_VALOR].apply(lambda x: f'R$ {x:,.2f}'.replace(",", "X").replace(".", ",").replace("X", "."))

        chart_bar_emerg = alt.Chart(top_emerg).mark_bar(color='rgb(219, 68, 55)').encode(
            x=alt.X(COL_VALOR, title='', axis=None), 
            y=alt.Y(COL_PEDIDO, 
                    sort='-x', 
                    title='', 
                    axis=alt.Axis(grid=False, titleAnchor='start')), 
            tooltip=[COL_PEDIDO, alt.Tooltip(COL_VALOR, format='$.2f', title='Valor')]
        )
        
        chart_text_emerg = alt.Chart(top_emerg).mark_text(
            align='left', 
            baseline='middle',
            dx=5 
        ).encode(
            x=alt.X(COL_VALOR, stack=None), 
            y=alt.Y(COL_PEDIDO, sort='-x'),
            text=alt.Text('VALOR_TEXTO'), 
            color=alt.value('#CCCCCC')
        )
        
        chart_emerg = (chart_bar_emerg + chart_text_emerg).properties(
            title=data_busca_dt.strftime('%d/%m/%Y')
        ).interactive() 
        
        st.altair_chart(chart_emerg, use_container_width=True)
        st.markdown("---")