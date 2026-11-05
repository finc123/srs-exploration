-- Latest vintage of each Zillow month (same view the Cotality portal export reads).
SELECT ENTITY, MONTH, TOTAL_LOANS_VOLUME, CAPTURE_TIMESTAMP
FROM BOTS.Z.LOAN_VOLUME_MONTHLY_LATEST
WHERE ENTITY = 'Z'
ORDER BY MONTH
