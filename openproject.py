import os
import json
import requests
from dotenv import load_dotenv
from fastapi.responses import JSONResponse

load_dotenv(override=True)

OPENPROJECT_API_URL = os.getenv('OPENPROJECT_API_URL')
OPENPROJECT_API_KEY = os.getenv('OPENPROJECT_API_KEY')

if not OPENPROJECT_API_URL or not OPENPROJECT_API_KEY:
    raise ValueError("As variáveis de ambiente OPENPROJECT_API_URL e OPENPROJECT_API_KEY devem ser definidas.")

def obter_lockversion_pacote_de_trabalho(id__pacote_de_trabalho):
    """Obtém o último LockVersion de um pacote de trabalho para fazer PATCH em suas propriedades evitando problemas de concorrência

    Args:
        id__pacote_de_trabalho (int): ID do pacote de trabalho
        
    Returns:
        int: O último LockVersion do pacote de trabalho
    """
    url = f"{OPENPROJECT_API_URL}/api/v3/work_packages/{id__pacote_de_trabalho}"
    
    response = requests.get(url, auth=('apikey', OPENPROJECT_API_KEY))
    
    response.raise_for_status()
    
    return response.json().get("lockVersion")

def add_responsible_to_work_package(work_package_id, user_href):
    """
    Adiciona um usuário como responsável por um pacote de trabalho específico.
    
    Parâmetros:
    - work_package_id (int): O ID do pacote de trabalho.
    - user_id (int): O ID do usuário a ser adicionado como responsável.
    """
    
    lockVersion = obter_lockversion_pacote_de_trabalho(work_package_id)
    
    
    url = f"{OPENPROJECT_API_URL}/api/v3/work_packages/{work_package_id}"
    
    payload = {
        "lockVersion": int(lockVersion),
        "_links": {
            "responsible": {
                "href": f"{user_href}"
            }
        }
    }

    try:
        response = requests.patch(url, json=payload, auth=('apikey', OPENPROJECT_API_KEY))
    
        response.raise_for_status()
    
        print(f"Usuário ID {user_href} adicionado como responsável ao pacote de trabalho {work_package_id} com sucesso!")

        return JSONResponse(content=f"Usuário ID {user_href} adicionado como responsável ao pacote de trabalho {work_package_id} com sucesso!", status_code=response.status_code)
    
    except requests.exceptions.RequestException as e:
        print(f"Erro ao adicionar responsável ao pacote de trabalho {work_package_id}: {e}")


def get_meeting_by_work_package_id(work_package_id):
    """
    Busca reuniões associadas a um pacote de trabalho específico.
    
    Args:
        work_package_id (int or str): O ID do pacote de trabalho (work package).
        
    Returns:
        dict: Resposta da API do OpenProject com as reuniões.
    """
    url = f"{OPENPROJECT_API_URL}/api/v3/meetings/"
    
    payload = {
        "_embedded": {
            "elements": {
                "_type": "Meeting",
                "_links": {
                    "work_package": {
                        "id": work_package_id
                    }
                }
            }
        }
    }
    
    try:
        response = requests.get(
            url,
            auth=('apikey', OPENPROJECT_API_KEY)
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar reuniões associadas ao pacote de trabalho {work_package_id}: {e}")
        raise
    