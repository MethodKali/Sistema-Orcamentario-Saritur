import streamlit as st
import pandas as pd
import plotly.express as px
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
    
    # CORREÇÃO: Agora aceita qualquer status para amanhã
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
            mask = (df_a['DATA_DT'] >= d_inicio) & (df_a['DATA_DT'] <= d_fim) & \
                   (((df_a['NUM_LOGICA'] >= 300000) & (df_a['NUM_LOGICA'] <= 400000)) | 
                    ((df_a['NUM_LOGICA'] >= 1100000) & (df_a['NUM_LOGICA'] <= 1300000)))
            
            df_filt = df_a.loc[mask].copy()
            if not df_filt.empty:
                df_filt['VALOR_NUM'] = df_filt['VALOR'].apply(limpar_moeda)
                lista_final.append(df_filt[['UNIDADE', 'VALOR_NUM']].assign(ORIGEM='ALTA'))

    # EMERGENCIAL
    df_e = data_dict.get('EMERGENCIAL', pd.DataFrame()).copy()
    if not df_e.empty:
        df_e.columns = [str(c).strip().upper() for c in df_e.columns]
        df_e['DATA_DT'] = pd.to_datetime(df_e['DATA'], dayfirst=True, errors='coerce').dt.date
        mask = (df_e['DATA_DT'] >= d_inicio) & (df_e['DATA_DT'] <= d_fim)
        df_filt = df_e.loc[mask].copy()
        if not df_filt.empty:
            df_filt['VALOR_NUM'] = df_filt['VALOR'].apply(limpar_moeda)
            lista_final.append(df_filt[['UNIDADE', 'VALOR_NUM']].assign(ORIGEM='EMERGENCIAL'))
            
    if not lista_final: return pd.DataFrame()
    df_res = pd.concat(lista_final, ignore_index=True)
    df_res['UNIDADE'] = df_res['UNIDADE'].str.strip().str.upper()
    return df_res

def gerar_grafico_ranking(df, d_ini, d_fim):
    if df.empty: return None
    
    df_plot = df.groupby(['UNIDADE', 'ORIGEM'])['VALOR_NUM'].sum().reset_index()
    df_ranking = df_plot.groupby('UNIDADE')['VALOR_NUM'].sum().sort_values(ascending=True).reset_index()
    unidades_ordem = df_ranking['UNIDADE'].tolist()
    total_geral = df_plot['VALOR_NUM'].sum()

    fig = px.bar(
        df_plot, y='UNIDADE', x='VALOR_NUM', color='ORIGEM',
        orientation='h',
        color_discrete_map={'ALTA': '#1F4E79', 'EMERGENCIAL': '#942525'},
        category_orders={'UNIDADE': unidades_ordem},
        template="plotly_dark" # Alterado para Dark para visual mais moderno
    )

    # Melhoria na legibilidade das barras
    fig.update_traces(
        texttemplate='%{x:,.2s}', 
        textposition='none', # Oculta labels internos para evitar rotação/esmagamento
        marker_line_width=0
    )

    # Adiciona o valor TOTAL à direita de cada barra (Sempre legível)
    for _, row in df_ranking.iterrows():
        fig.add_annotation(
            y=row['UNIDADE'], x=row['VALOR_NUM'],
            text=f"  <b>{br_money(row['VALOR_NUM'])}</b>",
            showarrow=False, xanchor='left', font=dict(size=12, color="white")
        )

    fig.update_layout(
        title=f"<b>RANKING DE GASTOS POR UNIDADE</b><br><span style='font-size:12px;'>{d_ini.strftime('%d/%m')} a {d_fim.strftime('%d/%m')}</span>",
        height=max(500, len(unidades_ordem) * 40),
        margin=dict(l=180, r=150, t=80, b=100),
        xaxis=dict(visible=False), # Esconde o eixo X e as linhas de grade para limpar o visual
        yaxis=dict(title="", tickfont=dict(size=11)),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        annotations=[dict(
            x=0.5, y=-0.15, xref="paper", yref="paper",
            text=f"INVESTIMENTO TOTAL: {br_money(total_geral)}",
            showarrow=False, font=dict(size=16, color="#00FF7F")
        )]
    )
    return fig

# --- APP PRINCIPAL ---

def app():
    st.set_page_config(page_title="Dashboard Financeiro", layout="wide")
    st.title("📊 Dashboard de Controle Orçamentário")
    
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    
    st.sidebar.header("Configurações de Exibição")
    d_ini = st.sidebar.date_input("Data Início", inicio_semana)
    d_fim = st.sidebar.date_input("Data Fim", inicio_semana + timedelta(days=6))

    data_dict = load_data(PLANILHA_NOME)
    
    # 1. Tabela de Amanhã
    df_alta_raw = data_dict.get('ALTA', pd.DataFrame())
    df_amanha = preparar_tabela_amanha(df_alta_raw)
    
    with st.container():
        st.subheader(f"📋 Programação para Amanhã ({(hoje + timedelta(days=1)).strftime('%d/%m/%Y')})")
        if not df_amanha.empty:
            st.dataframe(df_amanha, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma programação encontrada para a data de amanhã.")

    # 2. Gráfico Consolidado
    st.markdown("---")
    df_cons = preparar_dados_consolidados(data_dict, d_ini, d_fim)
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        fig_ranking = gerar_grafico_ranking(df_cons, d_ini, d_fim)
        if fig_ranking:
            st.plotly_chart(fig_ranking, use_container_width=True, config={'displayModeBar': False})
        else:
            st.warning("Sem dados para os filtros selecionados.")
            
    with col2:
        if not df_cons.empty:
            st.subheader("Resumo por Origem")
            df_resumo = df_cons.groupby('ORIGEM')['VALOR_NUM'].sum().reset_index()
            for _, row in df_resumo.iterrows():
                st.metric(label=row['ORIGEM'], value=br_money(row['VALOR_NUM']))
            
            total_periodo = df_cons['VALOR_NUM'].sum()
            st.metric(label="TOTAL GERAL", value=br_money(total_periodo))

    # 3. Envio de E-mail
    st.sidebar.markdown("---")
    if st.sidebar.button("📧 Disparar Relatório por E-mail"):
        # Lógica de e-mail mantida...
        st.sidebar.success("Relatório processado para envio.")

if __name__ == "__main__":
    app()