# Final scrape city list: City, Country, Place ID. Row order = rough priority (not shown).
import pandas as pd
exec(open('place_lookup.py',encoding='utf-8').read().split("rows=[]")[0])  # look(), ALT, CTY, a
ALT.update({'palma':['palma','palma de mallorca'],'ibiza':['ibiza','eivissa'],'dusseldorf':['dusseldorf','duesseldorf'],
 'frankfurt':['frankfurt','frankfurt am main'],'nuremberg':['nuremberg','nurnberg'],'ho chi minh city':['ho chi minh city','ho chi minh'],
 'cusco':['cusco','cuzco'],'antigua guatemala':['antigua guatemala','antigua'],'reykjavik':['reykjavik']})
CTY.update({'vietnam':['vietnam','viet nam']})
old=pd.read_csv('place_ids.csv',encoding='utf-8')
exec(open('build_list.py',encoding='utf-8').read().split("p=pd.read_csv")[0].split("ORDER = ")[0])
ORDER=eval(open('build_list.py',encoding='utf-8').read().split("ORDER = ")[1].split("\np=")[0])
T2_ADD=[('Palma','Spain',None),('Palm Springs','United States','CA'),('Key West','United States','FL'),('Charleston','United States','SC'),
 ('Anaheim','United States','CA'),('San Antonio','United States','TX'),('Hanoi','Vietnam',None),('Ho Chi Minh City','Vietnam',None),
 ('Punta Cana','Dominican Republic',None),('Puerto Vallarta','Mexico',None),('Cabo San Lucas','Mexico',None),('Reykjavik','Iceland',None),
 ('Dubrovnik','Croatia',None)]
T3_ADD=[('Ibiza','Spain',None),('Ocean City','United States','MD'),('Santa Barbara','United States','CA'),('Savannah','United States','GA'),
 ('Scottsdale','United States','AZ'),('Salt Lake City','United States','UT'),('Monterey','United States','CA'),('Virginia Beach','United States','VA'),
 ('Montauk','United States','NY'),('Nantucket','United States','MA'),('Düsseldorf','Germany',None),('Frankfurt','Germany',None),
 ('Nantes','France',None),('Bilbao','Spain',None),('Liverpool','United Kingdom',None),('Rotterdam','Netherlands',None),('Leipzig','Germany',None),
 ('Biarritz','France',None),('Nuremberg','Germany',None),('Split','Croatia',None),('Santorini','Greece',None),('Mykonos','Greece',None),
 ('Amalfi','Italy',None),('Da Nang','Vietnam',None),('Manila','Philippines',None),('Cebu City','Philippines',None),('Auckland','New Zealand',None),
 ('Queenstown','New Zealand',None),('La Fortuna','Costa Rica',None),('San José','Costa Rica',None),('Tamarindo','Costa Rica',None),
 ('Santo Domingo','Dominican Republic',None),('Montego Bay','Jamaica',None),('Antigua Guatemala','Guatemala',None),('Lima','Peru',None),
 ('Cusco','Peru',None),('Oaxaca','Mexico',None),('Cartagena','Colombia',None),('Kuala Lumpur','Malaysia',None),('Taipei','Taiwan',None),
 ('Brisbane','Australia',None),('Gold Coast','Australia',None)]
base=old.set_index('city')
rows=[]
for i,c in enumerate(ORDER):
    r=base.loc[c]; rows.append((c,r.country,r.place_id))
    if i+1==52:
        for c2,k,s in T2_ADD: rows.append((c2,k,look(c2,k,s)[1]))
for c2,k,s in T3_ADD: rows.append((c2,k,look(c2,k,s)[1]))
out=pd.DataFrame(rows,columns=['City','Country','Place ID'])
out['Place ID']=out['Place ID'].fillna('').replace('','to resolve')
f=r'C:\Users\fintan.creedon\code\exploration\abnb\docs\abnb_scrape_city_list_v2.xlsx'
with pd.ExcelWriter(f,engine='openpyxl') as w:
    out.to_excel(w,sheet_name='Scrape cities',index=False)
    ws=w.sheets['Scrape cities']; ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
    for L,wd in zip('ABC',(22,22,32)): ws.column_dimensions[L].width=wd
print(len(out), (out['Place ID']=='to resolve').sum())
print(out[out['Place ID']=='to resolve'].City.tolist())
