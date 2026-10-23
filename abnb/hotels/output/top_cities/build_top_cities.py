# Builds the top_cities CSVs from ted_raw_city_acc.parquet (= result of top_cities_ted.sql). Run from this folder.
import re, unicodedata, pandas as pd
OUT = r"C:\Users\fintan.creedon\code\exploration\abnb\hotels\output\top_cities"
df = pd.read_parquet('ted_raw_city_acc.parquet')

STATES = {'ALABAMA':'AL','ALASKA':'AK','ARIZONA':'AZ','ARKANSAS':'AR','CALIFORNIA':'CA','COLORADO':'CO','CONNECTICUT':'CT','DELAWARE':'DE',
 'DISTRICT OF COLUMBIA':'DC','FLORIDA':'FL','GEORGIA':'GA','HAWAII':'HI','IDAHO':'ID','ILLINOIS':'IL','INDIANA':'IN','IOWA':'IA','KANSAS':'KS',
 'KENTUCKY':'KY','LOUISIANA':'LA','MAINE':'ME','MARYLAND':'MD','MASSACHUSETTS':'MA','MICHIGAN':'MI','MINNESOTA':'MN','MISSISSIPPI':'MS',
 'MISSOURI':'MO','MONTANA':'MT','NEBRASKA':'NE','NEVADA':'NV','NEW HAMPSHIRE':'NH','NEW JERSEY':'NJ','NEW MEXICO':'NM','NEW YORK':'NY',
 'NORTH CAROLINA':'NC','NORTH DAKOTA':'ND','OHIO':'OH','OKLAHOMA':'OK','OREGON':'OR','PENNSYLVANIA':'PA','RHODE ISLAND':'RI',
 'SOUTH CAROLINA':'SC','SOUTH DAKOTA':'SD','TENNESSEE':'TN','TEXAS':'TX','UTAH':'UT','VERMONT':'VT','VIRGINIA':'VA','WASHINGTON':'WA',
 'WEST VIRGINIA':'WV','WISCONSIN':'WI','WYOMING':'WY','PUERTO RICO':'PR','VIRGIN ISLANDS':'VI'}
COUNTRY = {'USA':'US','UNITED STATES':'US','CANADA':'CA','UK':'UNITED KINGDOM','PANAMÁ':'PANAMA','THE BAHAMAS':'BAHAMAS','VI':'US VIRGIN ISLANDS'}
NYC_BOROUGH = {'NEW YORK':'Manhattan','NEW YORK CITY':'Manhattan','NYC':'Manhattan','MANHATTAN':'Manhattan','HARLEM':'Manhattan',
 'BROOKLYN':'Brooklyn','BRONX':'Bronx','THE BRONX':'Bronx','STATEN ISLAND':'Staten Island','QUEENS':'Queens'}
QUEENS_NBHD = ['JAMAICA','FLUSHING','ASTORIA','LONG ISLAND CITY','FOREST HILLS','ELMHURST','EAST ELMHURST','JACKSON HEIGHTS','RIDGEWOOD',
 'WOODSIDE','SUNNYSIDE','CORONA','BAYSIDE','FAR ROCKAWAY','ARVERNE','ROCKAWAY BEACH','ROCKAWAY PARK','OZONE PARK','SOUTH OZONE PARK',
 'RICHMOND HILL','SOUTH RICHMOND HILL','REGO PARK','MASPETH','MIDDLE VILLAGE','KEW GARDENS','HOLLIS','QUEENS VILLAGE','ST ALBANS',
 'SPRINGFIELD GARDENS','ROSEDALE','CAMBRIA HEIGHTS','FRESH MEADOWS','WHITESTONE','COLLEGE POINT','HOWARD BEACH','WOODHAVEN','GLENDALE',
 'LAURELTON','LITTLE NECK','DOUGLASTON','OAKLAND GARDENS','BELLEROSE','GLEN OAKS']
for n in QUEENS_NBHD:
    NYC_BOROUGH[n] = 'Queens'
DIRS = {'N': 'NORTH ', 'S': 'SOUTH ', 'E': 'EAST ', 'W': 'WEST '}


def clean(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper()
    s = re.sub(r"[.,'\u2019]", '', s)
    s = re.sub(r'[-/]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'^SAINT ', 'ST ', s)
    s = re.sub(r'^MOUNT ', 'MT ', s)
    s = re.sub(r'^FT ', 'FORT ', s)
    s = re.sub(r'^(N|S|E|W) (?=\w{3})', lambda m: DIRS[m.group(1)], s)
    return s


df['country'] = df.country_raw.fillna('').map(lambda c: COUNTRY.get(c, c)).replace('', '(missing)')
df['state'] = df.state_raw.fillna('').map(clean).map(lambda s: STATES.get(s, s))
df['city_clean'] = df.city_raw.fillna('').map(clean)
# Fill blank state where the (country, city) maps to one dominant state (>=90% of confirmations).
k = df[(df.state != '') & (df.city_clean != '')].groupby(['country', 'city_clean', 'state']).confirmations.sum()
dom = k.groupby(level=[0, 1]).apply(lambda s: s.idxmax()[2] if s.max() / s.sum() >= 0.9 else None).dropna()
m = (df.state == '') & (df.city_clean != '')
fill = pd.Series(list(zip(df.country, df.city_clean)), index=df.index)[m].map(dom).dropna()
df['state_filled'] = df.index.isin(fill.index)
df.loc[fill.index, 'state'] = fill

PROVINCES = {'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT'}
# 'CANADA' with no province = non-Canadian places (Dominican Rep., Costa Rica, South Africa, Jamaica...) mislabelled by the parser.
df.loc[(df.country == 'CA') & ~df.state.isin(PROVINCES), 'country'] = 'NON-CA (labelled CANADA, no province)'
# City field holding only a state code (e.g. 'NC', 'FL') or a country name -> no city.
df.loc[df.city_clean.isin(set(STATES.values()) | {'UKRAINE', 'USA', 'UNITED STATES', 'CANADA'}), 'city_clean'] = ''

nyc = (df.country == 'US') & (df.state == 'NY') & df.city_clean.isin(NYC_BOROUGH)
df['nyc_borough'] = df.city_clean.map(NYC_BOROUGH).where(nyc, '')
df['city'] = df.city_clean.str.title().where(~nyc, 'New York City').replace('', '(no city)')
df['is_hotel_or_room'] = df.accommodation_type.isin(['Hotel room', 'Room'])
df['is_hotel_room'] = df.accommodation_type.eq('Hotel room')
KEY = ['country', 'state', 'city']


def agg(d):
    out = d.groupby(KEY).agg(confirmations=('confirmations', 'sum'), nights=('nights', 'sum'),
                             conf_with_nights=('confirmations_with_nights', 'sum')).reset_index()
    hr = d[d.is_hotel_or_room].groupby(KEY).agg(conf_hotel_or_room=('confirmations', 'sum'), nights_hotel_or_room=('nights', 'sum'))
    h = d[d.is_hotel_room].groupby(KEY).agg(conf_hotel_room_only=('confirmations', 'sum'))
    out = out.merge(hr, on=KEY, how='left').merge(h, on=KEY, how='left').fillna(0)
    sp = d.assign(r=d.city_raw.fillna('') + '|' + d.state_raw.fillna('')).groupby(KEY + ['r']).confirmations.sum().reset_index()
    sp = sp.sort_values('confirmations', ascending=False).groupby(KEY).r.apply(lambda x: '; '.join(x.head(10))).rename('raw_spellings')
    out = out.merge(sp, on=KEY, how='left')
    for c in ['confirmations', 'nights', 'conf_with_nights', 'conf_hotel_or_room', 'nights_hotel_or_room', 'conf_hotel_room_only']:
        out[c] = out[c].astype(int)
    out['hotel_or_room_share'] = (out.conf_hotel_or_room / out.confirmations).round(4)
    return out


def rank(d, by):
    d = d.sort_values([by, 'confirmations'], ascending=False).reset_index(drop=True)
    d.insert(0, 'rank', d.index + 1)
    return d


total_all = df.confirmations.sum()
total_hr = df[df.is_hotel_or_room].confirmations.sum()
cities = agg(df[df.city != '(no city)'])
all_rank = rank(cities, 'confirmations')
us_rank = rank(cities[cities.country == 'US'], 'confirmations')
hr_rank = rank(cities[cities.conf_hotel_or_room > 0], 'conf_hotel_or_room')
nights_rank = rank(cities, 'nights')
all_rank.to_csv(f'{OUT}/top_cities_all.csv', index=False)
us_rank.to_csv(f'{OUT}/top_cities_us.csv', index=False)
hr_rank.to_csv(f'{OUT}/top_cities_hotel_or_room.csv', index=False)

nb = df[df.nyc_borough != ''].groupby('nyc_borough').confirmations.sum().to_frame().join(
    df[(df.nyc_borough != '') & df.is_hotel_or_room].groupby('nyc_borough').confirmations.sum().rename('conf_hotel_or_room')
).sort_values('confirmations', ascending=False)
nb.to_csv(f'{OUT}/nyc_borough_split.csv')

ctry = df.groupby('country').agg(confirmations=('confirmations', 'sum'), nights=('nights', 'sum')).join(
    df[df.city != '(no city)'].groupby('country').confirmations.sum().rename('conf_with_city')).join(
    df[df.is_hotel_or_room].groupby('country').confirmations.sum().rename('conf_hotel_or_room')).fillna(0).astype(int).sort_values('confirmations', ascending=False)
ctry['share_of_all'] = (ctry.confirmations / total_all).round(4)
ctry['city_coverage'] = (ctry.conf_with_city / ctry.confirmations).round(3)
ctry['hotel_or_room_share'] = (ctry.conf_hotel_or_room / ctry.confirmations).round(3)
ctry.to_csv(f'{OUT}/countries.csv')

rows = []
for name, d, col, denoms in [
    ('all types, all countries', all_rank, 'confirmations',
     {'all_confirmations': total_all, 'city_identified': cities.confirmations.sum(), 'us_ca': df[df.country.isin(['US', 'CA'])].confirmations.sum()}),
    ('all types, US only', us_rank, 'confirmations',
     {'us_total': df[df.country == 'US'].confirmations.sum(), 'us_city_identified': us_rank.confirmations.sum()}),
    ('Hotel room + Room, all countries', hr_rank, 'conf_hotel_or_room',
     {'all_hotel_or_room': total_hr, 'city_identified': hr_rank.conf_hotel_or_room.sum()}),
    ('nights, all types, all countries', nights_rank, 'nights',
     {'all_nights': df.nights.sum(), 'city_identified': cities.nights.sum()})]:
    for n in [25, 50, 100, 200, 500, 1000, 2000]:
        r = {'ranking': name, 'top_n': n, 'covered': int(d[col].head(n).sum())}
        for k_, v in denoms.items():
            r[f'pct_of_{k_}'] = round(100 * r['covered'] / v, 1)
        rows.append(r)
cov = pd.DataFrame(rows)
cov.to_csv(f'{OUT}/coverage_curves.csv', index=False)

pd.set_option('display.width', 250); pd.set_option('display.max_columns', 20)
cols = ['rank', 'country', 'state', 'city', 'confirmations', 'nights', 'conf_hotel_or_room', 'conf_hotel_room_only', 'hotel_or_room_share']
print(f'total {total_all:,}; hotel_or_room {total_hr:,}; city identified {cities.confirmations.sum():,}; distinct cities {len(cities):,}; '
      f'state-filled conf {df[df.state_filled].confirmations.sum():,}')
print(all_rank[cols].head(30).to_string(index=False))
print(us_rank[cols].head(30).to_string(index=False))
print(hr_rank[cols].head(30).to_string(index=False))
print(nights_rank[cols].head(15).to_string(index=False))
print(nb); print(ctry.head(25)); print(cov.to_string(index=False))
