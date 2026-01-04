import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import smtplib
import os
import sys
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
from datetime import date, timedelta

# --- IMPORTAÇÃO DOS DADOS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from pages.BACKLOG import load_data, PLANILHA_NOME
except:
    st.error("Erro ao carregar BACKLOG.py")
    st.stop()

# --- TRATAMENTO DE DADOS ---

def limpar_moeda(v):
    if pd.isna(v) or v == "": return 0.0
    s = str(v).replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try: return float(s)
    except: return 0.0

def preparar_dados_consolidados(data_dict, d_inicio, d_fim):
    lista_dfs = []
    
    # Processar ALTA (Apenas Status PEDIDO)
    df_a = data_dict.get('ALTA', pd.DataFrame()).copy()
    if not df_a.empty:
        df_a['DATA_DT'] = pd.to_datetime(df_a['DATA'], dayfirst=True, errors='coerce').dt.date
        df_a = df_a[df_a['STATUS'].astype(str).str.strip().str.upper() == "PEDIDO"]
        df_a['ORIGEM'] = 'ALTA'
        lista_dfs.append(df_a)
        
    # Processar EMERGENCIAL
    df_e = data_dict.get('EMERGENCIAL', pd.DataFrame()).copy()
    if not df_e.empty:
        df_e['DATA_DT'] = pd.to_datetime(df_e['DATA'], dayfirst=True, errors='coerce').dt.date
        df_e['ORIGEM'] = 'EMERGENCIAL'
        lista_dfs.append(df_e)
        
    if not lista_dfs: return pd.DataFrame()
    
    df_total = pd.concat(lista_dfs, ignore_index=True)
    df_total['VALOR_NUM'] = df_total['VALOR'].apply(limpar_moeda)
    df_total['UNIDADE'] = df_total['UNIDADE'].astype(str).str.strip().str.upper()
    
    # Filtrar por data
    mask = (df_total['DATA_DT'] >= d_inicio) & (df_total['DATA_DT'] <= d_fim)
    df_filtrado = df_total.loc[mask]
    
    # Agrupar por Unidade e Origem
    df_grouped = df_filtrado.groupby(['UNIDADE', 'ORIGEM'])['VALOR_NUM'].sum().reset_index()
    
    return df_grouped

def gerar_grafico_ranking_empilhado(df, titulo):
    if df.empty: return None

    # Calcular o total por unidade para ordenar o ranking
    df_total_unidade = df.groupby('UNIDADE')['VALOR_NUM'].sum().sort_values(ascending=True).reset_index()
    unidades_ordenadas = df_total_unidade['UNIDADE'].tolist()
    
    total_geral = df['VALOR_NUM'].sum()
    total_formatado = f"VALOR TOTAL GERAL: R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Criar o gráfico de barras empilhadas
    fig = px.bar(
        df, 
        y='UNIDADE', 
        x='VALOR_NUM', 
        color='ORIGEM',
        orientation='h',
        title=titulo,
        # Cores específicas para as abas
        color_discrete_map={'ALTA': '#1F617E', 'EMERGENCIAL': '#942525'},
        category_orders={'UNIDADE': unidades_ordenadas},
        text='VALOR_NUM'
    )

    fig.update_traces(
        texttemplate='R$ %{text:,.2f}', 
        textposition='inside', # Valor de cada aba dentro da barra
        insidetextanchor='middle',
        textfont=dict(size=12, color="white")
    )

    # Adicionar o rótulo do valor total no final de cada barra
    for _, row in df_total_unidade.iterrows():
        fig.add_annotation(
            y=row['UNIDADE'],
            x=row['VALOR_NUM'],
            text=f" R$ {row['VALOR_NUM']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            showarrow=False,
            xanchor='left',
            font=dict(size=13, color="black", fontweight="bold")
        )

    altura_dinamica = max(500, len(unidades_ordenadas) * 50)

    fig.update_layout(
        legend_title_text='Origem do Gasto',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor="#FFFFFF", 
        plot_bgcolor="#FFFFFF", 
        font=dict(color="black"), 
        height=altura_dinamica,
        margin=dict(l=220, r=150, t=100, b=100),
        xaxis=dict(title="Valor Acumulado (R$)", showticklabels=False, showgrid=False),
        yaxis=dict(title=None, tickfont=dict(size=13)),
        # Anotação do Total no Pé do Gráfico
        annotations=[dict(
            x=0.5, y=-0.08, xref="paper", yref="paper",
            text=f"<b>{total_formatado}</b>",
            showarrow=False, font=dict(size=22, color="#106332"), align="center"
        )]
    )
    
    return fig

# --- FUNÇÃO PRINCIPAL (APP) ---

def app():
    st.title("📊 Gestão de Gastos Saritur")
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    data_inicio = st.sidebar.date_input("Início", inicio_semana)
    data_fim = st.sidebar.date_input("Fim", inicio_semana + timedelta(days=6))

    data_dict = load_data(PLANILHA_NOME)
    
    # Preparar Dados Consolidados para o novo gráfico
    df_consolidado = preparar_dados_consolidados(data_dict, data_inicio, data_fim)

    # Processamento Tabela Amanhã (Reutilizando sua lógica)
    from pages.DASHBOARD import preparar_tabela_amanha # Se estiver no mesmo arquivo, use a def local
    df_tabela_amanha = preparar_tabela_amanha(data_dict.get('ALTA', pd.DataFrame()))

    st.markdown("---")
    st.subheader(f"📅 Programação para Amanhã ({(hoje + timedelta(days=1)).strftime('%d/%m/%Y')})")
    if not df_tabela_amanha.empty:
        st.dataframe(df_tabela_amanha, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Gerar o Ranking Único
    titulo_grafico = f"Ranking de Gastos por Unidade (ALTA vs EMERGENCIAL)<br><sup>Período: {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}</sup>"
    fig_ranking = gerar_grafico_ranking_empilhado(df_consolidado, titulo_grafico)
    
    if fig_ranking:
        st.plotly_chart(fig_ranking, use_container_width=True)
    else:
        st.info("Sem dados para o período selecionado.")

    # --- LÓGICA DE ENVIO (Adaptada para o novo gráfico único) ---
    def enviar():
        try:
            user, password = st.secrets["email_user"], st.secrets["email_password"]
            msg = MIMEMultipart()
            msg['Subject'] = f"Relatório Saritur: {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}"
            msg['From'], msg['To'] = user, "kerlesalves@gmail.com"
            msg.attach(MIMEText(f"Relatório Orçamentário Consolidado.\nPeríodo: {data_inicio} a {data_fim}", 'plain'))

            if fig_ranking:
                img_bytes = fig_ranking.to_image(format="png", width=1200, height=1000)
                part = MIMEImage(img_bytes)
                part.add_header('Content-Disposition', 'attachment', filename="Ranking_Consolidado.png")
                msg.attach(part)

            # ... (Restante da lógica de anexo da tabela amanhã permanece igual ao seu código original)
            
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
            st.success("✅ Relatório enviado com sucesso!")
        except Exception as e:
            st.error(f"Erro no envio: {e}")

    if st.button("📧 ENVIAR RELATÓRIO POR E-MAIL"):
        enviar()

if __name__ == "__main__":
    app()