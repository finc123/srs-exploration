-- Inv 3 spend cohorts: read-only Snowflake queries (run via .cache/q.py, local connector). Outputs cached in gta/.cache/.

-- 1) merchant scan: gaming-related merchants, 31 Jul 2024 - 24 Jun 2026 (exploration only)
select merchant_name, count(*) n, count(distinct mailbox_id) mb, sum(item_price*coalesce(item_quantity,1)) usd, median(item_price) med
from share_niq.srs.items_extended
where order_date between '2024-07-31' and '2026-06-24'
  and (merchant_name ilike any ('%sony%','%microsoft%','%xbox%','%playstation%','%steam%','%nintendo%','%roblox%','%rockstar%','%gamestop%',
        '%epic%','%valve%','%blizzard%','%ea %','%electronic arts%','%ubisoft%','%riot%','%twitch%','%humble%','%gog%','%fanatical%',
        '%green man%','%cdkeys%','%eneba%','%g2a%','%activision%','%take-two%','%2k%','%bethesda%','%square enix%','%bandai%','%sega%',
        '%capcom%','%battle.net%','%minecraft%','%mojang%','%fortnite%','%supercell%','%apple%','%google play%','%meta%','%oculus%','%valve%')
       or merchant_name in ('Origin','Epic Games','Steam'))
group by 1 order by n desc limit 120
;

-- 2) .cache/inv3_rows.parquet
-- gaming-merchant rows for 6_12_12 panel mailboxes, 31 Jul 2024 - 24 Jun 2026 (covers BF6 and GTA VI 12-month windows)
select t.mailbox_id, t.merchant_name, t.order_id, t.order_date, hash(t.description) h,
       t.item_price, t.item_quantity, t.order_total, t.digital_good
from share_niq.srs.items_extended t
join share_niq.srs.active_panel_users p on p.mailbox_id = t.mailbox_id and p.active_panel = '6_12_12_Month_Aging'
where t.order_date between '2024-07-31' and '2026-06-24'
  and t.merchant_name in ('Sony Entertainment Network','Microsoft store','Steam','Nintendo','Epic Games','Roblox','Rockstar Games',
        'GameStop','Sony','Origin','Riot Games','Blizzard Entertainment','Ubisoft','Green Man Gaming','GOG.com','Humble Bundle','Square Enix','Minecraft',
        'Sony Entertainment Network Cancellation','Microsoft store Cancellation','Steam Cancellation','Nintendo Cancellation','Roblox Cancellation',
        'Epic Games Cancellation','GameStop Cancellation')
;

-- 3) .cache/inv3_desc.parquet (description dictionary, joined on merchant_name + hash(description))
select t.merchant_name, hash(t.description) h, any_value(t.description) description, count(*) n, count(distinct t.mailbox_id) n_mb,
       median(t.item_price) med_price, min(t.item_price) min_price, max(t.item_price) max_price, count_if(t.item_price=0) n_zero, count_if(t.item_price is null) n_null
from share_niq.srs.items_extended t
join share_niq.srs.active_panel_users p on p.mailbox_id = t.mailbox_id and p.active_panel = '6_12_12_Month_Aging'
where t.order_date between '2024-07-31' and '2026-06-24'
  and t.merchant_name in ('Sony Entertainment Network','Microsoft store','Steam','Nintendo','Epic Games','Roblox','Rockstar Games',
        'GameStop','Sony','Origin','Riot Games','Blizzard Entertainment','Ubisoft','Green Man Gaming','GOG.com','Humble Bundle','Square Enix','Minecraft',
        'Sony Entertainment Network Cancellation','Microsoft store Cancellation','Steam Cancellation','Nintendo Cancellation','Roblox Cancellation',
        'Epic Games Cancellation','GameStop Cancellation')
group by 1,2
;

-- Also reused (built earlier): rows.parquet / desc_cls.parquet (notes/console_owners.sql), gta6.parquet (.cache/q_gta.sql),
-- bf6.parquet (.cache/q_bf6.sql), store_mb.parquet (.cache/q_store_mb.sql), mailboxes.parquet (.cache/q_mb.sql).
