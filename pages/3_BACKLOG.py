import streamlit as st
import re
import pandas as pd
import gspread 
from typing import List, Dict, Union
from datetime import date, timedelta
# LINHA REMOVIDA: A importação abaixo causava conflito ou erro no ambiente do Cloud
# import gspread.exceptions 
import calendar # Para manipular dias da semana

# Importações necessárias para autenticação no Streamlit Cloud
import json 
from oauth2client.service_account import ServiceAccountCredentials
import os # Necessário para verificar se está no Streamlit Cloud


# --- CONFIGURAÇÃO ---
PLANILHA_NOME = "Controle Orçamentário Diário V2" 
# CREDENTIALS_FILE = "acesso.json" <-- NÃO USADO MAIS NO CLOUD
COLUNAS_DADOS = ['PEDIDO', 'DATA', 'CARRO | UTILIZAÇÃO', 'STATUS']
COLUNA_CARRO = 'CARRO | UTILIZAÇÃO' 

# LISTA DAS ABAS A SEREM CARREGADAS
ABAS_PRINCIPAIS = ['ALTA', 'EMERGENCIAL']

# LISTA DOS CARROS CADASTRADOS
LISTA_CARROS_CADASTRO = [
    "- SELECIONE UM CRITÉRIO -",
    "BACKLOG",
    "24600", "23900", "23880", "23400", "13770", "26220", "30030", 
    "32990", "21400", "23600", "24000", "14400", "20330", "24300", "32220",
]

# ----------------------------------------------------
# 1. FUNÇÕES DE UTILIDADE E CÁLCULO DE DATA
# ----------------------------------------------------

def parse_pedidos(text: str) -> List[str]:
    """Trata a string de anotação e retorna apenas uma lista de números de pedidos (strings)."""
    if not text:
        return []
    
    text_cleaned = re.sub(r'[^\d]', ' ', text)
    raw_list = re.split(r'\s+', text_cleaned.strip())
    
    pedidos_limpos = {p for p in raw_list if p.isdigit() and len(p) > 0}
    
    return sorted(list(pedidos_limpos))


def calculate_backup_sheet_name() -> str:
    """
    Calcula o nome da aba de backup baseando-se na data atual.
    
    Regras:
    1. Dia útil = Segunda a Sexta.
    2. Se hoje for o PRIMEIRO DIA ÚTIL da semana (Segunda), busca a Semana Passada.
    3. Se não for o dia de atualização, busca a Semana Retrasada.
    4. Formato: 'dd.mm a dd.mm'.
    """
    today = date.today()
    
    # calendar.MONDAY é 0. Segunda-feira é o dia de atualização.
    is_update_day = today.weekday() == calendar.MONDAY

    if is_update_day:
        # É dia de atualização (Segunda): Buscamos a SEMANA PASSADA.
        # Encontra a última Sexta-feira (fim da semana passada)
        last_friday = today - timedelta(days=3) # Segunda (0) - 3 dias = Sexta (-3)
        end_date = last_friday
        
    else:
        # Não é dia de atualização: Buscamos a SEMANA RETRASADA.
        # Encontra a Sexta-feira da semana retrasada (Sexta passada - 7 dias)
        
        # Primeiro, encontra o último dia da semana passada (Sexta)
        # today.weekday() = 5 (Sábado) ou 6 (Domingo) ou 1-4 (Terça-Sexta)
        days_since_last_friday = (today.weekday() - calendar.FRIDAY + 7) % 7 
        
        # Se for sábado (5), days_since_last_friday é 0. Se for domingo (6), é 1.
        # Precisamos subtrair os dias até a última sexta:
        if today.weekday() in [calendar.SATURDAY, calendar.SUNDAY]:
            # Se é fim de semana, a última sexta foi há 1 ou 2 dias.
            last_friday_passada = today - timedelta(days=days_since_last_friday) 
        else:
             # Se é Terça-feira (1), a última sexta foi há 4 dias.
            last_friday_passada = today - timedelta(days=days_since_last_friday + 7)
            
        end_date = last_friday_passada - timedelta(days=7) # Sexta da semana retrasada

    
    # O último dia útil é sempre a Sexta-feira
    ultimo_dia_util = end_date
    
    # O primeiro dia útil é a Segunda-feira (4 dias antes da Sexta)
    primeiro_dia_util = ultimo_dia_util - timedelta(days=4)

    # Formato 'dd.mm a dd.mm'
    return f"{primeiro_dia_util.strftime('%d.%m')} a {ultimo_dia_util.strftime('%d.%m')}"


@st.cache_data
def load_data(sheet_name: str) -> Dict[str, pd.DataFrame]:
    """
    Conecta ao Google Sheets e carrega os dados das abas ALTA, EMERGENCIAL,
    e a aba de Backup calculada dinamicamente.
    """
    data = {}
    
    # 1. Calcula o nome da aba de backup
    BACKUP_SHEET_NAME = calculate_backup_sheet_name()
    ABAS_A_BUSCAR = ABAS_PRINCIPAIS + [BACKUP_SHEET_NAME]
    
    # --- AUTENTICAÇÃO ATUALIZADA PARA O STREAMLIT CLOUD ---
    try:
        # Tenta carregar as credenciais dos segredos do Streamlit
        creds_json = st.secrets.get("google_sheets_service_account")
        
        if creds_json:
            # Autenticação via Streamlit Secrets
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, gspread.auth.SCOPES)
            gc = gspread.authorize(creds)
        else:
            # Fallback para execução local (caso não use secrets)
            # Requer ServiceAccountCredentials importado do oauth2client.service_account
            gc = gspread.service_account(filename="acesso.json")
            
    except Exception as e:
        st.error(f"Erro ao autenticar no Google Sheets (Verifique Secrets/acesso.json). Erro: {e}")
        return None
    # ----------------------------------------------------
    
    try:
        sh = gc.open(sheet_name)
        
        for tab in ABAS_A_BUSCAR:
            try:
                worksheet = sh.worksheet(tab)
                list_of_lists = worksheet.get_all_values()
                
                if len(list_of_lists) < 2:
                    st.warning(f"A aba '{tab}' está vazia ou não tem cabeçalho.")
                    continue

                # Pula a primeira linha (cabeçalho da planilha V2)
                header = list_of_lists[1]
                data_rows = list_of_lists[2:] 
                df = pd.DataFrame(data_rows, columns=header)
                
                if not all(col in df.columns for col in COLUNAS_DADOS):
                    st.error(f"Erro: A aba '{tab}' não contém todas as colunas requeridas: {COLUNAS_DADOS}")
                    # Para abas de backup, podemos apenas ignorar a aba se as colunas estiverem erradas
                    if tab == BACKUP_SHEET_NAME:
                        continue 
                    return None
                
                df['PEDIDO'] = df['PEDIDO'].astype(str)
                data[tab] = df
                
            # MUDANÇA AQUI: Acessando a exceção diretamente do gspread
            except gspread.WorksheetNotFound: 
                # É muito comum que a aba de backup ainda não exista ou tenha o nome errado
                if tab == BACKUP_SHEET_NAME:
                    st.warning(f"Aviso: Aba de Backup esperada '{BACKUP_SHEET_NAME}' não foi encontrada. Ignorando esta aba na busca.")
                    continue
                st.error(f"Erro: A aba '{tab}' não foi encontrada na planilha '{sheet_name}'. Verifique o nome.")
                return None
        
        # Adiciona a aba de backup ao Carro Foco para que o usuário possa buscá-la
        if BACKUP_SHEET_NAME not in LISTA_CARROS_CADASTRO:
             # Isso garante que a aba de backup (com nome de data) possa ser selecionada como critério
             LISTA_CARROS_CADASTRO.insert(1, BACKUP_SHEET_NAME) 
        
        return data
        
    # MUDANÇA AQUI: Acessando a exceção diretamente do gspread
    except gspread.FileAccessError:
        st.error(f"Erro de Acesso: Verifique se o e-mail da conta de serviço possui permissão de leitura na planilha '{sheet_name}'.")
        return None
        
    except Exception as e:
        # Esta exceção captura erros genéricos, incluindo a falha de conexão do gspread.
        st.error(f"Ocorreu um erro inesperado ao carregar os dados: {e}")
        return None


# ----------------------------------------------------
# 2. FUNÇÕES DE BUSCA E CONTROLE DE ESTADO
# ----------------------------------------------------

# Funções initialize_state, search_pedido, perform_search, handle_search, 
# remove_last_search, clear_search_history (MANTIDAS)

def initialize_state():
    if 'search_history' not in st.session_state:
        st.session_state['search_history'] = []
    if 'feedback_message' not in st.session_state:
        st.session_state['feedback_message'] = None


def search_pedido(pedido: str, data: Dict[str, pd.DataFrame], carro_selecionado: str) -> Dict[str, str]:
    """Busca um único pedido em todas as abas carregadas."""
    found_data = {
        "Pedido": pedido, "Origem": "", "Data": "", COLUNA_CARRO: "", 
        "Status": "Pedido Não Encontrado", "Carro Foco": carro_selecionado
    }
    
    # Itera sobre todas as abas carregadas (ALTA, EMERGENCIAL, BACKUP)
    for sheet_name, df in data.items():
        match = df[df['PEDIDO'].astype(str) == pedido]
        if not match.empty:
            row = match.iloc[0]
            found_data.update({
                "Origem": sheet_name, "Data": row['DATA'], 
                COLUNA_CARRO: row[COLUNA_CARRO], "Status": row['STATUS']
            })
            return found_data
    return found_data


def perform_search(pedidos: List[str], data: Dict[str, pd.DataFrame], carro_selecionado: str) -> List[Dict[str, str]]:
    """Executa a busca para uma lista de pedidos."""
    if not pedidos or data is None:
        return []

    results = []
    for pedido in pedidos:
        result = search_pedido(pedido, data, carro_selecionado)
        results.append(result)
        
    return results


def handle_search(data_frames: Dict[str, pd.DataFrame]):
    """Callback para o botão BUSCAR. Adiciona/Substitui tabela no histórico."""
    
    input_text = st.session_state.backlog_input_text
    carro_selecionado = st.session_state.carro_select
    parsed_pedidos = parse_pedidos(input_text)
    
    if carro_selecionado == LISTA_CARROS_CADASTRO[0]:
        st.session_state['feedback_message'] = "ERRO: Por favor, selecione um critério (Carro Foco) antes de buscar."
        st.rerun()
        return

    if not parsed_pedidos:
        st.session_state['feedback_message'] = "ERRO: Nenhum pedido válido encontrado para buscar."
        st.rerun()
        return 
        
    search_results = perform_search(parsed_pedidos, data_frames, carro_selecionado)
    
    if search_results:
        new_df = pd.DataFrame(search_results)
        
        substituted = False
        new_history = []
        
        for existing_df in st.session_state['search_history']:
            existing_carro = existing_df['Carro Foco'].iloc[0]
            
            if existing_carro == carro_selecionado:
                new_history.append(new_df)
                substituted = True
            else:
                new_history.append(existing_df)
        
        if not substituted:
            new_history.append(new_df)

        st.session_state['search_history'] = new_history
        
        action_msg = "substituída" if substituted else "adicionada"
        st.session_state['feedback_message'] = f"✅ Tabela para '{carro_selecionado}' {action_msg}. {len(parsed_pedidos)} pedidos processados."
        
    st.session_state.backlog_input_text = ""
    st.rerun()


def remove_last_search():
    """Remove o último DataFrame (última tabela de pesquisa) do histórico."""
    if st.session_state['search_history']:
        removed_df = st.session_state['search_history'].pop()
        carro_removido = removed_df['Carro Foco'].iloc[0]
        st.session_state['feedback_message'] = f"✅ Última pesquisa (Tabela: {carro_removido}) removida com sucesso."
    else:
        st.session_state['feedback_message'] = "AVISO: Não há pesquisas no histórico para remover."
    st.rerun()


def clear_search_history():
    """Limpa todo o histórico de pesquisas."""
    st.session_state['search_history'] = []
    st.session_state['feedback_message'] = "✅ Histórico de buscas limpo com sucesso."
    st.rerun()


# ----------------------------------------------------
# 3. FUNÇÕES DE ESTILO E EXIBIÇÃO (Permanecem iguais)
# ----------------------------------------------------

def apply_text_color_by_status(row):
    """
    Define o estilo (cor do texto) para cada célula na linha baseada no Status.
    """
    style_list = []
    is_error = row['Status'] == "Pedido Não Encontrado"
    
    for col in row.index:
        
        if is_error:
            if col in ['Pedido', 'Status']:
                style_list.append('color: red; font-weight: bold;')
            else:
                style_list.append('color: grey;') 
        
        else:
            if col in ['Pedido', 'Status']:
                style_list.append('color: green; font-weight: bold;')
            else:
                style_list.append(None)
                
    return style_list


def display_search_history():
    """
    Itera sobre o histórico de DataFrames e exibe uma tabela separada para cada um,
    ordenando os pedidos encontrados antes dos pedidos não encontrados.
    """
    
    history = st.session_state['search_history']
    
    if not history:
        st.info("O histórico de buscas está vazio. Busque por pedidos e associe a um carro para criar tabelas.")
        return

    st.subheader(f"📊 Histórico de Pesquisas ({len(history)} tabelas)")
    
    for i, df in enumerate(history):
        
        carro_foco = df['Carro Foco'].iloc[0]
        
        df['Sort_Key'] = df['Status'].apply(lambda x: 1 if x == "Pedido Não Encontrado" else 0)
        df_sorted = df.sort_values(by='Sort_Key', ascending=True)
        df_sorted = df_sorted.drop(columns=['Sort_Key'])
        
        df_display = df_sorted.copy()
        df_display = df_display.rename(columns={COLUNA_CARRO: 'Carro Planilha'})
        df_display = df_display.drop(columns=['Carro Foco'])
        
        column_order = ['Pedido', 'Origem', 'Data', 'Carro Planilha', 'Status']
        df_display = df_display[column_order]

        styled_df = (
            df_display.style
            .apply(apply_text_color_by_status, axis=1) 
            .set_properties(**{'text-align': 'center'}) 
        )
        
        st.markdown(f"### 🚗 CRITÉRIO/CARRO: {carro_foco}")
        
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        st.markdown("---")


# ----------------------------------------------------
# 4. FUNÇÃO PRINCIPAL (APP)
# ----------------------------------------------------

def app():
    
    initialize_state()

    st.title("🔍 BACKLOG: Pesquisa Rápida de Pedidos")
    st.markdown("---")

    # Exibe a aba de backup que está sendo buscada
    try:
        BACKUP_SHEET_NAME = calculate_backup_sheet_name()
        st.info(f"Aba de Backup de Emergencial sendo rastreada: **{BACKUP_SHEET_NAME}**")
    except Exception:
        pass # Ignora erros de cálculo de data na info bar
        
    # EXIBE FEEDBACK
    if st.session_state.get('feedback_message'):
        if "ERRO" in st.session_state['feedback_message']:
            st.error(st.session_state['feedback_message'])
        elif "AVISO" in st.session_state['feedback_message']:
             st.warning(st.session_state['feedback_message'])
        else:
            st.success(st.session_state['feedback_message'])
        st.session_state['feedback_message'] = None 

    
    # === 1. CARREGAR DADOS ===
    # O cache garante que load_data só rode uma vez por sessão Streamlit (ou se as credenciais mudarem)
    with st.spinner(f"Conectando ao Google Planilhas: {PLANILHA_NOME}..."):
        data_frames = load_data(PLANILHA_NOME)
    
    if data_frames is None:
        st.stop()
    
    
    # === 2. ENTRADA DE DADOS E BOTÕES DE AÇÃO ===
    st.subheader("Pedidos e Critério")

    col1, col2 = st.columns([0.6, 0.4])

    with col1:
        st.text_area(
            "Cole aqui o(s) número(s) do(s) pedido(s):",
            height=100,
            key='backlog_input_text', 
            placeholder="Ex: 12345 54321, 67890..."
        )
    
    with col2:
        # A LISTA_CARROS_CADASTRO é modificada dentro de load_data para incluir o nome da aba de backup
        carro_selecionado = st.selectbox(
            "Selecione o Critério (Carro Foco ou Aba de Backup):",
            options=LISTA_CARROS_CADASTRO,
            key='carro_select'
        )
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        
        st.button(
            "BUSCAR INFORMAÇÕES", 
            type="primary", 
            use_container_width=True,
            on_click=handle_search,
            args=(data_frames,)
        )
    
    parsed_pedidos_preview = parse_pedidos(st.session_state.backlog_input_text)
    st.info(f"Prévia dos pedidos tratados (únicos): {', '.join(parsed_pedidos_preview) if parsed_pedidos_preview else 'Nenhum pedido válido encontrado.'}")

    st.markdown("---")
    
    
    # === 3. CONTROLES DE HISTÓRICO E EXIBIÇÃO ===
    
    col_hist_1, col_hist_2 = st.columns(2)
    
    with col_hist_1:
        st.button(
            "⬅️ REMOVER ÚLTIMA PESQUISA",
            use_container_width=True,
            on_click=remove_last_search
        )

    with col_hist_2:
        st.button(
            "❌ LIMPAR DADOS",
            help="Limpa todo o histórico de buscas.",
            use_container_width=True,
            on_click=clear_search_history
        )

    st.markdown("---")

    display_search_history()


# Chamada da função principal para execução
if __name__ == '__main__':
    app()