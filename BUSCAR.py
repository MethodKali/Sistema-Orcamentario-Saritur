import streamlit as st
import pandas as pd
import datetime
import re
import altair as alt
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# -----------------------
# CONFIGURAÇÃO DE ACESSO E LIMITES
# -----------------------
import os, json
from oauth2client.service_account import ServiceAccountCredentials

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# Carrega credenciais do Streamlit Secrets
creds_dict = st.secrets["google_key"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
gc = gspread.authorize(creds)

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

@st.cache_data(ttl=300)
def load_sheets(today_str):
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
    gc = gspread.authorize(creds)
    
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error(f"Erro ao abrir a planilha. Verifique o ID e as credenciais. Erro: {e}")
        return pd.DataFrame(), pd.DataFrame()


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
        
        except Exception as e:
            st.error(f"Erro ao carregar aba {sheet_name}. Erro: {e}")
            return pd.DataFrame()

    df_alta = load_sheet_as_df("ALTA")
    df_emerg = load_sheet_as_df("EMERGENCIAL")

    return df_alta, df_emerg


def sum_between(df, start, end):
    if df.empty or COL_DATA not in df.columns or COL_VALOR not in df.columns:
        return 0.0
    
    end_date_normalized = pd.to_datetime(end).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    mask = (df[COL_DATA] >= pd.to_datetime(start).normalize()) & (df[COL_DATA] <= end_date_normalized)
    return df.loc[mask, COL_VALOR].sum()


# -----------------------
# APP STREAMLIT
# -----------------------
st.sidebar.image("saritur1.png")

SAO_PAULO_TZ = pytz.timezone('America/Sao_Paulo')
today_date_tz = datetime.datetime.now(SAO_PAULO_TZ).date()
today_date_str = today_date_tz.isoformat() 

if st.sidebar.button("🔄 Recarregar Dados"):
    st.cache_data.clear()
    st.success("Cache limpo! Recarregando dados...")
    
df_alta, df_emerg = load_sheets(today_date_str)

st.title("Sistema de Consulta de Pedidos – *ALTA* e *EMERGENCIAL*")

## 1) Pesquisa por Número de Pedido

st.subheader("🔍 Situação da Solicitação/Pedido")
pedido_input = st.text_input("Digite o número do pedido:")

def show_result(row):
    st.write(f"📅 **Previsão de pagamento:** {row.get(COL_DATA).strftime('%d/%m/%Y')}") 
    st.write(f"📌 **Status:** {row.get(COL_STATUS)}")
    st.write(f"💰 **Valor:** {br_money(row.get(COL_VALOR))}")
    st.write(f"🏢 **Unidade solicitante:** {row.get(COL_UNIDADE)}")
    st.write(f"🚌 **Carro/Utilização:** {row.get(COL_CARRO)}")
    st.write(f"📦 **Fornecedor:** {row.get(COL_FORNECEDOR)}")
    st.write("---")


if pedido_input:
    pid = pedido_input.strip().upper() 
    
    if COL_PEDIDO in df_alta.columns:
        res_alta = df_alta[df_alta[COL_PEDIDO].astype(str).str.strip().str.upper() == pid]
    else:
        res_alta = pd.DataFrame()
        
    if COL_PEDIDO in df_emerg.columns:
        res_emerg = df_emerg[df_emerg[COL_PEDIDO].astype(str).str.strip().str.upper() == pid]
    else:
        res_emerg = pd.DataFrame()


    if res_alta.empty and res_emerg.empty:
        st.warning(f"❌ Pedido '{pedido_input}' não encontrado.")
    else:
        if not res_alta.empty:
            st.success("🟦 Pedido encontrado na aba ALTA")
            show_result(res_alta.iloc[0])

        if not res_emerg.empty:
            st.success("🟥 Pedido encontrado na aba EMERGENCIAL")
            show_result(res_emerg.iloc[0])

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
    # EXIBIÇÃO DE GASTOS, LIMITES E ALERTAS
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
        
        chart_bar_emerg = alt.Chart(top_emerg).mark_bar(color='red').encode(
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


    # =================================================================
    # BLOCO 3: UNIDADES SUPRIDAS E GASTOS (LÓGICA COM FILTRO "PEDIDO" E NOVO ESTILO)
    # =================================================================
    
    # ... (Os passos 1, 2, 3 e 4 de agrupamento e soma continuam os mesmos) ...
    
    if not alta_filtrado.empty or not emerg_filtrado.empty:
        
        df_combinado = pd.concat([alta_filtrado, emerg_filtrado], ignore_index=True)
        
        df_filtrado_pedido = df_combinado[
            df_combinado[COL_STATUS].astype(str).str.strip().str.upper() == "PEDIDO"
        ].copy()
        
        
        if not df_filtrado_pedido.empty:
            
            gastos_por_unidade = df_filtrado_pedido.groupby(COL_UNIDADE)[COL_VALOR].sum().reset_index()
            gastos_por_unidade.columns = [COL_UNIDADE, "TOTAL GASTO"]
            gastos_por_unidade = gastos_por_unidade.sort_values(by="TOTAL GASTO", ascending=False)
            
            gastos_show = gastos_por_unidade.copy()
            gastos_show["TOTAL GASTO_BR"] = gastos_show["TOTAL GASTO"].apply(br_money)

            st.markdown("---") 
            st.subheader(f"🏢 Gasto por Unidade Suprida (Status: PEDIDO) em {data_busca_dt.strftime('%d/%m/%Y')}")
            
            # **NOVO ESTILO CSS**: Sem bordas e discreto
            
            # Cria a lista iterando sobre as linhas
            for index, row in gastos_show.iterrows():
                unidade = row[COL_UNIDADE]
                total_gasto = row["TOTAL GASTO_BR"]
                
                # Usamos um único bloco Markdown por linha para simplificar a formatação
                st.markdown(
                    f"""
                    <div style="display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #282828;">
                        <span style='font-size: 15px; font-weight: 500; color: white;'>
                            {unidade}
                        </span>
                        <span style='font-size: 15px; font-weight: 500; color: #AAAAAA;'>
                            {total_gasto}
                        </span>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
        
        else:
            st.info(f"Nenhum pedido com status 'PEDIDO' encontrado para calcular gastos por unidade em {data_busca_dt.strftime('%d/%m/%Y')}.")


    else:
        st.info(f"Nenhum pedido encontrado para calcular gastos por unidade em {data_busca_dt.strftime('%d/%m/%Y')}.")
## 3) Soma por Intervalo (Sidebar)

st.sidebar.header("📊 Filtro por período")

start_date = st.sidebar.date_input("Data inicial", datetime.date.today() - datetime.timedelta(days=30))
end_date = st.sidebar.date_input("Data final", datetime.date.today())

total_alta = sum_between(df_alta, start_date, end_date)
total_emerg = sum_between(df_emerg, start_date, end_date)

st.sidebar.markdown("### 💵 Totais filtrados:")
st.sidebar.success(f"ALTA: {br_money(total_alta)}") 
st.sidebar.success(f"EMERGENCIAL: {br_money(total_emerg)}")


# --- Lógica de Alertas de Status ---

st.sidebar.markdown("### 🔔 Alertas de Status - ALTA")

hoje = pd.to_datetime(today_date_tz).normalize() 
data_amanha = hoje + datetime.timedelta(days=1)
data_depois_de_amanha = hoje + datetime.timedelta(days=2) 
data_amanha_br = data_amanha.strftime('%d/%m') 

qtde_nao_aprovada_pendente = 0
qtde_nao_aprovada_amanha = 0
qtde_aprovada_pendente = 0
qtde_aprovada_amanha = 0

if COL_STATUS in df_alta.columns and COL_DATA in df_alta.columns:
    
    df_alta["STATUS_CLEAN"] = df_alta[COL_STATUS].astype(str).str.strip().str.upper()
    df_alta['DATA_ONLY'] = df_alta[COL_DATA].dt.normalize()

    df_pendente_amanha = df_alta[
        (df_alta['DATA_ONLY'] == data_amanha) & 
        (pd.notna(df_alta['DATA_ONLY']))
    ].copy()
    
    df_pendente_futuro = df_alta[
        (df_alta['DATA_ONLY'] >= data_depois_de_amanha) & 
        (pd.notna(df_alta['DATA_ONLY']))
    ].copy()
    
    
    df_nao_aprovada_amanha_base = df_pendente_amanha[df_pendente_amanha["STATUS_CLEAN"] == "NÃO APROVADA"]
    qtde_nao_aprovada_amanha = df_nao_aprovada_amanha_base.shape[0]

    df_nao_aprovada_futuro_base = df_pendente_futuro[df_pendente_futuro["STATUS_CLEAN"] == "NÃO APROVADA"]
    qtde_nao_aprovada_pendente = df_nao_aprovada_futuro_base.shape[0]
    
    
    df_aprovada_amanha_base = df_pendente_amanha[df_pendente_amanha["STATUS_CLEAN"] == "APROVADA"]
    qtde_aprovada_amanha = df_aprovada_amanha_base.shape[0]

    df_aprovada_futuro_base = df_pendente_futuro[df_pendente_futuro["STATUS_CLEAN"] == "APROVADA"]
    qtde_aprovada_pendente = df_aprovada_futuro_base.shape[0]


# CONSTRUÇÃO E EXIBIÇÃO DOS ALERTAS
mensagem_nao_aprovada = (
    f"Existem **{qtde_nao_aprovada_pendente}** solicitações NÃO APROVADAS pendentes, "
    f"sendo **{qtde_nao_aprovada_amanha}** para amanhã ({data_amanha_br}). "
    "**Favor atualizar a planilha!**"
)
st.sidebar.error(mensagem_nao_aprovada, icon="🚨")

mensagem_aprovada = (
    f"Existem **{qtde_aprovada_pendente}** solicitações APROVADAS pendentes, "
    f"sendo **{qtde_aprovada_amanha}** para amanhã ({data_amanha_br}). "
    "Acompanhe o processo de PEDIDO e atualize a planilha!"
)
st.sidebar.warning(mensagem_aprovada, icon="⚠️")

# --- Rodapé da Sidebar ---

st.sidebar.markdown("---") 

st.sidebar.markdown(
    """
    <p style='font-size: 11px; color: #808489; text-align: center;'>
    Desenvolvido por Kerles Alves - Ass. Suprimentos
    </p>
    """,
    unsafe_allow_html=True
)

st.sidebar.markdown(
    """
    <p style='font-size: 11px; color: #808489; text-align: center;'>
    Unidade Jardim Montanhês (BH) - Saritur Santa Rita Transporte Urbano e Rodoviário
    </p>
    """,
    unsafe_allow_html=True
)