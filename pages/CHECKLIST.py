import streamlit as st
import pandas as pd
import json
import os
from datetime import date, datetime

# --- CONFIGURAÇÕES DE ARQUIVO ---
ARQUIVO_TAREFAS = "banco_checklist.json"

def carregar_tarefas():
    if os.path.exists(ARQUIVO_TAREFAS):
        with open(ARQUIVO_TAREFAS, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_tarefas(tarefas):
    with open(ARQUIVO_TAREFAS, "w", encoding="utf-8") as f:
        json.dump(tarefas, f, ensure_ascii=False, indent=4)

def app():
    st.title("✅ Gerenciador de Checklist Dinâmico")
    
    # Inicialização do banco de dados
    if 'db_tarefas' not in st.session_state:
        st.session_state.db_tarefas = carregar_tarefas()

    # --- ÁREA DE PROGRAMAÇÃO (INPUT) ---
    with st.expander("📅 Programar Nova Tarefa", expanded=False):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            nova_tarefa = st.text_input("Descrição da tarefa:", placeholder="Ex: Revisar planilha de custos")
        
        with col2:
            periodo = st.selectbox("Período:", ["Manhã", "Tarde"])
            data_execucao = st.date_input("Data para execução:", date.today())
        
        if st.button("🚀 Programar Tarefa"):
            if nova_tarefa:
                data_str = data_execucao.strftime("%Y-%m-%d")
                
                # Estrutura do JSON: { "2024-05-20": { "Manhã": [{"task": "...", "done": False}], "Tarde": [] } }
                if data_str not in st.session_state.db_tarefas:
                    st.session_state.db_tarefas[data_str] = {"Manhã": [], "Tarde": []}
                
                st.session_state.db_tarefas[data_str][periodo].append({
                    "task": nova_tarefa,
                    "done": False,
                    "created_at": datetime.now().strftime("%H:%M:%S")
                })
                
                salvar_tarefas(st.session_state.db_tarefas)
                st.success(f"Tarefa agendada para {data_execucao.strftime('%d/%m')} na {periodo}!")
                st.rerun()
            else:
                st.warning("Por favor, digite uma descrição para a tarefa.")

    st.markdown("---")

    # --- VISUALIZAÇÃO E CHECKLIST ---
    tab1, tab2 = st.tabs(["📋 Checklist de Hoje", "🗓️ Calendário de Tarefas"])

    with tab1:
        hoje_str = date.today().strftime("%Y-%m-%d")
        st.subheader(f"Tarefas para Hoje ({date.today().strftime('%d/%m/%Y')})")
        
        if hoje_str in st.session_state.db_tarefas:
            tarefas_hoje = st.session_state.db_tarefas[hoje_str]
            
            total = len(tarefas_hoje["Manhã"]) + len(tarefas_hoje["Tarde"])
            concluidas = 0

            # Renderização Manhã
            st.markdown("#### ☀️ Manhã")
            if not tarefas_hoje["Manhã"]: st.info("Nenhuma tarefa para esta manhã.")
            for i, item in enumerate(tarefas_hoje["Manhã"]):
                # O checkbox atualiza o estado 'done' no dicionário
                checked = st.checkbox(f"{item['task']}", value=item['done'], key=f"h_m_{i}")
                if checked != item['done']:
                    st.session_state.db_tarefas[hoje_str]["Manhã"][i]["done"] = checked
                    salvar_tarefas(st.session_state.db_tarefas)
                    st.rerun()
                if checked: concluidas += 1

            st.markdown("#### 🌙 Tarde")
            if not tarefas_hoje["Tarde"]: st.info("Nenhuma tarefa para esta tarde.")
            for i, item in enumerate(tarefas_hoje["Tarde"]):
                checked = st.checkbox(f"{item['task']}", value=item['done'], key=f"h_t_{i}")
                if checked != item['done']:
                    st.session_state.db_tarefas[hoje_str]["Tarde"][i]["done"] = checked
                    salvar_tarefas(st.session_state.db_tarefas)
                    st.rerun()
                if checked: concluidas += 1

            # Barra de Progresso
            if total > 0:
                st.markdown("---")
                progresso = concluidas / total
                st.write(f"**Progresso: {concluidas} de {total} concluídas**")
                st.progress(progresso)
                if concluidas == total:
                    st.balloons()
                    st.success("🎉 Excelente! Todas as tarefas de hoje foram concluídas.")
        else:
            st.info("Não há tarefas programadas para hoje. Use o campo acima para agendar.")

    with tab2:
        st.subheader("Filtro por Data")
        data_consulta = st.date_input("Selecione uma data para verificar:", date.today())
        consulta_str = data_consulta.strftime("%Y-%m-%d")
        
        if consulta_str in st.session_state.db_tarefas:
            resumo = st.session_state.db_tarefas[consulta_str]
            col_m, col_t = st.columns(2)
            with col_m:
                st.write("**Manhã:**")
                for t in resumo["Manhã"]:
                    status = "✅" if t["done"] else "⏳"
                    st.write(f"{status} {t['task']}")
            with col_t:
                st.write("**Tarde:**")
                for t in resumo["Tarde"]:
                    status = "✅" if t["done"] else "⏳"
                    st.write(f"{status} {t['task']}")
            
            if st.button("🗑️ Limpar tarefas deste dia"):
                del st.session_state.db_tarefas[consulta_str]
                salvar_tarefas(st.session_state.db_tarefas)
                st.rerun()
        else:
            st.warning("Nenhuma tarefa encontrada para esta data.")

if __name__ == "__main__":
    app()