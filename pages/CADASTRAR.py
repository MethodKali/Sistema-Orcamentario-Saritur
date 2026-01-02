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

st.title("📝 Gestão de Pedidos e Solicitações")

# Mensagens de Estado
if "mensagem_sucesso" in st.session_state:
    st.success(st.session_state.mensagem_sucesso)
    del st.session_state.mensagem_sucesso
if "alertas_erro" in st.session_state:
    for msg in st.session_state.alertas_erro: st.error(msg)
    del st.session_state.alertas_erro
if "alertas_info" in st.session_state:
    for msg in st.session_state.alertas_info: st.info(msg)
    del st.session_state.alertas_info

# FORMULÁRIO
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
        status_selecionado = ""
        if aba_dest == "ALTA":
            status_selecionado = st.selectbox("Status Solicitação *", ["COTAÇÃO", "PEDIDO", "APROVADA", "NÃO APROVADA"])
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
        # Busca atualizada para validar
        mapa_geral = buscar_em_todas_as_abas_detalhado(sh, todos_itens)
        
        itens_para_cadastrar = []
        st.session_state.alertas_erro = []
        st.session_state.alertas_info = []

        # Lógica de Triagem: O que entra e o que barra
        for item in todos_itens:
            if item in mapa_geral:
                # Se for PEDIDO na ALTA e o item duplicado for a Solicitação que vamos excluir, permitimos.
                if aba_dest == "ALTA" and status_selecionado == "PEDIDO" and item in s_nums:
                    itens_para_cadastrar.append(item)
                else:
                    st.session_state.alertas_erro.append(f"❌ Item {item} ignorado: já existe na aba {mapa_geral[item]}.")
            else:
                itens_para_cadastrar.append(item)

        if not itens_para_cadastrar:
            st.rerun()

        # Exclusão automática (Só ALTA -> PEDIDO)
        msg_exc = ""
        if aba_dest == "ALTA" and status_selecionado == "PEDIDO" and s_nums:
            q = excluir_por_numero(sh, "ALTA", s_nums) + excluir_por_numero(sh, "EMERGENCIAL", s_nums)
            if q > 0: msg_exc = " (Antigo removido)"

        # Preparação para Append (Garante inserção no final real, ignorando filtros)
        ws = sh.worksheet(aba_dest)
        novas_linhas = []
        dt_f = data_cad.strftime("%d/%m/%Y")

        for item in itens_para_cadastrar:
            if aba_dest == "ALTA":
                # Nota: a fórmula precisará ser ajustada manualmente ou via script se a linha mudar, 
                # mas o append_rows lida bem com valores brutos.
                status_item = status_selecionado if item in s_nums else "PEDIDO"
                # Deixamos a coluna A (fórmula) para o Sheets calcular ou inserimos texto
                novas_linhas.append(["", dt_f, unidade, carro, item, valor, fornecedor, status_item])
            else:
                # Emergencial: Status Vazio ("") conforme solicitado
                novas_linhas.append([unidade, datetime.now().strftime("%d/%m/%Y %H:%M:%S"), carro, item, valor, fornecedor, "", "", "", ""])

        if novas_linhas:
            ws.append_rows(novas_linhas, value_input_option='USER_ENTERED')
            st.session_state.mensagem_sucesso = f"✅ {len(novas_linhas)} itens cadastrados em {aba_dest}.{msg_exc}"
        
        st.rerun()

# --- EXCLUSÃO MANUAL ---
st.markdown("---")
st.subheader("🗑️ Exclusão Manual")
with st.expander("Ferramentas"):
    with st.form("form_exclusao", clear_on_submit=True):
        aba_ex = st.selectbox("Aba", ["ALTA", "EMERGENCIAL"])
        txt_ex = st.text_area("Números para excluir")
        if st.form_submit_button("EXCLUIR"):
            n_ex = extrair_numeros_da_string(txt_ex)
            if n_ex:
                qtd = excluir_por_numero(sh, aba_ex, n_ex)
                st.session_state.mensagem_sucesso = f"🗑️ {qtd} item(s) removidos."
                st.rerun()