import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import re

# --- CONFIGURAÇÕES ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_ID = "1X9trwwqVCwPXY2_O667WJcOR4CHNYbBjJDVsrYNZSgc"

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
    """
    Encontra a próxima linha disponível baseada em uma coluna específica (Coluna C = 3).
    Isso ignora filtros e outras colunas que possam ter fórmulas distantes.
    """
    valores_coluna = ws.col_values(coluna_referencia)
    return len(valores_coluna) + 1

def scanner_duplicatas_globais(sh):
    dados_alta = sh.worksheet("ALTA").get_all_values()[2:]
    dados_emerg = sh.worksheet("EMERGENCIAL").get_all_values()[2:]
    pedidos_alta = [limpar_apenas_numeros(r[5]) for r in dados_alta if len(r) > 5 and limpar_apenas_numeros(r[5])]
    pedidos_emerg = [limpar_apenas_numeros(r[3]) for r in dados_emerg if len(r) > 3 and limpar_apenas_numeros(r[3])]
    return sorted(list(set(pedidos_alta).intersection(set(pedidos_emerg))))

def buscar_em_todas_as_abas_detalhado(sh, lista_numeros):
    mapa_encontrados = {}
    dados_alta = sh.worksheet("ALTA").get_all_values()
    dados_emerg = sh.worksheet("EMERGENCIAL").get_all_values()
    for num in lista_numeros:
        for row in dados_alta[2:]:
            if len(row) > 5 and limpar_apenas_numeros(row[5]) == num:
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
    col_idx = 6 if aba_nome == "ALTA" else 4
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

# SIDEBAR (Scanner)
duplicas_globais = scanner_duplicatas_globais(sh)
if duplicas_globais:
    st.sidebar.warning(f"Existem {len(duplicas_globais)} duplicatas!")
    if st.sidebar.button("Mostrar Lista"):
        for num in duplicas_globais: st.sidebar.code(num)

st.title("📝 Gestão de Pedidos e Solicitações")

if "mensagem_sucesso" in st.session_state:
    st.success(st.session_state.mensagem_sucesso)
    del st.session_state.mensagem_sucesso
if "alertas_erro" in st.session_state:
    for msg in st.session_state.alertas_erro: st.error(msg)
    del st.session_state.alertas_erro

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
        solicitacao_raw = st.text_input("Nº Solicitação (Para busca/exclusão)")
        pedidos_raw = st.text_area("Bloco de Pedidos (Para cadastro)")
    
    btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

if btn_cadastrar:
    s_nums = extrair_numeros_da_string(solicitacao_raw)
    p_nums = extrair_numeros_da_string(pedidos_raw)
    st.session_state.alertas_erro = []
    
    # 1. EXCLUSÃO PRÉVIA
    msg_exc = ""
    if s_nums:
        qtd_rem = excluir_por_numero(sh, "ALTA", s_nums) + excluir_por_numero(sh, "EMERGENCIAL", s_nums)
        if qtd_rem > 0: msg_exc = f" ({qtd_rem} antigo(s) removido(s))"

    # 2. DEFINIÇÃO DE ITENS
    if aba_dest == "ALTA" and status_selecionado == "PEDIDO":
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

    # 4. INCLUSÃO REFORÇADA (ANTI-ESCADA / ANTI-FILTRO)
    if itens_finais:
        ws = sh.worksheet(aba_dest)
        dt_str = data_cad.strftime("%d/%m/%Y")
        
        # Encontra a linha real baseada na Coluna C (Data)
        prox_linha = get_actual_next_row(ws, coluna_referencia=3)
        novas_linhas = []

        for i, item in enumerate(itens_finais):
            linha_atual = prox_linha + i
            if aba_dest == "ALTA":
                status_item = status_selecionado if item in s_nums else "PEDIDO"
                formula_dias = f'=IF(C{linha_atual}=""; ""; TODAY()-C{linha_atual})'
                # IMPORTANTE: A lista começa com "" para a coluna A (que é vazia na sua imagem)
                # Coluna A: vazio, B: formula, C: data, D: unidade, E: carro, F: item, G: valor, H: fornecedor, I: status
                novas_linhas.append(["", formula_dias, dt_str, unidade, carro, item, valor, fornecedor, status_item])
            else:
                # EMERGENCIAL (Layout simplificado conforme sua descrição)
                # Coluna A: unidade, B: timestamp, C: carro, D: item, E: valor, F: fornecedor
                novas_linhas.append([unidade, datetime.now().strftime("%d/%m/%Y %H:%M:%S"), carro, item, valor, fornecedor])

        # A MÁGICA: Em vez de append_rows, usamos update para garantir o Range correto
        # Para ALTA (Coluna A até I), Para EMERGENCIAL (Coluna A até F)
        col_fim = "I" if aba_dest == "ALTA" else "F"
        range_target = f"A{prox_linha}:{col_fim}{prox_linha + len(novas_linhas) - 1}"
        
        ws.update(range_target, novas_linhas, value_input_option='USER_ENTERED')
        
        st.session_state.mensagem_sucesso = f"✅ {len(novas_linhas)} itens adicionados com segurança.{msg_exc}"
    
    st.rerun()