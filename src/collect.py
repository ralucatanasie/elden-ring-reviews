# Collect Elden Ring reviews from Steam

import json
import time
from pathlib import Path

import pandas as pd
import requests

app_id = 1245620
url = "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"
n_negative = 5000
pause = 1 

output_file = Path(__file__).parent.parent / "data" / "raw" / "reviews.csv"

base_params = {
    "appid": app_id,
    "filter": 1,
    "languages": ["english"],
    "purchase_type": 1,
    "num_per_page": 100,
}


def get_page(query):
    for attempt in range(5):
        try:
            r = requests.get(url, params={"input_json": json.dumps(query)}, timeout=30)
            if r.status_code == 429:
                print("rate limited, waiting 1 min")
                time.sleep(60)
                continue
            r.raise_for_status()
            return r.json()["response"]
        except Exception as e:
            print("error, retrying:", e)
            time.sleep(5)
    raise RuntimeError("request failed 5 times")


def make_row(review):
    author = review["author"]
    hours_at_review = round(author["playtime_at_review"] / 60, 1)
    hours_total = round(author["playtime_forever"] / 60, 1)

    return {
        "recommendationid": review["recommendationid"],
        "review": review["review"],
        "voted_up": review["voted_up"],
        "timestamp_created": review["timestamp_created"],
        "timestamp_updated": review["timestamp_updated"],
        "edited": review["timestamp_updated"] > review["timestamp_created"],
        "review_words": len(review["review"].split()),
        "votes_up": review["votes_up"],
        "votes_funny": review["votes_funny"],
        "comment_count": review["comment_count"],
        "steam_purchase": review["steam_purchase"],
        "primarily_steam_deck": review["primarily_steam_deck"],
        "refunded": review["refunded"],
        "num_reviews": author["num_reviews"],
        "hours_at_review": hours_at_review,
        "hours_total": hours_total,
        "hours_after_review": round(hours_total - hours_at_review, 1),
        "hours_last_two_weeks": round(author["playtime_last_two_weeks"] / 60, 1),
        "still_playing": author["playtime_last_two_weeks"] > 0,
        "last_played": author["last_played"],
    }


def get_reviews(review_type, how_many, start=None, end=None):
    rows = []
    seen = set()
    cursor = "*"

    while len(rows) < how_many:
        query = dict(base_params)
        query["review_type"] = review_type
        query["cursor"] = cursor
        if start is not None:
            query["date_range_start"] = start
            query["date_range_end"] = end

        response = get_page(query)
        page = response.get("reviews", [])
        if len(page) == 0:
            break

        for review in page:
            #skip duplicates and reviews with no text
            if review["recommendationid"] in seen or not review["review"].strip():
                continue
            seen.add(review["recommendationid"])
            rows.append(make_row(review))

        new_cursor = response.get("cursor")
        if not new_cursor or new_cursor == cursor:
            break
        cursor = new_cursor
        time.sleep(pause)

    return rows[:how_many]


#negative
print("getting negatives...")
negative = pd.DataFrame(get_reviews(2, n_negative))
print("got", len(negative), "negatives")

#how many neg/month
months = pd.to_datetime(negative["timestamp_created"], unit="s").dt.to_period("M")
per_month = months.value_counts().sort_index()

#for each month, get the same nr pos
print("getting positives per month...")
positive = []
for month, count in per_month.items():
    start = int(month.start_time.timestamp())
    end = int(month.end_time.timestamp())
    batch = get_reviews(1, count, start, end)
    print(f"{month}: {count} neg, {len(batch)} pos")
    positive += batch

#combine
df = pd.concat([negative, pd.DataFrame(positive)]).drop_duplicates(subset="recommendationid")
df.to_csv(output_file, index=False)

print(f"done, saved {len(df)} rows x {df.shape[1]} cols")
print(df["voted_up"].value_counts())