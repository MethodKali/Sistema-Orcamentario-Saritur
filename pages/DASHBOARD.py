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
    s = str(v).replace("R$", "").strip()
    try:
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except:
        return 0.0

def br_money(valor):
    """Formata número para o padrão de moeda brasileiro R$ 0.000,00"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def preparar_tabela_amanha(df_alta_orig):
    if df_alta_orig.empty: return pd.DataFrame()
    df = df_alta_orig.copy()
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
    amanha = date.today() + timedelta(days=1)
    
    mask = (df['DATA_DT'] == amanha)
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
    
    # ALTA
    df_a = data_dict.get('ALTA', pd.DataFrame()).copy()
    if not df_a.empty:
        df_a.columns = [str(c).strip().upper() for c in df_a.columns]
        df_a['DATA_DT'] = pd.to_datetime(df_a['DATA'], dayfirst=True, errors='coerce').dt.date
        
        if 'PEDIDO' in df_a.columns:
            df_a['NUM_LOGICA'] = pd.to_numeric(df_a['PEDIDO'], errors='coerce')
            mask_num = (df_a['NUM_LOGICA'].notna()) & (
                ((df_a['NUM_LOGICA'] >= 300000) & (df_a['NUM_LOGICA'] <= 400000)) | 
                ((df_a['NUM_LOGICA'] >= 1100000) & (df_a['NUM_LOGICA'] <= 1300000))
            )
            mask_txt = (df_a['NUM_LOGICA'].isna()) & (df_a['PEDIDO'].astype(str).str.strip() != "")
            mask_data = (df_a['DATA_DT'] >= d_inicio) & (df_a['DATA_DT'] <= d_fim)
            df_filt = df_a.loc[mask_data & (mask_num | mask_txt)].copy()
            
            if not df_filt.empty:
                df_filt['VALOR_NUM'] = df_filt['VALOR'].apply(limpar_moeda)
                lista_final.append(df_filt[['UNIDADE', 'VALOR_NUM']].assign(ORIGEM='ALTA'))

    # EMERGENCIAL
    df_e = data_dict.get('EMERGENCIAL', pd.DataFrame()).copy()
    if not df_e.empty:
        df_e.columns = [str(c).strip().upper() for c in df_e.columns]
        df_e['DATA_DT'] = pd.to_datetime(df_e['DATA'], dayfirst=True, errors='coerce').dt.date
        mask_data_e = (df_e['DATA_DT'] >= d_inicio) & (df_e['DATA_DT'] <= d_fim)
        df_filt_e = df_e.loc[mask_data_e].copy()
        if not df_filt_e.empty:
            df_filt_e['VALOR_NUM'] = df_filt_e['VALOR'].apply(limpar_moeda)
            lista_final.append(df_filt_e[['UNIDADE', 'VALOR_NUM']].assign(ORIGEM='EMERGENCIAL'))
            
    if not lista_final: return pd.DataFrame()
    df_res = pd.concat(lista_final, ignore_index=True)
    df_res['UNIDADE'] = df_res['UNIDADE'].str.strip().str.upper()
    return df_res

def gerar_grafico_ranking(df, d_ini, d_fim):
    if df.empty: return None
    
    # Agrupa e pivota
    df_pivot = df.groupby(['UNIDADE', 'ORIGEM'])['VALOR_NUM'].sum().unstack(fill_value=0).reset_index()
    
    # Garante que as colunas existam para evitar o erro do "get"
    if 'ALTA' not in df_pivot.columns: df_pivot['ALTA'] = 0.0
    if 'EMERGENCIAL' not in df_pivot.columns: df_pivot['EMERGENCIAL'] = 0.0
    
    df_pivot['TOTAL'] = df_pivot['ALTA'] + df_pivot['EMERGENCIAL']
    df_pivot = df_pivot.sort_values(by='TOTAL', ascending=True)
    
    total_geral = df_pivot['TOTAL'].sum()

    fig = go.Figure()

    # Barra de ALTA (superior)
    fig.add_trace(go.Bar(
        y=df_pivot['UNIDADE'], x=df_pivot['ALTA'],
        name='ALTA', orientation='h',
        marker=dict(color='#1F4E79'),
        text=[br_money(v) if v > 0 else "" for v in df_pivot['ALTA']],
        textposition='inside', insidetextanchor='end'
    ))

    # Barra de EMERGENCIAL (inferior)
    fig.add_trace(go.Bar(
        y=df_pivot['UNIDADE'], x=df_pivot['EMERGENCIAL'],
        name='EMERGENCIAL', orientation='h',
        marker=dict(color='#942525'),
        text=[br_money(v) if v > 0 else "" for v in df_pivot['EMERGENCIAL']],
        textposition='inside', insidetextanchor='end'
    ))

    fig.update_layout(
        template="plotly_dark",
        barmode='group',
        bargap=0.2,
        title=f"<b>RANKING FINANCEIRO CONSOLIDADO</b><br><span style='font-size:12px;'>Período: {d_ini.strftime('%d/%m')} a {d_fim.strftime('%d/%m')}</span>",
        height=max(500, len(df_pivot) * 60),
        margin=dict(l=200, r=50, t=100, b=100),
        xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', visible=False),
        paper_bgcolor='#0E1117',
        plot_bgcolor='#0E1117',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    # Label de valor TOTAL à direita
    for _, row in df_pivot.iterrows():
        fig.add_annotation(
            y=row['UNIDADE'], x=row['TOTAL'],
            text=f" <b>{br_money(row['TOTAL'])}</b>",
            showarrow=False, xanchor='left', font=dict(color="#00FF7F", size=12)
        )

    return fig

# --- ENVIO DE EMAIL ---

def enviar_relatorio_email(fig, d_ini, d_fim, total_valor):
    try:
        user = st.secrets["email_user"]
        password = st.secrets["email_password"]
        destinatario = "kerlesalves@gmail.com"

        msg = MIMEMultipart()
        msg['Subject'] = f"Relatório Financeiro Saritur: {d_ini.strftime('%d/%m')} a {d_fim.strftime('%d/%m')}"
        msg['From'], msg['To'] = user, destinatario

        corpo = f"Segue anexo o ranking de investimentos ({d_ini.strftime('%d/%m')} a {d_fim.strftime('%d/%m')}).\nTotal: {br_money(total_valor)}"
        msg.attach(MIMEText(corpo, 'plain'))

        # Exportação mantendo fundo para visualização profissional
        img_bytes = fig.to_image(format="png", width=1200, height=max(800, fig.layout.height), scale=2)
        part = MIMEImage(img_bytes)
        part.add_header('Content-Disposition', 'attachment', filename="ranking.png")
        msg.attach(part)

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True
    except Exception as e:
        st.sidebar.error(f"Erro: {e}")
        return False

# --- APP PRINCIPAL ---

def app():
    st.set_page_config(page_title="Dashboard Saritur", layout="wide")
    st.title("📊 Dashboard Financeiro")
    
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    
    st.sidebar.header("Filtros")
    d_ini = st.sidebar.date_input("Início", inicio_semana)
    d_fim = st.sidebar.date_input("Fim", inicio_semana + timedelta(days=6))

    data_dict = load_data(PLANILHA_NOME)
    
    # 1. Tabela de Amanhã
    df_amanha = preparar_tabela_amanha(data_dict.get('ALTA', pd.DataFrame()))
    st.subheader(f"📅 Programação para Amanhã ({(hoje + timedelta(days=1)).strftime('%d/%m/%Y')})")
    if not df_amanha.empty:
        st.dataframe(df_amanha, use_container_width=True, hide_index=True)
    else:
        st.info("Sem programação para amanhã.")

    st.markdown("---")
    
    # 2. Gráfico
    df_cons = preparar_dados_consolidados(data_dict, d_ini, d_fim)
    fig = gerar_grafico_ranking(df_cons, d_ini, d_fim)
    
    col_graf, col_met = st.columns([3, 1])
    
    with col_graf:
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Sem dados no período.")
            
    with col_met:
        if not df_cons.empty:
            st.subheader("Resumo")
            resumo = df_cons.groupby('ORIGEM')['VALOR_NUM'].sum()
            for origem, valor in resumo.items():
                st.metric(origem, br_money(valor))
            
            total_geral = df_cons['VALOR_NUM'].sum()
            st.metric("TOTAL GERAL", br_money(total_geral))

            if st.sidebar.button("📧 ENVIAR RELATÓRIO"):
                with st.sidebar.status("Enviando..."):
                    sucesso = enviar_relatorio_email(fig, d_ini, d_fim, total_geral)
                if sucesso: st.sidebar.success("Relatório enviado!")

if __name__ == "__main__":
    app()