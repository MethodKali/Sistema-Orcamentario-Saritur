import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import date, timedelta

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Dashboard Saritur", layout="wide")

# --- IMPORTAÇÃO DOS DADOS (BACKLOG.py) ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from BACKLOG import load_data, PLANILHA_NOME
except ImportError:
    try:
        from pages.BACKLOG import load_data, PLANILHA_NOME
    except ImportError:
        st.error("Erro: Arquivo BACKLOG.py não encontrado.")
        st.stop()

# --- TRATAMENTO DE DADOS COM PANDAS ---
def tratar_e_filtrar(df, d_inicio, d_fim):
    if df.empty: return pd.DataFrame()
    
    df = df.copy()
    # Limpeza de nomes e conversão de valores
    df['UNIDADE'] = df['UNIDADE'].astype(str).str.strip().str.upper()
    
    # Lógica de conversão monetária brasileira
    def converter_valor(v):
        if pd.isna(v) or v == "": return 0.0
        s = str(v).replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
        try: return float(s)
        except: return 0.0

    df['VALOR_NUM'] = df['VALOR'].apply(converter_valor)
    df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
    
    # Filtro de período
    mask = (df['DATA_DT'] >= d_inicio) & (df['DATA_DT'] <= d_fim)
    df_f = df.loc[mask]
    
    # Agrupamento por Unidade (Lógica de valor gasto)
    ranking = df_f.groupby('UNIDADE')['VALOR_NUM'].sum().reset_index()
    return ranking.sort_values('VALOR_NUM', ascending=True) # Ascending True para o Plotly mostrar o maior no topo

# --- CRIAÇÃO DO GRÁFICO COM PLOTLY ---
def criar_grafico_plotly(df, titulo, cor):
    if df.empty: return None
    
    fig = px.bar(
        df, 
        x='VALOR_NUM', 
        y='UNIDADE',
        orientation='h',
        text='VALOR_NUM', # Insere o valor na frente da barra
        title=titulo
    )
    
    # Estilização "Atrativa"
    fig.update_traces(
        marker_color=cor,
        texttemplate='R$ %{text:,.2f}', # Formatação contábil
        textposition='outside',
        cliponaxis=False
    )
    
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color="white"),
        xaxis=dict(showgrid=False, visible=False),
        yaxis=dict(showgrid=False, title=""),
        margin=dict(l=20, r=100, t=50, b=20), # Espaço para o texto não cortar
        height=400
    )
    return fig

def app():
    st.title("📊 Relatório de Gastos por Unidade")
    
    # --- FILTROS NO SIDEBAR ---
    st.sidebar.header("📅 Período do Relatório")
    hoje = date.today()
    inicio_padrao = hoje - timedelta(days=hoje.weekday())
    data_inicio = st.sidebar.date_input("Data Inicial", inicio_padrao)
    data_fim = st.sidebar.date_input("Data Final", inicio_padrao + timedelta(days=6))

    # --- PROCESSAMENTO ---
    data_dict = load_data(PLANILHA_NOME)
    
    df_alta = tratar_e_filtrar(data_dict.get('ALTA', pd.DataFrame()), data_inicio, data_fim)
    df_emerg = tratar_e_filtrar(data_dict.get('EMERGENCIAL', pd.DataFrame()), data_inicio, data_fim)

    # --- VISUALIZAÇÃO NO STREAMLIT ---
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Ranking ALTA")
        fig_alta = criar_grafico_plotly(df_alta, "Gastos Semanais - ALTA", "#00A2E8")
        if fig_alta: st.plotly_chart(fig_alta, use_container_width=True)
        else: st.info("Sem dados para este período.")

    with col2:
        st.subheader("Ranking EMERGENCIAL")
        fig_emerg = criar_grafico_plotly(df_emerg, "Gastos Semanais - EMERGENCIAL", "#FF4B4B")
        if fig_emerg: st.plotly_chart(fig_emerg, use_container_width=True)
        else: st.info("Sem dados para este período.")

    # --- LÓGICA DE ENVIO DE E-MAIL ---
    def enviar_relatorio():
        try:
            user = st.secrets["email_user"]
            password = st.secrets["email_password"]
            
            msg = MIMEMultipart()
            msg['Subject'] = f"Relatório Saritur - {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}"
            msg['From'] = user
            msg['To'] = "kerlesalves@gmail.com"

            corpo = f"""
            Seguem em anexo os rankings de gastos por unidade.
            Período: {data_inicio} a {data_fim}
            """
            msg.attach(MIMEText(corpo, 'plain'))

            # Gerar PNG dos gráficos Plotly
            for fig, nome in [(fig_alta, "ALTA"), (fig_emerg, "EMERGENCIAL")]:
                if fig:
                    # Converte para imagem estática (bytes)
                    img_bytes = fig.to_image(format="png", width=800, height=500)
                    part = MIMEImage(img_bytes)
                    part.add_header('Content-Disposition', 'attachment', filename=f"Ranking_{nome}.png")
                    msg.attach(part)

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
            st.success("✅ E-mail enviado com sucesso!")
            
        except Exception as e:
            st.error(f"Erro no envio: {e}")

    st.markdown("---")
    if st.button("🚀 GERAR E ENVIAR RELATÓRIO POR E-MAIL", use_container_width=True):
        enviar_relatorio()

if __name__ == "__main__":
    app()