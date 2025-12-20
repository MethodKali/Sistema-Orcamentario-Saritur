import streamlit as st
import pandas as pd
import altair as alt
import datetime
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, timedelta

# --- CONFIGURAÇÕES E UTILITÁRIOS (Corrigido) ---

def valor_brasileiro(valor):
    if pd.isna(valor) or valor is None: 
        return 0.0
    s = str(valor).strip()
    # Remove R$, espaços e pontos de milhar, troca vírgula decimal por ponto
    s = re.sub(r"[R$\s\.]", "", s).replace(",", ".")
    try:
        return float(s)
    except ValueError: # O erro estava aqui: precisa de 'except', não apenas 'else'
        return 0.0

def br_money(valor):
    if pd.isna(valor): 
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ----------------------------------------------------
# 1. FILTROS DE DATA (SEMANAL)
# ----------------------------------------------------
st.title("📊 Dashboard Orçamentário Semanal")

st.sidebar.header("📅 Filtro de Período")
hoje = date.today()

# Define automaticamente Segunda a Domingo da semana atual
inicio_semana_padrao = hoje - timedelta(days=hoje.weekday())
fim_semana_padrao = inicio_semana_padrao + timedelta(days=6)

data_inicio = st.sidebar.date_input("Início da Semana", inicio_semana_padrao)
data_fim = st.sidebar.date_input("Fim da Semana", fim_semana_padrao)

st.info(f"Relatório de **{data_inicio.strftime('%d/%m/%Y')}** até **{data_fim.strftime('%d/%m/%Y')}**")

# ----------------------------------------------------
# 2. CARREGAMENTO DOS DADOS (Simulado)
# ----------------------------------------------------
# Aqui você deve usar sua função load_sheets() definida nos outros arquivos
# df_alta, df_emerg, _ = load_sheets(hoje.isoformat())

# Exemplo de filtragem por data (considerando que a coluna DATA já é datetime)
# df_alta_f = df_alta[(df_alta['DATA'].dt.date >= data_inicio) & (df_alta['DATA'].dt.date <= data_fim)]
# df_emerg_f = df_emerg[(df_emerg['DATA'].dt.date >= data_inicio) & (df_emerg['DATA'].dt.date <= data_fim)]

# ----------------------------------------------------
# 3. GRÁFICOS DE RANKING POR UNIDADE
# ----------------------------------------------------



col1, col2 = st.columns(2)

with col1:
    st.subheader("🟦 Ranking ALTA")
    # rank_alta = df_alta_f.groupby("UNIDADE")["VALOR"].sum().reset_index().sort_values("VALOR", ascending=False)
    # chart_alta = alt.Chart(rank_alta).mark_bar(color='#4285F4').encode(
    #     x=alt.X('VALOR', title='Total (R$)'),
    #     y=alt.Y('UNIDADE', sort='-x', title='Unidade'),
    #     tooltip=['UNIDADE', alt.Tooltip('VALOR', format=',.2f')]
    # ).properties(height=400)
    # st.altair_chart(chart_alta, use_container_width=True)

with col2:
    st.subheader("🟥 Ranking EMERGENCIAL")
    # rank_emerg = df_emerg_f.groupby("UNIDADE")["VALOR"].sum().reset_index().sort_values("VALOR", ascending=False)
    # chart_emerg = alt.Chart(rank_emerg).mark_bar(color='#EA4335').encode(
    #     x=alt.X('VALOR', title='Total (R$)'),
    #     y=alt.Y('UNIDADE', sort='-x', title='Unidade'),
    #     tooltip=['UNIDADE', alt.Tooltip('VALOR', format=',.2f')]
    # ).properties(height=400)
    # st.altair_chart(chart_emerg, use_container_width=True)

# ----------------------------------------------------
# 4. FUNCIONALIDADE DE ENVIO DE E-MAIL
# ----------------------------------------------------

def enviar_relatorio_email(data_ini, data_fim, texto_corpo):
    remetente = "seu-email@gmail.com"
    senha = "sua-senha-de-app" # Gerada no Google Account
    destinatario = "financeiro@empresa.com"
    
    msg = MIMEMultipart()
    msg['From'] = remetente
    msg['To'] = destinatario
    msg['Subject'] = f"Relatório Orçamentário Semanal {data_ini.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}"
    
    msg.attach(MIMEText(texto_corpo, 'plain'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remetente, senha)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Erro ao enviar e-mail: {e}")
        return False

st.markdown("---")

if st.button("📧 ENVIAR RELATÓRIO"):
    # Criando o corpo do texto com o resumo dos gastos
    resumo_texto = f"Relatório Orçamentário Semanal {data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}\n\n"
    resumo_texto += "Resumo de gastos por unidade disponível no dashboard."
    
    if enviar_relatorio_email(data_inicio, data_fim, resumo_texto):
        st.success("Relatório enviado com sucesso!")

# ----------------------------------------------------
# 5. AUTOMAÇÃO DE DOMINGO (COMENTADO)
# ----------------------------------------------------
"""
# LÓGICA DE AUTOMAÇÃO PARA DOMINGO
# Para funcionar, este bloco deve estar fora de funções ou em um script de background.

dia_semana = date.today().weekday()
# 6 representa Domingo
if dia_semana == 6:
    # 1. Carregar dados da semana que passou
    # 2. Gerar resumo de valores
    # 3. enviar_relatorio_email(data_ini, data_fim, resumo)
    # Nota: Use um arquivo de log ou banco para garantir que envie apenas 1 vez no dia.
    pass
"""