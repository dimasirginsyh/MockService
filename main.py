import sqlite3
import time
import uuid

import redis
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from fastapi.responses import PlainTextResponse, JSONResponse
from pathlib import Path

app = FastAPI()

redis_client = redis.Redis(host='0.0.0.0', port=30073, db=0, password='123123')

def init_db():
    conn = sqlite3.connect('db/mock.db')
    cursor = conn.cursor()
    cursor.execute('''
       CREATE TABLE IF NOT EXISTS mock_templates
       (
           name TEXT PRIMARY KEY,
           content TEXT
       )
       ''')
    conn.commit()
    conn.close()

init_db()

class TemplateCreate(BaseModel):
    name: str
    content: str

@app.middleware("http")
async def cache_middleware(request: Request, call_next):
    if request.method != "GET" or not request.url.path == "docs":
        return await call_next(request)

    cache_key = request.url.path
    cache_response = redis_client.get(cache_key)
    if cache_response:
        return PlainTextResponse(
            content=cache_response.decode(),
            media_type="application/json"
        )

    response = await call_next(request)

    if 200 <= response.status_code < 300:
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        redis_client.setex(cache_key, 600, body)

        return PlainTextResponse(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers)
        )

    return response

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/mock/user")
async def mock_user():
    return {
        "id": str(uuid.uuid4()),
        "name": "Ganteng",
        "email": "ganteng@example.com"
    }

@app.get("/mock/order/{status}")
async def mock_order(status: str):
    status_map = {
        "success": 200,
        "failed": 400,
        "pending": 202
    }

    return JSONResponse(
        content={
            "order_id": f"ord-{uuid.uuid4().hex[:6]}",
            "status": status,
        },
        status_code=status_map.get(status, 200)
    )

@app.post("/template")
async def create_template(template: TemplateCreate):
    conn = sqlite3.connect('db/mock.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO mock_templates VALUES (?, ?)",
        (template.name, template.content)
    )
    conn.commit()
    conn.close()
    return {"message": "Template created"}

@app.get("/template/{name}")
async def get_template(name: str):
    conn = sqlite3.connect('db/mock.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT content FROM mock_templates WHERE name = ?",
        (name,)
    )
    result = cursor.fetchone()
    conn.close()

    if not result:
        raise HTTPException(status_code=404, detail="Template not found")

    return PlainTextResponse(content=result[0])

@app.get("/mock/payment")
async def mock_payment():
    template_path = Path("templates/payment.json")
    if not template_path.exists():
        raise HTTPException(status_code=404, detail="Payment not found")

    with open(template_path) as f:
        template = f.read()

    return PlainTextResponse(
        content=template.replace("{{timestamp}}", str(int(time.time()))).replace("{{uuid}}", str(uuid.uuid4())),
        media_type="application/json"
    )