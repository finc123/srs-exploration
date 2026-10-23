SELECT from_addr, REGEXP_REPLACE(subject,'[0-9]','#') s, COUNT(*) n_subj FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAIL_HEADER
WHERE domain='openai' AND subject ILIKE ANY ('%receipt%','%renew%','%invoice%','%payment%','%subscription%','%plus%','%plan%','%charge%','%billing%','%cancel%','%trial%')
GROUP BY 1,2 ORDER BY 3 DESC LIMIT 60
