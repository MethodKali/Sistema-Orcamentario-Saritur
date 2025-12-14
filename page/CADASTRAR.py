
#pip install st-gsheets-connection  --> instala o pacote de conexão com o planilhas 

#pip install streamlit --> instala o pacote python streamlit

#https://github.com/streamlit/gsheets-connection --> pacote python de conexão com o planilhas. Leia a documentação README.md

#https://console.cloud.google.com/apis/dashboard?project=playlists-475200 --> faça a conexão com as API do google drive e googlesheets

# CRIAÇÃO DE UM NOVO PROJETO
# - clique no projeto aberto 
# - clique em Novo Projeto
# - Dê um nome para o seu projeto
# - Clique em criar 
# - Clique no projeto aberto 
# - Clique no projeto criado

# API USADAS
# - Pesquise por Google Drive API e ative o produto
# - Faça o mesmo para Google Sheets API

# CRIAÇÃO DA CONTA SERVIÇO
# - Vá em Credenciais 
# - Clique em criar credencial
# - Selecione Conta de serviço
# - Dê um nome para sua Conta de Serviço
# - Clique em Criar e Continuar
# - Dẽ um papel para a Conta
# - Selecione Basico --> Editor
# - Clique em Concluido

# CRIAÇÃO DA CHAVE
# - Selecione a Conta de Serviço Criada  
# - Clique em Chaves 
# - Clique em Adicionar Chave
# - Selecione Criar nova Chave 
# - Clique em Criar 
# - Mova o arrquivo baixado para dentro da pasta .streamlit


# VALIDAÇÃO DAS INFORMAÇÕES DA SECRET DO STREAMLIT
# - Copie e cole no secret.toml a estrutura do repositorio do pacote de conexão com o planilhas
# - Abra o arquivo JSON baixado e complete as informações na estrutura colada do repositorio 
# - Em "spreadsheet" cole todo o link da planilha antes antes do "\edit" 
# - O email do "client_email" será o usuario tecnico que fará as edições 
# - O campo "worksheet" não precisa ser preeenchido 
# - Após preenchido todos os campos salve o arquivo secrets.toml e exclua o json criado



#streamlit run projeto.py --> executa a visualização web do código

# acesso-python@acesso-python-480514.iam.gserviceaccount.com --> Email do usuario tecnico que irá fazer as edições automaticas

# IMPORTE AS BIBLIOTECAS QUE SERÃO USADAS NESTE PROJETO
import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# TÍTULO
st.title("Pedidos/Solicitações")
st.markdown("Sistema de Cadastro de Pedidos/Solicitações")

# CONEXÃO
conexao = st.connection("gsheets", type=GSheetsConnection)

# -------------------- LEITURA DA PLANILHA --------------------
dados_raw = conexao.read(
    worksheet="ALTA",
    usecols=list(range(16)),
    ttl=5
)

# Remover linhas vazias
dados_raw = dados_raw.dropna(how="all")

if dados_raw.empty:
    st.error("A planilha está vazia ou não pôde ser carregada.")
    st.stop()

# -------------------- AJUSTAR CABEÇALHO NA PRIMEIRA LINHA --------------------

# A segunda linha lida (índice 1) é onde os dados começam.
novo_cabecalho = dados_raw.iloc[0].astype(str).str.strip()
dados_existentes = dados_raw.iloc[1:].reset_index(drop=True)

# ... (restante do seu código)

dados_existentes.columns = novo_cabecalho

# Padronizar colunas
dados_existentes.columns = (
    dados_existentes.columns
    .astype(str)
    .str.strip()
    .str.upper()
)

st.write("Colunas encontradas:", dados_existentes.columns.tolist())

# ... (código anterior, onde você define dados_existentes e dados_raw)

# -------------------- TRATAR COLUNA VALOR --------------------
if "VALOR" not in dados_existentes.columns:
    st.error("A coluna 'VALOR' não existe no cabeçalho da planilha.")
    st.stop()

# 1. TRATAMENTO E CONVERSÃO NUMÉRICA (Cria a coluna numérica temporária 'VALOR_NUM')
dados_existentes["VALOR_NUM"] = (
    dados_existentes["VALOR"]
    .astype(str)
    .str.replace("R$", "", regex=False)
    .str.replace(".", "", regex=False)
    .str.replace(",", ".", regex=False)
    .str.strip()
)
# Converte para número, trata NaN como 0.0 para cálculos
dados_existentes["VALOR_NUM"] = pd.to_numeric(dados_existentes["VALOR_NUM"], errors="coerce").fillna(0.0)


# -------------------- PREPARAR DATAFRAME PARA EXIBIÇÃO --------------------

# 2. ISOLAR E CONVERTER: Cria um novo DataFrame que herda apenas os dados como string
# Removemos a coluna VALOR_NUM, pois ela é float64 e não deve ser exibida.
colunas_para_mostrar = [col for col in dados_existentes.columns if col != "VALOR_NUM"]

# Cria o DataFrame de exibição, selecionando apenas as colunas originais
df_show = dados_existentes[colunas_para_mostrar].copy()

# Converte TUDO para string no DataFrame de exibição
df_show = df_show.astype(str) 

# Exibir tabela limpa (Linha 124 no seu novo traceback)
st.dataframe(df_show) 

# -------------------- CARD DE SOMA --------------------
# 3. CÁLCULO DA SOMA (Usa a coluna numérica original de dados_existentes)
soma = dados_existentes["VALOR_NUM"].sum()

st.markdown(
# ... (o código do st.markdown para o CARD DE SOMA) ...
    f"""
    <div style="
        background-color:#f0f2f6;
        padding:20px;
        border-radius:10px;
        box-shadow:0px 0px 10px rgba(0,0,0,0.1);
        text-align:center;
        width:250px;
        margin:auto;
        margin-top:20px;
    ">
        <h3 style="color:#333;">Total</h3>
        <h1 style="color:#4CAF50;">R$ {soma:,.2f}</h1>
    </div>
    """,
    unsafe_allow_html=True
)
# ...

# -------------------- FORMULÁRIO --------------------
UNIDADE = [
    "ADMINISTRATIVO", "CEL.FABRICIANO", "DURVAL DE BARROS", "EXPEDIÇÃO", "GARANTIA",
    "INDUSTRIA", "ITAUNA", "JARDIM MONTANHÊS", "LAGOA SANTA", "LAVRAS",
    "MONTES CLAROS", "OLIVEIRA", "PREDIO ADM", "SÃO MARCOS", "VENDA DE VEICULOS",
    "IPATINGA", "MORRO ALTO", "NEVES", "NOVA LIMA", "VARGINHA", "VESPASIANO",
]

STATUS = ["APROVADA", "NÃO APROVADA", "COTAÇÃO", "PEDIDO"]
AVALIACAO = ["EXPEDIÇÃO", "FINANCEIRO", "UNIDADE"]

with st.form(key="vendor_form"):
    pedido = st.sidebar.text_input(label="Pedido/Solicitação*")
    data = st.sidebar.date_input(label="Previsão de Pagamento*")
    unidade = st.sidebar.selectbox("Unidade*", options=UNIDADE, index=None)
    valor = st.sidebar.number_input(label="Valor")
    carro = st.sidebar.text_area(label="Carro/Utilização*")
    fornecedor = st.sidebar.text_input(label="Fornecedor")
    status = st.sidebar.selectbox("Status*", options=STATUS, index=None)
    avaliacao = st.sidebar.selectbox("Avaliação", options=AVALIACAO, index=None)
    observacao = st.sidebar.text_area(label="Observações")

    st.sidebar.markdown("**required*")

    cadastrar = st.form_submit_button(label="CADASTRAR")

    if cadastrar:
        data_formatada = data.strftime("%d/%m/%Y")

        # Checagem dos campos obrigatórios
        if not pedido or not data or not unidade or not carro or not status:
            st.warning("Preencha os campos obrigatórios!")
            st.stop()
        

        # -------------------- Verificar duplicidade (Ajustado) --------------------
        if "PEDIDO" in dados_existentes.columns:
    # Padroniza o pedido de entrada
            pedido_upper = str(pedido).strip().upper() 
    
    # Padroniza a coluna do DataFrame
            col_pedido = dados_existentes["PEDIDO"].astype(str).str.strip().str.upper()
    
    # Compara exatamente
            if (col_pedido == pedido_upper).any(): # <-- Mudança aqui
                st.warning(f"O pedido '{pedido}' já foi cadastrado!")
                st.stop()

        # Criar novo registro
        dado = pd.DataFrame([{
            "DATA": data_formatada,
            "UNIDADE": unidade,
            "CARRO | UTILIZAÇÃO": carro,
            "PEDIDO": pedido,
            "VALOR": valor,
            "FORNECEDOR": fornecedor,
            "STATUS": status,
            "AVALIAÇÃO": avaliacao,
            "OBSERVAÇÕES": observacao,
        }])

        update_df = pd.concat([dados_existentes, dado], ignore_index=True)

        # Salvar no Google Sheets
        conexao.update(worksheet="ALTA", data=update_df)

        st.success("Pedido cadastrado com sucesso!")
