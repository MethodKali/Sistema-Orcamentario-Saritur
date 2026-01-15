import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import re

# --- CONFIGURAÇÕES ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_ID = "1X9trwwqVCwPXY2_O667WJcOR4CHNYbBjJDVsrYNZSgc"

# Mapeamento Centralizado: Define onde o número do item (Pedido/Solicitação) fica em cada aba
# Abas de Ano: Coluna F (Índice 5) | Abas de Emergencial: Coluna D (Índice 3)
MAPA_ABAS = {
    "2025": {"col_idx": 6, "data_idx": 5},
    "2026": {"col_idx": 6, "data_idx": 5},
    "EMERGENCIAL": {"col_idx": 4, "data_idx": 3},
    "GERAL_EMERGENCIAL": {"col_idx": 4, "data_idx": 3}
}

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

def get_actual_next_row(ws, coluna_referencia=3):
    valores_coluna = ws.col_values(coluna_referencia)
    return len(valores_coluna) + 1

def scanner_duplicatas_globais(sh):
    """Verifica duplicatas cruzando TODAS as abas configuradas."""
    todos_pedidos = {} # Formato: {numero: [lista_de_abas]}
    
    for nome_aba, config in MAPA_ABAS.items():
        try:
            ws = sh.worksheet(nome_aba)
            dados = ws.get_all_values()[2:]
            idx = config["data_idx"]
            for r in dados:
                if len(r) > idx:
                    num = limpar_apenas_numeros(r[idx])
                    if num:
                        if num not in todos_pedidos: todos_pedidos[num] = []
                        todos_pedidos[num].append(nome_aba)
        except:
            continue
            
    # Retorna apenas os números que aparecem em mais de uma aba ou mais de uma vez
    duplicados = [n for n, abas in todos_pedidos.items() if len(abas) > 1]
    return sorted(duplicados)

def buscar_em_todas_as_abas_detalhado(sh, lista_numeros):
    """Busca detalhada para avisar o usuário antes de cadastrar."""
    mapa_encontrados = {}
    for nome_aba, config in MAPA_ABAS.items():
        try:
            ws = sh.worksheet(nome_aba)
            dados = ws.get_all_values()[2:]
            idx = config["data_idx"]
            for row in dados:
                if len(row) > idx:
                    num_limpo = limpar_apenas_numeros(row[idx])
                    if num_limpo in lista_numeros:
                        mapa_encontrados[num_limpo] = nome_aba
        except:
            continue
    return mapa_encontrados

def excluir_por_numero(sh, aba_nome, lista_numeros):
    """Remove linhas baseado no mapa de colunas dinâmico."""
    if aba_nome not in MAPA_ABAS: return 0
    ws = sh.worksheet(aba_nome)
    col_idx = MAPA_ABAS[aba_nome]["col_idx"]
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
if not client: st.stop()
sh = client.open_by_key(SPREADSHEET_ID)

# --- SIDEBAR: SCANNER DE DUPLICATAS ---
st.sidebar.title("🔍 Scanner de Duplicatas")
duplicas_globais = scanner_duplicatas_globais(sh)
if duplicas_globais:
    st.sidebar.warning(f"Existem {len(duplicas_globais)} duplicatas nas abas!")
    if st.sidebar.button("Mostrar Lista"):
        for num in duplicas_globais: st.sidebar.code(num)
else:
    st.sidebar.success("Sem duplicatas entre as abas.")

st.title("📝 Gestão de Pedidos e Solicitações")

# Feedback de Mensagens
if "mensagem_sucesso" in st.session_state:
    st.success(st.session_state.mensagem_sucesso)
    del st.session_state.mensagem_sucesso
if "alertas_erro" in st.session_state:
    for msg in st.session_state.alertas_erro: st.error(msg)
    del st.session_state.alertas_erro

# Seleção de Aba agora inclui todas as opções
aba_dest = st.selectbox("Selecione a Aba de Destino", list(MAPA_ABAS.keys()))

with st.form("form_cadastro", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        data_cad = st.date_input("Data *", datetime.now())
        unidade = st.selectbox("Unidade *", ["INDUSTRIA", "JARDIM MONTANHÊS", "SÃO MARCOS", "NOVA LIMA", "ITAÚNA", "LAGOA SANTA", "DURVAL DE BARROS", "MONTES CLAROS", "VARGINHA", "NEVES", "LAVRAS", "IPATINGA", "VESPASIANO", "GARANTIA", "VENDA DE VEÍCULOS", "ADMINISTRATIVO", "PREDIO ADM", "EXPEDIÇÃO", "CEL. FABRICIANO", "OLIVEIRA", "MORRO ALTO", "TRANSNORTE", "TIMOTEO", "ADMINISTRAÇÃO"])
        carro = st.text_input("Carro | Utilização")
        fornecedor = st.text_input("Fornecedor")
    with col2:
        valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
        status_selecionado = ""
        # Status só aparece para abas de ano (2025/2026)
        if aba_dest in ["2025", "2026"]:
            status_selecionado = st.selectbox("Status Solicitação *", ["COTAÇÃO", "PEDIDO", "APROVADA", "NÃO APROVADA"])
        solicitacao_raw = st.text_input("Nº Solicitação (Para busca/exclusão)")
        pedidos_raw = st.text_area("Bloco de Pedidos (Para cadastro)")
    
    btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

if btn_cadastrar:
    s_nums = extrair_numeros_da_string(solicitacao_raw)
    p_nums = extrair_numeros_da_string(pedidos_raw)
    st.session_state.alertas_erro = []
    
    # 1. EXCLUSÃO PRÉVIA (Agora percorre todas as 4 abas)
    msg_exc = ""
    if s_nums:
        qtd_total_rem = 0
        for aba in MAPA_ABAS.keys():
            qtd_total_rem += excluir_por_numero(sh, aba, s_nums)
        if qtd_total_rem > 0: msg_exc = f" ({qtd_total_rem} antigo(s) removido(s))"

    # 2. DEFINIÇÃO DE ITENS PARA CADASTRAR
    if aba_dest in ["2025", "2026"] and status_selecionado == "PEDIDO":
        itens_para_validar = p_nums
    else:
        itens_para_validar = s_nums + p_nums

    if not itens_para_validar:
        if s_nums and status_selecionado == "PEDIDO":
            st.session_state.mensagem_sucesso = f"✅ Limpeza concluída!{msg_exc}"
            st.rerun()
        st.stop()

    # 3. VALIDAÇÃO DE DUPLICATAS
    mapa_geral = buscar_em_todas_as_abas_detalhado(sh, itens_para_validar)
    itens_finais = [i for i in itens_para_validar if i not in mapa_geral]
    for item in itens_para_validar:
        if item in mapa_geral: st.session_state.alertas_erro.append(f"❌ Item {item} já existe na aba {mapa_geral[item]}.")

    # 4. INCLUSÃO REFORÇADA
    if itens_finais:
        ws = sh.worksheet(aba_dest)
        dt_str = data_cad.strftime("%d/%m/%Y")
        prox_linha = get_actual_next_row(ws, coluna_referencia=3)
        novas_linhas = []

        for i, item in enumerate(itens_finais):
            linha_atual = prox_linha + i
            if aba_dest in ["2025", "2026"]:
                status_item = status_selecionado if item in s_nums else "PEDIDO"
                formula_dias = f'=IF(C{linha_atual}=""; ""; TODAY()-C{linha_atual})'
                novas_linhas.append(["", formula_dias, dt_str, unidade, carro, item, valor, fornecedor, status_item])
            else:
                # Lógica para EMERGENCIAL e GERAL_EMERGENCIAL
                novas_linhas.append([unidade, datetime.now().strftime("%d/%m/%Y %H:%M:%S"), carro, item, valor, fornecedor, "", "", "", ""])

        col_fim = "I" if aba_dest in ["2025", "2026"] else "J"
        range_target = f"A{prox_linha}:{col_fim}{prox_linha + len(novas_linhas) - 1}"
        ws.update(range_target, novas_linhas, value_input_option='USER_ENTERED')
        
        st.session_state.mensagem_sucesso = f"✅ {len(novas_linhas)} itens adicionados.{msg_exc}"
    
    st.rerun()

# --- EXCLUSÃO MANUAL ---
st.markdown("---")
st.subheader("🗑️ Exclusão Manual")
with st.expander("Ferramentas"):
    with st.form("form_exclusao", clear_on_submit=True):
        aba_ex = st.selectbox("Aba", list(MAPA_ABAS.keys()), key="man_aba")
        txt_ex = st.text_area("Números para excluir")
        if st.form_submit_button("EXCLUIR"):
            n_ex = extrair_numeros_da_string(txt_ex)
            if n_ex:
                qtd = excluir_por_numero(sh, aba_ex, n_ex)
                st.session_state.mensagem_sucesso = f"🗑️ {qtd} item(s) removidos da aba {aba_ex}."
                st.rerun()