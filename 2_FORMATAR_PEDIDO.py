import streamlit as st
import datetime
import re
import pandas as pd 
import uuid 
# Importação necessária para injetar código HTML/JavaScript
from streamlit.components.v1 import html 

# -----------------------
# FUNÇÕES DE UTILIDADE (MANTIDAS)
# -----------------------

def parse_pedidos(text):
    """Função de parsing corrigida e robusta."""
    if not text:
        return []
    
    text_cleaned = re.sub(r'[^\d]', ' ', text)
    raw_list = re.split(r'\s+', text_cleaned.strip())
    pedidos_limpos = {p for p in raw_list if p.isdigit() and len(p) > 0}
    
    return sorted(list(pedidos_limpos))


def update_formatted_list(current_data, new_pedidos, action, date_str):
    """
    Atualiza a estrutura de dados agregada. 
    Garante que pedidos adicionados não existam em outras ações/datas.
    """
    key = f"{action} {date_str}"
    
    # 1. Adiciona/Atualiza a lista na chave atual
    if key in current_data:
        existing_pedidos = set(current_data[key])
        pedidos_to_add = [p for p in new_pedidos if p not in existing_pedidos]
        current_data[key].extend(pedidos_to_add)
    else:
        current_data[key] = new_pedidos
    
    # 2. Remove duplicatas de outras chaves
    pedidos_set_current = set(current_data[key])
    for other_key, pedido_list in current_data.items():
        if other_key != key:
            # Mantém apenas os pedidos que NÃO estão na lista que acabamos de adicionar/atualizar
            current_data[other_key] = [p for p in pedido_list if p not in pedidos_set_current]

    # 3. Limpa chaves vazias e ordena
    current_data = {k: sorted(v) for k, v in current_data.items() if v}
    
    return current_data


def render_formatted_output(data):
    """Formata a estrutura de dados agregada em uma única string de saída."""
    if not data:
        return ""
        
    output_parts = []
    
    # Ordena as chaves (Ação Data) antes de formatar
    for action_date_str, pedidos_list in sorted(data.items()): 
        if not pedidos_list:
            continue
            
        pedidos_str = ", ".join(pedidos_list)
        formatted_part = f"{pedidos_str} - {action_date_str}"
        output_parts.append(formatted_part)
        
    return " | ".join(output_parts)


# -----------------------
# FUNÇÕES DE CONTROLE DE ESTADO
# -----------------------

def initialize_state():
    """Inicializa chaves de estado essenciais e o driver do input."""
    if 'formatted_data' not in st.session_state:
        st.session_state['formatted_data'] = {}

    if 'input_widget_key' not in st.session_state:
        st.session_state['input_widget_key'] = str(uuid.uuid4())
        
    if 'feedback_message' not in st.session_state:
        st.session_state['feedback_message'] = None
        
    if 'needs_rerun' not in st.session_state:
        st.session_state['needs_rerun'] = False
        
    if 'final_output_string_copy' not in st.session_state:
        st.session_state['final_output_string_copy'] = ""


def clear_all_data():
    """Callback para limpar dados formatados e forçar recarregamento."""
    st.session_state['formatted_data'] = {}
    st.session_state['input_widget_key'] = str(uuid.uuid4())
    st.session_state['feedback_message'] = "Dados de formatação limpos com sucesso!"
    st.session_state['needs_rerun'] = True 


def handle_update(action):
    """
    Função de callback que processa a ação, limpa o input e define a flag de recarga.
    """
    
    raw_text_input_key = st.session_state['input_widget_key']
    raw_text_input = st.session_state.get(raw_text_input_key, '')
    
    date_selected = st.session_state.get('date_picker', datetime.date.today())
    date_str_formatted = date_selected.strftime('%d/%m')
    
    parsed_pedidos = parse_pedidos(raw_text_input)

    if not parsed_pedidos:
        st.session_state['feedback_message'] = "ERRO: Nenhum pedido válido encontrado para processar."
        return 
        
    # 1. Atualiza a lista formatada (OUTPUT)
    st.session_state['formatted_data'] = update_formatted_list(
        st.session_state['formatted_data'], 
        parsed_pedidos, 
        action, 
        date_str_formatted
    )
    
    # 2. LIMPEZA FORÇADA: TROCA A CHAVE DO WIDGET
    st.session_state['input_widget_key'] = str(uuid.uuid4())
    
    # 3. FEEDBACK
    st.session_state['feedback_message'] = f"✅ Pedidos processados como '{action}'. O resultado está pronto na caixa abaixo."
    
    # 4. DEFINE A FLAG DE RERUN
    st.session_state['needs_rerun'] = True


# -----------------------
# FUNÇÃO DE CÓPIA (LEGADA: MAIS RESISTENTE A BLOQUEIOS)
# -----------------------

def copy_to_clipboard():
    """Injeta JavaScript para copiar o conteúdo."""
    output_text = st.session_state.get('final_output_string_copy', '')
    
    if not output_text:
        st.session_state['feedback_message'] = "ERRO: Não há texto para copiar na Saída Formatada."
        st.session_state['needs_rerun'] = True
        return 
        
    safe_output_text = output_text.replace("'", "\\'").replace('\n', '\\n')

    js_code = f"""
        <script>
            var tempInput = document.createElement('textarea');
            tempInput.value = '{safe_output_text}';
            document.body.appendChild(tempInput);
            
            tempInput.select();
            tempInput.setSelectionRange(0, 99999); 
            
            var successful = false;
            try {{
                successful = document.execCommand('copy');
            }} catch (err) {{
                console.error('Erro ao usar execCommand:', err);
            }}
            
            document.body.removeChild(tempInput);
            
            if (!successful) {{
                 alert('Falha na cópia automática (API moderna e legada bloqueadas). Copie o texto manualmente.');
            }}
        </script>
    """
    
    html(js_code, height=0, width=0)
    
    st.session_state['feedback_message'] = "✅ Texto copiado para a área de transferência!"
    st.session_state['needs_rerun'] = True


# -----------------------
# FUNÇÃO PRINCIPAL (APP)
# -----------------------

def app(): 
    
    initialize_state()

    # CONTROLE DE RERUN: CHAMA st.rerun() SOMENTE SE A FLAG ESTIVER ATIVA
    if st.session_state.get('needs_rerun'):
        st.session_state['needs_rerun'] = False 
        st.rerun() 

    st.title("✂️ FORMATAR PEDIDO")
    st.markdown("---")

    # EXIBE FEEDBACK APÓS O PROCESSAMENTO
    if st.session_state.get('feedback_message'):
        if "ERRO" in st.session_state['feedback_message']:
            st.error(st.session_state['feedback_message'])
        else:
            st.success(st.session_state['feedback_message'])
        st.session_state['feedback_message'] = None 
        
    
    # === 1. INPUT DE PEDIDOS ===
    st.subheader("1. Anotar Pedidos")
    
    st.text_area(
        "Cole aqui o(s) número(s) do(s) pedido(s):",
        height=150,
        key=st.session_state['input_widget_key'], 
        value="" 
    )
    
    # PRÉVIA
    pedidos_raw_for_preview = st.session_state.get(st.session_state['input_widget_key'], '')
    parsed_preview = parse_pedidos(pedidos_raw_for_preview)
    st.info(f"Prévia dos pedidos tratados (únicos): {', '.join(parsed_preview) if parsed_preview else 'Nenhum pedido válido encontrado.'}")

    
    # === 2. AÇÃO E DATA (CONTROLES) - ORGANIZADO POR COLUNAS VERTICAIS ===
    st.subheader("2. Definir Ação e Data (Clique Único)")
    
    col_date, col_actions = st.columns([0.4, 0.6])
    
    # DATA
    with col_date:
        st.date_input(
            "Selecione a Data para a Ação:",
            datetime.date.today(),
            key="date_picker",
            min_value=datetime.date(2020, 1, 1)
        )  
    # BOTÕES DE AÇÃO (ORGANIZADOS)
    with col_actions:
        st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True) 
        
        # Cria 2 colunas para os botões (Pagamento e Entrega)
        col_pagamento, col_entrega = st.columns(2)
        
        # --- COLUNA 1: PAGAMENTO ---
        with col_pagamento:
            st.button(
                "PROGRAMAR PGTO", 
                on_click=handle_update, 
                args=["PROG. PGTO"],
                use_container_width=True,
                type="primary",
                help="Formato: PEDIDO - PROG. PGTO DD/MM"
            )
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True) 
            
            st.button(
                "PAGO", 
                on_click=handle_update, 
                args=["PAGO"],
                use_container_width=True,
                type="primary",
                help="Formato: PEDIDO - PAGO DD/MM"
            )

        # --- COLUNA 2: ENTREGA ---
        with col_entrega:
            st.button(
                "PREV. ENTREGA", 
                on_click=handle_update, 
                args=["PREV. ENTREGA"], 
                use_container_width=True,
                type="secondary",
                help="Formato: PEDIDO - PREV. ENTREGA DD/MM"
            )
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True) 

            st.button(
                "ENTREGUE", 
                on_click=handle_update, 
                args=["ENTREGUE"], 
                use_container_width=True,
                type="secondary",
                help="Formato: PEDIDO - ENTREGUE DD/MM"
            )

    st.markdown("---")


    # === 3. CAIXA DE EXIBIÇÃO (OUTPUT) ===
    st.subheader("3. Resultado Final (Formatação)")
    
    final_output_string = render_formatted_output(st.session_state['formatted_data'])
    
    # IMPORTANTE: ATUALIZA A CHAVE DE COPIA COM O VALOR MAIS RECENTE
    st.session_state['final_output_string_copy'] = final_output_string

    st.text_area(
        "Saída Formatada:",
        value=final_output_string,
        height=300,
        key='output_box_key',
        help="Este campo exibe o texto formatado completo."
    )
    
    
    col_copy, col_clear = st.columns(2)
    
    with col_copy:
        st.button("COPIAR", 
                  on_click=copy_to_clipboard, 
                  use_container_width=True)
        
    with col_clear:
        st.button("LIMPAR DADOS", 
                  help="Limpa todo o histórico de formatação.", 
                  on_click=clear_all_data, 
                  use_container_width=True) 

# Chamada da função principal para execução automática no Streamlit pages/
if __name__ == '__main__':
    app()