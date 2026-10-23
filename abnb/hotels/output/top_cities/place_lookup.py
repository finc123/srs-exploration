import pandas as pd, unicodedata, re
exec(open('city_list.py',encoding='utf-8').read())
src=open(r'C:\Users\fintan.creedon\code\exploration\abnb\hotels\output\top_cities\build_top_cities.py',encoding='utf-8').read()
exec(src[src.index('STATES = {'):src.index('COUNTRY = {')])
ST_FULL={v:k.title() for k,v in STATES.items()}; ST_FULL['DC']='District of Columbia'
def n(s): return re.sub(r'\s+',' ',unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower().replace('.','')).strip()
ALT={'rome':['roma'],'milan':['milano'],'mexico city':['ciudad de mexico','mexico city'],'lisbon':['lisboa'],'prague':['praha'],
     'vienna':['wien'],'munich':['munchen'],'florence':['firenze'],'venice':['venezia'],'naples':['napoli'],'seville':['sevilla'],
     'marrakesh':['marrakech'],'new york city':['new york'],'washington':['washington dc','washington'],'brussels':['bruxelles'],
     'copenhagen':['kobenhavn'],'athens':['athina'],'zurich':['zuerich']}
CTY={'czechia':['czechia','czech republic'],'turkiye':['turkiye','turkey'],'united kingdom':['united kingdom','uk'],
     'united arab emirates':['united arab emirates','uae'],'united states':['united states','usa'],'hong kong':['hong kong','hong kong sar']}
a=pd.read_parquet('all_places.parquet')
a['segs']=a['query'].astype(str).str.split(',').map(lambda p:[n(x) for x in p])
def look(city,country,state=None):
    names=[n(city)]+ALT.get(n(city),[]); cts=CTY.get(n(country),[n(country)])
    m=a[a.segs.map(lambda s: s[0] in names and (s[-1] in cts or (len(s)==1 and n(country)==s[0])))]
    if state: m=m[m.segs.map(lambda s: len(s)>=3 and s[-2] in (n(ST_FULL[state]),n(state)) or (state=='DC' and len(s)>=3 and s[-2] in ('washington dc','district of columbia')))]
    if not len(m): return '',''
    m=m.assign(L=m.segs.map(len)).sort_values(['L','scan'],ascending=[True,False])
    r=m.iloc[0]; return r['query'],r['place_id']
rows=[]
for c,k,*_ in INTL: rows.append((c,k,None)+look(c,k))
for c,s,*_ in US: rows.append((c,'United States',s)+look(c,'United States',s))
p=pd.DataFrame(rows,columns=['city','country','state','vendor_query','place_id'])
p.to_csv('place_ids.csv',index=False,encoding='utf-8')
print(p.to_string())
