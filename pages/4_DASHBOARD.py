import streamlit as st
import pandas as pd
import altair as alt
import re
import smtplib
import io
import vl_convert as vlc
import os
import sys

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import date, timedelta

# --- CORREÇÃO DE IMPORTAÇÃO ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
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

# --- FORMATAÇÃO DE GRÁFICOS (Estilo BUSCAR.py) ---
def criar_grafico_formatado(df, titulo, cor):
    """Cria o gráfico com barras e valores laterais conforme imagem de referência"""
    if df.empty:
        return None
    
    # Base do gráfico
    base = alt.Chart(df).encode(
        y=alt.Y('UNIDADE:N', sort='-x', title=None),
        x=alt.X('VALOR_NUM:Q', title=None, axis=None) # Esconde eixo X para limpar
    )

    # Camada 1: As barras
    bars = base.mark_bar(color=cor, cornerRadiusEnd=3).encode(
        tooltip=['UNIDADE', alt.Tooltip('VALOR_NUM:Q', format=',.2f')]
    )

    # Camada 2: O texto com o valor R$ na frente da barra
    text = base.mark_text(
        align='left',
        baseline='middle',
        dx=5, 
        color='black',
        fontWeight='bold'
    ).encode(
        text=alt.Text('VALOR_NUM:Q', format='R$ ,.2f')
    )

    # Combinação das camadas
    chart = (bars + text).properties(
        title=titulo,
        width=450,
        height=alt.Step(35) # Altura dinâmica baseada na quantidade de itens
    ).configure_view(strokeOpacity=0)

    return chart

# --- LÓGICA DO DASHBOARD ---
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

    # Carregamento
    with st.spinner("Carregando dados da Planilha..."):
        data_dict = load_data(PLANILHA_NOME)

    if not data_dict:
        st.error("Erro ao carregar dados.")
        return

    def preparar_ranking(aba_nome):
        df = data_dict.get(aba_nome, pd.DataFrame())
        if df.empty: return pd.DataFrame()
        df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
        df['VALOR_NUM'] = df['VALOR'].apply(valor_brasileiro)
        mask = (df['DATA_DT'] >= data_inicio) & (df['DATA_DT'] <= data_fim)
        df_f = df.loc[mask].copy()
        if df_f.empty: return pd.DataFrame()
        return df_f.groupby('UNIDADE')['VALOR_NUM'].sum().reset_index().sort_values('VALOR_NUM', ascending=False)

    df_alta_rank = preparar_ranking('ALTA')
    df_emerg_rank = preparar_ranking('EMERGENCIAL')

    # Criar objetos de gráfico formatados
    fig_alta = criar_grafico_formatado(df_alta_rank, "Ranking ALTA", "#4285F4")
    fig_emerg = criar_grafico_formatado(df_emerg_rank, "Ranking EMERGENCIAL", "#EA4335")

    # Exibição na tela
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🟦 Ranking ALTA")
        if fig_alta: st.altair_chart(fig_alta, use_container_width=True)
        else: st.warning("Sem dados: ALTA")

    with col2:
        st.subheader("🟥 Ranking EMERGENCIAL")
        if fig_emerg: st.altair_chart(fig_emerg, use_container_width=True)
        else: st.warning("Sem dados: EMERGENCIAL")

    st.markdown("---")

    # --- FUNÇÃO DE E-MAIL COM ANEXOS ---
    def enviar_email(automatico=False):
        try:
            remetente = st.secrets["email_user"]
            senha = st.secrets["email_password"]
            destinatario = "kerlesalves@gmail.com"

            t_alta = df_alta_rank['VALOR_NUM'].sum() if not df_alta_rank.empty else 0
            t_emerg = df_emerg_rank['VALOR_NUM'].sum() if not df_emerg_rank.empty else 0

            msg = MIMEMultipart()
            msg['From'] = remetente
            msg['To'] = destinatario
            msg['Subject'] = f"Relatório Orçamentário Semanal {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}"

            corpo = f"""
            Relatório Orçamentário Semanal {data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}
            
            RESUMO DE GASTOS:
            Total ALTA: {br_money(t_alta)}
            Total EMERGENCIAL: {br_money(t_emerg)}
            Total Geral: {br_money(t_alta + t_emerg)}
            
            Os gráficos de ranking por unidade seguem em anexo.
            Enviado via: {'Automação de Domingo' if automatico else 'Botão Manual'}
            """
            msg.attach(MIMEText(corpo, 'plain'))

            # --- ANEXAR GRÁFICOS COMO PNG ---
            for chart, nome in [(fig_alta, "Alta"), (fig_emerg, "Emergencial")]:
                if chart is not None:
                    # Converte o JSON do Altair para PNG usando vl-convert
                    png_data = vlc.vegalite_to_png(chart.to_json())
                    image = MIMEImage(png_data)
                    image.add_header('Content-Disposition', 'attachment', filename=f"Ranking_{nome}.png")
                    msg.attach(image)

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(remetente, senha)
                server.send_message(msg)
            
            if not automatico: st.success("✅ Relatório com gráficos em anexo enviado!")
            return True
        except Exception as e:
            if not automatico: st.error(f"❌ Erro ao processar e-mail: {e}")
            return False

    if st.button("📧 ENVIAR RELATÓRIO AGORA (COM ANEXOS)", use_container_width=True):
        enviar_email()

    # --- AUTOMAÇÃO DE DOMINGO ---
    if hoje.weekday() == 6:
        if 'email_enviado_hoje' not in st.session_state:
            if enviar_email(automatico=True):
                st.session_state['email_enviado_hoje'] = True
                st.info("ℹ️ Relatório automático de Domingo enviado com anexos.")

if __name__ == "__main__":
    app()