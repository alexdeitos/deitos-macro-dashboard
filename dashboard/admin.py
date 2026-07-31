from django.contrib import admin

from .models import CollectionRun, EconomicEvent, MarketNews, MarketPoint, MarketSnapshot


@admin.register(CollectionRun)
class CollectionRunAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "started_at", "finished_at", "task_id")
    list_filter = ("status",)
    search_fields = ("task_id", "error")


@admin.register(MarketSnapshot)
class MarketSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "collected_at", "is_complete", "duration_ms")
    list_filter = ("is_complete",)
    date_hierarchy = "collected_at"


@admin.register(MarketPoint)
class MarketPointAdmin(admin.ModelAdmin):
    list_display = ("symbol", "value", "change_percent", "source", "observed_at")
    list_filter = ("category", "source")
    search_fields = ("symbol", "name")
    date_hierarchy = "observed_at"


@admin.register(MarketNews)
class MarketNewsAdmin(admin.ModelAdmin):
    list_display = ("published_at", "category", "relevance_score", "title", "source")
    list_filter = ("category", "source")
    search_fields = ("title", "summary", "url")
    date_hierarchy = "published_at"
    ordering = ("-published_at",)


@admin.register(EconomicEvent)
class EconomicEventAdmin(admin.ModelAdmin):
    list_display = ("event_at", "country_code", "importance", "event", "actual", "consensus", "previous")
    list_filter = ("country_code", "importance", "category")
    search_fields = ("event", "country", "category")
    date_hierarchy = "event_at"
    ordering = ("event_at",)

from .models import CapitalMovement, Trade, TradeExit, TradeSetup, TradingAccount, TradingDay


class TradeExitInline(admin.TabularInline):
    model = TradeExit
    extra = 0


@admin.register(TradingAccount)
class TradingAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "broker", "initial_capital", "is_default", "is_active", "updated_at")
    list_filter = ("is_default", "is_active")
    search_fields = ("name", "broker")


@admin.register(TradeSetup)
class TradeSetupAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")


@admin.register(TradingDay)
class TradingDayAdmin(admin.ModelAdmin):
    list_display = ("date", "account", "no_trade", "updated_at")
    list_filter = ("no_trade", "account")
    search_fields = ("no_trade_reason", "premarket_notes", "opening_plan", "daily_review")
    date_hierarchy = "date"


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("trade_date", "entry_time", "account", "instrument", "direction", "setup_label", "contracts", "opening_matched", "had_relevant_news")
    list_filter = ("account", "instrument", "direction", "technical_quality", "had_relevant_news", "opening_matched", "followed_plan")
    search_fields = ("symbol", "setup_label", "technical_reading", "execution_notes")
    date_hierarchy = "trade_date"
    inlines = [TradeExitInline]


@admin.register(CapitalMovement)
class CapitalMovementAdmin(admin.ModelAdmin):
    list_display = ("movement_date", "account", "kind", "amount", "description")
    list_filter = ("account", "kind")
    date_hierarchy = "movement_date"
