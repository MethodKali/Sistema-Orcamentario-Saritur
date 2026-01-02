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
    """
    Lógica BACKLOG.py: Identifica todos os números em uma string suja.
    Ex: 'Pedido: 123; Solic-456/789' -> ['123', '456', '789']
    """
    if not texto:
        return []
    return re.findall(r'\d+', str(texto))

def get_actual_next_row(ws, col_index):
    col_values = ws.col_values(col_index)
    for i, value in enumerate(col_values[2:], start=3):
        if not value.strip():
            return i
    return len(col_values) + 1

def buscar_em_todas_as_abas(sh, lista_numeros):
    encontrados_alta, encontrados_emergencial = [], []
    dados_alta = sh.worksheet("ALTA").get_all_values()
    dados_emerg = sh.worksheet("EMERGENCIAL").get_all_values()
    
    for num in lista_numeros:
        for row in dados_alta[2:]:
            if len(row) > 4 and re.sub(r'\D', '', row[4]) == num:
                encontrados_alta.append(num)
        for row in dados_emerg[2:]:
            if len(row) > 3 and re.sub(r'\D', '', row[3]) == num:
                encontrados_emergencial.append(num)
    return list(set(encontrados_alta)), list(set(encontrados_emergencial))

def excluir_por_numero(sh, aba_nome, lista_numeros):
    ws = sh.worksheet(aba_nome)
    col_idx = 5 if aba_nome == "ALTA" else 4
    col_values = ws.col_values(col_idx)
    linhas_para_deletar = []
    for i, valor in enumerate(col_values):
        if re.sub(r'\D', '', valor) in lista_numeros:
            linhas_para_deletar.append(i + 1)
    if linhas_para_deletar:
        for linha in sorted(linhas_para_deletar, reverse=True):
            ws.delete_rows(linha)
        return len(linhas_para_deletar)
    return 0

def scanner_duplicatas_globais(sh):
    pedidos_alta = [re.sub(r'\D', '', row[4]) for row in sh.worksheet("ALTA").get_all_values()[2:] if len(row) > 4]
    pedidos_emerg = [re.sub(r'\D', '', row[3]) for row in sh.worksheet("EMERGENCIAL").get_all_values()[2:] if len(row) > 3]
    pedidos_alta = set([p for p in pedidos_alta if p])
    pedidos_emerg = set([p for p in pedidos_emerg if p])
    return sorted(list(pedidos_alta.intersection(pedidos_emerg)))

def app():
    st.title("📝 Gestão de Pedidos e Solicitações")
    client = get_gspread_client()
    if not client: return
    sh = client.open_by_key(SPREADSHEET_ID)

    # --- SIDEBAR: SCANNER VISUAL ---
    st.sidebar.title("🔍 Scanner de Duplicatas")
    duplicas_globais = scanner_duplicatas_globais(sh)
    if duplicas_globais:
        st.sidebar.warning(f"Existem {len(duplicas_globais)} duplicatas detectadas!")
        if st.sidebar.button("Mostrar Lista"):
            for num in duplicas_globais:
                st.sidebar.code(num)
    else:
        st.sidebar.success("Nenhuma duplicata entre abas.")

    # --- FORMULÁRIO PRINCIPAL ---
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
            status = st.selectbox("Status *", ["COTAÇÃO", "PEDIDO", "APROVADA", "NÃO APROVADA"])
            solicitacao_raw = st.text_input("Nº Solicitação (Ex: 300123)")
            pedidos_raw = st.text_area("Bloco de Pedidos (Pode colar texto sujo)")

        avaliacao = st.selectbox("Avaliação", ["EXPEDIÇÃO", "FINANCEIRO", "UNIDADE", "CREDITO"]) if aba_dest == "ALTA" else ""
        btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

    if btn_cadastrar:
        # TRATAMENTO INTELIGENTE (Regex)
        s_numeros = extrair_numeros_da_string(solicitacao_raw)
        p_numeros = extrair_numeros_da_string(pedidos_raw)
        
        # Consolida todos os números encontrados
        todos_itens = p_numeros + s_numeros
        
        if not todos_itens:
            st.warning("Nenhum número de Solicitação ou Pedido foi detectado.")
            return

        # 1. VALIDAÇÃO CRUZADA E ALERTAS
        alta_check, emerg_check = buscar_em_todas_as_abas(sh, todos_itens)
        
        # LÓGICA DE ALERTA PARA COTAÇÃO
        if status == "COTAÇÃO":
            solic_existente = [n for n in s_numeros if n in alta_check or n in emerg_check]
            if solic_existente:
                st.warning(f"⚠️ Alerta: A solicitação {', '.join(solic_existente)} já existe na planilha! Cadastrando novos itens...")
                # Remove da lista de erro fatal para permitir o cadastro
                alta_check = [n for n in alta_check if n not in s_numeros]
                emerg_check = [n for n in emerg_check if n not in s_numeros]

        # LÓGICA PARA STATUS PEDIDO (Limpa a solicitação da lista de erros para deletar depois)
        if status == "PEDIDO":
            alta_check = [n for n in alta_check if n not in s_numeros]
            emerg_check = [n for n in emerg_check if n not in s_numeros]

        # SE AINDA HOUVER DUPLICATAS (ERRO REAL)
        if alta_check or emerg_check:
            if alta_check: st.error(f"❌ Números já cadastrados na ALTA: {', '.join(alta_check)}")
            if emerg_check: st.error(f"❌ Números já cadastrados na EMERGENCIAL: {', '.join(emerg_check)}")
            st.stop()

        # 2. EXCLUSÃO AUTOMÁTICA (Somente PEDIDO)
        msg_exclusao = ""
        if status == "PEDIDO" and s_numeros:
            qtd_e = excluir_por_numero(sh, "ALTA", s_numeros) + excluir_por_numero(sh, "EMERGENCIAL", s_numeros)
            if qtd_e > 0: msg_exclusao = f" (Solicitação {', '.join(s_numeros)} antiga removida)"

        # 3. CADASTRO
        ws = sh.worksheet(aba_dest)
        dt_f = data_cad.strftime("%d/%m/%Y")
        col_ref = 5 if aba_dest == "ALTA" else 4
        
        for item in todos_itens:
            prox = get_actual_next_row(ws, col_ref)
            if aba_dest == "ALTA":
                formula = f'=IF(B{prox}=""; ""; TODAY()-B{prox})'
                linha = [formula, dt_f, unidade, carro, item, valor, fornecedor, status, avaliacao]
                ws.update(f"A{prox}:I{prox}", [linha], value_input_option='USER_ENTERED')
            else:
                d_h = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                linha = [unidade, d_h, carro, item, valor, fornecedor, "", "", "", status]
                ws.update(f"A{prox}:J{prox}", [linha], value_input_option='USER_ENTERED')

        st.success(f"✅ Sucesso! {len(todos_itens)} item(s) cadastrados na aba {aba_dest}.{msg_exclusao}")
        st.balloons()

    # --- MÓDULO: EXCLUSÃO MANUAL COM TRATAMENTO INTELIGENTE ---
    st.markdown("---")
    st.subheader("🗑️ Excluir Registros Manualmente")
    with st.expander("Opções de exclusão"):
        aba_excluir = st.selectbox("Aba para exclusão", ["ALTA", "EMERGENCIAL"])
        numeros_ex_raw = st.text_area("Cole os números/textos aqui para excluir")
        
        if st.button("CONFIRMAR EXCLUSÃO"):
            lista_ex = extrair_numeros_da_string(numeros_ex_raw)
            if lista_ex:
                qtd = excluir_por_numero(sh, aba_excluir, lista_ex)
                if qtd > 0:
                    st.success(f"🗑️ {qtd} linha(s) removida(s)!")
                    st.rerun()
                else:
                    st.info("Nenhum desses números foi encontrado.")
            else:
                st.error("Nenhum número detectado no texto.")

if __name__ == "__main__":
    app()