import os
import json
from watchlist import _carregar_e_normalizar_watchlist, _salvar_watchlist
from db_openproject import get_openproject_user, upsert_cost_rate, insert_cost_entry, get_all_meetings_with_participants, delete_cost_entries_by_meeting_id

def set_meeting_entry(meeting: dict, automation_user_id: int) -> int:
    """
    Orquestra o fluxo de inserção de custos nas reuniões que estão sendo processadas:
    1. Atualizar o CostRate para o CostType de Taxa Horária (id 4) informando o project_id.
    2. Registrar um cost_entries correspondente associando ao meeting diretamente.
    """
    project_id = meeting.get("project_id")
    meeting_id = meeting.get("meeting_id")
    meeting_start_time = meeting.get("meeting_start_time")
    duration = meeting.get("meeting_duration", 0.0)
    total_rate = meeting.get("total_rate", 0.0)
    participant_names = meeting.get("participant_names", [])

    comments = ", ".join(participant_names) if participant_names else ""

    # Passo 1: Atualizar o CostRate para Taxa Horária (id 4)
    rate_id = upsert_cost_rate(
        project_id=project_id,
        rate=total_rate,
        valid_from=meeting_start_time
    )

    # Custos calculados
    overridden_costs = total_rate * duration
    costs = duration * total_rate

    # Passo 2: Registrar o cost_entries
    cost_entry_id = insert_cost_entry(
        user_id=automation_user_id,
        project_id=project_id,
        work_package_id=None,
        cost_type_id=4,
        units=duration,
        spent_on=meeting_start_time,
        comments=comments,
        overridden_costs=overridden_costs,
        costs=costs,
        rate_id=rate_id,
        logged_by_id=automation_user_id,
        entity_type="Meeting",
        entity_id=meeting_id
    )

    return cost_entry_id

def processar_reunioes():
    """Busca reuniões periodicamente no banco de dados e registra custos para as fechadas."""
    
    automation_user_id = int(os.getenv('AUTOMATION_USER_ID', 4))
    watchlist_dict = _carregar_e_normalizar_watchlist()
    
    # 1. Carrega todas as reuniões com participantes diretamente do banco de dados
    meetings = get_all_meetings_with_participants()
    
    # Mapeamento numérico dos estados de reuniões
    STATE_MAPPING = {
        0: "Aberta",
        3: "Em Andamento",
        5: "Fechada"
    }
    
    # Cria conjuntos/dicionários auxiliares da watchlist
    abertos = watchlist_dict.get("abertos", {})
    nao_processados = watchlist_dict.get("fechados", {}).get("nao_processados", {})
    processados = watchlist_dict.get("fechados", {}).get("processados", {})
    
    # Variável para controlar se a watchlist foi alterada
    watchlist_changed = False
    
    # Dicionário de reuniões por ID para processamento posterior
    meetings_by_id = {m["meeting_id"]: m for m in meetings}
    
    # 2. Sincroniza o estado atual das reuniões do banco na watchlist
    for meeting in meetings:
        m_id = meeting["meeting_id"]
        m_id_str = str(m_id)
        state_val = meeting["meeting_state"]
        state_name = STATE_MAPPING.get(state_val, "Desconhecido")
        
        if state_val in (0, 3):  # Aberta ou Em Andamento
            was_closed = (m_id_str in nao_processados) or (m_id_str in processados)
            if was_closed:
                # Se a reunião estava fechada e agora está aberta, remove o custo unitário associado
                deleted = delete_cost_entries_by_meeting_id(m_id)
                if deleted > 0:
                    print(f"Reunião {m_id} reaberta. Removido {deleted} lançamentos de custos do banco.")
                # Remove das seções de fechados
                nao_processados.pop(m_id_str, None)
                processados.pop(m_id_str, None)
                # Adiciona em abertos
                abertos[m_id_str] = state_name
                watchlist_changed = True
            elif m_id_str not in abertos or abertos[m_id_str] != state_name:
                abertos[m_id_str] = state_name
                watchlist_changed = True
                
        elif state_val == 5:  # Fechada
            if m_id_str in abertos:
                # Remove de abertos
                abertos.pop(m_id_str)
                # Move para não processados
                nao_processados[m_id_str] = state_name
                watchlist_changed = True
            elif (m_id_str not in nao_processados) and (m_id_str not in processados):
                # Caso a reunião fechada não conste na watchlist, adiciona como não processada
                nao_processados[m_id_str] = state_name
                watchlist_changed = True

    # 3. Processa e registra custos para as reuniões fechadas e não processadas ainda
    processed_ids = []
    for m_id_str in list(nao_processados.keys()):
        m_id = int(m_id_str)
        meeting = meetings_by_id.get(m_id)
        if meeting:
            user_names = []
            total_rate = 0.0
            
            for user_id in meeting.get("participants", []):
                user_info = get_openproject_user(
                    user_id=user_id,
                    meeting_date=meeting.get("meeting_start_time"),
                    project_id=meeting.get("project_id")
                )
                if user_info:
                    user_names.append(user_info["name"])
                    total_rate += user_info["rate"]
            
            meeting["participant_names"] = user_names
            meeting["total_rate"] = total_rate
            
            # Registra custos no banco de dados para a reunião
            set_meeting_entry(meeting, automation_user_id)
            processed_ids.append(m_id_str)
            
            # Move para processados na watchlist
            status = nao_processados.pop(m_id_str)
            processados[m_id_str] = status
            watchlist_changed = True

    # 4. Salva a watchlist se houver alterações
    if watchlist_changed or processed_ids:
        _salvar_watchlist(watchlist_dict)
        if processed_ids:
            print(f"Reuniões fechadas processadas com sucesso: {processed_ids}")
        else:
            print("Watchlist sincronizada com sucesso com o banco de dados de reuniões.")
    else:
        print("Nenhuma alteração de estado de reuniões e nenhuma reunião fechada para processar.")

if __name__ == '__main__':
    processar_reunioes()