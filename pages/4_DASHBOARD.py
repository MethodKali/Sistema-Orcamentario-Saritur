import streamlit as st
import pandas as pd
import plotly.express as px
import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import date, timedelta

# --- IMPORTAÇÃO DOS DADOS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from pages.BACKLOG import load_data, PLANILHA_NOME
except:
    st.error("Erro ao carregar BACKLOG.py")
    st.stop()

# --- TRATAMENTO DE DADOS (PANDAS) ---
def preparar_dados_plotly(df, d_inicio, d_fim):
    if df.empty: return pd.DataFrame()
    df = df.copy()
    
    # Limpeza e Conversão
    df['UNIDADE'] = df['UNIDADE'].astype(str).str.strip().str.upper()
    df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
    
    def limpar_moeda(v):
        if pd.isna(v) or v == "": return 0.0
        s = str(v).replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
        try: return float(s)
        except: return 0.0

    df['VALOR_NUM'] = df['VALOR'].apply(limpar_moeda)
    
    # Filtro e Agrupamento
    mask = (df['DATA_DT'] >= d_inicio) & (df['DATA_DT'] <= d_fim)
    ranking = df.loc[mask].groupby('UNIDADE')['VALOR_NUM'].sum().reset_index()
    return ranking.sort_values('VALOR_NUM', ascending=True)

def gerar_figura(df, titulo, cor):
    if df.empty: return None
    
    # Criando o gráfico
    fig = px.bar(df, x='VALOR_NUM', y='UNIDADE', orientation='h', 
                 text='VALOR_NUM', title=titulo)
    
    fig.update_traces(
        marker_color=cor,
        texttemplate='R$ %{text:,.2f}', 
        textposition='outside',
        cliponaxis=False,
        textfont=dict(color="white") # Garante que o valor seja branco
    )
    
    fig.update_layout(
        # Define a cor do fundo (área do gráfico e área externa)
        paper_bgcolor='#111111', 
        plot_bgcolor='#111111',
        
        font=dict(color="white"), # Cor da fonte do título e eixos
        title=dict(font=dict(size=20, color="white")),
        
        xaxis=dict(
            visible=False, 
            showgrid=False, 
            range=[0, df['VALOR_NUM'].max() * 1.3] # Espaço para o texto não cortar
        ),
        yaxis=dict(
            title=None, 
            tickfont=dict(color="white", size=12),
            showgrid=False
        ),
        margin=dict(l=20, r=100, t=60, b=20),
        height=450
    )
    return fig
def app():
    st.title("📊 Gestão de Gastos Saritur")
    
    # Filtros
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    data_inicio = st.sidebar.date_input("Início", inicio_semana)
    data_fim = st.sidebar.date_input("Fim", inicio_semana + timedelta(days=6))

    # Processamento
    data_dict = load_data(PLANILHA_NOME)
    df_alta = preparar_dados_plotly(data_dict.get('ALTA', pd.DataFrame()), data_inicio, data_fim)
    df_emerg = preparar_dados_plotly(data_dict.get('EMERGENCIAL', pd.DataFrame()), data_inicio, data_fim)

    # Exibição na Tela
    col1, col2 = st.columns(2)
    with col1:
        fig_a = gerar_figura(df_alta, "Ranking ALTA", "#00A2E8")
        if fig_a: st.plotly_chart(fig_a, use_container_width=True)
    with col2:
        fig_e = gerar_figura(df_emerg, "Ranking EMERGENCIAL", "#FF4B4B")
        if fig_e: st.plotly_chart(fig_e, use_container_width=True)

    # Função de E-mail
    def enviar():
        try:
            user = st.secrets["email_user"]
            password = st.secrets["email_password"]
            
            msg = MIMEMultipart()
            msg['Subject'] = f"Relatório Saritur: {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}"
            msg['From'] = user
            msg['To'] = "kerlesalves@gmail.com"
            
            msg.attach(MIMEText(f"Relatório de gastos por unidade.\nPeríodo: {data_inicio} a {data_fim}", 'plain'))

            for fig, nome in [(fig_a, "ALTA"), (fig_e, "EMERGENCIAL")]:
                if fig:
                    # Tenta gerar a imagem. Se o Kaleido der erro de Chrome, 
                    # ele avisa mas não trava o envio do texto.
                    try:
                        img_bytes = fig.to_image(format="png")
                        part = MIMEImage(img_bytes)
                        part.add_header('Content-Disposition', 'attachment', filename=f"{nome}.png")
                        msg.attach(part)
                    except Exception as e:
                        st.error(f"Erro ao gerar imagem {nome}: {e}")

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
            st.success("✅ Enviado!")
        except Exception as e:
            st.error(f"Falha: {e}")

    if st.button("📧 ENVIAR AGORA"):
        enviar()

if __name__ == "__main__":
    app()