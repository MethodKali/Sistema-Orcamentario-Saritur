import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import re

# --- CONFIGURAÇÕES ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_ID = "1X9trwwqVCwPXY2_O667WJcOR4CHNYbBjJDVsrYNZSgc"

# Mapeamento Centralizado para as novas abas
# col_idx: para exclusão (1-based) | data_idx: para leitura de dados (0-based)
MAPA_ABAS = {
    "PROGRAMAÇÃO DIÁRIA": {"col_idx": 6, "data_idx": 5}, # Coluna F
    "EMERGENCIAL": {"col_idx": 4, "data_idx": 3}         # Coluna D
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

def get_actual_next_row(ws, coluna_referencia=4):
    """Encontra a próxima linha vazia baseada na coluna do Pedido/Solicitação."""
    valores_coluna = ws.col_values(coluna_referencia)
    return len(valores_coluna) + 1

def scanner_duplicatas_globais(sh):
    todos_pedidos = {} 
    for nome_aba, config in MAPA_ABAS.items():
        try:
            ws = sh.worksheet(nome_aba)
            # Lê a partir da linha 3 (dados reais após cabeçalho na linha 2)
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
    return [n for n, abas in todos_pedidos.items() if len(abas) > 1]

def buscar_em_todas_as_abas_detalhado(sh, lista_numeros):
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
    if aba_nome not in MAPA_ABAS: return 0
    try:
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
    except:
        pass
    return 0

# --- INÍCIO DO APP ---
client = get_gspread_client()
if not client: st.stop()
sh = client.open_by_key(SPREADSHEET_ID)

# --- SIDEBAR: SCANNER ---
st.sidebar.title("🔍 Scanner Operacional")
duplicas_globais = scanner_duplicatas_globais(sh)
if duplicas_globais:
    st.sidebar.warning(f"⚠️ {len(duplicas_globais)} duplicatas encontradas!")
    if st.sidebar.button("Ver Pedidos Duplicados"):
        for num in duplicas_globais: st.sidebar.code(num)
else:
    st.sidebar.success("✅ Bases sem duplicatas.")

st.title("📝 Cadastro de Pedidos – Saritur")

# Feedback
if "mensagem_sucesso" in st.session_state:
    st.success(st.session_state.mensagem_sucesso)
    del st.session_state.mensagem_sucesso
if "alertas_erro" in st.session_state:
    for msg in st.session_state.alertas_erro: st.error(msg)
    del st.session_state.alertas_erro

aba_dest = st.selectbox("Aba de Destino", list(MAPA_ABAS.keys()))

with st.form("form_cadastro", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        data_cad = st.date_input("Data do Pedido *", datetime.now())
        unidade = st.selectbox("Unidade *", ["INDUSTRIA", "JARDIM MONTANHÊS", "SÃO MARCOS", "NOVA LIMA", "ITAÚNA", "LAGOA SANTA", "DURVAL DE BARROS", "MONTES CLAROS", "VARGINHA", "NEVES", "LAVRAS", "IPATINGA", "VESPASIANO", "GARANTIA", "VENDA DE VEÍCULOS", "ADMINISTRATIVO", "PREDIO ADM", "EXPEDIÇÃO", "CEL. FABRICIANO", "OLIVEIRA", "MORRO ALTO", "TRANSNORTE", "TIMOTEO", "ADMINISTRAÇÃO"])
        carro = st.text_input("Carro | Utilização")
        fornecedor = st.text_input("Fornecedor")
    with col2:
        valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
        # Status só para Programação Diária
        status_selecionado = "PEDIDO"
        if aba_dest == "PROGRAMAÇÃO DIÁRIA":
            status_selecionado = st.selectbox("Status Orçamentário *", ["COTAÇÃO", "PEDIDO", "APROVADA", "NÃO APROVADA"])
        
        solicitacao_raw = st.text_input("Nº Solicitação (Exclui antes de cadastrar)")
        pedidos_raw = st.text_area("Números de Pedidos (Cadastro em Lote)")
    
    btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

if btn_cadastrar:
    s_nums = extrair_numeros_da_string(solicitacao_raw)
    p_nums = extrair_numeros_da_string(pedidos_raw)
    st.session_state.alertas_erro = []
    
    # 1. Limpeza (Exclui de ambas as abas)
    msg_exc = ""
    if s_nums:
        qtd_rem = sum(excluir_por_numero(sh, aba, s_nums) for aba in MAPA_ABAS.keys())
        if qtd_rem > 0: msg_exc = f" ({qtd_rem} duplicata(s) removida(s))"

    itens_para_validar = list(set(s_nums + p_nums))
    if not itens_para_validar: st.stop()

    # 2. Verificação de Duplicatas
    mapa_geral = buscar_em_todas_as_abas_detalhado(sh, itens_para_validar)
    itens_finais = [i for i in itens_para_validar if i not in mapa_geral]
    
    for item in itens_para_validar:
        if item in mapa_geral: 
            st.session_state.alertas_erro.append(f"❌ O pedido {item} já existe na aba {mapa_geral[item]}.")

    # 3. Inserção
    if itens_finais:
        ws = sh.worksheet(aba_dest)
        dt_str = data_cad.strftime("%d/%m/%Y")
        prox_linha = get_actual_next_row(ws, coluna_referencia=MAPA_ABAS[aba_dest]["col_idx"])
        novas_linhas = []

        for i, item in enumerate(itens_finais):
            linha_idx = prox_linha + i
            if aba_dest == "PROGRAMAÇÃO DIÁRIA":
                # Estrutura: [A]Vazio, [B]Dias(Fórmula), [C]Data, [D]Unidade, [E]Carro, [F]Pedido, [G]Valor, [H]Fornecedor, [I]Status
                formula_dias = f'=IF(C{linha_idx}=""; ""; TODAY()-C{linha_idx})'
                novas_linhas.append(["", formula_dias, dt_str, unidade, carro, item, valor, fornecedor, status_selecionado])
            else:
                # Estrutura EMERGENCIAL: [A]Unidade, [B]Timestamp, [C]Carro, [D]Pedido, [E]Valor, [F]Fornecedor...
                novas_linhas.append([unidade, datetime.now().strftime("%d/%m/%Y %H:%M"), carro, item, valor, fornecedor])

        col_fim = "I" if aba_dest == "PROGRAMAÇÃO DIÁRIA" else "F"
        range_target = f"A{prox_linha}:{col_fim}{prox_linha + len(novas_linhas) - 1}"
        ws.update(range_target, novas_linhas, value_input_option='USER_ENTERED')
        
        st.session_state.mensagem_sucesso = f"✅ {len(novas_linhas)} itens cadastrados em {aba_dest}.{msg_exc}"
    
    st.rerun()

# --- EXCLUSÃO MANUAL ---
st.markdown("---")
st.subheader("🗑️ Limpeza de Base")
with st.expander("Remover Pedidos Manualmente"):
    with st.form("form_exclusao", clear_on_submit=True):
        aba_ex = st.selectbox("De qual aba deseja remover?", list(MAPA_ABAS.keys()))
        txt_ex = st.text_area("Cole os números:")
        if st.form_submit_button("EXCLUIR PERMANENTEMENTE"):
            n_ex = extrair_numeros_da_string(txt_ex)
            if n_ex:
                qtd = excluir_por_numero(sh, aba_ex, n_ex)
                st.session_state.mensagem_sucesso = f"🗑️ {qtd} item(s) removidos de {aba_ex}."
                st.rerun()