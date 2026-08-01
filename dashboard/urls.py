from django.urls import path

from . import diary_views, views

app_name = "dashboard"

urlpatterns = [
    path("", views.index, name="index"),
    path("validacao/", views.validation, name="validation"),
    path("diario/", diary_views.trade_diary, name="trade_diary"),
    path("diario/prints/<int:trade_id>/", diary_views.trade_screenshot, name="trade_screenshot"),
    path("api/dashboard/", views.api_dashboard, name="api_dashboard"),
    path("api/refresh/", views.api_refresh, name="api_refresh"),
    path("api/news/", views.api_news, name="api_news"),
    path("api/news/refresh/", views.api_refresh_news, name="api_refresh_news"),
    path("api/calendar/", views.api_calendar, name="api_calendar"),
    path("api/calendar/refresh/", views.api_refresh_calendar, name="api_refresh_calendar"),
    path("api/tasks/<str:task_id>/", views.api_task_status, name="api_task_status"),
    path("api/raw/", views.api_raw_snapshot, name="api_raw_snapshot"),
    path("api/trade/accounts/", diary_views.api_trade_accounts, name="api_trade_accounts"),
    path("api/trade/accounts/<int:account_id>/", diary_views.api_trade_account_detail, name="api_trade_account_detail"),
    path("api/trade/setups/", diary_views.api_trade_setups, name="api_trade_setups"),
    path("api/trade/trades/", diary_views.api_trades, name="api_trades"),
    path("api/trade/trades/<int:trade_id>/", diary_views.api_trade_detail, name="api_trade_detail"),
    path("api/trade/context/", diary_views.api_trade_context, name="api_trade_context"),
    path("api/trade/day/", diary_views.api_trading_day, name="api_trading_day"),
    path("api/trade/analytics/", diary_views.api_trade_analytics, name="api_trade_analytics"),
    path("api/trade/capital/", diary_views.api_capital_movements, name="api_capital_movements"),
    path("api/trade/capital/<int:movement_id>/", diary_views.api_capital_movement_detail, name="api_capital_movement_detail"),
    path("health/", views.health, name="health"),
    path(
        "api/public-market-snapshot/",
        views.api_public_market_snapshot,
        name="api_public_market_snapshot",
    ),
]
