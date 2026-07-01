from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse

router = APIRouter(
    prefix='',
    tags=['Hello']
)

@router.get('/hello')
async def hello():
    """Função de teste da API"""    
    
    return JSONResponse(content="<h1>Hello, OpenProject!</h1>", status_code=200)