import q, pandas as pd
s = pd.read_parquet('supra_subj.parquet')
ids = ",".join("'" + x.replace("'", "''") + "'" for x in s.SUBJECT_ID)
out = []
for y in range(2018, 2027):
    sql = f"""select e.mailbox_id, e.subject_id, min(e.email_sent_date) first_date, count(*) n
              from share_niq.srs.supra_quality_merchant_emails e
              where e.email_sent_date between '{y}-01-01' and '{y}-12-31'
                and e.subject_id in ({ids})
              group by 1,2"""
    df = q.q(sql); df['YEAR'] = y; out.append(df); print(y, len(df), flush=True)
pd.concat(out).to_parquet('supra_mb.parquet')
