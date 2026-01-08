import streamlit as st
import pandas as pd
import pymssql  # Ou pyodbc
from datetime import datetime

# --- CONEXÃO COM O BANCO DE DADOS ---
def get_db_connection():
    db_config = st.secrets["database"]
    return pymssql.connect(
        server=db_config["server"],
        user=db_config["username"],
        password=db_config["password"],
        database=db_config["database"]
    )

def consulta_sql(numero, tipo):
    conn = get_db_connection()
    # Ajuste do filtro WHERE conforme o tipo de busca
    filtro_id = "NUMEROSOLIC" if tipo == "SOLICITACAO" else "NUMEROPEDIDO"
    
    query = f"""
    SELECT DISTINCT
        CAST (FACT_CPR_SOLIC_COTACAO_PEDIDO.NUMEROSOLIC AS NVARCHAR (20)) AS NUM_SOLIC,
        CAST (FACT_CPR_SOLIC_COTACAO_PEDIDO.NUMEROPEDIDO AS NVARCHAR (20)) AS NUM_PEDIDO,
        CAST (FACT_CPR_SOLIC_COTACAO_PEDIDO.NUMEROCOTACAO AS NVARCHAR(20)) AS NUM_COTACAO,
        CAST (FACT_CPR_PEDIDO.NUMERONF AS NVARCHAR(20)) AS NUM_NF,
        CAST (FACT_CPR_SOLIC_COTACAO_PEDIDO.DATASOLIC AS DATETIME) AS DATASOLIC,
        CAST (FACT_CPR_SOLIC_COTACAO_PEDIDO.DATA_APROVACAO AS DATETIME) AS DATAAPROVACAO
    FROM FACT_CPR_SOLIC_COTACAO_PEDIDO
    LEFT JOIN
        FACT_CPR_PEDIDO ON FACT_CPR_SOLIC_COTACAO_PEDIDO.NUMEROPEDIDO = FACT_CPR_PEDIDO.NUMEROPEDIDO
    WHERE FACT_CPR_SOLIC_COTACAO_PEDIDO.{filtro_id} = '{numero}'
    AND DATASOLIC > '2025-01-01'
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# --- INTERFACE ---
st.title("🔍 Consulta de Status Real-Time")
st.markdown("Consulte o andamento de solicitações e pedidos diretamente no ERP.")

busca = st.text_input("Digite o número da Solicitação ou Pedido", placeholder="Ex: 305400 ou 1120500")

if busca:
    # Validação dos intervalos
    try:
        num_int = int(busca)
        is_solic = 300000 <= num_int <= 400000
        is_ped = 1100000 <= num_int <= 1300000
    except:
        st.error("Por favor, digite apenas números.")
        st.stop()

    if not (is_solic or is_ped):
        st.warning("Número fora dos intervalos permitidos (Solicitação: 300k-400k | Pedido: 1.1M-1.3M).")
    else:
        tipo_busca = "SOLICITACAO" if is_solic else "PEDIDO"
        with st.spinner(f"Consultando {tipo_busca} no Banco de Dados..."):
            df_res = consulta_sql(busca, tipo_busca)

        if df_res.empty:
            st.info(f"Nenhum registro encontrado para o número {busca}.")
        else:
            # --- LÓGICA DE EXIBIÇÃO: SOLICITAÇÃO ---
            if tipo_busca == "SOLICITACAO":
                # Como uma solicitação pode ter vários pedidos, pegamos a primeira linha para dados gerais
                row = df_res.iloc[0]
                
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.subheader(f"📝 Solicitação: {row['NUM_SOLIC']}")
                    
                    # Tag de Aprovação
                    aprovada = pd.notna(row['DATAAPROVACAO'])
                    status_cor = "green" if aprovada else "red"
                    status_txt = "APROVADA" if aprovada else "NÃO APROVADA"
                    col2.markdown(f"**<p style='color:{status_cor}; text-align:right;'>{status_txt}</p>**", unsafe_allow_html=True)
                    
                    st.divider()
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Data Solicitação", row['DATASOLIC'].strftime('%d.%m.%Y') if pd.notna(row['DATASOLIC']) else "---")
                    
                    # Data Aprovação
                    dt_aprov = row['DATAAPROVACAO'].strftime('%d.%m.%Y') if aprovada else "Pendente"
                    c2.metric("Data Aprovação", dt_aprov)
                    
                    # Tag Cotação
                    tem_cotacao = pd.notna(row['NUM_COTACAO']) and str(row['NUM_COTACAO']).strip() != ""
                    if tem_cotacao:
                        c3.markdown(f"📦 **Cotação:** `{row['NUM_COTACAO']}`")
                        c3.markdown(":material/check_circle: **STATUS: COTAÇÃO**")

                    st.markdown("---")
                    st.write("**Pedidos Gerados:**")
                    # Lista de pedidos únicos ignorando nulos
                    pedidos = df_res['NUM_PEDIDO'].dropna().unique().tolist()
                    pedidos = [p for p in pedidos if str(p).strip() != "None" and str(p).strip() != ""]
                    
                    if pedidos:
                        for p in pedidos:
                            st.info(f"🛒 Pedido Gerado: **{p}**")
                    else:
                        st.warning("⚠️ Não há pedidos gerados para esta solicitação.")

            # --- LÓGICA DE EXIBIÇÃO: PEDIDO ---
            else:
                row = df_res.iloc[0]
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.subheader(f"🛒 Pedido: {row['NUM_PEDIDO']}")
                    
                    # Tag de Entrega (NF)
                    entregue = pd.notna(row['NUM_NF']) and str(row['NUM_NF']).strip() != ""
                    status_cor = "green" if entregue else "orange"
                    status_txt = "ENTREGUE" if entregue else "NÃO ENTREGUE"
                    col2.markdown(f"**<p style='color:{status_cor}; text-align:right;'>{status_txt}</p>**", unsafe_allow_html=True)
                    
                    st.divider()
                    
                    c1, c2 = st.columns(2)
                    c1.markdown(f"📄 **NF:** `{row['NUM_NF'] if entregue else 'Aguardando...'}`")
                    c2.markdown(f"📝 **Solicitação Origem:** `{row['NUM_SOLIC']}`")