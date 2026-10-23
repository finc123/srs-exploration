-- NIQ main feed (TED): Airbnb Order Confirmations, emails sent 2025-10-01..2026-09-30, aggregated to raw city x accommodation_type.
WITH oc AS (
  SELECT
    message_id,
    email_attributes:reservation:reservation_number::STRING                          AS reservation_number,
    UPPER(TRIM(email_attributes:reservation:hotel_address:country::STRING))         AS country_raw,
    TRIM(email_attributes:reservation:hotel_address:state::STRING)                  AS state_raw,
    TRIM(email_attributes:reservation:hotel_address:city::STRING)                   AS city_raw,
    TRIM(email_attributes:reservation:accommodation_type::STRING)                   AS accommodation_type,
    -- nights: 'stay_duration' ("3 nights", template C from Nov-2025); else checkout-checkin from "Mon D" strings
    COALESCE(
      TRY_TO_NUMBER(REGEXP_SUBSTR(email_attributes:reservation:stay_duration::STRING, '^\s*(\d+)\s+night', 1, 1, 'ie', 1)),
      IFF(TRY_TO_DATE(email_attributes:reservation:checkin_date::STRING || ' 2000', 'MON DD YYYY') IS NOT NULL
          AND TRY_TO_DATE(email_attributes:reservation:checkout_date::STRING || ' 2000', 'MON DD YYYY') IS NOT NULL,
          MOD(DATEDIFF(day, TRY_TO_DATE(email_attributes:reservation:checkin_date::STRING || ' 2001', 'MON DD YYYY'),
                            TRY_TO_DATE(email_attributes:reservation:checkout_date::STRING || ' 2001', 'MON DD YYYY')) + 365, 365),
          NULL)
    ) AS nights
  FROM share_niq.srs.transaction_email_details
  WHERE merchant_name = 'AirBnB'
    AND email_sent_time >= '2025-10-01' AND email_sent_time < '2026-10-01'
    AND email_attributes:reservation:email_type::STRING = 'confirmation'
    AND email_attributes:reservation:order_status::STRING = 'confirmed'
)
SELECT country_raw, state_raw, city_raw, accommodation_type,
       COUNT(*)                            AS confirmations,
       COUNT(DISTINCT reservation_number)  AS distinct_reservations,
       SUM(IFF(nights BETWEEN 1 AND 180, nights, NULL))   AS nights,
       COUNT_IF(nights BETWEEN 1 AND 180)  AS confirmations_with_nights
FROM oc
GROUP BY ALL;
