-- Zillow mortgage job postings per month (Revelio Indeed). The table is a full snapshot; BATCH_ID dates the load.
select LEFT(post_date, 7) as post_month, COUNT(DISTINCT job_id) as job_count, MAX(batch_id) as batch_id
from SRS_MCP.REVELIO.INDEED_JOB_POSTINGS
where regexp_like(company, '.*zillow.*', 'i')
and regexp_like(title_raw, '.*mortgage.*', 'i')
group by LEFT(post_date, 7)
order by LEFT(post_date, 7) desc
