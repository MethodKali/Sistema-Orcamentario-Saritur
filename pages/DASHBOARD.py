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
    """Formata valor numérico para String de moeda brasileira"""
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

    colunas_desejadas = ["DATA", "UNIDADE", "CARRO | UTILIZAÇÃO", "ITEM", "VALOR"]
    colunas_existentes = [c for c in colunas_desejadas if c in df_f.columns]
    df_f = df_f[colunas_existentes]

    total_num = df_f['VALOR'].apply(limpar_moeda).sum()
    linha_total = pd.DataFrame([{ 
        "DATA": "TOTAL GERAL", 
        "UNIDADE": "---", 
        "CARRO | UTILIZAÇÃO": "---", 
        "ITEM": "---",
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
        
        # Converte a coluna ITEM (Coluna F) para número para checar intervalo 300k-400k
        df_a['NUM_SOLIC'] = pd.to_numeric(df_a['ITEM'], errors='coerce')
        
        # Lógica: No período da semana E (Se for STATUS PEDIDO OU ID entre 300.000 e 400.000)
        mask = (
            (df_a['DATA_DT'] >= d_inicio) & (df_a['DATA_DT'] <= d_fim)
        ) & (
            (df_a['STATUS'].astype(str).str.strip().str.upper() == "PEDIDO") | 
            ((df_a['NUM_SOLIC'] >= 300000) & (df_a['NUM_SOLIC'] <= 400000))
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
    
    # Agrupar e Ordenar (Menor para Maior para o gráfico horizontal subir o ranking)
    df_plot = df.groupby(['UNIDADE', 'ORIGEM'])['VALOR_NUM'].sum().reset_index()
    df_ranking = df_plot.groupby('UNIDADE')['VALOR_NUM'].sum().sort_values(ascending=True).reset_index()
    unidades_ordem = df_ranking['UNIDADE'].tolist()
    
    total_geral = df_plot['VALOR_NUM'].sum()

    # Cores Corporativas
    cor_alta = '#1F4E79'  # Azul Sóbrio
    cor_emerg = '#C00000' # Vermelho Decisivo

    fig = px.bar(
        df_plot, 
        y='UNIDADE', 
        x='VALOR_NUM', 
        color='ORIGEM',
        orientation='h',
        color_discrete_map={'ALTA': cor_alta, 'EMERGENCIAL': cor_emerg},
        category_orders={'UNIDADE': unidades_ordem},
        template="plotly_white"
    )

    # Configurações de Traços (Barras)
    fig.update_traces(
        marker_line_color='white',
        marker_line_width=1,
        opacity=0.9
    )

    # Adicionar Rótulos de Valor na extremidade de cada barra
    for _, row in df_ranking.iterrows():
        fig.add_annotation(
            y=row['UNIDADE'], 
            x=row['VALOR_NUM'],
            text=f" <b>{br_money(row['VALOR_NUM'])}</b>",
            showarrow=False, 
            xanchor='left', 
            font=dict(size=12, color="#2c3e50")
        )

    # Layout Profissional
    fig.update_layout(
        title={
            'text': f"<b>RANKING DE INVESTIMENTO POR UNIDADE</b><br><span style='font-size:14px;color:grey;'>Período: {d_ini.strftime('%d/%m')} a {d_fim.strftime('%d/%m')}</span>",
            'y':0.95, 'x':0.05, 'xanchor': 'left', 'yanchor': 'top'
        },
        paper_bgcolor="white", 
        plot_bgcolor="white",
        height=max(500, len(unidades_ordem) * 45),
        margin=dict(l=200, r=120, t=100, b=100),
        xaxis=dict(title="Total Investido (R$)", showgrid=True, gridcolor='whitesmoke'),
        yaxis=dict(title="", tickfont=dict(size=12, color='black')),
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
        st.warning("Não há dados para os filtros selecionados.")

    # 3. Envio de E-mail
    if st.button("📧 ENVIAR RELATÓRIO"):
        try:
            user, password = st.secrets["email_user"], st.secrets["email_password"]
            msg = MIMEMultipart()
            msg['Subject'] = f"Relatório Financeiro Saritur: {d_ini.strftime('%d/%m')} a {d_fim.strftime('%d/%m')}"
            msg['From'], msg['To'] = user, "kerlesalves@gmail.com"
            msg.attach(MIMEText("Segue anexo o ranking de investimentos consolidado.", 'plain'))

            if fig_ranking:
                img = fig_ranking.to_image(format="png", width=1200, height=800)
                part = MIMEImage(img)
                part.add_header('Content-Disposition', 'attachment', filename="Ranking_Financeiro.png")
                msg.attach(part)

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
            st.success("Relatório enviado com sucesso!")
        except Exception as e:
            st.error(f"Erro no envio: {e}")

if __name__ == "__main__":
    app()