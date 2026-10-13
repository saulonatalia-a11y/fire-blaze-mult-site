import os,time,json,base64,hmac
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI,HTTPException,Header
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,EmailStr,Field
import psycopg
from psycopg.rows import dict_row
from cryptography.hazmat.primitives import serialization
DATABASE_URL=os.environ['DATABASE_URL']
ADMIN_PASSWORD=os.environ['FIRE_ADMIN_PASSWORD']
key=serialization.load_pem_private_key(base64.b64decode(os.environ['FIRE_SIGNING_KEY_B64']),password=None)
public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()
app=FastAPI(title="FIRE BLAZE Mult")
@contextmanager
def db():
 with psycopg.connect(DATABASE_URL,row_factory=dict_row) as c: yield c
class Start(BaseModel):
 email:EmailStr
 device:str=Field(min_length=16,max_length=128)
class Action(BaseModel):
 email:EmailStr
 device:str|None=None
class Request(BaseModel):
 email:EmailStr
 kind:str
 note:str=''
def auth(a):
 if not a or not a.startswith('Bearer ') or not hmac.compare_digest(a[7:],ADMIN_PASSWORD):raise HTTPException(401,'Acesso negado')
def user(c,e):return c.execute('SELECT * FROM customers WHERE email=%s',(str(e).lower(),)).fetchone()
def result(c,u):
 lic=c.execute('SELECT license_payload FROM licenses WHERE customer_id=%s AND revoked_at IS NULL ORDER BY id DESC LIMIT 1',(u['id'],)).fetchone()
 return {'status':u['status'],'remaining_seconds':u['trial_seconds_remaining'],'license':lic['license_payload'] if lic else None}
def audit(c,a,d):c.execute('INSERT INTO audit_events(action,details) VALUES(%s,%s::jsonb)',(a,json.dumps(d)))
@app.get('/api/health')
def health():
 with db() as c:c.execute('SELECT 1')
 return {'ok':True}
@app.get('/api/config')
def config():
 with db() as c:r=c.execute("SELECT value FROM app_settings WHERE key='lifetime_price_brl'").fetchone()
 return {'price':r['value'] if r else '29.90','trial_hours':7,'public_key':public}
@app.post('/api/start')
def start(req:Start):
 with db() as c:
  u=user(c,req.email)
  if not u:
   if c.execute('SELECT id FROM customers WHERE device_hash=%s',(req.device,)).fetchone():raise HTTPException(403,'Teste já utilizado neste PC')
   c.execute('INSERT INTO customers(email,device_hash) VALUES(%s,%s)',(str(req.email).lower(),req.device));u=user(c,req.email)
  if u['device_hash']!=req.device or u['status']=='blocked':raise HTTPException(403,'PC não autorizado')
  return result(c,u)
@app.post('/api/heartbeat')
def heartbeat(req:Start):
 now=int(time.time())
 with db() as c:
  u=c.execute('SELECT * FROM customers WHERE email=%s FOR UPDATE',(str(req.email).lower(),)).fetchone()
  if not u or u['device_hash']!=req.device or u['status']=='blocked':raise HTTPException(403,'Não autorizado')
  if u['status']=='lifetime':return result(c,u)
  if u['status']=='expired' or u['trial_seconds_remaining']<=0:raise HTTPException(403,'Teste expirado')
  last=int(u['last_heartbeat_at'].timestamp()) if u['last_heartbeat_at'] else None
  elapsed=min(65,max(0,now-last)) if last else 0
  left=max(0,u['trial_seconds_remaining']-elapsed)
  status='trial' if left else 'expired'
  c.execute('UPDATE customers SET trial_seconds_remaining=%s,last_heartbeat_at=to_timestamp(%s),status=%s WHERE id=%s',(left,now,status,u['id']))
  return {'status':status,'remaining_seconds':left,'license':None}
@app.post('/api/request')
def request_change(req:Request):
 if req.kind not in ('reset_pc','delete_account'):raise HTTPException(400,'Pedido inválido')
 with db() as c:
  u=user(c,req.email)
  if not u:raise HTTPException(404,'Conta não encontrada')
  c.execute('INSERT INTO customer_requests(customer_id,request_type,note) VALUES(%s,%s,%s)',(u['id'],req.kind,req.note[:500]))
 return {'ok':True}
@app.get('/api/admin/dashboard')
def dashboard(authorization:str|None=Header(None)):
 auth(authorization)
 with db() as c:
  users=c.execute('SELECT id,email,device_hash AS device,trial_seconds_remaining AS trial_seconds,status FROM customers ORDER BY id DESC').fetchall()
  requests=c.execute('SELECT r.id,r.request_type AS kind,r.note,r.status,c.email FROM customer_requests r JOIN customers c ON c.id=r.customer_id ORDER BY r.id DESC LIMIT 100').fetchall()
 return {'users':users,'requests':requests}
@app.post('/api/admin/grant')
def grant(req:Action,authorization:str|None=Header(None)):
 auth(authorization)
 with db() as c:
  u=user(c,req.email)
  if not u or not u['device_hash']:raise HTTPException(404,'Cliente sem PC')
  payload=json.dumps({'product':'fire-blaze-mult','type':'lifetime','email':u['email'],'device':u['device_hash'],'issued':int(time.time()),'version':1},sort_keys=True,separators=(',',':')).encode()
  token=base64.urlsafe_b64encode(payload).decode().rstrip('=')+'.'+base64.urlsafe_b64encode(key.sign(payload)).decode().rstrip('=')
  c.execute('UPDATE licenses SET revoked_at=now() WHERE customer_id=%s AND revoked_at IS NULL',(u['id'],))
  c.execute('INSERT INTO licenses(customer_id,device_hash,license_payload) VALUES(%s,%s,%s)',(u['id'],u['device_hash'],token))
  c.execute("UPDATE customers SET status='lifetime' WHERE id=%s",(u['id'],));audit(c,'grant',{'email':u['email']})
 return {'ok':True}
@app.post('/api/admin/reset-pc')
def reset(req:Action,authorization:str|None=Header(None)):
 auth(authorization)
 if not req.device or len(req.device)<16:raise HTTPException(400,'Identificador inválido')
 with db() as c:
  u=user(c,req.email)
  if not u:raise HTTPException(404,'Cliente não encontrado')
  c.execute('UPDATE licenses SET revoked_at=now() WHERE customer_id=%s',(u['id'],))
  c.execute("UPDATE customers SET device_hash=%s,status='blocked',last_heartbeat_at=NULL WHERE id=%s",(req.device,u['id']))
  audit(c,'reset_pc',{'email':u['email']})
 return {'ok':True,'note':'Reemita licença após verificar novo PC'}
@app.post('/api/admin/block')
def block(req:Action,authorization:str|None=Header(None)):
 auth(authorization)
 with db() as c:
  u=user(c,req.email)
  if not u:raise HTTPException(404,'Cliente não encontrado')
  c.execute("UPDATE customers SET status='blocked' WHERE id=%s",(u['id'],))
  c.execute('UPDATE licenses SET revoked_at=now() WHERE customer_id=%s',(u['id'],));audit(c,'block',{'email':u['email']})
 return {'ok':True}
@app.post('/api/admin/delete')
def delete(req:Action,authorization:str|None=Header(None)):
 auth(authorization)
 with db() as c:
  u=user(c,req.email)
  if not u:raise HTTPException(404,'Cliente não encontrado')
  c.execute('DELETE FROM customers WHERE id=%s',(u['id'],));audit(c,'delete',{'email':str(req.email)})
 return {'ok':True}
app.mount('/',StaticFiles(directory=str(Path(__file__).parent),html=True),name='site')
