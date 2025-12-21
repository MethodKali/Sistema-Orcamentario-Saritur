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
    
    # Garantimos que os valores são floats e não nulos para o Altair não se perder
    df['VALOR_NUM'] = df['VALOR_NUM'].fillna(0).astype(float)
    
    # Criamos o gráfico
    bars = alt.Chart(df).mark_bar(
        color=cor_barra,
        cornerRadiusEnd=5,
        height=20  # Altura fixa da barra
    ).encode(
        y=alt.Y('UNIDADE:N', sort='-x', title=None),
        x=alt.X('VALOR_NUM:Q', title=None, axis=None, scale=alt.Scale(nice=True)),
        tooltip=['UNIDADE', alt.Tooltip('VALOR_NUM:Q', format=',.2f')]
    )

    text = bars.mark_text(
        align='left',
        baseline='middle',
        dx=5,
        color='white', # Texto branco para garantir visão no fundo preto
        fontWeight='bold'
    ).encode(
        text=alt.Text('VALOR_NUM:Q', format='R$ ,.2f')
    )

    chart = (bars + text).properties(
        title=alt.TitleParams(text=titulo, anchor='start', color='white', fontSize=16),
        width=500, # Largura fixa em pixels para teste (mude para 'container' se funcionar)
        height=alt.Step(40)
    ).configure_view(
        strokeOpacity=0
    )

    return chart

def app():
    st.title("📊 Dashboard Orçamentário Semanal")
    st.markdown("---")

    # 1. Definição das variáveis de data (agora declaradas antes do uso)
    st.sidebar.header("📅 Filtro de Período")
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    fim_semana = inicio_semana + timedelta(days=6)

    data_inicio = st.sidebar.date_input("Início", inicio_semana)
    data_fim = st.sidebar.date_input("Fim", fim_semana)

    # 2. Carregamento dos dados
    with st.spinner("Carregando dados..."):
        data_dict = load_data(PLANILHA_NOME)

    if not data_dict:
        st.error("Falha ao carregar planilha.")
        return

    # 3. Função preparar_ranking COM as variáveis declaradas nos argumentos
    def preparar_ranking(aba_nome, d_inicio, d_fim):
        df = data_dict.get(aba_nome, pd.DataFrame())
        if df.empty: 
            return pd.DataFrame()
        
        # Limpeza e Conversão
        df = df.copy()
        df['UNIDADE'] = df['UNIDADE'].astype(str).str.strip().str.upper()
        df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
        df['VALOR_NUM'] = df['VALOR'].apply(valor_brasileiro)
        
        # Filtro usando as variáveis passadas
        mask = (df['DATA_DT'] >= d_inicio) & (df['DATA_DT'] <= d_fim)
        df_f = df.loc[mask].copy()
        
        if df_f.empty: 
            return pd.DataFrame()
        # Agrupa, soma, reseta o índice e remove unidades que somam R$ 0,00
        df_final = df_f.groupby('UNIDADE')['VALOR_NUM'].sum().reset_index()
        df_final = df_final[df_final['VALOR_NUM'] > 0] # Remove zeros
        return df_final.sort_values('VALOR_NUM', ascending=False)
    
    # 4. Chamada da função passando as datas corretamente
    df_alta = preparar_ranking('ALTA', data_inicio, data_fim)
    df_emerg = preparar_ranking('EMERGENCIAL', data_inicio, data_fim)

    # --- DEPURAÇÃO (REMOVA APÓS FUNCIONAR) ---
    with st.expander("🔍 Verificação de Dados (Debug)"):
        st.write(f"Período selecionado: {data_inicio} até {data_fim}")
        col_d1, col_d2 = st.columns(2)
        col_d1.write("Tabela ALTA filtrada:")
        col_d1.dataframe(df_alta)
        col_d2.write("Tabela EMERGENCIAL filtrada:")
        col_d2.dataframe(df_emerg)

# --- RESTANTE DO CÓDIGO (Gráficos e E-mail) ---
    fig_alta = criar_grafico_formatado(df_alta, "Ranking ALTA", "#00A2E8")
    fig_emerg = criar_grafico_formatado(df_emerg, "Ranking EMERGENCIAL", "#FF4B4B")

    # Exibição
    if fig_alta:
        st.altair_chart(fig_alta, use_container_width=True)
        # Se o Altair falhar, isso aqui VAI mostrar as barras:
        st.bar_chart(df_alta.set_index('UNIDADE')['VALOR_NUM'])
    
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