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

def limpar_apenas_numeros(texto):
    return re.sub(r'\D', '', str(texto))

def get_actual_next_row(ws, col_index):
    col_values = ws.col_values(col_index)
    for i, value in enumerate(col_values[2:], start=3):
        if not value.strip():
            return i
    return len(col_values) + 1

def buscar_em_todas_as_abas(sh, itens_validar):
    encontrados_alta, encontrados_emergencial = [], []
    dados_alta = sh.worksheet("ALTA").get_all_values()
    dados_emerg = sh.worksheet("EMERGENCIAL").get_all_values()
    
    for item in itens_validar:
        num = str(item)
        if not num: continue
        for row in dados_alta[2:]:
            if len(row) > 4 and limpar_apenas_numeros(row[4]) == num:
                encontrados_alta.append(num)
        for row in dados_emerg[2:]:
            if len(row) > 3 and limpar_apenas_numeros(row[3]) == num:
                encontrados_emergencial.append(num)
    return list(set(encontrados_alta)), list(set(encontrados_emergencial))

def excluir_por_numero(sh, aba_nome, numeros_excluir):
    ws = sh.worksheet(aba_nome)
    col_idx = 5 if aba_nome == "ALTA" else 4
    col_values = ws.col_values(col_idx)
    linhas_para_deletar = []
    for i, valor in enumerate(col_values):
        if limpar_apenas_numeros(valor) in numeros_excluir:
            linhas_para_deletar.append(i + 1)
    if linhas_para_deletar:
        for linha in sorted(linhas_para_deletar, reverse=True):
            ws.delete_rows(linha)
        return len(linhas_para_deletar)
    return 0

def scanner_duplicatas_globais(sh):
    pedidos_alta = [limpar_apenas_numeros(row[4]) for row in sh.worksheet("ALTA").get_all_values()[2:] if len(row) > 4]
    pedidos_emerg = [limpar_apenas_numeros(row[3]) for row in sh.worksheet("EMERGENCIAL").get_all_values()[2:] if len(row) > 3]
    return sorted(list(set(pedidos_alta).intersection(set(pedidos_emerg))))

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
            solicitacao_raw = st.text_input("Nº Solicitação")
            pedidos_raw = st.text_area("Nº Pedidos (Separe por vírgula)")

        avaliacao = st.selectbox("Avaliação", ["EXPEDIÇÃO", "FINANCEIRO", "UNIDADE", "CREDITO"]) if aba_dest == "ALTA" else ""
        responsavel, num_ad = ("", "")
        if aba_dest == "EMERGENCIAL":
            responsavel = st.text_input("Responsável Coleta/Entrega")
            num_ad = st.text_input("Nº AD")

        btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

    if btn_cadastrar:
        s_limpa = limpar_apenas_numeros(solicitacao_raw)
        p_limpos = [limpar_apenas_numeros(x) for x in pedidos_raw.split(",") if x.strip()]
        
        # Decide o que cadastrar: Se houver pedidos, eles são a prioridade. Caso contrário, a solicitação.
        itens_para_cadastrar = p_limpos if p_limpos else ([s_limpa] if s_limpa else [])

        if not itens_para_cadastrar:
            st.warning("Preencha ao menos um número de Solicitação ou Pedido.")
        else:
            # 1. VERIFICAÇÃO DE DUPLICATAS (Sempre faz para evitar cadastrar o que já existe)
            na_alta, na_emerg = buscar_em_todas_as_abas(sh, itens_para_cadastrar)
            
            # Se for PEDIDO, permitimos ignorar a duplicata da Solicitação original (pois vamos excluí-la)
            if status == "PEDIDO" and s_limpa:
                if s_limpa in na_alta: na_alta.remove(s_limpa)
                if s_limpa in na_emerg: na_emerg.remove(s_limpa)

            if na_alta or na_emerg:
                if na_alta: st.error(f"⚠️ Já existe na aba ALTA: {', '.join(na_alta)}")
                if na_emerg: st.error(f"🚨 Já existe na aba EMERGENCIAL: {', '.join(na_emerg)}")
                st.stop()

            # 2. LÓGICA DE EXCLUSÃO (Somente se status for PEDIDO e houver solicitação para limpar)
            msg_exclusao = ""
            if status == "PEDIDO" and s_limpa:
                exc_alta = excluir_por_numero(sh, "ALTA", [s_limpa])
                exc_emerg = excluir_por_numero(sh, "EMERGENCIAL", [s_limpa])
                if exc_alta or exc_emerg:
                    msg_exclusao = f" (Solicitação {s_limpa} antiga removida)"

            # 3. EFETUAR CADASTRO
            ws = sh.worksheet(aba_dest)
            dt_f = data_cad.strftime("%d/%m/%Y")
            col_ref = 5 if aba_dest == "ALTA" else 4
            
            for item in itens_para_cadastrar:
                prox = get_actual_next_row(ws, col_ref)
                if aba_dest == "ALTA":
                    formula = f'=IF(B{prox}=""; ""; TODAY()-B{prox})'
                    linha = [formula, dt_f, unidade, carro, item, valor, fornecedor, status, avaliacao]
                    ws.update(f"A{prox}:I{prox}", [linha], value_input_option='USER_ENTERED')
                else:
                    d_h = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    linha = [unidade, d_h, carro, item, valor, fornecedor, responsavel, num_ad, "", status]
                    ws.update(f"A{prox}:J{prox}", [linha], value_input_option='USER_ENTERED')

            st.success(f"✅ Sucesso! {len(itens_para_cadastrar)} registro(s) inserido(s) na aba {aba_dest}.{msg_exclusao}")
            st.balloons()

    # --- MÓDULO: EXCLUSÃO MANUAL ---
    st.markdown("---")
    st.subheader("🗑️ Excluir Registros Manualmente")
    with st.expander("Clique aqui para abrir as opções de exclusão"):
        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            aba_excluir = st.selectbox("Aba para exclusão", ["ALTA", "EMERGENCIAL"])
        with col_ex2:
            numeros_ex_raw = st.text_area("Nº para excluir (separe por vírgula)")
        
        if st.button("CONFIRMAR EXCLUSÃO DEFINITIVA"):
            if numeros_ex_raw:
                lista_ex = [limpar_apenas_numeros(x) for x in numeros_ex_raw.split(",") if x.strip()]
                qtd = excluir_por_numero(sh, aba_excluir, lista_ex)
                if qtd > 0:
                    st.success(f"🗑️ {qtd} linha(s) removida(s) da aba {aba_excluir}!")
                    st.rerun()
                else:
                    st.info("Nenhum número correspondente encontrado.")
            else:
                st.error("Digite os números.")

if __name__ == "__main__":
    app()