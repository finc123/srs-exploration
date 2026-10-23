# Candidate scrape cities: (city, country label for Airbnb query, lat, lon, tier, region)
INTL = [
 # tier 1: global gateways / big Airbnb hotel supply / top panel countries
 ('Paris','France',48.8566,2.3522,1),('London','United Kingdom',51.5072,-0.1276,1),('Rome','Italy',41.9028,12.4964,1),
 ('Barcelona','Spain',41.3874,2.1686,1),('Tokyo','Japan',35.6762,139.6503,1),('Mexico City','Mexico',19.4326,-99.1332,1),
 ('Madrid','Spain',40.4168,-3.7038,1),('Amsterdam','Netherlands',52.3676,4.9041,1),('Lisbon','Portugal',38.7223,-9.1393,1),
 ('Milan','Italy',45.4642,9.1900,1),('Toronto','Canada',43.6532,-79.3832,1),('Cancún','Mexico',21.1619,-86.8515,1),
 # tier 2
 ('Florence','Italy',43.7696,11.2558,2),('Venice','Italy',45.4408,12.3155,2),('Berlin','Germany',52.5200,13.4050,2),
 ('Prague','Czechia',50.0755,14.4378,2),('Vienna','Austria',48.2082,16.3738,2),('Budapest','Hungary',47.4979,19.0402,2),
 ('Athens','Greece',37.9838,23.7275,2),('Dublin','Ireland',53.3498,-6.2603,2),('Edinburgh','United Kingdom',55.9533,-3.1883,2),
 ('Istanbul','Türkiye',41.0082,28.9784,2),('Seoul','South Korea',37.5665,126.9780,2),('Bangkok','Thailand',13.7563,100.5018,2),
 ('Singapore','Singapore',1.3521,103.8198,2),('Sydney','Australia',-33.8688,151.2093,2),('Montreal','Canada',45.5019,-73.5674,2),
 ('Vancouver','Canada',49.2827,-123.1207,2),('San Juan','Puerto Rico',18.4655,-66.1057,2),('Dubai','United Arab Emirates',25.2048,55.2708,2),
 ('Kyoto','Japan',35.0116,135.7681,2),('Osaka','Japan',34.6937,135.5023,2),('Tulum','Mexico',20.2114,-87.4654,2),
 ('Melbourne','Australia',-37.8136,144.9631,2),('Buenos Aires','Argentina',-34.6037,-58.3816,2),('Rio de Janeiro','Brazil',-22.9068,-43.1729,2),
 # tier 3
 ('Munich','Germany',48.1351,11.5820,3),('Porto','Portugal',41.1579,-8.6291,3),('Seville','Spain',37.3891,-5.9845,3),
 ('Nice','France',43.7102,7.2620,3),('Naples','Italy',40.8518,14.2681,3),('Valencia','Spain',39.4699,-0.3763,3),
 ('Málaga','Spain',36.7213,-4.4214,3),('Copenhagen','Denmark',55.6761,12.5683,3),('Brussels','Belgium',50.8503,4.3517,3),
 ('Zurich','Switzerland',47.3769,8.5417,3),('Lyon','France',45.7640,4.8357,3),('Montpellier','France',43.6108,3.8767,3),
 ('Marseille','France',43.2965,5.3698,3),('Stockholm','Sweden',59.3293,18.0686,3),('Hong Kong','Hong Kong',22.3193,114.1694,3),
 ('Bali','Indonesia',-8.4095,115.1889,3),('Cape Town','South Africa',-33.9249,18.4241,3),('Marrakesh','Morocco',31.6295,-7.9811,3),
 ('Playa del Carmen','Mexico',20.6296,-87.0739,3),('Medellín','Colombia',6.2476,-75.5658,3),('Mumbai','India',19.0760,72.8777,3),
 ('New Delhi','India',28.6139,77.2090,3),
]
US = [ # top 30 US by Hotel room + Room confirmations (Oct-25..Sep-26), + Honolulu (Hawaii absent from scrape)
 ('New York City','NY',40.7128,-74.0060),('Chicago','IL',41.8781,-87.6298),('San Francisco','CA',37.7749,-122.4194),
 ('Orlando','FL',28.5384,-81.3789),('Las Vegas','NV',36.1699,-115.1398),('Miami Beach','FL',25.7907,-80.1300),
 ('Philadelphia','PA',39.9526,-75.1652),('San Diego','CA',32.7157,-117.1611),('New Orleans','LA',29.9511,-90.0715),
 ('Atlanta','GA',33.7490,-84.3880),('Los Angeles','CA',34.0522,-118.2437),('Houston','TX',29.7604,-95.3698),
 ('Kissimmee','FL',28.2920,-81.4076),('Washington','DC',38.9072,-77.0369),('Austin','TX',30.2672,-97.7431),
 ('Miami','FL',25.7617,-80.1918),('Seattle','WA',47.6062,-122.3321),('Nashville','TN',36.1627,-86.7816),
 ('Boston','MA',42.3601,-71.0589),('Charlotte','NC',35.2271,-80.8431),('Denver','CO',39.7392,-104.9903),
 ('Dallas','TX',32.7767,-96.7970),('Jacksonville','FL',30.3322,-81.6557),('Portland','OR',45.5152,-122.6784),
 ('Newark','NJ',40.7357,-74.1724),('Fort Lauderdale','FL',26.1224,-80.1373),('Cambridge','MA',42.3736,-71.1097),
 ('Baltimore','MD',39.2904,-76.6122),('San Jose','CA',37.3382,-121.8863),('Pittsburgh','PA',40.4406,-79.9959),
 ('Honolulu','HI',21.3069,-157.8583),
]
