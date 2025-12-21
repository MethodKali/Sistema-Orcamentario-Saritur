import streamlit as st
import pandas as pd
import altair as alt
import re
import smtplib
import sys
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, timedelta

# --- CORREÇÃO DE IMPORTAÇÃO ---
# Se o arquivo BACKLOG.py estiver na raiz, usamos o path hack:
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    # Se o BACKLOG.py estiver na pasta pages, use 'from BACKLOG import...'
    # Se estiver na raiz e você usou o sys.path.append, use apenas 'import BACKLOG'
    from BACKLOG import load_data, PLANILHA_NOME
except ImportError:
    try:
        from pages.BACKLOG import load_data, PLANILHA_NOME
    except ImportError:
        st.error("Erro crítico: Arquivo BACKLOG.py não encontrado.")
        st.stop()

# --- UTILITÁRIOS ---
def valor_brasileiro(valor):
    if pd.isna(valor) or valor is None: return 0.0
    s = str(valor).strip()
    s = re.sub(r"[R$\s\.]", "", s).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

def br_money(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- LÓGICA DO DASHBOARD ---

def app():
    st.title("📊 Dashboard Orçamentário Semanal")
    st.markdown("---")

    # Filtros de Data (Sidebar)
    st.sidebar.header("📅 Filtro de Período")
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    fim_semana = inicio_semana + timedelta(days=6)

    data_inicio = st.sidebar.date_input("Início da Semana", inicio_semana)
    data_fim = st.sidebar.date_input("Fim da Semana", fim_semana)

    # Carregamento de Dados
    with st.spinner("Carregando dados da Planilha..."):
        data_dict = load_data(PLANILHA_NOME)

    if not data_dict:
        st.error("Erro ao carregar dados.")
        return

    # Processamento dos Rankings
    def preparar_ranking(aba_nome):
        df = data_dict.get(aba_nome, pd.DataFrame())
        if df.empty: return pd.DataFrame()
        df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
        df['VALOR_NUM'] = df['VALOR'].apply(valor_brasileiro)
        mask = (df['DATA_DT'] >= data_inicio) & (df['DATA_DT'] <= data_fim)
        df_filtrado = df.loc[mask].copy()
        if df_filtrado.empty: return pd.DataFrame()
        return df_filtrado.groupby('UNIDADE')['VALOR_NUM'].sum().reset_index().sort_values('VALOR_NUM', ascending=False)

    df_alta_rank = preparar_ranking('ALTA')
    df_emerg_rank = preparar_ranking('EMERGENCIAL')

    # Exibição dos Gráficos
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🟦 Ranking ALTA")
        if not df_alta_rank.empty:
            chart = alt.Chart(df_alta_rank).mark_bar(color='#4285F4').encode(
                x=alt.X('VALOR_NUM:Q', title='Gasto (R$)'),
                y=alt.Y('UNIDADE:N', sort='-x', title='Unidade'),
                tooltip=['UNIDADE', alt.Tooltip('VALOR_NUM:Q', format=',.2f')]
            ).properties(height=350)
            st.altair_chart(chart, use_container_width=True)
        else: st.warning("Sem dados: ALTA")

    with col2:
        st.subheader("🟥 Ranking EMERGENCIAL")
        if not df_emerg_rank.empty:
            chart = alt.Chart(df_emerg_rank).mark_bar(color='#EA4335').encode(
                x=alt.X('VALOR_NUM:Q', title='Gasto (R$)'),
                y=alt.Y('UNIDADE:N', sort='-x', title='Unidade'),
                tooltip=['UNIDADE', alt.Tooltip('VALOR_NUM:Q', format=',.2f')]
            ).properties(height=350)
            st.altair_chart(chart, use_container_width=True)
        else: st.warning("Sem dados: EMERGENCIAL")

    st.markdown("---")

    # --- FUNÇÃO DE E-MAIL ---
    def enviar_email(automatico=False):
        try:
            # Busca as chaves nos Secrets
            remetente = st.secrets["email_user"]
            senha = st.secrets["email_password"]
            destinatario = "kerlesalves@gmail.com"

            t_alta = df_alta_rank['VALOR_NUM'].sum() if not df_alta_rank.empty else 0
            t_emerg = df_emerg_rank['VALOR_NUM'].sum() if not df_emerg_rank.empty else 0

            corpo = f"""
            Relatório Orçamentário Semanal {data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}
            
            Total ALTA: {br_money(t_alta)}
            Total EMERGENCIAL: {br_money(t_emerg)}
            Total Geral: {br_money(t_alta + t_emerg)}
            
            Enviado via: {'Automação de Domingo' if automatico else 'Botão Manual'}
            """

            msg = MIMEMultipart()
            msg['From'] = remetente
            msg['To'] = destinatario
            msg['Subject'] = f"Relatório Orçamentário Semanal {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}"
            msg.attach(MIMEText(corpo, 'plain'))

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(remetente, senha)
                server.send_message(msg)
            
            if not automatico: st.success("✅ Relatório enviado com sucesso!")
            return True
        except Exception as e:
            if not automatico: st.error(f"❌ Erro: {e}")
            return False

    # Botão de Envio Manual
    if st.button("📧 ENVIAR RELATÓRIO AGORA", use_container_width=True):
        enviar_email()

    # --- 5. LÓGICA DE AUTOMAÇÃO (DOMINGO) ---
    # Para testar, você pode mudar o número 6 para o número do dia de hoje
    # 0=Segunda, 1=Terça, ..., 5=Sábado, 6=Domingo
    if hoje.weekday() == 6:
        # Usamos session_state para garantir que ele envie apenas uma vez enquanto a página estiver aberta
        if 'email_enviado_hoje' not in st.session_state:
            sucesso = enviar_email(automatico=True)
            if sucesso:
                st.session_state['email_enviado_hoje'] = True
                st.info("ℹ️ Relatório automático de Domingo enviado.")

if __name__ == "__main__":
    app()