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
    s = str(valor).strip()
    s = s.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

def br_money(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- FORMATAÇÃO DE GRÁFICOS (ALTAIR BLINDADO) ---
def criar_grafico_formatado(df, titulo, cor_barra):
    if df.empty:
        return None
    
    df = df.copy()
    df['VALOR_NUM'] = pd.to_numeric(df['VALOR_NUM'], errors='coerce').fillna(0)
    df['UNIDADE'] = df['UNIDADE'].astype(str)
    
    # CALCULANDO O LIMITE DO EIXO X PARA NÃO CORTAR O TEXTO
    # Isso força o Altair a criar um espaço horizontal real
    max_valor = df['VALOR_NUM'].max() * 1.4 
    
    # Base do gráfico: Forçamos largura fixa de 350px e domínio X manual
    base = alt.Chart(df).encode(
        y=alt.Y('UNIDADE:N', sort='-x', title=None),
        x=alt.X('VALOR_NUM:Q', title=None, axis=None, scale=alt.Scale(domain=[0, max_valor]))
    ).properties(
        width=350, 
        height=alt.Step(40),
        title=alt.TitleParams(text=titulo, anchor='start', color='white', fontSize=18)
    )

    # Camada de barras
    bars = base.mark_bar(color=cor_barra, cornerRadiusEnd=3).encode(
        tooltip=['UNIDADE', alt.Tooltip('VALOR_NUM:Q', format=',.2f')]
    )

    # Camada de texto (Valores na frente das barras)
    text = base.mark_text(
        align='left',
        baseline='middle',
        dx=8,
        color='white',
        fontWeight='bold',
        size=12
    ).encode(
        text=alt.Text('VALOR_NUM:Q', format='R$ ,.2f')
    )

    # Combinamos e configuramos para remover qualquer borda que atrapalhe
    return (bars + text).configure_view(strokeOpacity=0).configure_axis(grid=False)

def app():
    st.set_page_config(layout="wide") # Melhora a visualização lateral
    st.title("📊 Dashboard Orçamentário Semanal")
    st.markdown("---")

    # 1. Filtros de data
    st.sidebar.header("📅 Filtro de Período")
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    fim_semana = inicio_semana + timedelta(days=6)

    data_inicio = st.sidebar.date_input("Início", inicio_semana)
    data_fim = st.sidebar.date_input("Fim", fim_semana)

    # 2. Carregamento dos dados
    with st.spinner("Carregando dados da planilha..."):
        data_dict = load_data(PLANILHA_NOME)

    if not data_dict:
        st.error("Falha ao carregar planilha.")
        return

    # 3. Preparação dos Rankings (Limpando nomes duplicados como 'EXPEDIÇÃO')
    def preparar_ranking(aba_nome, d_inicio, d_fim):
        df = data_dict.get(aba_nome, pd.DataFrame())
        if df.empty: return pd.DataFrame()
        
        df = df.copy()
        # strip() remove espaços que duplicam nomes no seu debug
        df['UNIDADE'] = df['UNIDADE'].astype(str).str.strip().str.upper()
        df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
        df['VALOR_NUM'] = df['VALOR'].apply(valor_brasileiro)
        
        mask = (df['DATA_DT'] >= d_inicio) & (df['DATA_DT'] <= d_fim)
        df_f = df.loc[mask].copy()
        
        if df_f.empty: return pd.DataFrame()
        
        # Agrupamento consolida unidades repetidas
        df_final = df_f.groupby('UNIDADE')['VALOR_NUM'].sum().reset_index()
        df_final = df_final[df_final['VALOR_NUM'] > 0]
        return df_final.sort_values('VALOR_NUM', ascending=False)
    
    df_alta = preparar_ranking('ALTA', data_inicio, data_fim)
    df_emerg = preparar_ranking('EMERGENCIAL', data_inicio, data_fim)

    # 4. Debug (Expander)
    with st.expander("🔍 Verificação de Dados (Debug)"):
        st.write(f"Período: {data_inicio} até {data_fim}")
        c1, c2 = st.columns(2)
        c1.dataframe(df_alta)
        c2.dataframe(df_emerg)

    # 5. Criação e Exibição dos Gráficos
    st.markdown("---")
    fig_alta = criar_grafico_formatado(df_alta, "Ranking ALTA", "#00A2E8")
    fig_emerg = criar_grafico_formatado(df_emerg, "Ranking EMERGENCIAL", "#FF4B4B")

    col1, col2 = st.columns(2)
    with col1:
        if fig_alta:
            # use_container_width=False para garantir que respeite a largura de 350px
            st.altair_chart(fig_alta, use_container_width=False)
        else:
            st.warning("Sem dados para ALTA")

    with col2:
        if fig_emerg:
            st.altair_chart(fig_emerg, use_container_width=False)
        else:
            st.warning("Sem dados para EMERGENCIAL")

    # 6. Função de e-mail com Anexos
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

            corpo = f"Relatório Semanal\nTOTAL ALTA: {br_money(t_alta)}\nTOTAL EMERG: {br_money(t_emerg)}"
            msg.attach(MIMEText(corpo, 'plain'))

            # Anexar gráficos
            for chart, nome in [(fig_alta, "ALTA"), (fig_emerg, "EMERGENCIAL")]:
                if chart:
                    png_data = vlc.vegalite_to_png(chart.to_json())
                    img = MIMEImage(png_data)
                    img.add_header('Content-Disposition', 'attachment', filename=f"Ranking_{nome}.png")
                    msg.attach(img)

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(remetente, senha)
                server.send_message(msg)
            st.success("✅ Relatório enviado com sucesso!")
        except Exception as e:
            st.error(f"❌ Erro no envio: {e}")

    st.markdown("---")
    if st.button("📧 ENVIAR RELATÓRIO AGORA", use_container_width=True):
        enviar_email()

if __name__ == "__main__":
    app()