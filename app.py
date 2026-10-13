import os,time,json,base64,hmac,secrets,hashlib,smtplib,ssl
from email.message import EmailMessage
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI,HTTPException,Header,Response,Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,EmailStr,Field
import psycopg
from psycopg.rows import dict_row
from cryptography.hazmat.primitives import serialization
DATABASE_URL=os.environ['DATABASE_URL']
ADMIN_PASSWORD=os.environ['FIRE_ADMIN_PASSWORD']
key=None
if os.environ.get('FIRE_SIGNING_KEY_B64'):
 key=serialization.load_pem_private_key(base64.b64decode(os.environ['FIRE_SIGNING_KEY_B64']),password=None)
public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode() if key else None
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
 device:str|None=Field(default=None,min_length=16,max_length=128)
def auth(a):
 if not a or not a.startswith('Bearer ') or ADMIN_PASSWORD=='fire-blaze-admin-config-pending' or len(ADMIN_PASSWORD)<20 or not hmac.compare_digest(a[7:],ADMIN_PASSWORD):raise HTTPException(401,'Acesso negado')
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
 if req.kind not in ('reset_pc','delete_account','lifetime'):raise HTTPException(400,'Pedido inválido')
 with db() as c:
  u=user(c,req.email)
  if req.kind=='lifetime' and not u:
   if not req.device:raise HTTPException(400,'Identificação do computador obrigatória')
   if c.execute('SELECT id FROM customers WHERE device_hash=%s',(req.device,)).fetchone():
    raise HTTPException(409,'Este computador já está vinculado a outra conta. Contate o suporte.')
   c.execute('INSERT INTO customers(email,device_hash) VALUES(%s,%s)',(str(req.email).lower(),req.device))
   u=user(c,req.email)
  if not u:raise HTTPException(404,'Conta não encontrada')
  if req.kind=='lifetime':
   if not req.device or u['device_hash']!=req.device:raise HTTPException(409,'Computador diferente do registrado. Contate o suporte.')
   if u['status']=='lifetime':return {'ok':True,'status':'lifetime'}
   pending=c.execute("SELECT id FROM customer_requests WHERE customer_id=%s AND request_type='lifetime' AND status='pending' LIMIT 1",(u['id'],)).fetchone()
   if pending:return {'ok':True,'status':'pending'}
  c.execute('INSERT INTO customer_requests(customer_id,request_type,note) VALUES(%s,%s,%s)',(u['id'],req.kind,req.note[:500]))
 return {'ok':True,'status':'pending'}

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
  if key is None:raise HTTPException(503,'Assinatura de licenças não configurada')
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

# Portal access is intentionally separate from device licensing.
# Never grant access solely because an email exists.
class PortalEmail(BaseModel):
 email:EmailStr
class PortalVerify(BaseModel):
 email:EmailStr
 code:str=Field(min_length=6,max_length=12)
 password:str=Field(min_length=12,max_length=128)
def eligible(c,email):
 return bool(c.execute("""SELECT 1 FROM legacy_imports WHERE lower(email)=lower(%s)
 AND original_plan='lifetime' AND original_status='active'
 AND (expires_at IS NULL OR expires_at>now()) AND review_status='approved' LIMIT 1""",(email,)).fetchone())
def password_digest(password,salt=None):
 salt=salt or secrets.token_bytes(16)
 digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1)
 return base64.b64encode(salt+digest).decode()
def password_check(password,stored):
 try:
  raw=base64.b64decode(stored);return hmac.compare_digest(base64.b64decode(password_digest(password,raw[:16]))[16:],raw[16:])
 except (ValueError,TypeError):return False
def send_code(email,code):
 host=os.environ.get('SMTP_HOST');user=os.environ.get('SMTP_USER');password=os.environ.get('SMTP_PASSWORD')
 sender=os.environ.get('SMTP_FROM')
 if not all((host,user,password,sender)):raise HTTPException(503,'Envio de e-mails ainda não configurado')
 msg=EmailMessage();msg['Subject']='Seu código FIRE BLAZE';msg['From']=sender;msg['To']=email
 msg.set_content('Seu código de confirmação é: '+code+'\\nExpira em 10 minutos. Não compartilhe.')
 try:
  with smtplib.SMTP(host,int(os.environ.get('SMTP_PORT','587')),timeout=10) as smtp:
   smtp.starttls(context=ssl.create_default_context());smtp.login(user,password);smtp.send_message(msg)
 except Exception:raise HTTPException(503,'Serviço de e-mail indisponível')
class ManualGrant(BaseModel):
 email:EmailStr
 payment_checked:bool=False
@app.post('/api/admin/approve-legacy')
def approve_legacy(req:ManualGrant,authorization:str|None=Header(None)):
 auth(authorization)
 if not req.payment_checked:raise HTTPException(400,'Confirme o pagamento antes de aprovar')
 email=str(req.email).lower().strip()
 with db() as c:
  rows=c.execute("""UPDATE legacy_imports SET review_status='approved'
  WHERE lower(email)=%s AND original_plan='lifetime' AND original_status='active'
  AND (expires_at IS NULL OR expires_at>now()) RETURNING legacy_license_id""",(email,)).fetchall()
  if not rows:raise HTTPException(404,'Nenhuma licença vitalícia ativa encontrada')
  audit(c,'legacy_approved',{'email':email,'count':len(rows)})
 return {'ok':True,'licenses':len(rows)}
@app.post('/api/admin/manual-code')
def manual_code(req:PortalEmail,authorization:str|None=Header(None)):
 auth(authorization)
 email=str(req.email).lower().strip()
 with db() as c:
  if not eligible(c,email):raise HTTPException(403,'Aprove a licença vitalícia antes de emitir código')
  code=str(secrets.randbelow(90000000)+10000000)
  digest=hashlib.sha256((email+':'+code).encode()).hexdigest()
  c.execute("""INSERT INTO portal_manual_codes(email,code_hash,expires_at,attempts)
  VALUES(%s,%s,now()+interval '24 hours',0)
  ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash,expires_at=excluded.expires_at,attempts=0""",(email,digest))
  audit(c,'manual_code_created',{'email':email})
 return {'email':email,'code':code,'expires_in_hours':24}
@app.post('/api/portal/check-email')
def portal_check(req:PortalEmail):
 email=str(req.email).lower().strip()
 with db() as c:
  if not eligible(c,email):return {'next':'purchase'}
  existing=c.execute('SELECT 1 FROM portal_accounts WHERE email=%s AND password_hash IS NOT NULL',(email,)).fetchone()
  return {'next':'login' if existing else 'verify'}
@app.post('/api/portal/request-code')
def portal_request(req:PortalEmail):
 email=str(req.email).lower().strip()
 with db() as c:
  if not eligible(c,email):
   return {'ok':True,'next':'purchase','message':'Não há licença vitalícia aprovada para este e-mail.'}
  prior=c.execute('SELECT sent_at FROM portal_verifications WHERE email=%s',(email,)).fetchone()
  if prior and (time.time()-prior['sent_at'].timestamp())<90:raise HTTPException(429,'Aguarde antes de solicitar outro código')
  code=f'{secrets.randbelow(1000000):06d}'
  send_code(email,code)
  digest=hashlib.sha256((email+':'+code).encode()).hexdigest()
  c.execute("""INSERT INTO portal_verifications(email,code_hash,expires_at,attempts,sent_at)
  VALUES(%s,%s,now()+interval '10 minutes',0,now())
  ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash,expires_at=excluded.expires_at,
  attempts=0,sent_at=now()""",(email,digest))
 return {'ok':True,'next':'verify','message':'Código enviado para seu e-mail.'}
@app.post('/api/portal/create-password')
def portal_create(req:PortalVerify):
 email=str(req.email).lower().strip()
 with db() as c:
  if not eligible(c,email):raise HTTPException(403,'Licença não autorizada')
  v=c.execute('SELECT * FROM portal_verifications WHERE email=%s FOR UPDATE',(email,)).fetchone()
  manual=False
  if not v:
   v=c.execute('SELECT * FROM portal_manual_codes WHERE email=%s FOR UPDATE',(email,)).fetchone()
   manual=bool(v)
  if not v or v['expires_at'].timestamp()<time.time() or v['attempts']>=5:raise HTTPException(403,'Código expirado ou bloqueado')
  c.execute('UPDATE '+('portal_manual_codes' if manual else 'portal_verifications')+' SET attempts=attempts+1 WHERE email=%s',(email,))
  if not hmac.compare_digest(v['code_hash'],hashlib.sha256((email+':'+req.code).encode()).hexdigest()):
   raise HTTPException(403,'Código inválido')
  c.execute("""INSERT INTO portal_accounts(email,password_hash,email_verified_at) VALUES(%s,%s,now())
  ON CONFLICT(email) DO UPDATE SET password_hash=excluded.password_hash,email_verified_at=now()""",(email,password_digest(req.password)))
  c.execute('DELETE FROM portal_verifications WHERE email=%s',(email,))
  c.execute('DELETE FROM portal_manual_codes WHERE email=%s',(email,))
 return {'ok':True}
class PortalLogin(BaseModel):
 email:EmailStr
 password:str
@app.post('/api/portal/login')
def portal_login(req:PortalLogin,response:Response):
 email=str(req.email).lower().strip()
 with db() as c:
  account=c.execute('SELECT password_hash FROM portal_accounts WHERE email=%s',(email,)).fetchone()
  if not account or not eligible(c,email) or not password_check(req.password,account['password_hash']):
   raise HTTPException(401,'Credenciais inválidas ou licença não autorizada')
  token=secrets.token_urlsafe(40)
  c.execute("INSERT INTO portal_sessions(token_hash,email,expires_at) VALUES(%s,%s,now()+interval '7 days')",(hashlib.sha256(token.encode()).hexdigest(),email))
 response.set_cookie('fb_session',token,httponly=True,secure=True,samesite='lax',max_age=604800,path='/api/portal')
 return {'ok':True}
@app.get('/api/portal/me')
def portal_me(request:Request):
 token=request.cookies.get('fb_session','')
 if not token:raise HTTPException(401,'Faça login')
 with db() as c:
  sess=c.execute('SELECT email FROM portal_sessions WHERE token_hash=%s AND expires_at>now()',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
  if not sess or not eligible(c,sess['email']):raise HTTPException(401,'Sessão inválida')
  return {'email':sess['email'],'plan':'lifetime','status':'active'}
@app.post('/api/portal/logout')
def portal_logout(request:Request,response:Response):
 token=request.cookies.get('fb_session','')
 if token:
  with db() as c:c.execute('DELETE FROM portal_sessions WHERE token_hash=%s',(hashlib.sha256(token.encode()).hexdigest(),))
 response.delete_cookie('fb_session',path='/api/portal')
 return {'ok':True}
app.mount('/',StaticFiles(directory=str(Path(__file__).parent / 'site'),html=True),name='site')
