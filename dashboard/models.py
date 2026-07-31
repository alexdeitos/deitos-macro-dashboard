from django.db import models


class CollectionRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Executando"
        SUCCESS = "success", "Sucesso"
        PARTIAL = "partial", "Parcial"
        FAILED = "failed", "Falhou"

    task_id = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    source_status = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Coleta {self.pk} - {self.status}"


class MarketSnapshot(models.Model):
    collected_at = models.DateTimeField(db_index=True)
    payload = models.JSONField(default=dict)
    source_status = models.JSONField(default=dict)
    is_complete = models.BooleanField(default=False)
    duration_ms = models.PositiveIntegerField(default=0)
    run = models.OneToOneField(
        CollectionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="snapshot",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-collected_at"]
        indexes = [models.Index(fields=["-collected_at"], name="dashboard_m_collect_9e7df0_idx")]

    def __str__(self) -> str:
        return f"Snapshot {self.collected_at:%Y-%m-%d %H:%M:%S}"


class MarketPoint(models.Model):
    observed_at = models.DateTimeField(db_index=True)
    symbol = models.CharField(max_length=40, db_index=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=40, db_index=True)
    value = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    change_percent = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    source = models.CharField(max_length=50, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["observed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["observed_at", "symbol", "source"],
                name="unique_market_point",
            )
        ]
        indexes = [
            models.Index(fields=["symbol", "observed_at"], name="dashboard_m_symbol_eb67e1_idx"),
            models.Index(fields=["category", "observed_at"], name="dashboard_m_categor_7c896a_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} @ {self.observed_at:%Y-%m-%d %H:%M}"


class MarketNews(models.Model):
    source = models.CharField(max_length=50, default="Investing RSS", db_index=True)
    external_id = models.CharField(max_length=64, unique=True)
    title = models.TextField()
    summary = models.TextField(blank=True)
    url = models.URLField(max_length=1000)
    category = models.CharField(max_length=40, db_index=True)
    published_at = models.DateTimeField(db_index=True)
    collected_at = models.DateTimeField(auto_now_add=True)
    relevance_score = models.PositiveSmallIntegerField(default=0, db_index=True)
    win_relevance = models.PositiveSmallIntegerField(default=0)
    wdo_relevance = models.PositiveSmallIntegerField(default=0)
    markets = models.JSONField(default=list, blank=True)
    topics = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-published_at", "-id"]
        indexes = [
            models.Index(fields=["category", "-published_at"], name="dashboard_n_cat_pub_idx"),
            models.Index(fields=["relevance_score", "-published_at"], name="dashboard_n_rel_pub_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.category}: {self.title[:80]}"


class EconomicEvent(models.Model):
    external_id = models.CharField(max_length=64, unique=True)
    event_at = models.DateTimeField(db_index=True)
    country = models.CharField(max_length=80, db_index=True)
    country_code = models.CharField(max_length=4, db_index=True)
    category = models.CharField(max_length=100, blank=True, db_index=True)
    event = models.CharField(max_length=320)
    reference = models.CharField(max_length=60, blank=True)
    importance = models.PositiveSmallIntegerField(default=1, db_index=True)
    actual = models.CharField(max_length=80, blank=True)
    previous = models.CharField(max_length=80, blank=True)
    revised = models.CharField(max_length=80, blank=True)
    consensus = models.CharField(max_length=80, blank=True)
    forecast = models.CharField(max_length=80, blank=True)
    url = models.URLField(max_length=1000, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    collected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event_at", "-importance", "country_code"]
        indexes = [
            models.Index(fields=["event_at", "country_code"], name="dashboard_e_at_country_idx"),
            models.Index(fields=["importance", "event_at"], name="dashboard_e_imp_at_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.country_code} {self.event_at:%Y-%m-%d %H:%M} - {self.event}"


class TradingAccount(models.Model):
    name = models.CharField(max_length=120, unique=True)
    broker = models.CharField(max_length=120, blank=True)
    initial_capital = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_default = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "name"]

    def __str__(self) -> str:
        return self.name


class TradeSetup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class CapitalMovement(models.Model):
    class Kind(models.TextChoices):
        DEPOSIT = "deposit", "Aporte"
        WITHDRAWAL = "withdrawal", "Retirada"
        ADJUSTMENT = "adjustment", "Ajuste"

    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name="capital_movements")
    movement_date = models.DateField(db_index=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-movement_date", "-id"]
        indexes = [models.Index(fields=["account", "movement_date"], name="dashboard_cap_account_date_idx")]

    def __str__(self) -> str:
        return f"{self.account} {self.get_kind_display()} {self.amount}"

    @property
    def signed_amount(self):
        return -self.amount if self.kind == self.Kind.WITHDRAWAL else self.amount


class TradingDay(models.Model):
    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name="trading_days")
    date = models.DateField(db_index=True)
    no_trade = models.BooleanField(default=False)
    no_trade_reason = models.CharField(max_length=240, blank=True)
    premarket_notes = models.TextField(blank=True)
    opening_plan = models.TextField(blank=True)
    daily_review = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["account", "date"], name="unique_trading_day_account_date")
        ]

    def __str__(self) -> str:
        return f"{self.account} - {self.date:%d/%m/%Y}"


class Trade(models.Model):
    class Instrument(models.TextChoices):
        WIN = "WIN", "Mini índice (WIN)"
        WDO = "WDO", "Mini dólar (WDO)"
        IND = "IND", "Índice cheio (IND)"
        DOL = "DOL", "Dólar cheio (DOL)"
        STOCK = "STOCK", "Ação"
        OTHER = "OTHER", "Outro"

    class Direction(models.TextChoices):
        BUY = "BUY", "Compra"
        SELL = "SELL", "Venda"

    class NewsImpact(models.TextChoices):
        NONE = "none", "Não impactou"
        LOW = "low", "Impacto leve"
        MEDIUM = "medium", "Impacto moderado"
        HIGH = "high", "Impacto forte"
        UNKNOWN = "unknown", "Não avaliado"

    class OpeningBias(models.TextChoices):
        BUY = "buy", "Comprador"
        SELL = "sell", "Vendedor"
        NEUTRAL = "neutral", "Neutro/aguardar"
        UNKNOWN = "unknown", "Indisponível"

    class TechnicalQuality(models.TextChoices):
        FORCED = "forced", "Forçada"
        WEAK = "weak", "Fraca"
        VALID = "valid", "Válida"
        EXCELLENT = "excellent", "Excelente"
        UNRATED = "unrated", "Não avaliada"

    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name="trades")
    trade_date = models.DateField(db_index=True)
    entry_time = models.TimeField()
    exit_time = models.TimeField(null=True, blank=True)
    instrument = models.CharField(max_length=12, choices=Instrument.choices, db_index=True)
    symbol = models.CharField(max_length=40, blank=True)
    setup = models.ForeignKey(TradeSetup, on_delete=models.SET_NULL, null=True, blank=True, related_name="trades")
    setup_label = models.CharField(max_length=120, blank=True, db_index=True)
    direction = models.CharField(max_length=8, choices=Direction.choices, db_index=True)
    contracts = models.PositiveIntegerField(default=1)
    entry_price = models.DecimalField(max_digits=16, decimal_places=4)
    exit_price = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    point_value = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    planned_stop_points = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    mae_points = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    mfe_points = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    fees = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    financial_result_override = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    screenshot = models.FileField(upload_to="trade_screenshots/%Y/%m/", blank=True)
    screenshot_url = models.URLField(max_length=1000, blank=True)
    technical_reading = models.TextField(blank=True)
    execution_notes = models.TextField(blank=True)
    emotions_before = models.JSONField(default=list, blank=True)
    emotions_after = models.JSONField(default=list, blank=True)
    discipline_score = models.PositiveSmallIntegerField(default=0)
    technical_quality = models.CharField(
        max_length=16, choices=TechnicalQuality.choices, default=TechnicalQuality.UNRATED, db_index=True
    )
    followed_plan = models.BooleanField(null=True, blank=True, db_index=True)
    mistakes = models.JSONField(default=list, blank=True)
    had_relevant_news = models.BooleanField(default=False, db_index=True)
    news_impact = models.CharField(max_length=12, choices=NewsImpact.choices, default=NewsImpact.UNKNOWN, db_index=True)
    news_notes = models.TextField(blank=True)
    linked_event = models.ForeignKey(
        EconomicEvent, on_delete=models.SET_NULL, null=True, blank=True, related_name="trades"
    )
    opening_bias = models.CharField(
        max_length=12, choices=OpeningBias.choices, default=OpeningBias.UNKNOWN, db_index=True
    )
    opening_score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    opening_matched = models.BooleanField(null=True, blank=True, db_index=True)
    opening_notes = models.TextField(blank=True)
    market_snapshot = models.ForeignKey(
        MarketSnapshot, on_delete=models.SET_NULL, null=True, blank=True, related_name="trades"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-trade_date", "-entry_time", "-id"]
        indexes = [
            models.Index(fields=["account", "trade_date", "entry_time"], name="trade_acc_date_time_idx"),
            models.Index(fields=["setup_label", "trade_date"], name="trade_setup_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.trade_date:%d/%m/%Y} {self.instrument} {self.get_direction_display()}"

    @staticmethod
    def default_point_value(instrument: str):
        from decimal import Decimal

        return {
            "WIN": Decimal("0.20"),
            "WDO": Decimal("10.00"),
            "IND": Decimal("1.00"),
            "DOL": Decimal("50.00"),
            "STOCK": Decimal("1.00"),
            "OTHER": Decimal("1.00"),
        }.get(instrument, Decimal("1.00"))

    def save(self, *args, **kwargs):
        if not self.point_value:
            self.point_value = self.default_point_value(self.instrument)
        if self.setup and not self.setup_label:
            self.setup_label = self.setup.name
        super().save(*args, **kwargs)


class TradeExit(models.Model):
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name="partial_exits")
    exit_time = models.TimeField(null=True, blank=True)
    contracts = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=16, decimal_places=4)
    fees = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["exit_time", "id"]

    def __str__(self) -> str:
        return f"Saída {self.contracts} @ {self.price}"
