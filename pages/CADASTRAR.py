import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import re

# --- CONFIGURAÇÕES ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_ID = "1n5I4U7siMsRB-eeAcWr56zNqudlcVbK7T2OImIjnMWs"

def get_gspread_client():
    try:
        creds_json = st.secrets.get("google_sheets_service_account")
        if creds_json:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(creds_json), SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("acesso.json", SCOPE)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro de autenticação: {e}")
        return None

def extrair_numeros_da_string(texto):
    if not texto: return []
    return re.findall(r'\d+', str(texto))

def limpar_apenas_numeros(texto):
    return re.sub(r'\D', '', str(texto))

def get_actual_next_row(ws, col_index):
    col_values = ws.col_values(col_index)
    for i, value in enumerate(col_values[2:], start=3):
        if not value.strip():
            return i
    return len(col_values) + 1

def scanner_duplicatas_globais(sh):
    dados_alta = sh.worksheet("ALTA").get_all_values()[2:]
    dados_emerg = sh.worksheet("EMERGENCIAL").get_all_values()[2:]
    pedidos_alta = [limpar_apenas_numeros(r[4]) for r in dados_alta if len(r) > 4 and limpar_apenas_numeros(r[4])]
    pedidos_emerg = [limpar_apenas_numeros(r[3]) for r in dados_emerg if len(r) > 3 and limpar_apenas_numeros(r[3])]
    return sorted(list(set(pedidos_alta).intersection(set(pedidos_emerg))))

def buscar_em_todas_as_abas_detalhado(sh, lista_numeros):
    mapa_encontrados = {}
    dados_alta = sh.worksheet("ALTA").get_all_values()
    dados_emerg = sh.worksheet("EMERGENCIAL").get_all_values()
    for num in lista_numeros:
        for row in dados_alta[2:]:
            if len(row) > 4 and limpar_apenas_numeros(row[4]) == num:
                mapa_encontrados[num] = "ALTA"
                break
        if num not in mapa_encontrados:
            for row in dados_emerg[2:]:
                if len(row) > 3 and limpar_apenas_numeros(row[3]) == num:
                    mapa_encontrados[num] = "EMERGENCIAL"
                    break
    return mapa_encontrados

def excluir_por_numero(sh, aba_nome, lista_numeros):
    ws = sh.worksheet(aba_nome)
    col_idx = 5 if aba_nome == "ALTA" else 4
    col_values = ws.col_values(col_idx)
    linhas_para_deletar = []
    for i, valor in enumerate(col_values):
        if limpar_apenas_numeros(valor) in lista_numeros:
            linhas_para_deletar.append(i + 1)
    if linhas_para_deletar:
        for linha in sorted(linhas_para_deletar, reverse=True):
            ws.delete_rows(linha)
        return len(linhas_para_deletar)
    return 0

# --- INÍCIO DO APP ---
client = get_gspread_client()
sh = client.open_by_key(SPREADSHEET_ID)

# SIDEBAR
st.sidebar.title("🔍 Scanner de Duplicatas")
duplicas_globais = scanner_duplicatas_globais(sh)
if duplicas_globais:
    st.sidebar.warning(f"Existem {len(duplicas_globais)} duplicatas!")
    if st.sidebar.button("Mostrar Lista"):
        for num in duplicas_globais: st.sidebar.code(num)
else:
    st.sidebar.success("Sem duplicatas entre abas.")

st.title("📝 Gestão de Pedidos e Solicitações")

# Exibição de mensagens do session_state
if "mensagem_sucesso" in st.session_state:
    st.success(st.session_state.mensagem_sucesso)
    del st.session_state.mensagem_sucesso
if "alertas_info" in st.session_state:
    for msg in st.session_state.alertas_info: st.info(msg)
    del st.session_state.alertas_info
if "alertas_warning" in st.session_state:
    for msg in st.session_state.alertas_warning: st.warning(msg)
    del st.session_state.alertas_warning

# FORMULÁRIO DE CADASTRO
aba_dest = st.selectbox("Selecione a Aba de Destino", ["ALTA", "EMERGENCIAL"])

with st.form("form_cadastro", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        data_cad = st.date_input("Data *", datetime.now())
        unidade = st.selectbox("Unidade *", ["INDÚSTRIA", "JARDIM MONTANHÊS", "SÃO MARCOS", "NOVA LIMA", "ITAÚNA", "LAGOA SANTA", "DURVAL DE BARROS", "MONTES CLAROS", "VARGINHA", "NEVES", "LAVRAS", "IPATINGA", "VESPASIANO", "GARANTIA", "VENDA DE VEÍCULOS", "ADMINISTRATIVO", "PREDIO ADM", "EXPEDIÇÃO", "CEL. FABRICIANO", "OLIVEIRA", "MORRO ALTO", "TRANSNORTE", "TIMOTEO", "ADMINISTRAÇÃO"])
        carro = st.text_input("Carro | Utilização")
        fornecedor = st.text_input("Fornecedor")
    with col2:
        valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
        
        # STATUS DINÂMICO (Apenas para ALTA)
        if aba_dest == "ALTA":
            status_selecionado = st.selectbox("Status Solicitação *", ["COTAÇÃO", "PEDIDO", "APROVADA", "NÃO APROVADA"])
        else:
            status_selecionado = st.text_input("Status Emergencial (Opcional)", value="PENDENTE")
            
        solicitacao_raw = st.text_input("Nº Solicitação")
        pedidos_raw = st.text_area("Bloco de Pedidos")
    
    btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

if btn_cadastrar:
    s_nums = extrair_numeros_da_string(solicitacao_raw)
    p_nums = extrair_numeros_da_string(pedidos_raw)
    todos_itens = s_nums + p_nums
    
    if not todos_itens:
        st.warning("Nenhum número detectado.")
    else:
        mapa_geral = buscar_em_todas_as_abas_detalhado(sh, todos_itens)
        st.session_state.alertas_warning = []
        st.session_state.alertas_info = []

        # Lógica de validação e alertas para ALTA
        if aba_dest == "ALTA":
            # 1. Tratar Solicitações
            if status_selecionado == "COTAÇÃO":
                for s in s_nums:
                    if s in mapa_geral:
                        st.session_state.alertas_warning.append(f"⚠️ A solicitação {s} já está em COTAÇÃO na aba {mapa_geral[s]}")
                        mapa_geral.pop(s)
                    else:
                        st.session_state.alertas_info.append(f"ℹ️ A solicitação {s} foi incluída como COTAÇÃO.")
            
            if status_selecionado == "PEDIDO":
                for s in s_nums:
                    if s in mapa_geral: mapa_geral.pop(s)

            # 2. Tratar Pedidos (Sempre status PEDIDO, então removemos do mapa de erro se forem ser substituídos ou apenas ignora erro se for a regra da empresa)
            for p in p_nums:
                if p in mapa_geral:
                    # Se o pedido já existe, você quer bloquear ou sobrescrever? 
                    # Por padrão, mantemos o erro de duplicata para segurança.
                    pass 

        # Se houver duplicata fatal (números que já existem e não foram tratados acima)
        if mapa_geral:
            for num, aba in mapa_geral.items():
                st.error(f"❌ O número {num} já existe na aba {aba}!")
            st.stop()

        # Exclusão automática (Só para ALTA quando a solicitação vira PEDIDO)
        msg_exc = ""
        if aba_dest == "ALTA" and status_selecionado == "PEDIDO" and s_nums:
            q = excluir_por_numero(sh, "ALTA", s_nums) + excluir_por_numero(sh, "EMERGENCIAL", s_nums)
            if q > 0: msg_exc = f" (Solicitação {', '.join(s_nums)} removida)"

        # --- CADASTRO FINAL ---
        ws = sh.worksheet(aba_dest)
        dt_f = data_cad.strftime("%d/%m/%Y")
        col_ref = 5 if aba_dest == "ALTA" else 4
        
        # Cadastro das Solicitações (Status do seletor)
        for item in s_nums:
            prox = get_actual_next_row(ws, col_ref)
            if aba_dest == "ALTA":
                linha = [f'=IF(B{prox}=""; ""; TODAY()-B{prox})', dt_f, unidade, carro, item, valor, fornecedor, status_selecionado]
                ws.update(f"A{prox}:H{prox}", [linha], value_input_option='USER_ENTERED')
            else:
                linha = [unidade, datetime.now().strftime("%d/%m/%Y %H:%M:%S"), carro, item, valor, fornecedor, "", "", "", status_selecionado]
                ws.update(f"A{prox}:J{prox}", [linha], value_input_option='USER_ENTERED')

        # Cadastro dos Pedidos (Sempre Status PEDIDO para ALTA)
        for item in p_nums:
            prox = get_actual_next_row(ws, col_ref)
            status_final_pedido = "PEDIDO" if aba_dest == "ALTA" else status_selecionado
            
            if aba_dest == "ALTA":
                linha = [f'=IF(B{prox}=""; ""; TODAY()-B{prox})', dt_f, unidade, carro, item, valor, fornecedor, status_final_pedido]
                ws.update(f"A{prox}:H{prox}", [linha], value_input_option='USER_ENTERED')
            else:
                linha = [unidade, datetime.now().strftime("%d/%m/%Y %H:%M:%S"), carro, item, valor, fornecedor, "", "", "", status_final_pedido]
                ws.update(f"A{prox}:J{prox}", [linha], value_input_option='USER_ENTERED')

        st.session_state.mensagem_sucesso = f"✅ Processamento concluído na aba {aba_dest}!{msg_exc}"
        st.rerun()

# --- EXCLUSÃO MANUAL ---
st.markdown("---")
st.subheader("🗑️ Exclusão Manual")
with st.expander("Ferramentas"):
    with st.form("form_exclusao", clear_on_submit=True):
        aba_ex = st.selectbox("Aba", ["ALTA", "EMERGENCIAL"])
        txt_ex = st.text_area("Cole os números para excluir")
        if st.form_submit_button("EXCLUIR DEFINITIVAMENTE"):
            n_ex = extrair_numeros_da_string(txt_ex)
            if n_ex:
                qtd = excluir_por_numero(sh, aba_ex, n_ex)
                st.session_state.mensagem_sucesso = f"🗑️ {qtd} item(s) removido(s)!"
                st.rerun()