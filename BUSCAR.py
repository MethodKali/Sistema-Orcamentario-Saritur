import streamlit as st
import pandas as pd
import datetime
import re
import altair as alt
import pytz

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# -----------------------
# CONFIGURAÇÃO
# -----------------------
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
CREDS_FILE = "/home/deep_writer/Downloads/Saritur/acesso.json"
SPREADSHEET_ID = "1n5I4U7siMsRB-eeAcWr56zNqudlcVbK7T2OImIjnMWs"


# -----------------------
# CONVERSÃO DE VALORES BR (FINAL)
# -----------------------

def valor_brasileiro(valor):
    """
    Converte uma string de moeda brasileira (que pode vir como '1.534,00') para float.
    Otimizado para robustez.
    """
    if pd.isna(valor) or valor is None:
        return 0.0
    
    s = str(valor).strip()
    
    # Usa Regex para remover R$, espaços e pontos de milhar, mantendo vírgulas e números
    s = re.sub(r"[R$\s\.]", "", s)
    
    # Troca vírgula (decimal) por ponto
    s = s.replace(",", ".")
    
    try:
        return float(s)
    except ValueError:
        return 0.0

# -----------------------
# OUTRAS FUNÇÕES
# -----------------------

# A função to_date não é mais estritamente necessária após a otimização de safe_load, 
# mas mantida por segurança.
def to_date(data):
    # Converte para data do Pandas
    return pd.to_datetime(data, dayfirst=True, errors="coerce")

def br_money(valor):
    # Formata o float de volta para string R$ X.XX,XX
    if pd.isna(valor):
        return "R$ 0,00"
    # Usa locale ou formatação f-string
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ... (Função valor_brasileiro) ...

def safe_load(df):
    """Padroniza colunas, converte datas e valores e normaliza a DATA."""
    df = df.copy()
    df.columns = df.columns.str.strip().str.upper()

    if "DATA" in df.columns:
        # Conversão robusta de data com dayfirst=True
        df["DATA"] = pd.to_datetime(df["DATA"], dayfirst=True, errors="coerce") 
        # NORMALIZAÇÃO: Remove o componente de tempo (hora/minuto/segundo)
        df["DATA"] = df["DATA"].dt.normalize()  

    if "VALOR" in df.columns:
        df["VALOR"] = df["VALOR"].apply(valor_brasileiro)
    
    # Otimização: Remove linhas onde a DATA é inválida (NaT)
    df = df[pd.notna(df["DATA"])].copy()

    return df

@st.cache_data(ttl=3600)
def load_sheets(today_str): # today_str é o 'trigger' de cache que muda todo dia
    # ... (Seu código para carregar as credenciais e abrir a planilha) ...
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)

    def load_sheet_as_df(sheet_name):
        try:
            # ... (Lógica de carregamento permanece a mesma) ...
            data = sh.worksheet(sheet_name).get_all_values() 
            headers = [h.strip().upper() for h in data[1]]
            df = pd.DataFrame(data[2:], columns=headers)
            df.replace('', pd.NA, inplace=True)
            df.dropna(how='all', inplace=True) 
            return safe_load(df) # Garante que safe_load é chamado para normalizar a DATA
        except Exception as e:
            st.error(f"Erro ao carregar aba {sheet_name}: {e}")
            return pd.DataFrame()

    df_alta = load_sheet_as_df("ALTA")
    df_emerg = load_sheet_as_df("EMERGENCIAL")

    return df_alta, df_emerg

def sum_between(df, start, end):
    if df.empty or "DATA" not in df.columns or "VALOR" not in df.columns:
        return 0.0

    # Normaliza a data final para incluir todo o último dia
    end_date_normalized = pd.to_datetime(end).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    mask = (df["DATA"] >= pd.to_datetime(start).normalize()) & (df["DATA"] <= end_date_normalized)
    return df.loc[mask, "VALOR"].sum()


# -----------------------
# APP (COM BOTÃO DE RECARREGAMENTO)
# -----------------------
st.sidebar.image("saritur1.png")

# CORREÇÃO CRÍTICA DO FUSO HORÁRIO
# Define o fuso horário de São Paulo, que cobre a maioria do Brasil (e Minas Gerais).
SAO_PAULO_TZ = pytz.timezone('America/Sao_Paulo')
today_date_tz = datetime.datetime.now(SAO_PAULO_TZ).date()

# Usa a data de hoje formatada como string para o argumento de cache
today_date_str = today_date_tz.isoformat() 

if st.sidebar.button("🔄 Recarregar Dados"):
    st.cache_data.clear()
    st.success("Cache limpo! Recarregando dados...")
    
# Chame a função passando a data de hoje corrigida
df_alta, df_emerg = load_sheets(today_date_str)

st.title("Sistema de Consulta de Pedidos – *ALTA* e *EMERGENCIAL*")

## 1) Pesquisa por Número de Pedido

st.subheader("🔍 Situação da Solicitação/Pedido")
pedido_input = st.text_input("Digite o número do pedido:")

def show_result(row):
    # Otimização: Garante que o VALOR seja formatado
    st.write(f"📅 **Previsão de pagamento:** {row.get('DATA').strftime('%d/%m/%Y')}") 
    st.write(f"📌 **Status:** {row.get('STATUS')}")
    st.write(f"💰 **Valor:** {br_money(row.get('VALOR'))}")
    st.write(f"🏢 **Unidade solicitante:** {row.get('UNIDADE')}")
    st.write(f"🚌 **Carro/Utilização:** {row.get('CARRO | UTILIZAÇÃO')}")
    st.write(f"📦 **Fornecedor:** {row.get('FORNECEDOR')}")
    st.write("---")


if pedido_input:
    pid = pedido_input.strip().upper() # Otimização: Padroniza para pesquisa
    
    # Otimização: Converte a coluna PEDIDO para string e padroniza para comparação
    res_alta = df_alta[df_alta["PEDIDO"].astype(str).str.strip().str.upper() == pid]
    res_emerg = df_emerg[df_emerg["PEDIDO"].astype(str).str.strip().str.upper() == pid]

    if res_alta.empty and res_emerg.empty:
        st.warning(f"❌ Pedido '{pedido_input}' não encontrado.")
    else:
        if not res_alta.empty:
            st.success("🟦 Pedido encontrado na aba ALTA")
            show_result(res_alta.iloc[0])

        if not res_emerg.empty:
            st.success("🟥 Pedido encontrado na aba EMERGENCIAL")
            show_result(res_emerg.iloc[0])

## 2) Pesquisa por Data (Layout Vertical)

st.subheader("📅 Buscar pedidos por data")
data_busca = st.date_input("Selecione a data do pedido:", key="data_busca_2")  

if data_busca:
    data_busca_dt = pd.to_datetime(data_busca).normalize()  

    # --- Filtros (Robusto contra NaT) ---
    mask_alta = pd.notna(df_alta["DATA"]) & (df_alta["DATA"] == data_busca_dt)
    alta_filtrado = df_alta[mask_alta].copy()
    
    mask_emerg = pd.notna(df_emerg["DATA"]) & (df_emerg["DATA"] == data_busca_dt)
    emerg_filtrado = df_emerg[mask_emerg].copy()

    # 3. CÁLCULOS
    total_alta = alta_filtrado["VALOR"].sum()
    total_emerg = emerg_filtrado["VALOR"].sum()
    total_geral = total_alta + total_emerg

    contagem_alta = len(alta_filtrado)
    contagem_emerg = len(emerg_filtrado)
    
    # ----------------------------------------------------
    # 4. EXIBIÇÃO DOS TOTAIS E CONTAGENS
    # ----------------------------------------------------
    
    col1, col2, col3 = st.columns(3)
    
    col1.metric(label="🟦 Total ALTA do dia", value=br_money(total_alta))
    col2.metric(label="🟥 Total EMERGENCIAL do dia", value=br_money(total_emerg))
    col3.metric(label="💰 TOTAL GERAL do dia", value=br_money(total_geral))
    
    st.info(
        f"🟦 **ALTA:** {contagem_alta} pedidos encontrados. | "
        f"🟥 **EMERGENCIAL:** {contagem_emerg} pedidos encontrados."
    )
    
    st.markdown("---")
    
    # 5. CONFIGURAÇÃO DA TABELA BASE
    COLS_BASE = ["PEDIDO", "STATUS", "UNIDADE", "CARRO | UTILIZAÇÃO", "FORNECEDOR"]

    # =================================================================
    # BLOCO 1: ALTA (Tabela + Gráfico)
    # =================================================================
    if not alta_filtrado.empty:
        # --- TABELA ALTA ---
        st.write("### 🟦 Pedidos da ALTA")
        
        # Prepara a tabela para exibição (VALOR como string formatada)
        alta_filtrado_show = alta_filtrado.copy()
        alta_filtrado_show["VALOR"] = alta_filtrado_show["VALOR"].apply(br_money)
        cols_final_alta = COLS_BASE[:1] + ["VALOR"] + COLS_BASE[1:]
        st.dataframe(alta_filtrado_show[cols_final_alta], hide_index=True)
        
        # --- GRÁFICO ALTA ---
        st.markdown("#### 📈 ALTA: Top 10 Pedidos por Valor")
        
        top_alta = alta_filtrado.sort_values(by="VALOR", ascending=False).head(10)
        
        chart_alta = alt.Chart(top_alta).mark_bar().encode(
            # Configuração do Eixo X
            x=alt.X('VALOR', 
                    title='Valor (R$)', 
                    axis=alt.Axis(format='$,.2f', grid=False)), 
            
            # Configuração do Eixo Y
            y=alt.Y('PEDIDO', 
                    sort='-x', 
                    title='Pedido/Solicitação', 
                    axis=alt.Axis(grid=False)), 
            
            tooltip=['PEDIDO', alt.Tooltip('VALOR', format='$.2f', title='Valor')]
        ).properties(
            title=data_busca_dt.strftime('%d/%m/%Y')
        ).interactive() 
        
        st.altair_chart(chart_alta, use_container_width=True)
        st.markdown("---") # Separador visual

    # =================================================================
    # BLOCO 2: EMERGENCIAL (Tabela + Gráfico)
    # =================================================================
    if not emerg_filtrado.empty:
        # --- TABELA EMERGENCIAL ---
        st.write("### 🟥 Pedidos da EMERGENCIAL")
        
        # Prepara a tabela para exibição (VALOR como string formatada)
        emerg_filtrado_show = emerg_filtrado.copy()
        emerg_filtrado_show["VALOR"] = emerg_filtrado_show["VALOR"].apply(br_money)
        cols_final_emerg = COLS_BASE[:1] + ["VALOR"] + COLS_BASE[1:]
        st.dataframe(emerg_filtrado_show[cols_final_emerg], hide_index=True)

        # --- GRÁFICO EMERGENCIAL ---
        st.markdown("#### 📈 EMERGENCIAL: Top 10 Pedidos por Valor")
        
        top_emerg = emerg_filtrado.sort_values(by="VALOR", ascending=False).head(10)
        
        chart_emerg = alt.Chart(top_emerg).mark_bar(color='red').encode(
            # Configuração do Eixo X
            x=alt.X('VALOR', 
                    title='Valor (R$)',
                    axis=alt.Axis(grid=False)), 
            
            # Configuração do Eixo Y
            y=alt.Y('PEDIDO', 
                    sort='-x', 
                    title='Pedido/Solicitação',
                    axis=alt.Axis(grid=False)), 
            
            tooltip=['PEDIDO', alt.Tooltip('VALOR', format='$.2f', title='Valor')]
        ).properties(
            title=data_busca_dt.strftime('%d/%m/%Y')
        ).interactive()
        
        st.altair_chart(chart_emerg, use_container_width=True)

## 3) Soma por Intervalo (Sidebar)

st.sidebar.header("📊 Filtro por período")

start_date = st.sidebar.date_input("Data inicial", datetime.date.today() - datetime.timedelta(days=30))
end_date = st.sidebar.date_input("Data final", datetime.date.today())

total_alta = sum_between(df_alta, start_date, end_date)
total_emerg = sum_between(df_emerg, start_date, end_date)

st.sidebar.markdown("### 💵 Totais filtrados:")
st.sidebar.success(f"ALTA: {br_money(total_alta)}") 
st.sidebar.success(f"EMERGENCIAL: {br_money(total_emerg)}")

# -----------------------------------------
# 4) ALERTAS DE STATUS (SIDEBAR)
# -----------------------------------------
st.sidebar.markdown("### 🔔 Alertas de Status - ALTA")

# 1. Definir as datas (hoje e amanhã, normalizadas)
# 'hoje' será 08/12/2025 00:00:00 (garantido pelo fuso horário)
hoje = pd.to_datetime(today_date_tz).normalize() 
data_amanha = hoje + datetime.timedelta(days=1)
data_amanha_br = data_amanha.strftime('%d/%m') # Agora será 09/12

# Inicializar contagens como 0
qtde_nao_aprovada_pendente = 0
qtde_nao_aprovada_amanha = 0
qtde_aprovada_pendente = 0
qtde_aprovada_amanha = 0

if "STATUS" in df_alta.columns and "DATA" in df_alta.columns:
    
    # 1. TRATAMENTO INICIAL
    df_alta["STATUS_CLEAN"] = df_alta["STATUS"].astype(str).str.strip().str.upper()
    
    # 2. FILTRO DE DATAS: Seleciona todas as pendências ativas (APENAS FUTURAS)
    # df["DATA"] está normalizado para 00:00:00, e 'hoje' também está normalizado.
    df_pendente_ativa = df_alta[
        (df_alta["DATA"] > hoje) &  # Filtro estritamente futuro (exclui o dia de hoje e datas passadas como 25/09)
        (pd.notna(df_alta["DATA"]))
    ].copy()
    
    # ----------------------------------------------------------------------
    # --- NÃO APROVADAS ---
    
    # 2.1. BASE PENDENTE: Filtra status 'NÃO APROVADA' na base ativa (Total estritamente Futuro)
    df_nao_aprovada_base = df_pendente_ativa[df_pendente_ativa["STATUS_CLEAN"] == "NÃO APROVADA"]
    qtde_nao_aprovada_pendente = df_nao_aprovada_base.shape[0]

    # 2.2. SUB-FILTRO AMANHÃ: Filtra data 'AMANHÃ' (09/12) na base de NÂO APROVADAS
    qtde_nao_aprovada_amanha = df_nao_aprovada_base[
        df_nao_aprovada_base["DATA"] == data_amanha
    ].shape[0]
    
    # ----------------------------------------------------------------------
    # --- APROVADAS ---
    
    # 2.1. BASE PENDENTE: Filtra status 'APROVADA' na base ativa (Total estritamente Futuro)
    df_aprovada_base = df_pendente_ativa[df_pendente_ativa["STATUS_CLEAN"] == "APROVADA"]
    qtde_aprovada_pendente = df_aprovada_base.shape[0]

    # 2.2. SUB-FILTRO AMANHÃ: Filtra data 'AMANHÃ' (09/12) na base de APROVADAS
    qtde_aprovada_amanha = df_aprovada_base[
        df_aprovada_base["DATA"] == data_amanha
    ].shape[0]


# 3. CONSTRUÇÃO E EXIBIÇÃO DOS ALERTAS (Execução Incondicional)

# --- NÃO APROVADAS (CRÍTICO) ---
mensagem_nao_aprovada = (
    f"Existem **{qtde_nao_aprovada_pendente}** solicitações NÃO APROVADAS, "
    f"sendo **{qtde_nao_aprovada_amanha}** para amanhã ({data_amanha_br}). "
    "**Favor atualizar a planilha!**"
)
st.sidebar.error(mensagem_nao_aprovada, icon="🚨")


# --- APROVADAS (ATENÇÃO) ---
mensagem_aprovada = (
    f"Existem **{qtde_aprovada_pendente}** solicitações APROVADAS, "
    f"sendo **{qtde_aprovada_amanha}** para amanhã ({data_amanha_br}). "
    "Acompanhe o processo de PEDIDO e atualize a planilha!"
)
st.sidebar.warning(mensagem_aprovada, icon="⚠️")

# --- ADICIONE ESTA SEÇÃO NO FINAL DA SUA SIDEBAR ---

st.sidebar.markdown("---") # Linha divisória sutil

# O texto será pequeno e discreto
st.sidebar.markdown(
    """
    <p style='font-size: 11px; color: #808489; text-align: center;'>
    Desenvolvido por Kerles Alves - Ass. Suprimentos
    </p>
    """,
    unsafe_allow_html=True
)