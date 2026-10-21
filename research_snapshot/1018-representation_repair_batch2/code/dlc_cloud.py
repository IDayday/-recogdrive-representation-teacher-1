"""Explicit per-profile ACS3 authentication; credential values never leave memory."""
import datetime as dt,hashlib,hmac,json,os,urllib.error,urllib.parse,urllib.request,uuid

def credential(profile):
    auth=profile['auth'];kind=auth['kind']
    try:
        if kind=='instance_role':
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(os.environ[auth.get('uri_env','ALIBABA_CLOUD_CREDENTIALS_URI')],timeout=15) as response:value=json.load(response)
            value=value.get('Credentials',value)
        elif kind=='environment':
            value=dict(AccessKeyId=os.environ[auth['id_env']],AccessKeySecret=os.environ[auth['secret_env']])
            if auth.get('token_env'):value['SecurityToken']=os.environ[auth['token_env']]
        elif kind=='json_file':
            with open(os.environ[auth['path_env']]) as stream:value=json.load(stream)
            value=value.get('Credentials',value)
            value={k:value.get(k,value.get(other)) for k,other in [('AccessKeyId','access_key_id'),('AccessKeySecret','access_key_secret'),('SecurityToken','security_token')]}
        else:raise ValueError('Unsupported credential provider')
        assert value['AccessKeyId'] and value['AccessKeySecret'];return value
    except Exception as error:raise RuntimeError('Credential provider failed: '+type(error).__name__) from None

def request(profile,service,version,action,method,path,query=None,payload=None):
    credentials=credential(profile);host=f"{service}.{profile['region']}.aliyuncs.com"
    body=b'' if payload is None else json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
    content_hash=hashlib.sha256(body).hexdigest();headers={
        'host':host,'x-acs-action':action,'x-acs-version':version,
        'x-acs-date':dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'x-acs-signature-nonce':str(uuid.uuid4()),'x-acs-content-sha256':content_hash}
    if credentials.get('SecurityToken'):headers['x-acs-security-token']=credentials['SecurityToken']
    if payload is not None:headers['content-type']='application/json'
    signed=';'.join(sorted(headers));canonical_headers=''.join(f'{k}:{headers[k].strip()}\n' for k in sorted(headers))
    quote=lambda value:urllib.parse.quote(str(value),safe='-_.~')
    canonical_path='/'.join(quote(piece) for piece in path.split('/'))
    qs='&'.join(f'{quote(k)}={quote(v)}' for k,v in sorted((query or {}).items()))
    canonical='\n'.join([method,canonical_path,qs,canonical_headers,signed,content_hash])
    string_to_sign='ACS3-HMAC-SHA256\n'+hashlib.sha256(canonical.encode()).hexdigest()
    signature=hmac.new(credentials['AccessKeySecret'].encode(),string_to_sign.encode(),hashlib.sha256).hexdigest()
    headers['Authorization']=f"ACS3-HMAC-SHA256 Credential={credentials['AccessKeyId']},SignedHeaders={signed},Signature={signature}"
    req=urllib.request.Request('https://'+host+canonical_path+('?' +qs if qs else ''),
        data=body if payload is not None else None,headers=headers,method=method)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req,timeout=60) as response:return json.load(response)
    except urllib.error.HTTPError as error:
        try:value=json.loads(error.read());safe={k:value[k] for k in ['Code','Message','RequestId'] if k in value}
        except Exception:safe=dict(status=error.code)
        message=json.dumps(safe,ensure_ascii=False)
        for value in credentials.values():
            if isinstance(value,str) and len(value)>4:message=message.replace(value,'[credential redacted]')
        raise RuntimeError(message) from None
    except Exception as error:raise RuntimeError('Cloud transport failed: '+type(error).__name__) from None
