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
    if pd.isna(valor) or valor is None or valor == "": return 0.0
    # Remove R$, espaços e pontos de milhar, troca vírgula decimal por ponto
    s = str(valor).strip()
    s = s.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

def br_money(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- FORMATAÇÃO DE GRÁFICOS ---
def criar_grafico_formatado(df, titulo, cor_barra):
    if df.empty:
        return None
    
    # Base do gráfico
    base = alt.Chart(df).encode(
        y=alt.Y('UNIDADE:N', sort='-x', title=None),
        x=alt.X('VALOR_NUM:Q', title=None, axis=None)
    )

    # Camada 1: As barras
    bars = base.mark_bar(color=cor_barra, cornerRadiusEnd=3).encode(
        tooltip=['UNIDADE', alt.Tooltip('VALOR_NUM:Q', format=',.2f', title="Total")]
    )

    # Camada 2: O texto (Ajustado para ser visível no Dark Mode)
    text = base.mark_text(
        align='left',
        baseline='middle',
        dx=5, 
        color='white', # Forçado branco para aparecer no fundo escuro da imagem
        fontWeight='bold',
        size=12
    ).encode(
        text=alt.Text('VALOR_NUM:Q', format='R$ ,.2f')
    )

    # Combinação
    chart = (bars + text).properties(
        title=alt.TitleParams(text=titulo, anchor='start', fontSize=18),
        width=500, # Largura fixa para garantir espaço para o texto
        height=alt.Step(40) 
    ).configure_view(strokeOpacity=0)

    return chart

# --- LÓGICA DO DASHBOARD ---
def app():
    st.title("📊 Dashboard Orçamentário Semanal")
    
    # Filtros de Data
    st.sidebar.header("📅 Filtro de Período")
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    fim_semana = inicio_semana + timedelta(days=6)

    data_inicio = st.sidebar.date_input("Início", inicio_semana)
    data_fim = st.sidebar.date_input("Fim", fim_semana)

    with st.spinner("Carregando dados..."):
        data_dict = load_data(PLANILHA_NOME)

    if not data_dict:
        st.error("Falha ao carregar planilha.")
        return

    def preparar_ranking(aba_nome):
        df = data_dict.get(aba_nome, pd.DataFrame())
        if df.empty: return pd.DataFrame()
        
        # Garante que a coluna DATA seja lida corretamente
        df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
        df['VALOR_NUM'] = df['VALOR'].apply(valor_brasileiro)
        
        # Filtro
        mask = (df['DATA_DT'] >= data_inicio) & (df['DATA_DT'] <= data_fim)
        df_f = df.loc[mask].copy()
        
        if df_f.empty: return pd.DataFrame()
        
        return df_f.groupby('UNIDADE')['VALOR_NUM'].sum().reset_index().sort_values('VALOR_NUM', ascending=False)

    df_alta = preparar_ranking('ALTA')
    df_emerg = preparar_ranking('EMERGENCIAL')

    # --- DEPURAÇÃO (REMOVA APÓS FUNCIONAR) ---
    with st.expander("🔍 Verificação de Dados (Debug)"):
        st.write(f"Período selecionado: {data_inicio} até {data_fim}")
        col_d1, col_d2 = st.columns(2)
        col_d1.write("Tabela ALTA filtrada:")
        col_d1.dataframe(df_alta)
        col_d2.write("Tabela EMERGENCIAL filtrada:")
        col_d2.dataframe(df_emerg)

    # Criar Gráficos
    fig_alta = criar_grafico_formatado(df_alta, "Ranking ALTA", "#00A2E8")
    fig_emerg = criar_grafico_formatado(df_emerg, "Ranking EMERGENCIAL", "#FF4B4B")

    # Exibição
    st.markdown("---")
    if fig_alta:
        st.altair_chart(fig_alta, use_container_width=True)
    else:
        st.warning("Sem dados para ALTA no período.")

    if fig_emerg:
        st.altair_chart(fig_emerg, use_container_width=True)
    else:
        st.warning("Sem dados para EMERGENCIAL no período.")

    # --- FUNÇÃO DE E-MAIL ---
    def enviar_email():
        try:
            remetente = st.secrets["email_user"]
            senha = st.secrets["email_password"]
            
            msg = MIMEMultipart()
            msg['From'] = remetente
            msg['To'] = "kerlesalves@gmail.com"
            msg['Subject'] = f"Relatório Saritur - {data_inicio.strftime('%d/%m')}"

            t_alta = df_alta['VALOR_NUM'].sum() if not df_alta.empty else 0
            t_emerg = df_emerg['VALOR_NUM'].sum() if not df_emerg.empty else 0

            corpo = f"""
            Resumo Orçamentário Semanal
            
            TOTAL ALTA: {br_money(t_alta)}
            TOTAL EMERGENCIAL: {br_money(t_emerg)}
            TOTAL GERAL: {br_money(t_alta + t_emerg)}
            """
            msg.attach(MIMEText(corpo, 'plain'))

            # Anexos PNG
            for chart, nome in [(fig_alta, "ALTA"), (fig_emerg, "EMERGENCIAL")]:
                if chart:
                    # O vl-convert precisa do JSON do gráfico
                    png_data = vlc.vegalite_to_png(chart.to_json())
                    img = MIMEImage(png_data)
                    img.add_header('Content-Disposition', 'attachment', filename=f"Ranking_{nome}.png")
                    msg.attach(img)

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(remetente, senha)
                server.send_message(msg)
            st.success("✅ E-mail enviado com gráficos anexados!")
        except Exception as e:
            st.error(f"❌ Erro: {e}")

    st.markdown("---")
    if st.button("📧 ENVIAR RELATÓRIO AGORA", use_container_width=True):
        enviar_email()

if __name__ == "__main__":
    app()