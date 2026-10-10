WITH reviews AS (
    SELECT *
    FROM {{ ref('int_reviews_clean') }}
    WHERE quality_status = 'clean'
),

sentiment_scored AS (
    SELECT
        *,
        CASE sentiment
            WHEN 'positive' THEN 4.5
            WHEN 'neutral'  THEN 3.0
            WHEN 'negative' THEN 1.5
        END AS sentiment_score
    FROM reviews
),

topic_counts AS (
    SELECT
        business_id,
        primary_topic,
        COUNT(*) AS topic_count,
        ROW_NUMBER() OVER (
            PARTITION BY business_id
            ORDER BY COUNT(*) DESC
        ) AS topic_rank
    FROM reviews
    GROUP BY 1, 2
)

SELECT
    r.business_id,
    COUNT(*)                                                            AS total_reviews,
    ROUND(AVG(r.stars), 2)                                             AS avg_stars,
    ROUND(AVG(r.intensity), 2)                                         AS avg_intensity,
    ROUND(AVG(IFF(r.sentiment = 'positive', 1, 0)) * 100, 1) AS pct_positive,
    ROUND(AVG(IFF(r.sentiment = 'negative', 1, 0)) * 100, 1) AS pct_negative,
    ROUND(AVG(IFF(r.sentiment = 'neutral', 1, 0)) * 100, 1) AS pct_neutral,
    ROUND(AVG(IFF(r.is_local_regular = TRUE, 1, 0)) * 100, 1) AS pct_local_regulars,
    ROUND(AVG(r.stars) - AVG(r.sentiment_score), 2)                   AS sentiment_stars_gap,
    t.primary_topic                                                     AS top_topic
FROM sentiment_scored r
LEFT JOIN topic_counts t
    ON r.business_id = t.business_id AND t.topic_rank = 1
GROUP BY r.business_id, t.primary_topic
HAVING COUNT(*) > 5