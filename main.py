import os
import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from routers.hello import router as hello_router
from routers.webhooks import router as webhooks_router

from processar_reunioes import processar_reunioes

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Processar periodicamente as reuniões para realização do cálculo de horas e custo enquanto o servidor estiver ativo.

    # Configura o agendamento
    scheduler.add_job(processar_reunioes, 'interval', minutes=30)
    scheduler.start()
    
    yield
    
    # Desliga o agendador junto com o app
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

app.include_router(webhooks_router)
app.include_router(hello_router)

if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=30300, reload=True)