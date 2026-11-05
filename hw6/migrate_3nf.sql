-- HW6: move the data from the HW5 table `requests` into the 3NF tables.
-- (normalize.py empties the three new tables first, so this can be re-run.)

-- 1. one row per country; is_banned comes from the HW5 rows of that country
INSERT INTO country (country_name, is_banned)
SELECT country, MAX(is_banned)
FROM requests
WHERE country IS NOT NULL
GROUP BY country;

-- 2. one row per IP with the country it was seen with. If an IP was ever seen with
--    more than one country (only possible for hand-made test requests), the most
--    frequent non-NULL country wins; check_3nf.sql reports how many such IPs exist.
INSERT INTO client_ip (client_ip, country_id)
SELECT x.client_ip, c.country_id
FROM (
    SELECT client_ip, country,
           ROW_NUMBER() OVER (PARTITION BY client_ip
                              ORDER BY (country IS NULL), COUNT(*) DESC, country) AS rn
    FROM requests
    WHERE client_ip IS NOT NULL
    GROUP BY client_ip, country
) AS x
LEFT JOIN country AS c ON c.country_name = x.country
WHERE x.rn = 1;

-- 3. the requests themselves, without the transitively-dependent columns
INSERT INTO request (request_id, received_at, client_ip, gender, age_group, income_group,
                     client_time, requested_file, status_code)
SELECT request_id, received_at, client_ip, gender, age_group, income_group,
       client_time, requested_file, status_code
FROM requests;
