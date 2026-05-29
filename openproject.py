import os
import requests
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import uvicorn

load_dotenv(override=True)

OPENPROJECT_API_URL = os.getenv('OPENPROJECT_API_URL')
OPENPROJECT_API_KEY = os.getenv('OPENPROJECT_API_KEY')

app = FastAPI()

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

@app.api_route('/hello', methods=["POST", "GET"])
async def hello():
    print("Hello, OpenProject!")
    return JSONResponse(content="<h1>Hello, OpenProject!</h1>", status_code=200)


@app.api_route("/work_package_update", methods=['POST'])
async def work_package_update(request: Request):
    """Função para receber webhooks de teste

    Args:
        request (Request): Webhook enviado pelo OpenProject

    Returns:
        JSONResponse: "Work package update received!", 200
    """    
    data = await request.json()
    print(data)
    return JSONResponse(content={"message": "Work package update received!"}, status_code=200)


@app.api_route('/atribuicao_gestor', methods=['POST'])
async def atribuicao_gestor(request: Request):
    data = await request.json()
    
    if data.get("work_package").get("_links").get("responsible").get("href") is not None:
        return JSONResponse(content={"message": "O pacote de trabalho já possui um responsável atribuído."}, status_code=200)
    
    work_package__id = data.get("work_package").get("id")
    
    memberships_url = data.get("work_package").get("_embedded").get("project").get("_links").get("memberships").get("href")
    
    memberships = requests.get(f"{OPENPROJECT_API_URL}{memberships_url}", auth=('apikey', OPENPROJECT_API_KEY))
    
    memberships.raise_for_status()

    memberships_data = memberships.json()
    
    elements = memberships_data.get("_embedded", {}).get("elements", [])
    
    admin_href = None
    for member in elements:
        if member.get("_type") == "Membership" and member.get("_links").get("principal").get("href") != "/api/v3/users/23": # Se não for a Giu
            for role in member.get("_links").get("roles"):
                if role.get("title") == "Administrador de Projeto":
                    admin_href = member.get("_links").get("principal").get("href")
                    admin_name = member.get("_links").get("self").get("title")
                    break
    if admin_href is None:
        return JSONResponse(content={"message": "Administrador de projeto não encontrado."}, status_code=404)

    print(f"href do administrador encontrado: {admin_href}")
    print(f"Nome do administrador encontrado: {admin_name}")
    
    json_response = add_responsible_to_work_package(work_package__id, admin_href)
           
    return json_response

if __name__ == '__main__':
    uvicorn.run("openproject:app", host="0.0.0.0", port=30200, reload=True)