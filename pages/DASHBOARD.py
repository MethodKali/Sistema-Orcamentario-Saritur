import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import smtplib
import os
import sys
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

    total_num = df_f['VALOR'].apply(limpar_moeda).sum()
    linha_total = pd.DataFrame([{"DATA": "TOTAL GERAL", "UNIDADE": "---", "VALOR": br_money(total_num)}])
    return pd.concat([df_f, linha_total], ignore_index=True)

def preparar_dados_consolidados(data_dict, d_inicio, d_fim):
    lista_final = []
    for aba in ['ALTA', 'EMERGENCIAL']:
        df = data_dict.get(aba, pd.DataFrame()).copy()
        if not df.empty:
            df.columns = [str(c).strip().upper() for c in df.columns]
            df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
            mask = (df['DATA_DT'] >= d_inicio) & (df['DATA_DT'] <= d_fim)
            df_filt = df.loc[mask].copy()
            if not df_filt.empty:
                df_filt['VALOR_NUM'] = df_filt['VALOR'].apply(limpar_moeda)
                lista_final.append(df_filt[['UNIDADE', 'VALOR_NUM']].assign(ORIGEM=aba))
    return pd.concat(lista_final, ignore_index=True) if lista_final else pd.DataFrame()

def gerar_grafico_ranking(df, d_ini, d_fim):
    if df.empty: return None
    
    df_pivot = df.groupby(['UNIDADE', 'ORIGEM'])['VALOR_NUM'].sum().unstack(fill_value=0).reset_index()
    if 'ALTA' not in df_pivot.columns: df_pivot['ALTA'] = 0.0
    if 'EMERGENCIAL' not in df_pivot.columns: df_pivot['EMERGENCIAL'] = 0.0
    
    df_pivot['TOTAL'] = df_pivot['ALTA'] + df_pivot['EMERGENCIAL']
    df_pivot = df_pivot.sort_values(by='TOTAL', ascending=True)
    
    total_alta = df_pivot['ALTA'].sum()
    total_emer = df_pivot['EMERGENCIAL'].sum()
    total_geral = df_pivot['TOTAL'].sum()

    fig = go.Figure()

    # Barra de ALTA (Acima)
    fig.add_trace(go.Bar(
        y=df_pivot['UNIDADE'], x=df_pivot['ALTA'],
        name='ALTA', orientation='h',
        marker=dict(color='#1F4E79'),
        text=[br_money(v) if v > 0 else "" for v in df_pivot['ALTA']],
        textposition='outside', textfont=dict(color='black', size=11)
    ))

    # Barra de EMERGENCIAL (Abaixo)
    fig.add_trace(go.Bar(
        y=df_pivot['UNIDADE'], x=df_pivot['EMERGENCIAL'],
        name='EMERGENCIAL', orientation='h',
        marker=dict(color='#942525'),
        text=[br_money(v) if v > 0 else "" for v in df_pivot['EMERGENCIAL']],
        textposition='outside', textfont=dict(color='black', size=11)
    ))

    # Adicionando o "RESUMO" dentro da imagem (Canto Superior Direito)
    resumo_texto = (
        f"<b>RESUMO DO PERÍODO</b><br>"
        f"<span style='color:#1F4E79'>ALTA: {br_money(total_alta)}</span><br>"
        f"<span style='color:#942525'>EMERGENCIAL: {br_money(total_emer)}</span><br>"
        f"<span style='color:black'>TOTAL GERAL: {br_money(total_geral)}</span>"
    )

    fig.update_layout(
        template="plotly_white",
        barmode='group',
        bargap=0.35,
        title=f"<b>RANKING FINANCEIRO CONSOLIDADO</b><br><span style='font-size:12px;'>{d_ini.strftime('%d/%m')} a {d_fim.strftime('%d/%m')}</span>",
        height=max(600, len(df_pivot) * 80),
        margin=dict(l=220, r=180, t=120, b=80),
        xaxis=dict(visible=False),
        yaxis=dict(autorange="reversed", tickfont=dict(color='black', size=12)),
        paper_bgcolor='white',
        plot_bgcolor='white',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color='black')),
        annotations=[dict(
            x=1.1, y=1.05, xref="paper", yref="paper",
            text=resumo_texto, showarrow=False, align="right",
            font=dict(size=14), bordercolor="black", borderpad=10
        )]
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

        corpo = f"Olá, segue em anexo o relatório financeiro consolidado do período {d_ini.strftime('%d/%m')} a {d_fim.strftime('%d/%m')}."
        msg.attach(MIMEText(corpo, 'plain'))

        # Exportação em alta definição para manter textos legíveis
        img_bytes = fig.to_image(format="png", width=1400, height=fig.layout.height + 100, scale=2)
        part = MIMEImage(img_bytes)
        part.add_header('Content-Disposition', 'attachment', filename="relatorio_financeiro.png")
        msg.attach(part)

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True
    except Exception as e:
        st.sidebar.error(f"Erro no envio: {e}")
        return False

# --- APP PRINCIPAL ---

def app():
    st.set_page_config(page_title="Dashboard Saritur", layout="wide")
    st.title("📊 Dashboard Financeiro (Modelo Light)")
    
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    
    st.sidebar.header("Filtros")
    d_ini = st.sidebar.date_input("Início", inicio_semana)
    d_fim = st.sidebar.date_input("Fim", inicio_semana + timedelta(days=6))

    data_dict = load_data(PLANILHA_NOME)
    
    df_amanha = preparar_tabela_amanha(data_dict.get('ALTA', pd.DataFrame()))
    st.subheader(f"📅 Programação para Amanhã ({(hoje + timedelta(days=1)).strftime('%d/%m/%Y')})")
    if not df_amanha.empty:
        st.dataframe(df_amanha, use_container_width=True, hide_index=True)

    st.markdown("---")
    
    df_cons = preparar_dados_consolidados(data_dict, d_ini, d_fim)
    fig = gerar_grafico_ranking(df_cons, d_ini, d_fim)
    
    if fig:
        st.plotly_chart(fig, use_container_width=True)
        
        total_geral = df_cons['VALOR_NUM'].sum()
        if st.sidebar.button("📧 ENVIAR RELATÓRIO AGORA"):
            with st.sidebar.status("Gerando imagem e enviando..."):
                sucesso = enviar_relatorio_email(fig, d_ini, d_fim, total_geral)
            if sucesso: st.sidebar.success("Relatório enviado com sucesso!")
    else:
        st.warning("Sem dados para o período selecionado.")

if __name__ == "__main__":
    app()