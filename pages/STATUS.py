import streamlit as st
import pymssql

st.title("🧪 Teste de Conexão SQL")

db_config = st.secrets["database"]

st.write(f"Tentando conectar ao servidor: `{db_config['server']}`")

try:
    # Tentativa de conexão com timeout curto para não travar o app
    conn = pymssql.connect(
        server=db_config["server"],
        user=db_config["username"],
        password=db_config["password"],
        database=db_config["database"],
        login_timeout=10  # Espera apenas 10 segundos
    )
    st.success("✅ Conexão estabelecida com sucesso!")
    conn.close()
except pymssql.OperationalError as e:
    st.error("❌ Erro Operacional: Não foi possível alcançar o servidor.")
    st.info("Dica: Verifique se o servidor permite conexões externas e se o IP do Streamlit não está bloqueado no Firewall.")
    st.code(str(e))
except Exception as e:
    st.error(f"❌ Ocorreu um erro inesperado: {e}")