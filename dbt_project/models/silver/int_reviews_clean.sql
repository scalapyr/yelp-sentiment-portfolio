WITH base AS (
    SELECT * FROM {{ ref('stg_reviews') }}
),

cleaned AS (
    SELECT
        review_id,
        business_id,
        user_id,
        stars::INT                                      AS stars,
        TO_TIMESTAMP_NTZ(date / 1000000000)::DATE       AS review_date,
        LOWER(COALESCE(sentiment, 'neutral'))           AS sentiment,
        COALESCE(primary_topic, 'unknown')              AS primary_topic,
        COALESCE(intensity::INT, 3)                     AS intensity,
        COALESCE(is_local_regular::BOOLEAN, FALSE)      AS is_local_regular,
        -- parse secondary_topics from JSON string if stored as varchar
        TRY_PARSE_JSON(secondary_topics)                AS secondary_topics,
        -- quality flag must check raw nulls BEFORE coalesce
        CASE
            WHEN sentiment IS NULL
                OR primary_topic IS NULL         THEN 'flagged_incomplete'
            WHEN stars IS NULL
                OR stars NOT BETWEEN 1 AND 5     THEN 'flagged_invalid_rating'
            ELSE 'clean'
        END AS quality_status
    FROM base
)

SELECT * FROM cleaned