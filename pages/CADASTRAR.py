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

# --- FUNÇÕES DE BUSCA E SCANNER ---

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
                break
        for row in dados_emerg[2:]:
            if len(row) > 3 and limpar_apenas_numeros(row[3]) == num:
                encontrados_emergencial.append(num)
                break
    return list(set(encontrados_alta)), list(set(encontrados_emergencial))

def excluir_por_numero(sh, aba_nome, numeros_excluir):
    ws = sh.worksheet(aba_nome)
    col_idx = 5 if aba_nome == "ALTA" else 4 # Coluna E ou D
    
    # Pegamos os valores da coluna específica
    col_values = ws.col_values(col_idx)
    linhas_para_deletar = []
    
    # Identifica as linhas (de baixo para cima para não perder o índice ao deletar)
    for i, valor in enumerate(col_values):
        valor_limpo = limpar_apenas_numeros(valor)
        if valor_limpo in numeros_excluir:
            linhas_para_deletar.append(i + 1)
    
    if linhas_para_deletar:
        for linha in sorted(linhas_para_deletar, reverse=True):
            ws.delete_rows(linha)
        return len(linhas_para_deletar)
    return 0

def scanner_duplicatas_globais(sh):
    pedidos_alta = [limpar_apenas_numeros(row[4]) for row in sh.worksheet("ALTA").get_all_values()[2:] if len(row) > 4]
    pedidos_emerg = [limpar_apenas_numeros(row[3]) for row in sh.worksheet("EMERGENCIAL").get_all_values()[2:] if len(row) > 3]
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
        st.sidebar.warning("Existem duplicatas de pedidos/solicitações na aba ALTA e EMERGENCIAL!")
        if st.sidebar.button("Mostrar Lista"):
            for num in duplicas_globais:
                st.sidebar.code(num) # Mostra um abaixo do outro com estilo scannable
    else:
        st.sidebar.success("A planilha não possui dados duplicados")

    # --- ABA DE CADASTRO ---
    st.subheader("Cadastrar Novo Registro")
    aba_dest = st.selectbox("Selecione a Aba de Destino", ["ALTA", "EMERGENCIAL"])

    with st.form("form_cadastro"):
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
        itens = p_limpos if p_limpos else ([s_limpa] if s_limpa else [])

        if not itens:
            st.warning("Preencha o número do Pedido ou Solicitação.")
        else:
            # Lógica Status PEDIDO: Excluir solicitação anterior se existir
            if status == "PEDIDO" and s_limpa:
                # Busca em ambas as abas e deleta antes de cadastrar o novo
                excluir_por_numero(sh, "ALTA", [s_limpa])
                excluir_por_numero(sh, "EMERGENCIAL", [s_limpa])

            # Validação de Duplicatas (apenas impede se não for o fluxo de conversão COTAÇÃO -> PEDIDO)
            na_alta, na_emerg = buscar_em_todas_as_abas(sh, itens)
            if na_alta: st.error(f"⚠️ Já existe na aba **ALTA**: {', '.join(na_alta)}")
            if na_emerg: st.error(f"🚨 Já existe na aba **EMERGENCIAL**: {', '.join(na_emerg)}")
            
            if not na_alta and not na_emerg:
                ws = sh.worksheet(aba_dest)
                dt_f = data_cad.strftime("%d/%m/%Y")
                col_ref = 5 if aba_dest == "ALTA" else 4
                for item in itens:
                    prox = get_actual_next_row(ws, col_ref)
                    if aba_dest == "ALTA":
                        formula = f'=IF(B{prox}=""; ""; TODAY()-B{prox})'
                        linha = [formula, dt_f, unidade, carro, item, valor, fornecedor, status, avaliacao]
                        ws.update(f"A{prox}:I{prox}", [linha], value_input_option='USER_ENTERED')
                    else:
                        d_h = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        linha = [unidade, d_h, carro, item, valor, fornecedor, responsavel, num_ad, "", status]
                        ws.update(f"A{prox}:J{prox}", [linha], value_input_option='USER_ENTERED')
                st.success("Cadastro realizado!")
                st.rerun()

    st.markdown("---")

    # --- NOVO MÓDULO: EXCLUSÃO DE REGISTROS ---
    st.subheader("🗑️ Excluir Registros")
    col_ex1, col_ex2 = st.columns(2)
    with col_ex1:
        aba_excluir = st.selectbox("De qual aba deseja excluir?", ["ALTA", "EMERGENCIAL"])
    with col_ex2:
        numeros_ex_raw = st.text_area("Nº Solicitação/Pedido (Unico ou separados por vírgula)")
    
    if st.button("EXCLUIR LINHAS DEFINITIVAMENTE"):
        if numeros_ex_raw:
            lista_ex = [limpar_apenas_numeros(x) for x in numeros_ex_raw.split(",") if x.strip()]
            qtd = excluir_por_numero(sh, aba_excluir, lista_ex)
            if qtd > 0:
                st.success(f"Foram excluídas {qtd} linha(s) da aba {aba_excluir}.")
                st.rerun()
            else:
                st.warning("Nenhum registro encontrado para exclusão.")
        else:
            st.error("Informe ao menos um número para excluir.")

if __name__ == "__main__":
    app()