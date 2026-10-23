SELECT from_addr, REGEXP_REPLACE(subject,'[0-9]','#') s, COUNT(*) n_subj FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAIL_HEADER
WHERE domain='google' AND (subject ILIKE ANY ('%google ai %','%gemini%','%ai premium%','%google one%') ) AND subject ILIKE ANY ('%cancel%','%ended%','%renew%','%receipt%','%payment%','%subscription%','%welcome%','%expire%','%will end%')
GROUP BY 1,2 ORDER BY 3 DESC LIMIT 40
