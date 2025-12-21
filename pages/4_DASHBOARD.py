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
    
    # Limpeza de espaços e padronização de nomes para evitar duplicatas por erro de digitação
    df['UNIDADE'] = df['UNIDADE'].astype(str).str.strip().str.upper()
    df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
    
    def limpar_moeda(v):
        if pd.isna(v) or v == "": return 0.0
        s = str(v).replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
        try: return float(s)
        except: return 0.0

    df['VALOR_NUM'] = df['VALOR'].apply(limpar_moeda)
    
    # Filtro de data
    mask = (df['DATA_DT'] >= d_inicio) & (df['DATA_DT'] <= d_fim)
    df_filtrado = df.loc[mask]
    
    # Agrupamento e Soma (Garante que unidades iguais sejam somadas)
    ranking = df_filtrado.groupby('UNIDADE')['VALOR_NUM'].sum().reset_index()
    return ranking.sort_values('VALOR_NUM', ascending=True)

def gerar_figura(df, titulo, cor):
    if df.empty: return None
    
    # Altura dinâmica: mais barras = gráfico mais alto para não espremer as barras
    altura_dinamica = max(450, len(df) * 45)
    
    fig = px.bar(df, x='VALOR_NUM', y='UNIDADE', orientation='h', 
                 text='VALOR_NUM', title=titulo)
    
    fig.update_traces(
        marker_color=cor,
        texttemplate='R$ %{text:,.2f}', 
        textposition='outside',
        cliponaxis=False,
        textfont=dict(color="white", size=13)
    )
    
    fig.update_layout(
        paper_bgcolor="#FFFFFF", 
        plot_bgcolor="#FFFFFF",
        font=dict(color="white"),
        height=altura_dinamica,
        
        # Margem esquerda aumentada para nomes longos como "JARDIM MONTANHÊS"
        margin=dict(l=220, r=120, t=80, b=50), 
        
        yaxis=dict(
            title=None, 
            automargin=True,
            tickfont=dict(color="white", size=13),
            categoryorder='total ascending',
            dtick=1 # Garante que cada nome de unidade apareça
        ),
        
        xaxis=dict(
            visible=False, 
            # Define o limite do eixo X com folga para o texto do valor não ser cortado
            range=[0, df['VALOR_NUM'].max() * 1.4] 
        ),
        
        title=dict(x=0.5, font=dict(size=22))
    )
    return fig

def app():
    st.title("📊 Gestão de Gastos Saritur")
    
    # --- FILTROS NO SIDEBAR ---
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    data_inicio = st.sidebar.date_input("Início", inicio_semana)
    data_fim = st.sidebar.date_input("Fim", inicio_semana + timedelta(days=6))

    # --- PROCESSAMENTO DOS DADOS ---
    data_dict = load_data(PLANILHA_NOME)
    
    # 1. Ranking ALTA (Filtrado por status "PEDIDO")
    df_alta_raw = data_dict.get('ALTA', pd.DataFrame())
    if not df_alta_raw.empty:
        # Aplicação do filtro de status antes do processamento de valores
        df_alta_raw = df_alta_raw[df_alta_raw['STATUS'].astype(str).str.strip().str.upper() == "PEDIDO"]
    df_alta = preparar_dados_plotly(df_alta_raw, data_inicio, data_fim)

    # 2. Ranking EMERGENCIAL (Sem filtro de status)
    df_emerg = preparar_dados_plotly(data_dict.get('EMERGENCIAL', pd.DataFrame()), data_inicio, data_fim)

    # 3. Gráfico CONSOLIDADO (Soma ALTA + EMERGENCIAL)
    df_total = pd.concat([df_alta, df_emerg], ignore_index=True)
    if not df_total.empty:
        # Re-agrupa para somar unidades que aparecem em ambas as abas
        df_total = df_total.groupby('UNIDADE')['VALOR_NUM'].sum().reset_index()
        df_total = df_total.sort_values('VALOR_NUM', ascending=True)

    # --- EXIBIÇÃO NA TELA ---
# --- EXIBIÇÃO NA TELA (UM EMBAIXO DO OUTRO) ---
    st.markdown("---")
    
    # 1. Gráfico Total Consolidado (Destaque no topo)
    st.subheader("📊 Visão Geral Consolidada")
    fig_total = gerar_figura(df_total, "Total Gasto na ALTA e EMERGENCIAL", "#106332")
    if fig_total:
        st.plotly_chart(fig_total, use_container_width=True)
    else:
        st.info("Sem dados consolidados para o período.")

    st.markdown("---")

    # 2. Ranking ALTA (Agora ocupando a largura total)
    st.subheader("🔵 Detalhamento ALTA")
    fig_a = gerar_figura(df_alta, "Ranking ALTA (Status: PEDIDO)", "#1F617E")
    if fig_a: 
        st.plotly_chart(fig_a, use_container_width=True)
    else:
        st.warning("Sem dados para a aba ALTA com status 'PEDIDO'.")

    st.markdown("---")

    # 3. Ranking EMERGENCIAL (Agora ocupando a largura total)
    st.subheader("🔴 Detalhamento EMERGENCIAL")
    fig_e = gerar_figura(df_emerg, "Ranking EMERGENCIAL", "#942525")
    if fig_e: 
        st.plotly_chart(fig_e, use_container_width=True)
    else:
        st.warning("Sem dados para a aba EMERGENCIAL.")    
        st.plotly_chart(fig_e, use_container_width=True)

    # --- FUNÇÃO DE ENVIO DE E-MAIL ---
    def enviar():
        try:
            user = st.secrets["email_user"]
            password = st.secrets["email_password"]
            
            msg = MIMEMultipart()
            msg['Subject'] = f"Relatório Saritur: {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}"
            msg['From'] = user
            msg['To'] = "kerlesalves@gmail.com"
            
            corpo = f"Seguem em anexo os rankings de gastos por unidade.\nPeríodo: {data_inicio} a {data_fim}"
            msg.attach(MIMEText(corpo, 'plain'))

            # Lista de gráficos para anexo
            graficos = [
                (fig_total, "Total_Consolidado"),
                (fig_a, "Ranking_ALTA"),
                (fig_e, "Ranking_EMERGENCIAL")
            ]

            for fig, nome in graficos:
                if fig:
                    try:
                        # Converte a figura Plotly para imagem estática (PNG)
                        img_bytes = fig.to_image(format="png", width=1000, height=800)
                        part = MIMEImage(img_bytes)
                        part.add_header('Content-Disposition', 'attachment', filename=f"{nome}.png")
                        msg.attach(part)
                    except Exception as e:
                        st.error(f"Erro ao anexar imagem {nome}: {e}")

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
            st.success("✅ Relatório enviado com sucesso!")
        except Exception as e:
            st.error(f"Falha no envio do e-mail: {e}")

    st.markdown("---")
    if st.button("📧 ENVIAR RELATÓRIO POR E-MAIL"):
        enviar()

if __name__ == "__main__":
    app()