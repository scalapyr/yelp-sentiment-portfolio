SELECT
    r.review_id,
    r.business_id,
    r.user_id,
    r.stars,
    r.text,
    r.date,
    e.sentiment,
    e.primary_topic,
    e.secondary_topics,
    e.intensity,
    e.is_local_regular
FROM 
    {{ source('raw', 'raw_reviews') }} r 
JOIN 
    {{ source('raw', 'raw_reviews_enriched') }} e 
ON 
    r.review_id = e.review_id