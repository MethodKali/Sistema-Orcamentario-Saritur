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

def get_actual_next_row(ws, col_index):
    col_values = ws.col_values(col_index)
    for i, value in enumerate(col_values[2:], start=3):
        if not value.strip():
            return i
    return len(col_values) + 1

def buscar_em_todas_as_abas_detalhado(sh, lista_numeros):
    """Retorna um dicionário mapeando o número à aba onde foi encontrado."""
    mapa_encontrados = {}
    dados_alta = sh.worksheet("ALTA").get_all_values()
    dados_emerg = sh.worksheet("EMERGENCIAL").get_all_values()
    
    for num in lista_numeros:
        # Procurar na ALTA
        for row in dados_alta[2:]:
            if len(row) > 4 and re.sub(r'\D', '', row[4]) == num:
                mapa_encontrados[num] = "ALTA"
                break
        # Procurar na EMERGENCIAL (se ainda não achou)
        if num not in mapa_encontrados:
            for row in dados_emerg[2:]:
                if len(row) > 3 and re.sub(r'\D', '', row[3]) == num:
                    mapa_encontrados[num] = "EMERGENCIAL"
                    break
    return mapa_encontrados

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
    return sorted(list(set(pedidos_alta).intersection(set(pedidos_emerg))))

def app():
    st.title("📝 Gestão de Pedidos e Solicitações")
    client = get_gspread_client()
    if not client: return
    sh = client.open_by_key(SPREADSHEET_ID)

    # --- SIDEBAR: SCANNER ---
    st.sidebar.title("🔍 Scanner de Duplicatas")
    duplicas_globais = scanner_duplicatas_globais(sh)
    if duplicas_globais:
        st.sidebar.warning(f"Existem {len(duplicas_globais)} duplicatas detectadas!")
        if st.sidebar.button("Mostrar Lista"):
            for num in duplicas_globais: st.sidebar.code(num)
    else:
        st.sidebar.success("Nenhuma duplicata entre abas.")

    # --- FORMULÁRIO ---
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
            pedidos_raw = st.text_area("Bloco de Pedidos/Texto Sujo")
        
        avaliacao = st.selectbox("Avaliação", ["EXPEDIÇÃO", "FINANCEIRO", "UNIDADE", "CREDITO"]) if aba_dest == "ALTA" else ""
        btn_cadastrar = st.form_submit_button("CONCLUIR CADASTRO")

    if btn_cadastrar:
        s_nums = extrair_numeros_da_string(solicitacao_raw)
        p_nums = extrair_numeros_da_string(pedidos_raw)
        todos_itens = p_nums + s_nums
        
        if not todos_itens:
            st.warning("Nenhum número detectado.")
            return

        # 1. VALIDAÇÃO CRUZADA DETALHADA
        mapa_geral = buscar_em_todas_as_abas_detalhado(sh, todos_itens)

        # Tratar alertas de COTAÇÃO
        if status == "COTAÇÃO":
            for s in s_nums:
                if s in mapa_geral:
                    st.warning(f"⚠️ A solicitação {s} já está em **COTAÇÃO** na aba **{mapa_geral[s]}**")
                    # Removemos do mapa de erros fatais para permitir cadastro de outros itens
                    mapa_geral.pop(s)
                else:
                    st.info(f"ℹ️ A solicitação {s} foi incluída na aba **{aba_dest}** como **COTAÇÃO**")

        # Se for PEDIDO, removemos a solicitação do mapa de erro pois ela será excluída
        if status == "PEDIDO":
            for s in s_nums:
                if s in mapa_geral: mapa_geral.pop(s)

        # SE AINDA HOUVER DUPLICATAS (ERRO REAL EM PEDIDOS)
        if mapa_geral:
            for num, aba in mapa_geral.items():
                st.error(f"❌ O número {num} já existe como pedido na aba {aba}!")
            st.stop()

        # 2. EXCLUSÃO AUTOMÁTICA (Somente PEDIDO)
        msg_exclusao = ""
        if status == "PEDIDO" and s_nums:
            qtd_e = excluir_por_numero(sh, "ALTA", s_nums) + excluir_por_numero(sh, "EMERGENCIAL", s_nums)
            if qtd_e > 0: msg_exclusao = f" (Solicitação {', '.join(s_nums)} removida)"

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

        st.success(f"✅ Sucesso! {len(todos_itens)} item(s) processados.{msg_exclusao}")
        st.balloons()

    # --- MÓDULO EXCLUSÃO ---
    st.markdown("---")
    st.subheader("🗑️ Excluir Registros Manualmente")
    with st.expander("Abrir ferramentas de exclusão"):
        aba_ex = st.selectbox("Aba", ["ALTA", "EMERGENCIAL"])
        txt_ex = st.text_area("Cole os textos/números aqui")
        if st.button("CONFIRMAR EXCLUSÃO"):
            nums_ex = extrair_numeros_da_string(txt_ex)
            if nums_ex:
                q = excluir_por_numero(sh, aba_ex, nums_ex)
                st.success(f"🗑️ {q} linha(s) removida(s)!")
                st.rerun()

if __name__ == "__main__":
    app()