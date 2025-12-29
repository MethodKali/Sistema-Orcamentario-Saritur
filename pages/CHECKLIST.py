import streamlit as st

def app():
    st.title("✅ Checklist de Operações Diárias")
    st.markdown("---")

    # --- LISTA DE TAREFAS (EDITE AQUI MANUALMENTE) ---
    # Você pode adicionar ou remover itens nestas listas
    tarefas_manha = [
        "Atualizar planilha EMERGENCIAL",
        "Aprovar solicitação dando foco a Jardim Montanhês e Transnorte",
        "Extrair solicitações e pedidos da Planilha de Carro Parado",
        "Responder Planilha de Carro Parado JDM e MC",
        "Responder Planilha de Carro Parado demais Garagens. *Nota confira o arquivo IMPORTANTE.txt.",

    ]

    tarefas_tarde = [
        "Lançamentos na EMERGENCIAL",
        "Revisar gastos da aba EMERGENCIAL",
        "Preparar programação para o dia seguinte",
        "Acesse o N8N: https://first-project.app.n8n.cloud/workflow/wLYYG2BNTSiSLkPN\nAcesse a API do Facebook: https://developers.facebook.com/apps/895177043047943/whatsapp-business/api-testing/?business_id=182588088036619"
    ]
    # -----------------------------------------------

    # Cálculo de Progresso
    total_tarefas = len(tarefas_manha) + len(tarefas_tarde)
    concluidas = 0

    st.subheader("☀️ Período da Manhã")
    for tarefa in tarefas_manha:
        if st.checkbox(tarefa, key=f"manha_{tarefa}"):
            concluidas += 1

    st.markdown("---")
    st.subheader("🌙 Período da Tarde")
    for tarefa in tarefas_tarde:
        if st.checkbox(tarefa, key=f"tarde_{tarefa}"):
            concluidas += 1

    # Barra de Progresso no Rodapé
    st.markdown("---")
    progresso = concluidas / total_tarefas
    st.write(f"**Progresso do Dia: {concluidas} de {total_tarefas} tarefas concluídas**")
    st.progress(progresso)

    if concluidas == total_tarefas:
        st.balloons()
        st.success("🎉 Todas as tarefas do dia foram concluídas!")

if __name__ == "__main__":
    app()