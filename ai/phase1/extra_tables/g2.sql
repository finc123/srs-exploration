SELECT from_addr, REGEXP_REPLACE(REGEXP_REPLACE(subject,'[0-9]','#'),'(ChatGPT|Claude|Gemini|Google One|Grok|Perplexity|Google AI Pro|X)','<P>') s, COUNT(*) n_subj FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAIL_HEADER
WHERE domain='google' AND from_addr ILIKE ANY ('googleplay%','googleone%','payments-noreply%') AND subject ILIKE ANY ('%chatgpt%','%claude%','%gemini%','%google one%','%google ai%','%grok%','%perplexity%','%muse%','%anthropic%','%openai%')
GROUP BY 1,2 ORDER BY 3 DESC LIMIT 40
