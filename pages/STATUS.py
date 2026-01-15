import streamlit as st
import pymssql

st.title("🧪 Teste de Conexão SQL")

# Carrega o dicionário principal
try:
    db_config = st.secrets["database"]
except KeyError:
    st.error("❌ A seção [database] não foi encontrada no secrets.toml")
    st.stop()

st.write(f"Tentando conectar ao servidor: `{db_config['server']}`")

try:
    # Agora acessamos pelas CHAVES do dicionário, não pelos VALORES
    conn = pymssql.connect(
        server=db_config["server"],      # Puxa o IP do segredo
        user=db_config["user"],          # Puxa o usuário do segredo
        password=db_config["password"],  # Puxa a senha do segredo
        database=db_config["database"],  # Puxa o nome do banco
        login_timeout=10 
    )
    
    st.success("✅ Conexão estabelecida com sucesso!")
    
    # Teste rápido de query
    cursor = conn.cursor()
    cursor.execute("SELECT @@VERSION")
    row = cursor.fetchone()
    st.info(f"Versão do SQL Server: {row[0]}")
    
    conn.close()

except pymssql.OperationalError as e:
    st.error("❌ Erro Operacional: Servidor inacessível.")
    st.warning("Verifique se o VPN está ativo ou se o Firewall libera o IP: 192.168.0.11")
    st.code(str(e))
except Exception as e:
    st.error(f"❌ Erro de Configuração: {e}")
    st.info("Certifique-se de que as chaves 'server', 'user', 'password' e 'database' existem em [database].")