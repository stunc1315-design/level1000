cache = get_cached_signal_data()

df = cache["df"]

return {
    "ok": True,
    "status": (
        "READY"
        if df is not None and not df.empty
        else "NO_DATA"
    ),

    "historical_total":
        cache["total"],

    "historical_buy":
        cache["buy"],

    "historical_sell":
        cache["sell"],

    "historical_hold":
        cache["hold"],

    "strong_signals":
        cache["buy"] + cache["sell"],

    "top":
        cache["buy"] + cache["sell"],

    "min_score":
        MIN_SIGNAL_SCORE,

    "plan":
        "OPEN",

    "plan_level":
        999999,

    "plan_limit":
        999999,

    "plan_features":
        PUBLIC_PLAN,

    "signal_file": (
        cache["path"].name
        if cache["path"]
        else None
    ),

    "live_prices": True,

    "live_price_cache_seconds":
        LIVE_PRICE_CACHE_SECONDS,

    "price_source":
        "Yahoo Finance / yfinance",
}