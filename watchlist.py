import os
import json
import requests
from openproject import OPENPROJECT_API_URL, OPENPROJECT_API_KEY
from db_openproject import delete_cost_entries_by_work_package_id

WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'watchlist.json')

def _carregar_e_normalizar_watchlist() -> dict:
    """
    Lê a watchlist de WATCHLIST_FILE e a normaliza para a nova estrutura:
    {
        "abertos": { "id_str": "status_name" },
        "fechados": {
            "nao_processados": { "id_str": "status_name" },
            "processados": { "id_str": "status_name" }
        }
    }
    
    Retorna:
        dict: O dicionário normalizado da watchlist.
    """
    watchlist_dict = {
        "abertos": {},
        "fechados": {
            "nao_processados": {},
            "processados": {}
        }
    }
    
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    raw = json.loads(content)
                    
                    # Se já estiver na estrutura nova
                    if isinstance(raw, dict) and "abertos" in raw and "fechados" in raw:
                        watchlist_dict["abertos"] = raw.get("abertos", {})
                        fechados = raw.get("fechados", {})
                        if isinstance(fechados, dict):
                            watchlist_dict["fechados"]["nao_processados"] = fechados.get("nao_processados", {})
                            watchlist_dict["fechados"]["processados"] = fechados.get("processados", {})
                        return watchlist_dict
                    
                    # Caso esteja no formato antigo de dicionário plano
                    if isinstance(raw, dict):
                        for k, v in raw.items():
                            id_str = str(k)
                            status_name = "Desconhecido"
                            if isinstance(v, dict):
                                status_name = v.get("status", "Desconhecido")
                            elif isinstance(v, str):
                                status_name = v
                            
                            if status_name == "Fechada - 100%":
                                watchlist_dict["fechados"]["nao_processados"][id_str] = status_name
                            else:
                                watchlist_dict["abertos"][id_str] = status_name
                                
                    # Caso esteja no formato de lista antigo
                    elif isinstance(raw, list):
                        for item in raw:
                            if isinstance(item, dict) and "id" in item:
                                id_str = str(item["id"])
                                status_name = item.get("status", "Desconhecido")
                            elif isinstance(item, int):
                                id_str = str(item)
                                status_name = "Desconhecido"
                            else:
                                continue
                            
                            if status_name == "Fechada - 100%":
                                watchlist_dict["fechados"]["nao_processados"][id_str] = status_name
                            else:
                                watchlist_dict["abertos"][id_str] = status_name
                                
        except (json.JSONDecodeError, IOError) as e:
            print(f"Erro ao ler a watchlist ({e}). Retornando estrutura vazia.")
    return watchlist_dict

def _salvar_watchlist(watchlist_dict: dict) -> None:
    """
    Salva a watchlist no WATCHLIST_FILE, ordenando as chaves numericamente.
    """
    def sort_dict(d):
        try:
            return dict(sorted(d.items(), key=lambda item: int(item[0])))
        except (ValueError, TypeError):
            return dict(sorted(d.items()))

    ordered_watchlist = {
        "abertos": sort_dict(watchlist_dict.get("abertos", {})),
        "fechados": {
            "nao_processados": sort_dict(watchlist_dict.get("fechados", {}).get("nao_processados", {})),
            "processados": sort_dict(watchlist_dict.get("fechados", {}).get("processados", {}))
        }
    }
    
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(ordered_watchlist, f, indent=4, ensure_ascii=False)


def add_work_package_to_watchlist(work_package_id) -> bool:
    """
    Adiciona o ID de um pacote de trabalho (work package) do OpenProject a uma watchlist salva como JSON.
    A watchlist é estruturada dividindo pacotes abertos e fechados (processados/não processados).
    
    Args:
        work_package_id (int or str): O ID do pacote de trabalho.
        
    Returns:
        bool: True se adicionado ou atualizado com sucesso, False em caso de erro.
    """
    try:
        # Validação estrita do ID: deve ser um inteiro positivo
        try:
            wp_id = int(work_package_id)
            if wp_id <= 0:
                raise ValueError("O ID deve ser um número inteiro positivo.")
        except (ValueError, TypeError) as ve:
            print(f"ID inválido para watchlist: {work_package_id}. Erro: {ve}")
            return False

        # Obter o status do pacote de trabalho da API do OpenProject
        url = f"{OPENPROJECT_API_URL}/api/v3/work_packages/{wp_id}"
        try:
            response = requests.get(url, auth=('apikey', OPENPROJECT_API_KEY))
            response.raise_for_status()
            wp_data = response.json()
            status_name = (
                wp_data.get("_links", {}).get("status", {}).get("title")
                or wp_data.get("_embedded", {}).get("status", {}).get("name")
                or "Desconhecido"
            )
        except requests.exceptions.RequestException as e:
            print(f"Erro ao buscar status do pacote de trabalho {wp_id}: {e}")
            status_name = "Desconhecido"

        watchlist_dict = _carregar_e_normalizar_watchlist()
        wp_id_str = str(wp_id)

        is_in_abertos = wp_id_str in watchlist_dict["abertos"]
        is_in_nao_processados = wp_id_str in watchlist_dict["fechados"]["nao_processados"]
        is_in_processados = wp_id_str in watchlist_dict["fechados"]["processados"]

        is_closed = (status_name == "Fechada - 100%")

        # Remove o ID das seções antigas se ele mudou de estado
        if is_closed:
            if is_in_abertos:
                del watchlist_dict["abertos"][wp_id_str]
            
            if not is_in_nao_processados and not is_in_processados:
                watchlist_dict["fechados"]["nao_processados"][wp_id_str] = status_name
                _salvar_watchlist(watchlist_dict)
                print(f"ID {wp_id} adicionado a fechados/não processados com status '{status_name}'.")
            else:
                target_group = "processados" if is_in_processados else "nao_processados"
                if watchlist_dict["fechados"][target_group][wp_id_str] != status_name:
                    watchlist_dict["fechados"][target_group][wp_id_str] = status_name
                    _salvar_watchlist(watchlist_dict)
                    print(f"ID {wp_id} atualizado em fechados/{target_group} com status '{status_name}'.")
                else:
                    print(f"ID {wp_id} já está registrado como fechado com status '{status_name}'.")
        else:
            was_in_closed = is_in_nao_processados or is_in_processados
            if is_in_nao_processados:
                del watchlist_dict["fechados"]["nao_processados"][wp_id_str]
            if is_in_processados:
                del watchlist_dict["fechados"]["processados"][wp_id_str]
            
            if not is_in_abertos:
                watchlist_dict["abertos"][wp_id_str] = status_name
                _salvar_watchlist(watchlist_dict)
                print(f"ID {wp_id} adicionado a abertos com status '{status_name}'.")
            else:
                if watchlist_dict["abertos"][wp_id_str] != status_name:
                    watchlist_dict["abertos"][wp_id_str] = status_name
                    _salvar_watchlist(watchlist_dict)
                    print(f"ID {wp_id} atualizado em abertos com status '{status_name}'.")
                else:
                    print(f"ID {wp_id} já está registrado em abertos com status '{status_name}'.")
            
            if was_in_closed:
                deleted_count = delete_cost_entries_by_work_package_id(wp_id)
                print(f"Removido {deleted_count} lançamentos de custos para o pacote de trabalho {wp_id} que voltou para abertos.")

        return True
    except Exception as e:
        print(f"Erro inesperado ao gerenciar a watchlist: {e}")
        return False