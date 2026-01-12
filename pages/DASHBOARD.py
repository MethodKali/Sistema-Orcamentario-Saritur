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

# --- CONFIGURAÇÕES DE PATH ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from pages.BACKLOG import load_data, PLANILHA_NOME
except:
    st.error("Erro ao carregar BACKLOG.py")
    st.stop()

# --- FUNÇÕES DE APOIO ---

def limpar_moeda(v):
    if pd.isna(v) or v == "": return 0.0
    s = str(v).replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try: return float(s)
    except: return 0.0

def br_money(valor):
    """Formata número para o padrão de moeda brasileiro"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def preparar_tabela_amanha(df_alta_orig):
    if df_alta_orig.empty: return pd.DataFrame()
    df = df_alta_orig.copy()
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
    amanha = date.today() + timedelta(days=1)
    
    mask = (df['DATA_DT'] == amanha) & (df['STATUS'].astype(str).str.strip().str.upper() != "PEDIDO")
    df_f = df.loc[mask].copy()
    
    if df_f.empty: return pd.DataFrame()

    colunas_desejadas = ["DATA", "UNIDADE", "CARRO | UTILIZAÇÃO", "PEDIDO", "VALOR"]
    colunas_existentes = [c for c in colunas_desejadas if c in df_f.columns]
    df_f = df_f[colunas_existentes]

    total_num = df_f['VALOR'].apply(limpar_moeda).sum()
    linha_total = pd.DataFrame([{ 
        "DATA": "TOTAL GERAL", 
        "UNIDADE": "---", 
        "CARRO | UTILIZAÇÃO": "---", 
        "PEDIDO": "---",
        "VALOR": br_money(total_num)
    }])
    return pd.concat([df_f, linha_total], ignore_index=True)

def preparar_dados_consolidados(data_dict, d_inicio, d_fim):
    lista_final = []
    
    # --- PROCESSAR ALTA ---
    df_a = data_dict.get('ALTA', pd.DataFrame()).copy()
    if not df_a.empty:
        df_a.columns = [str(c).strip().upper() for c in df_a.columns]
        df_a['DATA_DT'] = pd.to_datetime(df_a['DATA'], dayfirst=True, errors='coerce').dt.date
        
        # Lógica centralizada na coluna 'PEDIDO' (onde residem solicitações e pedidos)
        if 'PEDIDO' in df_a.columns:
            df_a['NUM_LOGICA'] = pd.to_numeric(df_a['PEDIDO'], errors='coerce')
            
            # FILTRO: Data correta E (Número entre 300k-400k OU 1.1M-1.3M)
            mask = (
                (df_a['DATA_DT'] >= d_inicio) & (df_a['DATA_DT'] <= d_fim)
            ) & (
                ((df_a['NUM_LOGICA'] >= 300000) & (df_a['NUM_LOGICA'] <= 400000)) | 
                ((df_a['NUM_LOGICA'] >= 1100000) & (df_a['NUM_LOGICA'] <= 1300000))
            )
            
            df_filt = df_a.loc[mask]
            if not df_filt.empty:
                lista_final.append(pd.DataFrame({
                    'UNIDADE': df_filt['UNIDADE'].astype(str).str.strip().str.upper(),
                    'VALOR_NUM': df_filt['VALOR'].apply(limpar_moeda),
                    'ORIGEM': 'ALTA'
                }))
            
    # --- PROCESSAR EMERGENCIAL ---
    df_e = data_dict.get('EMERGENCIAL', pd.DataFrame()).copy()
    if not df_e.empty:
        df_e.columns = [str(c).strip().upper() for c in df_e.columns]
        df_e['DATA_DT'] = pd.to_datetime(df_e['DATA'], dayfirst=True, errors='coerce').dt.date
        
        mask = (df_e['DATA_DT'] >= d_inicio) & (df_e['DATA_DT'] <= d_fim)
        df_filt = df_e.loc[mask]
        
        if not df_filt.empty:
            lista_final.append(pd.DataFrame({
                'UNIDADE': df_filt['UNIDADE'].astype(str).str.strip().str.upper(),
                'VALOR_NUM': df_filt['VALOR'].apply(limpar_moeda),
                'ORIGEM': 'EMERGENCIAL'
            }))
            
    if not lista_final: return pd.DataFrame()
    return pd.concat(lista_final, ignore_index=True)

def gerar_grafico_ranking(df, d_ini, d_fim):
    if df.empty: return None
    
    # Agrupar e Ordenar para o Ranking (Maiores em cima)
    df_plot = df.groupby(['UNIDADE', 'ORIGEM'])['VALOR_NUM'].sum().reset_index()
    df_ranking = df_plot.groupby('UNIDADE')['VALOR_NUM'].sum().sort_values(ascending=False).reset_index()
    unidades_ordem = df_ranking['UNIDADE'].tolist()
    
    total_geral = df_plot['VALOR_NUM'].sum()

    fig = px.bar(
        df_plot, 
        y='UNIDADE', 
        x='VALOR_NUM', 
        color='ORIGEM',
        orientation='h',
        color_discrete_map={'ALTA': '#1F4E79', 'EMERGENCIAL': '#C00000'},
        category_orders={'UNIDADE': unidades_ordem},
        template="plotly_white"
    )

    fig.update_traces(
        marker_line_color='white',
        marker_line_width=1,
        opacity=0.9
    )

    # Valores totais ao lado das barras
    for _, row in df_ranking.iterrows():
        fig.add_annotation(
            y=row['UNIDADE'], x=row['VALOR_NUM'],
            text=f" <b>{br_money(row['VALOR_NUM'])}</b>",
            showarrow=False, xanchor='left', font=dict(size=12, color="#2c3e50")
        )

    fig.update_layout(
        title={
            'text': f"<b>RANKING CONSOLIDADO DE GASTOS</b><br><span style='font-size:14px;color:grey;'>Período: {d_ini.strftime('%d/%m')} a {d_fim.strftime('%d/%m')}</span>",
            'y':0.95, 'x':0.05, 'xanchor': 'left', 'yanchor': 'top'
        },
        height=max(500, len(unidades_ordem) * 45),
        margin=dict(l=200, r=130, t=100, b=100),
        xaxis=dict(title="Investimento Total (R$)", showgrid=True, gridcolor='whitesmoke'),
        yaxis=dict(title="", tickfont=dict(size=12)),
        legend=dict(title="Origem", orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        annotations=[dict(
            x=0.5, y=-0.15, xref="paper", yref="paper",
            text=f"<b>INVESTIMENTO TOTAL NO PERÍODO: {br_money(total_geral)}</b>",
            showarrow=False, font=dict(size=18, color="#106332")
        )]
    )
    return fig

# --- APP PRINCIPAL ---

def app():
    st.title("📊 Dashboard Financeiro")
    
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    
    st.sidebar.header("Filtros")
    d_ini = st.sidebar.date_input("Início", inicio_semana)
    d_fim = st.sidebar.date_input("Fim", inicio_semana + timedelta(days=6))

    data_dict = load_data(PLANILHA_NOME)
    
    # 1. Tabela de Amanhã
    df_alta_raw = data_dict.get('ALTA', pd.DataFrame())
    df_amanha = preparar_tabela_amanha(df_alta_raw)
    
    st.subheader(f"📅 Programação para Amanhã ({(hoje + timedelta(days=1)).strftime('%d/%m/%Y')})")
    if not df_amanha.empty:
        st.dataframe(df_amanha, use_container_width=True, hide_index=True)
    else:
        st.info("Sem programação pendente para amanhã.")

    # 2. Gráfico Consolidado
    st.markdown("---")
    df_cons = preparar_dados_consolidados(data_dict, d_ini, d_fim)
    fig_ranking = gerar_grafico_ranking(df_cons, d_ini, d_fim)
    
    if fig_ranking:
        st.plotly_chart(fig_ranking, use_container_width=True)
    else:
        st.warning("Não há dados (Pedidos 1.1M-1.3M ou Solicitações 300k-400k) neste período.")

    # 3. Envio de E-mail
    if st.button("📧 ENVIAR RELATÓRIO"):
        try:
            user, password = st.secrets["email_user"], st.secrets["email_password"]
            msg = MIMEMultipart()
            msg['Subject'] = f"Relatório Financeiro Saritur: {d_ini.strftime('%d/%m')} a {d_fim.strftime('%d/%m')}"
            msg['From'], msg['To'] = user, "kerlesalves@gmail.com"
            msg.attach(MIMEText("Segue anexo o relatório de investimentos.", 'plain'))

            if fig_ranking:
                img = fig_ranking.to_image(format="png", width=1200, height=800)
                part = MIMEImage(img)
                part.add_header('Content-Disposition', 'attachment', filename="Ranking.png")
                msg.attach(part)

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
            st.success("Relatório enviado!")
        except Exception as e:
            st.error(f"Erro no envio: {e}")

if __name__ == "__main__":
    app()