-- Quarterly reported + consensus volume (Visible Alpha) as joined by the portal backtest view.
SELECT ENTITY, PERIOD, IS_CURRENT, REPORTED_VOLUME, CONSENSUS_VOLUME
FROM BOTS.Z.LOAN_VOLUME_BACKTEST
WHERE ENTITY = 'Z'
ORDER BY PERIOD
