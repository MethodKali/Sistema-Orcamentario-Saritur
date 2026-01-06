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

def get_actual_next_row(ws):
    return len(ws.col_values(3)) + 1

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

# --- NOVA LÓGICA: LIMPEZA DE DUPLICATAS AUTOMÁTICA ---
def limpar_todas_duplicatas(sh):
    total_removido = 0
    hoje = datetime.now().date()
    detalhes_limpeza = [] # Para armazenar o resumo por aba
    
    for aba_nome in ["ALTA", "EMERGENCIAL"]:
        ws = sh.worksheet(aba_nome)
        dados = ws.get_all_values()
        
        idx_data = 2 if aba_nome == "ALTA" else 1
        idx_item = 5 if aba_nome == "ALTA" else 3
        
        vistos = set()
        linhas_para_excluir = []
        removidos_nesta_aba = 0
        
        for i, linha in enumerate(dados):
            if i < 2: continue 
            if len(linha) > idx_item:
                # 1. Filtro Temporal (Apenas hoje ou futuro)
                data_str = linha[idx_data]
                try:
                    data_dt = datetime.strptime(data_str, "%d/%m/%Y").date()
                    if data_dt < hoje: continue 
                except: continue

                # 2. Filtro de Intervalo Numérico
                raw_num = limpar_apenas_numeros(linha[idx_item])
                if not raw_num: continue
                
                num_int = int(raw_num)
                is_solicitacao = 300000 <= num_int <= 400000
                is_pedido = 1100000 <= num_int <= 1300000
                
                if is_solicitacao or is_pedido:
                    # 3. Identificação de Duplicata
                    if num_int in vistos:
                        linhas_para_excluir.append(i + 1)
                    else:
                        vistos.add(num_int)
        
        if linhas_para_excluir:
            for idx in sorted(linhas_para_excluir, reverse=True):
                ws.delete_rows(idx)
            removidos_nesta_aba = len(linhas_para_excluir)
            total_removido += removidos_nesta_aba
        
        detalhes_limpeza.append(f"{aba_nome}: {removidos_nesta_aba}")
            
    return total_removido, ", ".join(detalhes_limpeza)
# --- INÍCIO DO APP ---
client = get_gspread_client()
if not client: st.stop()
sh = client.open_by_key(SPREADSHEET_ID)

# SIDEBAR
st.sidebar.title("🔍 Scanner de Duplicatas")
duplicas_globais = scanner_duplicatas_globais(sh)
if duplicas_globais:
    st.sidebar.warning(f"Existem {len(duplicas_globais)} duplicatas entre abas!")
    if st.sidebar.button("Mostrar Lista"):
        for num in duplicas_globais: st.sidebar.code(num)
else:
    st.sidebar.success("Sem duplicatas entre abas.")

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
    
    msg_exc = ""
    if s_nums:
        qtd_rem = excluir_por_numero(sh, "ALTA", s_nums) + excluir_por_numero(sh, "EMERGENCIAL", s_nums)
        if qtd_rem > 0: msg_exc = f" ({qtd_rem} antigo(s) removido(s))"

    if aba_dest == "ALTA" and status_selecionado == "PEDIDO":
        itens_para_validar = p_nums
    else:
        itens_para_validar = s_nums + p_nums

    if not itens_para_validar:
        if s_nums and status_selecionado == "PEDIDO":
            st.session_state.mensagem_sucesso = f"✅ Limpeza concluída!{msg_exc}"
            st.rerun()
        st.stop()

    mapa_geral = buscar_em_todas_as_abas_detalhado(sh, itens_para_validar)
    itens_finais = [i for i in itens_para_validar if i not in mapa_geral]
    for item in itens_para_validar:
        if item in mapa_geral: st.session_state.alertas_erro.append(f"❌ Item {item} já existe na aba {mapa_geral[item]}.")

    if itens_finais:
        ws = sh.worksheet(aba_dest)
        dt_str = data_cad.strftime("%d/%m/%Y")
        prox_linha = get_actual_next_row(ws)
        novas_linhas = []

        for i, item in enumerate(itens_finais):
            linha_atual = prox_linha + i
            if aba_dest == "ALTA":
                status_item = status_selecionado if item in s_nums else "PEDIDO"
                formula_dias = f'=IF(C{linha_atual}=""; ""; TODAY()-C{linha_atual})'
                # [A:Vazio, B:Dias, C:Data, D:Unidade, E:Carro, F:Item, G:Valor, H:Fornecedor, I:Status]
                novas_linhas.append(["", formula_dias, dt_str, unidade, carro, item, valor, fornecedor, status_item])
            else:
                novas_linhas.append([unidade, datetime.now().strftime("%d/%m/%Y %H:%M:%S"), carro, item, valor, fornecedor, "", "", "", ""])

        ws.append_rows(novas_linhas, value_input_option='USER_ENTERED')
        st.session_state.mensagem_sucesso = f"✅ {len(novas_linhas)} itens adicionados.{msg_exc}"
    
    st.rerun()

# --- FERRAMENTAS ---
st.markdown("---")
st.subheader("🛠️ Ferramentas de Manutenção")
col_tools1, col_tools2 = st.columns(2)

with col_tools1:
    with st.expander("🗑️ Exclusão Manual"):
        with st.form("form_exclusao", clear_on_submit=True):
            aba_ex = st.selectbox("Aba", ["ALTA", "EMERGENCIAL"], key="man_aba")
            txt_ex = st.text_area("Números para excluir")
            if st.form_submit_button("EXCLUIR"):
                n_ex = extrair_numeros_da_string(txt_ex)
                if n_ex:
                    qtd = excluir_por_numero(sh, aba_ex, n_ex)
                    st.session_state.mensagem_sucesso = f"🗑️ {qtd} item(s) removidos."
                    st.rerun()

# --- NO BLOCO DO BOTÃO (DENTRO DA COL_TOOLS2) ---
with col_tools2:
    with st.expander("Sweep 🧹 Limpeza de Duplicatas"):
        st.write("Foco: Hoje/Futuro | Pedidos (1.1M-1.3M) | Solicit. (300k-400k)")
        if st.button("EXECUTAR LIMPEZA GERAL"):
            with st.spinner("Analisando e limpando duplicatas atuais..."):
                qtd, resumo = limpar_todas_duplicatas(sh)
                if qtd > 0:
                    termo = "duplicata removida" if qtd == 1 else "duplicatas removidas"
                    st.session_state.mensagem_sucesso = f"✅ Sucesso! {qtd} {termo} ({resumo})."
                else:
                    st.info("Nenhuma duplicata atual encontrada para os critérios definidos.")
                st.rerun()