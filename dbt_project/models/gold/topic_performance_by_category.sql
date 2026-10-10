WITH reviews AS (
    SELECT
        c.*,
        b.categories,
        b.name AS business_name
    FROM {{ ref('int_reviews_clean') }} c
    LEFT JOIN {{ source('raw', 'raw_businesses') }} b
        ON c.business_id = b.business_id
    WHERE quality_status = 'clean'
)

SELECT
    categories,
    primary_topic,
    COUNT(*)                                                        AS review_count,
    ROUND(AVG(stars), 2)                                            AS avg_stars,
    ROUND(AVG(intensity), 2)                                        AS avg_intensity,
    ROUND(COUNT_IF(sentiment = 'positive') / COUNT(*) * 100, 1)    AS pct_positive
FROM reviews
GROUP BY 1, 2
HAVING COUNT(*) > 20
ORDER BY 1, review_count DESC