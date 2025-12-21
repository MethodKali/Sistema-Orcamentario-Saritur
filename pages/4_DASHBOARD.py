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
# Garante que o Python encontre o BACKLOG.py na pasta de cima
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from pages.BACKLOG import load_data, PLANILHA_NOME
except ImportError:
    st.error("Não foi possível encontrar o arquivo BACKLOG.py na raiz do projeto.")
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

# ... restante do código do Dashboard ...
def br_money(valor):
    """Formata float para R$ 1.234,56"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- 2. LOGICA PRINCIPAL ---

def app():
    st.title("📊 Dashboard Orçamentário Semanal")
    st.markdown("---")

    # Filtros de Data
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
        st.error("Erro ao carregar dados. Verifique a conexão com o Google Sheets.")
        return

    # Processamento para os Gráficos
    def preparar_ranking(aba_nome):
        df = data_dict.get(aba_nome, pd.DataFrame())
        if df.empty: return pd.DataFrame()
        
        # Converter coluna DATA e VALOR
        df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
        df['VALOR_NUM'] = df['VALOR'].apply(valor_brasileiro)
        
        # Filtrar por data
        mask = (df['DATA_DT'] >= data_inicio) & (df['DATA_DT'] <= data_fim)
        df_filtrado = df.loc[mask].copy()
        
        if df_filtrado.empty: return pd.DataFrame()
        
        return df_filtrado.groupby('UNIDADE')['VALOR_NUM'].sum().reset_index().sort_values('VALOR_NUM', ascending=False)

    df_alta_rank = preparar_ranking('ALTA')
    df_emerg_rank = preparar_ranking('EMERGENCIAL')

    # --- 3. EXIBIÇÃO ---

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🟦 Ranking ALTA")
        if not df_alta_rank.empty:
            chart = alt.Chart(df_alta_rank).mark_bar(color='#4285F4').encode(
                x=alt.X('VALOR_NUM:Q', title='Gasto (R$)'),
                y=alt.Y('UNIDADE:N', sort='-x', title='Unidade'),
                tooltip=['UNIDADE', alt.Tooltip('VALOR_NUM:Q', format=',.2f')]
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.warning("Nenhum dado na aba ALTA neste período.")

    with col2:
        st.subheader("🟥 Ranking EMERGENCIAL")
        if not df_emerg_rank.empty:
            chart = alt.Chart(df_emerg_rank).mark_bar(color='#EA4335').encode(
                x=alt.X('VALOR_NUM:Q', title='Gasto (R$)'),
                y=alt.Y('UNIDADE:N', sort='-x', title='Unidade'),
                tooltip=['UNIDADE', alt.Tooltip('VALOR_NUM:Q', format=',.2f')]
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.warning("Nenhum dado na aba EMERGENCIAL neste período.")

    st.markdown("---")

    # --- 4. ENVIO DE E-MAIL ---

    def enviar_email():
        # ATENÇÃO: Configure esses valores no painel do Streamlit Cloud (Secrets)
        remetente = st.secrets.get("email_user")
        senha = st.secrets.get("email_password")
        destinatario = "financeiro@empresa.com" # Substitua pelo e-mail real

        if not remetente or not senha:
            st.error("Credenciais de e-mail não configuradas nos Secrets do Streamlit.")
            return

        total_alta = df_alta_rank['VALOR_NUM'].sum() if not df_alta_rank.empty else 0
        total_emerg = df_emerg_rank['VALOR_NUM'].sum() if not df_emerg_rank.empty else 0

        corpo = f"""
        Relatório Orçamentário Semanal
        Período: {data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}

        Total Gasto ALTA: {br_money(total_alta)}
        Total Gasto EMERGENCIAL: {br_money(total_emerg)}
        Total Geral: {br_money(total_alta + total_emerg)}

        Relatório gerado automaticamente pelo Sistema de Gestão.
        """

        msg = MIMEMultipart()
        msg['From'] = remetente
        msg['To'] = destinatario
        msg['Subject'] = f"Relatório Orçamentário Semanal {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}"
        msg.attach(MIMEText(corpo, 'plain'))

        try:
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(remetente, senha)
                server.send_message(msg)
            st.success("✅ Relatório enviado com sucesso!")
        except Exception as e:
            st.error(f"❌ Erro no envio: {e}")

    if st.button("📧 ENVIAR RELATÓRIO AGORA", use_container_width=True):
        enviar_email()

    # --- 5. AUTOMAÇÃO DE DOMINGO (COMENTADO) ---
    """
    # Lógica para rodar automaticamente aos Domingos:
    hoje_check = date.today()
    if hoje_check.weekday() == 6: # 6 = Domingo
        # Aqui o script chamaria enviar_email() automaticamente
        # É recomendado salvar um log para evitar envios duplicados.
        pass
    """

if __name__ == "__main__":
    app()