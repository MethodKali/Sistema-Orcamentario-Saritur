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

# --- IMPORTAÇÃO DOS DADOS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from pages.BACKLOG import load_data, PLANILHA_NOME
except:
    st.error("Erro ao carregar BACKLOG.py")
    st.stop()

# --- TRATAMENTO DE DADOS (PANDAS) ---
def preparar_dados_plotly(df, d_inicio, d_fim):
    if df.empty: return pd.DataFrame()
    df = df.copy()
    df['UNIDADE'] = df['UNIDADE'].astype(str).str.strip().str.upper()
    df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
    
    def limpar_moeda(v):
        if pd.isna(v) or v == "": return 0.0
        s = str(v).replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
        try: return float(s)
        except: return 0.0

    df['VALOR_NUM'] = df['VALOR'].apply(limpar_moeda)
    mask = (df['DATA_DT'] >= d_inicio) & (df['DATA_DT'] <= d_fim)
    df_filtrado = df.loc[mask]
    ranking = df_filtrado.groupby('UNIDADE')['VALOR_NUM'].sum().reset_index()
    return ranking.sort_values('VALOR_NUM', ascending=True)

def preparar_tabela_amanha(df):
    if df.empty: return pd.DataFrame()
    df = df.copy()
    df['DATA_DT'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
    amanha = date.today() + timedelta(days=1)
    
    # Filtro: Dia Seguinte E Status NÃO é "PEDIDO"
    mask = (df['DATA_DT'] == amanha) & (df['STATUS'].astype(str).str.strip().str.upper() != "PEDIDO")
    df_f = df.loc[mask].copy()
    
    if df_f.empty: return pd.DataFrame()

    colunas = ["DATA", "UNIDADE", "CARRO | UTILIZAÇÃO", "PEDIDO", "VALOR"]
    colunas_existentes = [c for c in colunas if c in df_f.columns]
    df_f = df_f[colunas_existentes]

    def limpar_valor(v):
        s = str(v).replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
        try: return float(s)
        except: return 0.0

    total_num = df_f['VALOR'].apply(limpar_valor).sum()
    valor_formatado = f"R$ {total_num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Linha de total com preenchimento para todas as colunas (evita erros no PNG/Excel)
    linha_total = pd.DataFrame([{ 
        "DATA": "TOTAL GERAL", 
        "UNIDADE": "---", 
        "CARRO | UTILIZAÇÃO": "---", 
        "PEDIDO": "---",
        "VALOR": valor_formatado
    }])
    return pd.concat([df_f, linha_total], ignore_index=True)

def gerar_figura(df, titulo, cor):
    if df.empty: return None
    altura_dinamica = max(450, len(df) * 45)
    fig = px.bar(df, x='VALOR_NUM', y='UNIDADE', orientation='h', text='VALOR_NUM', title=titulo)
    fig.update_traces(marker_color=cor, texttemplate='R$ %{text:,.2f}', textposition='outside', cliponaxis=False, textfont=dict(color="black", size=13))
    fig.update_layout(paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", font=dict(color="black"), height=altura_dinamica, margin=dict(l=220, r=120, t=80, b=50), yaxis=dict(title=None, automargin=True, tickfont=dict(color="black", size=13), categoryorder='total ascending', dtick=1), xaxis=dict(visible=False, range=[0, df['VALOR_NUM'].max() * 1.4]), title=dict(x=0.5, font=dict(size=22)))
    return fig

def app():
    st.title("📊 Gestão de Gastos Saritur")
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    data_inicio = st.sidebar.date_input("Início", inicio_semana)
    data_fim = st.sidebar.date_input("Fim", inicio_semana + timedelta(days=6))

    data_dict = load_data(PLANILHA_NOME)
    
    # Processamento Rankings
    df_alta_orig = data_dict.get('ALTA', pd.DataFrame())
    df_alta_filt = df_alta_orig[df_alta_orig['STATUS'].astype(str).str.strip().str.upper() == "PEDIDO"] if not df_alta_orig.empty else pd.DataFrame()
    df_alta = preparar_dados_plotly(df_alta_filt, data_inicio, data_fim)
    df_emerg = preparar_dados_plotly(data_dict.get('EMERGENCIAL', pd.DataFrame()), data_inicio, data_fim)

    df_total = pd.concat([df_alta, df_emerg], ignore_index=True)
    if not df_total.empty:
        df_total = df_total.groupby('UNIDADE')['VALOR_NUM'].sum().reset_index().sort_values('VALOR_NUM', ascending=True)

    # Processamento Tabela Amanhã
    df_tabela_amanha = preparar_tabela_amanha(df_alta_orig)

    # --- EXIBIÇÃO NO STREAMLIT ---
    st.markdown("---")
    st.subheader(f"📅 Programação para Amanhã ({(hoje + timedelta(days=1)).strftime('%d/%m/%Y')})")
    if not df_tabela_amanha.empty:
        st.dataframe(df_tabela_amanha, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma programação para amanhã (Excluindo 'PEDIDO').")

    st.markdown("---")
    fig_total = gerar_figura(df_total, f"Ranking Geral - {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}", "#106332")
    if fig_total: st.plotly_chart(fig_total, use_container_width=True)

    fig_a = gerar_figura(df_alta, f"Ranking ALTA (PEDIDO) - {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}", "#1F617E")
    if fig_a: st.plotly_chart(fig_a, use_container_width=True)

    fig_e = gerar_figura(df_emerg, f"Ranking EMERGENCIAL - {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}", "#942525")
    if fig_e: st.plotly_chart(fig_e, use_container_width=True)

    def enviar():
        try:
            user, password = st.secrets["email_user"], st.secrets["email_password"]
            msg = MIMEMultipart()
            msg['Subject'] = f"Relatório Saritur: {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}"
            msg['From'], msg['To'] = user, "kerlesalves@gmail.com"
            msg.attach(MIMEText(f"Relatório consolidado e programação de amanhã.\nPeríodo: {data_inicio} a {data_fim}", 'plain'))

            # 1. Anexos de Rankings (PNG)
            for fig, nome in [(fig_total, "Total"), (fig_a, "ALTA"), (fig_e, "EMERG")]:
                if fig:
                    img_bytes = fig.to_image(format="png", width=1000, height=800)
                    part = MIMEImage(img_bytes)
                    part.add_header('Content-Disposition', 'attachment', filename=f"{nome}.png")
                    msg.attach(part)

            # 2. Anexos da Tabela de Amanhã (PNG + XLSX)
            if not df_tabela_amanha.empty:
                # Gerar PNG da Tabela com ALTURA DINÂMICA
                altura_calc = 150 + (len(df_tabela_amanha) * 35)
                fig_tbl = go.Figure(data=[go.Table(
                    columnwidth=[100, 150, 200, 100, 120],
                    header=dict(values=list(df_tabela_amanha.columns), fill_color='#1F617E', font=dict(color='white', size=14), align='center'),
                    cells=dict(values=[df_tabela_amanha[col] for col in df_tabela_amanha.columns], fill_color='#F5F5F5', font=dict(color='black', size=12), align='center', height=30)
                )])
                fig_tbl.update_layout(margin=dict(l=10, r=10, t=10, b=10))
                img_tbl_bytes = fig_tbl.to_image(format="png", width=1100, height=altura_calc)
                part_tbl_png = MIMEImage(img_tbl_bytes)
                part_tbl_png.add_header('Content-Disposition', 'attachment', filename="Programacao_Amanha.png")
                msg.attach(part_tbl_png)

                # Gerar Excel
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df_tabela_amanha.to_excel(writer, index=False, sheet_name='Amanha')
                part_ex = MIMEBase('application', "octet-stream")
                part_ex.set_payload(buf.getvalue())
                encoders.encode_base64(part_ex)
                part_ex.add_header('Content-Disposition', 'attachment', filename="Programacao_Amanha.xlsx")
                msg.attach(part_ex)

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
            st.success("✅ Relatório e Tabela enviados com sucesso!")
        except Exception as e:
            st.error(f"Erro no envio: {e}")

    st.markdown("---")
    if st.button("📧 ENVIAR RELATÓRIO POR E-MAIL"):
        enviar()

if __name__ == "__main__":
    app()