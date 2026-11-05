-- Every weekly vintage of the last 8 Zillow months (same window as the portal export): fill curves + chain-ladder factors.
SELECT ENTITY, MONTH, CAPTURE_TIMESTAMP, TOTAL_LOANS_VOLUME
FROM BOTS.Z.LOAN_VOLUME_VINTAGES
WHERE ENTITY = 'Z'
  AND MONTH >= TO_CHAR(DATEADD('month', -8, CURRENT_DATE), 'YYYY-MM')
ORDER BY MONTH, CAPTURE_TIMESTAMP
