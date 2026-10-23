import pandas as pd, glob, re, sys
src=open(r'C:\Users\fintan.creedon\code\exploration\abnb\hotels\output\top_cities\build_top_cities.py',encoding='utf-8').read()
exec(src.split("df['country'] =")[0].replace("df = pd.read_parquet('ted_raw_city_acc.parquet')",''))  # STATES, NYC_BOROUGH, clean
PROV={'ALBERTA':'AB','BRITISH COLUMBIA':'BC','MANITOBA':'MB','NEW BRUNSWICK':'NB','NEWFOUNDLAND AND LABRADOR':'NL','NOVA SCOTIA':'NS','ONTARIO':'ON','PRINCE EDWARD ISLAND':'PE','QUEBEC':'QC','SASKATCHEWAN':'SK','YUKON':'YT'}
a=pd.concat([pd.read_csv(f,encoding='utf-8').assign(scan=f[-14:-4]) for f in sorted(glob.glob('city_place/*.csv'))])
a=a[a.scan<='2026-10-05']  # production scans only (10-19 = Will's new 60k list)
a['first']=~a.duplicated(['scan','user_input','country'])
def parse(q):
    p=[x.strip() for x in str(q).split(',')]
    if len(p)<2 or p[-1] not in('United States','Canada'): return None
    cc='US' if p[-1]=='United States' else 'CA'
    st=clean(p[-2]) if len(p)>=3 else '*'
    st={'WASHINGTON DC':'DC','DISTRICT OF COLUMBIA':'DC'}.get(st,(STATES if cc=='US' else PROV).get(st,st))
    city=clean(p[0])
    if cc=='US' and st=='NY' and city in NYC_BOROUGH: city='NEW YORK CITY'
    return (cc,st,city.title() if city!='NEW YORK CITY' else 'New York City')
a['key']=a['query'].map(parse)
a=a.dropna(subset=['key'])
latest=a[a.scan=='2026-10-05']
sets={'latest_first':set(latest[latest['first']].key),'latest_any':set(latest.key),'all_first':set(a[a['first']].key),'all_any':set(a.key)}
t=pd.read_csv(r'C:\Users\fintan.creedon\code\exploration\abnb\hotels\output\top_cities\top_cities_all.csv')
t=t[t.country.isin(['US','CA'])&(t.city!='(no city)')].sort_values('confirmations',ascending=False).reset_index(drop=True)
t['k']=list(zip(t.country,t.state,t.city))
tot=t.confirmations.sum(); toth=t.conf_hotel_or_room.sum()
def hit(k,s): return k in s or (k[0],'*',k[2]) in s
for n,s in sets.items():
    t[n]=t.k.map(lambda k: hit(k,s))
    print(n,len(s),'| top25/50/100/200:',[int(t.head(k)[n].sum()) for k in (25,50,100,200)],'| conf cov %.1f%%, hotel+room cov %.1f%%'%(100*t.confirmations[t[n]].sum()/tot,100*t.conf_hotel_or_room[t[n]].sum()/toth))
t['rank']=t.index+1
m=t[~t.all_any].head(40)
print(m[['rank','country','state','city','confirmations','conf_hotel_or_room']].to_string(index=False))
print('covered in top 40:',t.head(40)[t.head(40).all_any][['rank','city','state']].to_string(index=False))
t.drop(columns='k').to_csv('vendor_city_coverage.csv',index=False)
