from fastapi import APIRouter, Request, BackgroundTasks
import openproject, watchlist
from watchlist import add_work_package_to_watchlist
from fastapi.responses import JSONResponse
import requests
from openproject import OPENPROJECT_API_URL, OPENPROJECT_API_KEY
from db_openproject import delete_cost_entries_by_work_package_id

router = APIRouter(
    prefix='',
    tags=['Rotas']
)

@router.post('/work_package_update')
async def work_package_update(request: Request, background_tasks: BackgroundTasks):
    """Função para receber webhooks de atualização de pacote de trabalho
    """
    data = await request.json()
    
    work_package = data.get("work_package", {})
    if not work_package:
        return JSONResponse(content={"message": "Nenhum dado de pacote de trabalho recebido."}, status_code=400)
    
    wp_type = (
        work_package.get("_links", {}).get("type", {}).get("title")
        or work_package.get("_embedded", {}).get("type", {}).get("name")
    )
    
    if wp_type == "Reunião":
        wp_id = work_package.get("id")
        if wp_id is not None:
            wp_id_str = str(wp_id)
            current_status = (
                work_package.get("_links", {}).get("status", {}).get("title")
                or work_package.get("_embedded", {}).get("status", {}).get("name")
                or "Desconhecido"
            )
            
            watchlist_dict = watchlist._carregar_e_normalizar_watchlist()
            
            is_in_abertos = wp_id_str in watchlist_dict["abertos"]
            is_in_nao_processados = wp_id_str in watchlist_dict["fechados"]["nao_processados"]
            is_in_processados = wp_id_str in watchlist_dict["fechados"]["processados"]
            
            if is_in_abertos or is_in_nao_processados or is_in_processados:
                is_closed = (current_status == "Fechada - 100%")
                
                # Vamos identificar se houve mudança de status de fato
                old_status = None
                if is_in_abertos:
                    old_status = watchlist_dict["abertos"][wp_id_str]
                elif is_in_nao_processados:
                    old_status = watchlist_dict["fechados"]["nao_processados"][wp_id_str]
                elif is_in_processados:
                    old_status = watchlist_dict["fechados"]["processados"][wp_id_str]
                
                if old_status != current_status:
                    # Remove do local antigo
                    if is_in_abertos:
                        del watchlist_dict["abertos"][wp_id_str]
                    elif is_in_nao_processados:
                        del watchlist_dict["fechados"]["nao_processados"][wp_id_str]
                    elif is_in_processados:
                        del watchlist_dict["fechados"]["processados"][wp_id_str]
                        
                    # Insere no novo local
                    if is_closed:
                        # Se mudou para Fechada - 100%, deve ir para nao_processados por padrão
                        watchlist_dict["fechados"]["nao_processados"][wp_id_str] = current_status
                        print(f"Watchlist atualizada via webhook: Pacote de trabalho {wp_id} mudou para 'Fechada - 100%' e foi para não processados.")
                    else:
                        # Se reabriu, vai para abertos
                        watchlist_dict["abertos"][wp_id_str] = current_status
                        print(f"Watchlist atualizada via webhook: Pacote de trabalho {wp_id} foi reaberto com status '{current_status}'.")
                        
                        if is_in_nao_processados or is_in_processados:
                            deleted_count = delete_cost_entries_by_work_package_id(int(wp_id))
                            print(f"Watchlist atualizada via webhook: Removido {deleted_count} lançamentos de custos para o pacote {wp_id} que foi reaberto.")
                        
                    watchlist._salvar_watchlist(watchlist_dict)
                else:
                    print(f"Pacote de trabalho {wp_id} recebido via webhook sem alteração no status ('{current_status}').")
            else:
                watchlist.add_work_package_to_watchlist(wp_id)
    
    return JSONResponse(content={"message": "Work package update processed successfully!"}, status_code=200)


@router.post('/atribuicao_gestor')
async def atribuicao_gestor(request: Request):
    data = await request.json()
    if data is None:
        return JSONResponse(content={"message": "Nenhum dado recebido."}, status_code=400)

    
    if data.get("work_package").get("_links").get("type").get("title"):
        
        work_package_type = data.get("work_package").get("_links").get("type").get("title")

        if work_package_type == "Reunião": 
        
            work_package_id = data.get("work_package").get("id")

            watchlist.add_work_package_to_watchlist(work_package_id)
    
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
    
    json_response = openproject.add_responsible_to_work_package(work_package__id, admin_href)
           
    return json_response