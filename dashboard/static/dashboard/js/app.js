(() => {
    "use strict";

    const API_URL = "/api/dashboard/";
    const REFRESH_URL = "/api/refresh/";

    const PLOT_CONFIG = {
        responsive: true,
        displaylogo: false,
        modeBarButtonsToRemove: ["lasso2d", "select2d"],
    };

    const PLOT_LAYOUT = {
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: {
            color: "#cbd5e1",
        },
        margin: {
            l: 55,
            r: 20,
            t: 20,
            b: 45,
        },
        xaxis: {
            gridcolor: "#233652",
        },
        yaxis: {
            gridcolor: "#233652",
        },
        legend: {
            orientation: "h",
            y: 1.12,
        },
    };

    const byId = (id) => document.getElementById(id);

    /**
     * Converte números vindos da API sem transformar percentuais
     * em categorias no Plotly.
     *
     * Formatos aceitos:
     * - 1.25
     * - "1.25"
     * - "1,25"
     * - "+1,25%"
     * - "-1,25%"
     * - "1.234,56"
     * - "1,234.56"
     * - "−1,25%" com sinal negativo Unicode
     */
    function toNumeric(value) {
        if (
            value === null ||
            value === undefined ||
            value === ""
        ) {
            return null;
        }

        if (typeof value === "number") {
            return Number.isFinite(value) ? value : null;
        }

        let normalized = String(value)
            .trim()
            .replace(/[\u00A0\s%]/g, "")
            .replace(/[−–—]/g, "-")
            .replace(/^\+/, "");

        if (!normalized) {
            return null;
        }

        const comma = normalized.lastIndexOf(",");
        const dot = normalized.lastIndexOf(".");

        if (comma !== -1 && dot !== -1) {
            /*
             * Quando existem ponto e vírgula, o separador que aparece
             * por último é considerado o separador decimal.
             *
             * Exemplos:
             * 1.234,56 -> 1234.56
             * 1,234.56 -> 1234.56
             */
            normalized = comma > dot
                ? normalized
                    .replace(/\./g, "")
                    .replace(",", ".")
                : normalized.replace(/,/g, "");
        } else if (comma !== -1) {
            /*
             * Exemplo:
             * 1,25 -> 1.25
             */
            normalized = normalized.replace(",", ".");
        }

        const numeric = Number(normalized);

        return Number.isFinite(numeric)
            ? numeric
            : null;
    }

    function validTimestamp(value) {
        return Boolean(value) &&
            Number.isFinite(Date.parse(value));
    }

    function csrfToken() {
        const item = document.cookie
            .split(";")
            .map((value) => value.trim())
            .find((value) => value.startsWith("csrftoken="));

        return item
            ? decodeURIComponent(
                item.split("=").slice(1).join("=")
            )
            : "";
    }

    function number(value, decimals = 2) {
        const numeric = toNumeric(value);

        if (numeric === null) {
            return "N/D";
        }

        return numeric.toLocaleString("pt-BR", {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
    }

    function percent(value, decimals = 2) {
        const numeric = toNumeric(value);

        if (numeric === null) {
            return "N/D";
        }

        return `${numeric > 0 ? "+" : ""}${number(
            numeric,
            decimals
        )}%`;
    }

    function showMessage(text, type = "warning") {
        const node = byId("message");

        if (!node) {
            return;
        }

        node.hidden = !text;
        node.className = `message ${type}`;
        node.textContent = text;
    }

    function renderQuote(symbol, quote, decimals = 2) {
        const valueNode = byId(`q${symbol}`);
        const changeNode = byId(`c${symbol}`);

        if (!valueNode || !changeNode) {
            return;
        }

        const value = toNumeric(quote?.value);

        if (value === null) {
            valueNode.textContent = "N/D";
            changeNode.textContent =
                quote?.source || "Fonte indisponível";
            changeNode.className = "";
            return;
        }

        valueNode.textContent = number(value, decimals);

        const change = toNumeric(
            quote?.change_percent
        );

        const source =
            quote?.source || "fonte não identificada";

        changeNode.textContent = change === null
            ? source
            : `${percent(change)} · ${source}`;

        changeNode.className = change > 0
            ? "positive"
            : change < 0
                ? "negative"
                : "";
    }

    let latestRealEurUsdParity = null;

    function calculateFrp0Parity() {
        const input = byId("frp0Input");
        const result = byId("frp0Result");

        if (!input || !result) {
            return;
        }

        const frp0 = toNumeric(input.value);

        result.className = "frp0-result";

        if (frp0 === null) {
            result.textContent = "Informe um FRP0 válido";
            result.classList.add("error");
            return;
        }

        if (latestRealEurUsdParity === null) {
            result.textContent = "Paridade indisponível";
            result.classList.add("error");
            return;
        }

        /*
         * A paridade é exibida como cotação (ex.: 5,1629), mas o FRP0
         * informado pelo usuário está na escala de pontos do dólar futuro.
         * Portanto, convertemos 5,1629 -> 5162,9 antes da soma.
         * Exemplo: 5162,9 + 36,80 = 5199,70.
         */
        const total = (latestRealEurUsdParity * 1000) + frp0;
        result.textContent = `Paridade + FRP0: ${number(total, 2)}`;
        result.classList.add("has-value");
    }

    function bindFrp0Calculator() {
        const input = byId("frp0Input");
        const button = byId("frp0CalculateButton");

        if (!input || !button) {
            return;
        }

        button.addEventListener("click", calculateFrp0Parity);
        input.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                calculateFrp0Parity();
            }
        });
    }

    function renderWinOpeningEstimate(quotes) {
        const valueNode = byId("qWIN_OPENING");
        const detailNode = byId("cWIN_OPENING");

        if (!valueNode || !detailNode) {
            return;
        }

        const ibovClose = toNumeric(quotes?.IBOV?.value);
        const dowChange = toNumeric(quotes?.DJI?.change_percent);
        const sp500Change = toNumeric(quotes?.SP500?.change_percent);
        const nasdaqChange = toNumeric(quotes?.NASDAQ?.change_percent);

        // Driver principal: Dow Jones. S&P 500 e Nasdaq entram somente
        // como confirmações secundárias para reduzir dependência de um
        // único índice americano. Pesos somam 100%.
        const usChanges = [
            { value: dowChange, weight: 0.70 },
            { value: sp500Change, weight: 0.20 },
            { value: nasdaqChange, weight: 0.10 },
        ].filter(item => item.value !== null);

        const availableWeight = usChanges.reduce(
            (sum, item) => sum + item.weight,
            0
        );
        const weightedUsChange = availableWeight > 0
            ? usChanges.reduce(
                (sum, item) => sum + (item.value * item.weight),
                0
            ) / availableWeight
            : null;

        if (ibovClose === null || weightedUsChange === null) {
            valueNode.textContent = "N/D";
            detailNode.textContent =
                "Aguardando Ibovespa e Dow Jones (driver principal)";
            detailNode.className = "";
            return;
        }

        /*
         * Estimativa da abertura do WIN:
         * fechamento do Ibovespa ajustado por um composto das bolsas dos EUA,
         * com 70% de peso no Dow Jones, 20% no S&P 500 e 10% no Nasdaq.
         * Quando algum componente não estiver disponível, os pesos
         * disponíveis são renormalizados.
         */
        const estimatedOpening =
            ibovClose * (1 + (weightedUsChange / 100));

        valueNode.textContent = number(
            estimatedOpening,
            3
        );

        detailNode.textContent =
            `Fech. IBOV: ${number(ibovClose, 3)} · Dow: ${percent(dowChange)} · S&P: ${percent(sp500Change)} · Nasdaq: ${percent(nasdaqChange)} · Composto EUA: ${percent(weightedUsChange)}`;

        detailNode.className = weightedUsChange > 0
            ? "positive"
            : weightedUsChange < 0
                ? "negative"
                : "";
    }

    function renderQuotes(quotes) {
        renderQuote(
            "USD_BRL",
            quotes.USD_BRL,
            4
        );

        renderQuote(
            "REAL_EUR_USD_PARITY",
            quotes.REAL_EUR_USD_PARITY,
            4
        );

        latestRealEurUsdParity =
            toNumeric(quotes.REAL_EUR_USD_PARITY?.value);

        renderQuote(
            "DOL_FUT",
            quotes.DOL_FUT,
            2
        );

        renderQuote(
            "DXY",
            quotes.DXY,
            3
        );

        renderQuote(
            "IBOV",
            quotes.IBOV,
            3
        );

        renderWinOpeningEstimate(quotes);

        renderQuote(
            "EWZ",
            quotes.EWZ,
            2
        );

        renderQuote(
            "VIX",
            quotes.VIX,
            2
        );

        renderQuote(
            "BRENT",
            quotes.BRENT,
            2
        );

        renderQuote(
            "IRON_ORE",
            quotes.IRON_ORE,
            2
        );
    }

    function renderComponents(
        targetId,
        components
    ) {
        const target = byId(targetId);

        if (!target) {
            return;
        }

        if (
            !components ||
            components.length === 0
        ) {
            target.innerHTML = `
                <div class="muted">
                    Nenhum componente real disponível.
                </div>
            `;

            return;
        }

        target.innerHTML = components
            .map((item) => {
                const raw = toNumeric(
                    item.raw_change_percent ??
                    item.change_percent ??
                    item.adjusted_change_percent
                );

                const adjusted = toNumeric(
                    item.adjusted_change_percent
                );

                const inverted =
                    Number(item.orientation) === -1;

                const label =
                    item.label ||
                    item.symbol ||
                    "Componente";

                return `
                    <div class="component">
                        <span>
                            ${escapeHtml(label)}

                            <small
                                class="muted"
                                style="display:block"
                            >
                                Variação real:
                                ${percent(raw)}
                            </small>
                        </span>

                        <strong>
                            ${
                                inverted
                                    ? "Impacto no risco"
                                    : "Contribuição"
                            }:
                            ${percent(adjusted)}
                        </strong>
                    </div>
                `;
            })
            .join("");
    }

    function renderAnalysis(analysis) {
        const global =
            analysis?.global || {};

        const brazil =
            analysis?.brazil || {};

        const globalDirection =
            byId("globalDirection");

        const globalComposite =
            byId("globalComposite");

        const globalConfidence =
            byId("globalConfidence");

        const brazilDirection =
            byId("brazilDirection");

        const brazilComposite =
            byId("brazilComposite");

        const brazilConfidence =
            byId("brazilConfidence");

        if (globalDirection) {
            globalDirection.textContent =
                global.direction ||
                "indisponível";
        }

        if (globalComposite) {
            globalComposite.textContent =
                global.composite_change_percent === null ||
                global.composite_change_percent === undefined
                    ? "N/D"
                    : `Composto: ${percent(
                        global.composite_change_percent,
                        3
                    )}`;
        }

        if (globalConfidence) {
            globalConfidence.textContent =
                global.confidence?.sample_size
                    ? (
                        `Confiança ${
                            global.confidence.label
                        }; concordância ${
                            number(
                                global.confidence
                                    .agreement_percent,
                                1
                            )
                        }%; ${
                            global.confidence.sample_size
                        } sinais.`
                    )
                    : "Sem amostra suficiente.";
        }

        renderComponents(
            "globalComponents",
            global.components
        );

        if (brazilDirection) {
            brazilDirection.textContent =
                brazil.direction ||
                "indisponível";
        }

        if (brazilComposite) {
            brazilComposite.textContent =
                brazil.composite_change_percent === null ||
                brazil.composite_change_percent === undefined
                    ? "N/D"
                    : `Composto: ${percent(
                        brazil.composite_change_percent,
                        3
                    )}`;
        }

        if (brazilConfidence) {
            brazilConfidence.textContent =
                brazil.confidence?.sample_size
                    ? (
                        `Confiança ${
                            brazil.confidence.label
                        }; concordância ${
                            number(
                                brazil.confidence
                                    .agreement_percent,
                                1
                            )
                        }%; ${
                            brazil.confidence.sample_size
                        } sinais.`
                    )
                    : "Sem amostra suficiente.";
        }

        renderComponents(
            "brazilComponents",
            brazil.components
        );
    }

    function macroResultClass(score, missingComponents) {
        const numeric = toNumeric(score);
        if ((missingComponents || []).length || numeric === null) return "incomplete";
        if (Math.abs(numeric) < 1.5) return "lateral";
        return numeric > 0 ? "positive" : "negative";
    }

    function renderMacroComponents(components) {
        const target = byId("macroComponents");
        if (!target) return;

        const rows = (components || [])
            .map((item) => ({
                ...item,
                contribution: toNumeric(item.contribution),
                raw_change_percent: toNumeric(item.raw_change_percent),
            }))
            .filter((item) => item.contribution !== null);

        if (!rows.length) {
            target.innerHTML = '<div class="muted">Nenhum componente disponível.</div>';
            return;
        }

        const maxAbsolute = Math.max(
            1,
            ...rows.map((item) => Math.abs(item.contribution))
        );

        target.innerHTML = rows.map((item) => {
            const contribution = item.contribution;
            const width = Math.min(100, Math.abs(contribution) / maxAbsolute * 100);
            const sideClass = contribution > 0
                ? "positive"
                : contribution < 0
                    ? "negative"
                    : "neutral";

            return `
                <div class="macro-component-row">
                    <div class="macro-component-header">
                        <span>
                            ${escapeHtml(item.label || item.symbol)}
                            <small>Real: ${percent(item.raw_change_percent)}</small>
                        </span>
                        <strong class="${sideClass}">
                            ${contribution > 0 ? "+" : ""}${number(contribution, 2)}
                        </strong>
                    </div>
                    <div class="macro-component-track">
                        <div class="macro-component-half left"></div>
                        <div class="macro-component-half right"></div>
                        <div
                            class="macro-component-bar ${sideClass}"
                            style="${
                                contribution < 0
                                    ? `right:50%;width:${width / 2}%`
                                    : `left:50%;width:${width / 2}%`
                            }"
                        ></div>
                        <span class="macro-component-center"></span>
                    </div>
                </div>
            `;
        }).join("");
    }

    function renderMacroContext(context) {
        const target = byId("macroContext");
        if (!target) return;

        const rows = context || [];
        target.innerHTML = rows.map((item) => {
            const change = toNumeric(item.change_percent);
            const cssClass = change > 0
                ? "positive"
                : change < 0
                    ? "negative"
                    : "";
            return `
                <div class="macro-context-item">
                    <span>${escapeHtml(item.label || item.symbol)}</span>
                    <strong class="${cssClass}">${percent(change)}</strong>
                </div>
            `;
        }).join("") || '<div class="muted">Contexto indisponível.</div>';
    }

    function renderMacroOpening(macro, collectedAt) {
        const score = toNumeric(macro?.score);
        const missing = macro?.missing_components || [];
        const card = byId("macroResultCard");
        const scoreNode = byId("macroScore");
        const direction = byId("macroDirection");
        const strength = byId("macroStrength");
        const bias = byId("macroOpeningBias");
        const strategy = byId("macroStrategy");
        const formula = byId("macroFormula");
        const total = byId("macroTotal");
        const snapshot = byId("macroSnapshot");
        const missingNode = byId("macroMissing");
        const disclaimer = byId("macroDisclaimer");
        const calendar = byId("macroCalendar");

        const resultClass = macroResultClass(score, missing);
        if (card) card.className = `macro-result-card ${resultClass}`;
        if (scoreNode) {
            scoreNode.textContent = score === null
                ? "N/D"
                : `${score > 0 ? "+" : ""}${number(score, 2)}`;
        }
        if (direction) {
            direction.textContent = macro?.direction || "indisponível";
            direction.className = `pill ${
                resultClass === "positive"
                    ? "ok"
                    : resultClass === "negative"
                        ? "error"
                        : "partial"
            }`;
        }
        if (strength) {
            strength.textContent = macro?.strength || "indisponível";
            strength.className = `pill ${
                resultClass === "positive"
                    ? "ok"
                    : resultClass === "negative"
                        ? "error"
                        : "partial"
            }`;
        }
        if (bias) bias.textContent = macro?.opening_bias || "dados insuficientes";
        if (strategy) strategy.textContent = macro?.strategy || "Aguardar dados.";
        if (formula) formula.textContent = `Fórmula: ${macro?.formula || "N/D"}`;
        if (total) {
            total.textContent = score === null
                ? "N/D"
                : `${score > 0 ? "+" : ""}${number(score, 2)}`;
            total.className = score > 0 ? "positive" : score < 0 ? "negative" : "";
        }
        if (snapshot) {
            snapshot.textContent = validTimestamp(collectedAt)
                ? `Snapshot ${new Date(collectedAt).toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"})}`
                : "Horário indisponível";
            snapshot.className = `pill ${missing.length ? "partial" : "ok"}`;
        }
        if (missingNode) {
            missingNode.hidden = missing.length === 0;
            missingNode.textContent = missing.length
                ? `Cálculo macro incompleto. Componentes ausentes: ${missing.join(", ")}. Nenhum valor substituto foi usado.`
                : "";
        }
        if (disclaimer) {
            disclaimer.textContent = macro?.disclaimer || "Cálculo direcional, não probabilístico.";
        }
        if (calendar) {
            calendar.textContent = macro?.economic_calendar?.message || "Calendário visual disponível na lateral; os eventos não entram automaticamente neste cálculo.";
        }

        renderMacroComponents(macro?.components || []);
        renderMacroContext(macro?.context || []);
    }

    function openingClass(score) {
        const numeric = toNumeric(score);
        if (numeric === null || Math.abs(numeric) < 15) return "wait";
        return numeric > 0 ? "buy" : "sell";
    }

    function renderOpeningComponents(targetId, components) {
        const target = byId(targetId);
        if (!target) return;
        const rows = (components || [])
            .filter(item => toNumeric(item.contribution) !== null)
            .sort((a, b) => Math.abs(toNumeric(b.contribution) || 0) - Math.abs(toNumeric(a.contribution) || 0))
            .slice(0, 6);
        if (!rows.length) {
            target.innerHTML = '<div class="muted">Nenhum sinal disponível.</div>';
            return;
        }
        target.innerHTML = rows.map(item => {
            const contribution = toNumeric(item.contribution);
            const raw = toNumeric(item.raw_change_percent);
            return `
                <div class="component">
                    <span>${escapeHtml(item.label || item.symbol)}<small style="display:block">Real: ${percent(raw)}</small></span>
                    <strong class="${contribution > 0 ? "positive" : contribution < 0 ? "negative" : ""}">${contribution > 0 ? "+" : ""}${number(contribution, 2)} pts</strong>
                </div>`;
        }).join("");
    }

    function renderOpeningSide(prefix, data) {
        const score = toNumeric(data?.score);
        const card = byId(`${prefix}OpeningCard`);
        const bias = byId(`${prefix}Bias`);
        const scoreNode = byId(`${prefix}Score`);
        const confidence = byId(`${prefix}Confidence`);
        const action = byId(`${prefix}Action`);
        const bar = byId(`${prefix}ScoreBar`);
        if (card) card.className = `opening-card ${openingClass(score)}`;
        if (bias) bias.textContent = data?.bias || "dados insuficientes";
        if (scoreNode) scoreNode.textContent = score === null ? "N/D" : `${score > 0 ? "+" : ""}${number(score, 1)}`;
        const conf = data?.confidence || {};
        if (confidence) {
            const agreement = toNumeric(conf.agreement_percent);
            const coverage = toNumeric(conf.coverage_percent);
            confidence.textContent = `Confiança ${conf.label || "insuficiente"}; cobertura ${number(coverage, 1)}%; concordância ${agreement === null ? "N/D" : number(agreement, 1) + "%"}; ${conf.sample_size || 0} sinais.`;
        }
        if (action) action.textContent = data?.action_plan || "Aguardar confirmação no preço.";
        if (bar) {
            const clipped = score === null ? 0 : Math.max(-100, Math.min(100, score));
            bar.style.left = clipped < 0 ? `${50 + clipped / 2}%` : "50%";
            bar.style.width = `${Math.abs(clipped) / 2}%`;
        }
        renderOpeningComponents(`${prefix}OpeningComponents`, data?.components || []);
    }

    function renderOpeningAnalysis(opening, collectedAt) {
        renderOpeningSide("win", opening?.win || {});
        renderOpeningSide("wdo", opening?.wdo || {});
        const snapshot = byId("openingSnapshot");
        if (snapshot) {
            snapshot.textContent = validTimestamp(collectedAt)
                ? `Snapshot ${new Date(collectedAt).toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"})}`
                : "Horário indisponível";
        }
        const disclaimer = byId("openingDisclaimer");
        if (disclaimer) disclaimer.textContent = opening?.disclaimer || "Score direcional; não é probabilidade estatística.";
    }

    function dataItem(label, value) {
        return `
            <div class="data-item">
                <span>
                    ${escapeHtml(label)}
                </span>

                <strong>
                    ${escapeHtml(value)}
                </strong>
            </div>
        `;
    }

    function renderParity(parity) {
        const grid =
            byId("parityGrid");

        const missing =
            byId("parityMissing");

        if (!grid || !missing) {
            return;
        }

        const items = [
            [
                "Spot em pontos",
                number(
                    parity?.spot_points,
                    2
                ),
            ],
            [
                "Futuro observado",
                number(
                    parity?.future_points,
                    2
                ),
            ],
            [
                "Base observada",
                number(
                    parity?.observed_basis_points,
                    2
                ),
            ],
            [
                "PTAX oficial",
                number(
                    parity?.ptax,
                    4
                ),
            ],
            [
                "Selic base 252",
                parity?.selic_252_percent == null
                    ? "N/D"
                    : percent(
                        parity.selic_252_percent,
                        4
                    ),
            ],
            [
                "Treasury 1 ano",
                parity?.us_1y_yield_percent == null
                    ? "N/D"
                    : percent(
                        parity.us_1y_yield_percent,
                        4
                    ),
            ],
            [
                "Vencimento considerado",
                parity?.expiry_date || "N/D",
            ],
            [
                "Dias úteis",
                parity?.business_days == null
                    ? "N/D"
                    : String(
                        parity.business_days
                    ),
            ],
            [
                "Futuro teórico",
                number(
                    parity
                        ?.theoretical_future_points,
                    2
                ),
            ],
            [
                "Base teórica",
                number(
                    parity
                        ?.theoretical_basis_points,
                    2
                ),
            ],
            [
                "Futuro - teórico",
                number(
                    parity
                        ?.future_minus_theoretical_points,
                    2
                ),
            ],
            [
                "Desvio percentual",
                parity
                    ?.future_minus_theoretical_percent ==
                null
                    ? "N/D"
                    : percent(
                        parity
                            .future_minus_theoretical_percent,
                        4
                    ),
            ],
        ];

        grid.innerHTML = items
            .map(([label, value]) => {
                return dataItem(label, value);
            })
            .join("");

        const missingInputs =
            parity?.missing_for_theoretical || [];

        missing.hidden =
            missingInputs.length === 0;

        missing.textContent =
            missingInputs.length
                ? (
                    "Paridade teórica não calculada. " +
                    "Entradas reais ausentes: " +
                    `${missingInputs.join(", ")}.`
                )
                : "";
    }

    function sourceRows(status) {
        return Object
            .entries(status || {})
            .map(([name, item]) => {
                const stateClass =
                    item.complete
                        ? "ok"
                        : item.ok
                            ? "partial"
                            : "error";

                const stateLabel =
                    item.complete
                        ? "COMPLETA"
                        : item.ok
                            ? "PARCIAL"
                            : "FALHA";

                return `
                    <article class="source-row">
                        <div>
                            <strong>
                                ${escapeHtml(name)}
                            </strong>

                            <span
                                class="pill ${stateClass}"
                            >
                                ${stateLabel}
                            </span>
                        </div>

                        <div class="source-meta">
                            <span>
                                ${
                                    item.quote_count || 0
                                } cotações
                            </span>

                            <span>
                                ${
                                    item.duration_ms || 0
                                } ms
                            </span>
                        </div>

                        ${
                            item.error
                                ? `
                                    <div class="error-text">
                                        ${
                                            escapeHtml(
                                                item.error
                                            )
                                        }
                                    </div>
                                `
                                : ""
                        }
                    </article>
                `;
            })
            .join("");
    }

    function renderSources(status) {
        const target =
            byId("sourceStatus");

        if (!target) {
            return;
        }

        target.innerHTML =
            sourceRows(status) ||
            `
                <div class="muted">
                    Sem status disponível.
                </div>
            `;
    }

    function deduplicateSeries(rows) {
        const map = new Map();

        (rows || []).forEach((row) => {
            const value =
                toNumeric(row?.value);

            if (
                !validTimestamp(row?.timestamp) ||
                value === null
            ) {
                return;
            }

            map.set(row.timestamp, {
                ...row,
                value,
            });
        });

        return [...map.values()].sort(
            (a, b) =>
                Date.parse(a.timestamp) -
                Date.parse(b.timestamp)
        );
    }

    function renderUsdChart(history) {
        const rows = deduplicateSeries(
            history?.series?.USD_BRL || []
        );

        if (rows.length < 2) {
            return emptyPlot(
                "usdChart",
                "Histórico real ainda insuficiente."
            );
        }

        Plotly.react(
            "usdChart",
            [
                {
                    x: rows.map(
                        (row) => row.timestamp
                    ),
                    y: rows.map(
                        (row) => row.value
                    ),
                    type: "scatter",
                    mode: "lines",
                    name: "USD/BRL",
                    connectgaps: false,
                    hovertemplate:
                        "%{x|%d/%m/%Y %H:%M}" +
                        "<br>USD/BRL: %{y:.4f}" +
                        "<extra></extra>",
                },
            ],
            {
                ...PLOT_LAYOUT,
                xaxis: {
                    ...PLOT_LAYOUT.xaxis,
                    type: "date",
                },
                yaxis: {
                    ...PLOT_LAYOUT.yaxis,
                    type: "linear",
                    tickformat: ".4f",
                },
            },
            PLOT_CONFIG
        );
    }

    function renderCompositeChart(history) {
        const map = new Map();

        (history?.composite || []).forEach(
            (row) => {
                if (
                    !validTimestamp(
                        row?.timestamp
                    )
                ) {
                    return;
                }

                const globalValue =
                    toNumeric(row.global);

                const brazilValue =
                    toNumeric(row.brazil);

                if (
                    globalValue === null &&
                    brazilValue === null
                ) {
                    return;
                }

                map.set(row.timestamp, {
                    ...row,
                    global: globalValue,
                    brazil: brazilValue,
                });
            }
        );

        const rows = [...map.values()].sort(
            (a, b) =>
                Date.parse(a.timestamp) -
                Date.parse(b.timestamp)
        );

        if (rows.length < 2) {
            return emptyPlot(
                "compositeChart",
                "São necessárias pelo menos duas coletas válidas."
            );
        }

        const globalCustom = rows.map(
            (row) => [
                toNumeric(
                    row.global_sample_size ??
                    row.global_count
                ) ?? "N/D",
                row.global_direction || "N/D",
            ]
        );

        const brazilCustom = rows.map(
            (row) => [
                toNumeric(
                    row.brazil_sample_size ??
                    row.brazil_count
                ) ?? "N/D",
                row.brazil_direction || "N/D",
            ]
        );

        const traces = [
            {
                x: rows.map(
                    (row) => row.timestamp
                ),
                y: rows.map(
                    (row) => row.global
                ),
                customdata: globalCustom,
                type: "scatter",
                mode: "lines+markers",
                name: "Global",
                connectgaps: false,
                hovertemplate:
                    "Global" +
                    "<br>%{x|%d/%m/%Y %H:%M}" +
                    "<br>Composto: %{y:.4f}%" +
                    "<br>Sinais: %{customdata[0]}" +
                    "<br>Direção: %{customdata[1]}" +
                    "<extra></extra>",
            },
            {
                x: rows.map(
                    (row) => row.timestamp
                ),
                y: rows.map(
                    (row) => row.brazil
                ),
                customdata: brazilCustom,
                type: "scatter",
                mode: "lines+markers",
                name: "Brasil",
                connectgaps: false,
                hovertemplate:
                    "Brasil" +
                    "<br>%{x|%d/%m/%Y %H:%M}" +
                    "<br>Composto: %{y:.4f}%" +
                    "<br>Sinais: %{customdata[0]}" +
                    "<br>Direção: %{customdata[1]}" +
                    "<extra></extra>",
            },
        ];

        const layout = {
            ...PLOT_LAYOUT,

            hovermode: "x unified",

            xaxis: {
                ...PLOT_LAYOUT.xaxis,
                type: "date",
                title: "Horário da coleta",
            },

            yaxis: {
                ...PLOT_LAYOUT.yaxis,
                type: "linear",
                title: "Composto ajustado (%)",
                ticksuffix: "%",
                tickformat: ".4f",
                rangemode: "tozero",
                zeroline: true,
                zerolinewidth: 2,
                fixedrange: false,
            },

            shapes: [
                {
                    type: "rect",
                    xref: "paper",
                    x0: 0,
                    x1: 1,
                    y0: -0.10,
                    y1: 0.10,
                    line: {
                        width: 0,
                    },
                    fillcolor:
                        "rgba(148, 163, 184, 0.10)",
                    layer: "below",
                },
            ],

            annotations: [
                {
                    xref: "paper",
                    yref: "y",
                    x: 1,
                    y: 0,
                    xanchor: "right",
                    yanchor: "bottom",
                    text: "Linha neutra",
                    showarrow: false,
                    font: {
                        size: 10,
                        color: "#94a3b8",
                    },
                },
            ],
        };

        Plotly.react(
            "compositeChart",
            traces,
            layout,
            PLOT_CONFIG
        );
    }

    function normalizedTrace(
        symbol,
        rows
    ) {
        const clean = deduplicateSeries(rows)
            .filter(
                (row) => row.value !== 0
            );

        if (clean.length < 2) {
            return null;
        }

        const base = clean[0].value;

        if (
            !Number.isFinite(base) ||
            base === 0
        ) {
            return null;
        }

        return {
            x: clean.map(
                (row) => row.timestamp
            ),
            y: clean.map(
                (row) =>
                    (row.value / base) * 100
            ),
            type: "scatter",
            mode: "lines",
            name: symbol,
            connectgaps: false,
            hovertemplate:
                `${symbol}` +
                "<br>%{x|%d/%m/%Y %H:%M}" +
                "<br>Base 100: %{y:.2f}" +
                "<extra></extra>",
        };
    }

    function renderMarketChart(history) {
        const symbols = [
            "DXY",
            "IBOV",
            "EWZ",
            "DJI",
            "SP500",
            "VIX",
        ];

        const traces = symbols
            .map((symbol) => {
                return normalizedTrace(
                    symbol,
                    history?.series?.[symbol] ||
                    []
                );
            })
            .filter(Boolean);

        if (traces.length === 0) {
            return emptyPlot(
                "marketChart",
                "Histórico real ainda insuficiente."
            );
        }

        Plotly.react(
            "marketChart",
            traces,
            {
                ...PLOT_LAYOUT,
                xaxis: {
                    ...PLOT_LAYOUT.xaxis,
                    type: "date",
                },
                yaxis: {
                    ...PLOT_LAYOUT.yaxis,
                    type: "linear",
                    title: "Base 100",
                },
            },
            PLOT_CONFIG
        );
    }

    function renderAdrChart(groups) {
        const adrs = (
            groups?.adrs || []
        )
            .map((row) => ({
                ...row,
                change_percent: toNumeric(
                    row.change_percent
                ),
            }))
            .filter(
                (row) =>
                    row.change_percent !== null
            );

        adrs.sort(
            (a, b) =>
                a.change_percent -
                b.change_percent
        );

        if (adrs.length === 0) {
            return emptyPlot(
                "adrChart",
                "Nenhuma ADR real disponível."
            );
        }

        Plotly.react(
            "adrChart",
            [
                {
                    x: adrs.map(
                        (row) =>
                            row.change_percent
                    ),
                    y: adrs.map(
                        (row) => row.symbol
                    ),
                    type: "bar",
                    orientation: "h",
                    name: "Variação %",
                    hovertemplate:
                        "%{y}: %{x:.2f}%" +
                        "<extra></extra>",
                },
            ],
            {
                ...PLOT_LAYOUT,
                margin: {
                    l: 80,
                    r: 20,
                    t: 20,
                    b: 45,
                },
                xaxis: {
                    ...PLOT_LAYOUT.xaxis,
                    type: "linear",
                    ticksuffix: "%",
                    zeroline: true,
                },
            },
            PLOT_CONFIG
        );
    }

    function emptyPlot(id, text) {
        const node = byId(id);

        if (!node) {
            return;
        }

        if (
            window.Plotly &&
            typeof Plotly.purge === "function"
        ) {
            Plotly.purge(node);
        }

        node.innerHTML = `
            <div
                class="muted"
                style="
                    padding:40px 10px;
                    text-align:center
                "
            >
                ${escapeHtml(text)}
            </div>
        `;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(
                /[&<>'"]/g,
                (char) => ({
                    "&": "&amp;",
                    "<": "&lt;",
                    ">": "&gt;",
                    "'": "&#39;",
                    '"': "&quot;",
                })[char]
            );
    }

    function renderIndexOpening(data, collectedAt) {
        const estimate = toNumeric(data?.opening_estimate_points);
        const fair = toNumeric(data?.fair_value_points);
        const base = toNumeric(data?.base_points);
        const observed = toNumeric(data?.observed_points);
        const deviation = toNumeric(data?.deviation_points);
        const expectedPct = toNumeric(data?.expected_change_percent);
        const confidence = data?.confidence || {};

        const resultCard = byId("indexResultCard");
        const estimateNode = byId("indexOpeningEstimate");
        const fairNode = byId("indexFairValue");
        const baseNode = byId("indexBase");
        const observedNode = byId("indexObserved");
        const deviationNode = byId("indexDeviation");
        const biasNode = byId("indexBias");
        const strengthNode = byId("indexStrength");
        const confidenceNode = byId("indexConfidence");
        const coverageNode = byId("indexCoverage");
        const snapshotNode = byId("indexOpeningSnapshot");
        const readNode = byId("indexOperationalRead");
        const missingNode = byId("indexMissing");
        const disclaimerNode = byId("indexDisclaimer");
        const componentsNode = byId("indexComponents");
        const weightsNode = byId("indexWeights");

        let resultClass = "neutral";
        if (expectedPct !== null) {
            resultClass = expectedPct > 0.15 ? "positive" : expectedPct < -0.15 ? "negative" : "neutral";
        }
        if (resultCard) resultCard.className = `index-result-card ${resultClass}`;

        if (estimateNode) estimateNode.textContent = estimate === null ? "N/D" : number(estimate, 3);
        if (fairNode) fairNode.textContent = fair === null ? "N/D" : number(fair, 3);
        if (baseNode) baseNode.textContent = base === null ? "N/D" : number(base, 3);
        if (observedNode) observedNode.textContent = observed === null ? "N/D" : number(observed, 3);

        if (deviationNode) {
            deviationNode.textContent = deviation === null ? "N/D" : `${deviation > 0 ? "+" : ""}${number(deviation, 3)} pts`;
            deviationNode.className = deviation > 0 ? "positive" : deviation < 0 ? "negative" : "";
        }

        const bias = data?.bias || "dados insuficientes";
        const strength = data?.strength || "indisponível";
        if (biasNode) {
            biasNode.textContent = bias;
            biasNode.className = `pill ${resultClass === "positive" ? "ok" : resultClass === "negative" ? "error" : "partial"}`;
        }
        if (strengthNode) {
            strengthNode.textContent = strength;
            strengthNode.className = `pill ${resultClass === "positive" ? "ok" : resultClass === "negative" ? "error" : "partial"}`;
        }

        if (confidenceNode) confidenceNode.textContent = `Confiança: ${confidence.label || "N/D"}`;
        if (coverageNode) {
            coverageNode.textContent = `Cobertura: ${confidence.coverage_percent == null ? "N/D" : number(confidence.coverage_percent, 1) + "%"}`;
        }

        if (snapshotNode) {
            snapshotNode.textContent = validTimestamp(collectedAt)
                ? `Snapshot ${new Date(collectedAt).toLocaleTimeString("pt-BR", {hour:"2-digit", minute:"2-digit"})}`
                : "Horário indisponível";
            snapshotNode.className = `pill ${(data?.missing_components || []).length ? "partial" : "ok"}`;
        }

        if (readNode) {
            if (estimate === null || fair === null) {
                readNode.textContent = "Sem base suficiente para estimar a abertura. Não interpretar ausência de dados como sinal.";
            } else if (Math.abs(deviation || 0) >= 250) {
                const side = deviation < 0 ? "abaixo" : "acima";
                readNode.textContent = `O WIN observado está ${number(Math.abs(deviation), 0)} pontos ${side} do fair value calculado. Use a diferença como contexto e aguarde confirmação de preço, volume e VWAP; não é uma entrada automática.`;
            } else {
                readNode.textContent = `Fair value próximo do WIN observado. O modelo aponta ${bias}, com retorno estimado de ${expectedPct === null ? "N/D" : (expectedPct > 0 ? "+" : "") + number(expectedPct, 2) + "%"}. A confirmação deve ocorrer no preço após a abertura.`;
            }
        }

        const rows = (data?.components || []).slice().sort(
            (a, b) => Math.abs(toNumeric(b.weighted_contribution_percent) || 0) - Math.abs(toNumeric(a.weighted_contribution_percent) || 0)
        );
        if (componentsNode) {
            componentsNode.innerHTML = rows.length
                ? rows.map(item => {
                    const contribution = toNumeric(item.weighted_contribution_percent) || 0;
                    const raw = toNumeric(item.raw_change_percent);
                    return `
                        <div class="component">
                            <span>${escapeHtml(item.label || item.symbol)}<small style="display:block">Peso ${number((toNumeric(item.weight) || 0) * 100, 1)}% · Real ${percent(raw)}</small></span>
                            <strong class="${contribution > 0 ? "positive" : contribution < 0 ? "negative" : ""}">${contribution > 0 ? "+" : ""}${number(contribution, 3)}%</strong>
                        </div>`;
                }).join("")
                : '<div class="muted">Nenhum driver disponível.</div>';
        }

        if (weightsNode) {
            const weights = data?.weights || {};
            weightsNode.innerHTML = Object.entries(weights).map(([label, weight]) =>
                `<span>${escapeHtml(label)} <strong>${number((toNumeric(weight) || 0) * 100, 0)}%</strong></span>`
            ).join("");
        }

        const missing = data?.missing_components || [];
        if (missingNode) {
            missingNode.hidden = missing.length === 0;
            missingNode.textContent = missing.length ? `Cobertura parcial. Ausentes: ${missing.join(", ")}. Nenhum valor substituto foi usado.` : "";
        }
        if (disclaimerNode) {
            disclaimerNode.textContent = data?.disclaimer || "Modelo multifatorial; não é probabilidade de acerto.";
        }
    }

    function renderDashboard(data) {
        renderQuotes(
            data.quotes || {}
        );

        renderAnalysis(
            data.analysis || {}
        );

        renderMacroOpening(
            data.macro_opening || {},
            data.collected_at
        );

        renderOpeningAnalysis(
            data.opening_analysis || {},
            data.collected_at
        );

        renderIndexOpening(
            data.index_opening || {},
            data.collected_at
        );

        renderParity(
            data.dollar_parity || {}
        );

        renderSources(
            data.source_status || {}
        );

        renderUsdChart(
            data.history || {}
        );

        renderCompositeChart(
            data.history || {}
        );

        renderMarketChart(
            data.history || {}
        );

        renderAdrChart(
            data.groups || {}
        );

        const dataPolicy =
            byId("dataPolicy");

        if (dataPolicy) {
            dataPolicy.textContent =
                data.data_policy ||
                "Valores ausentes permanecem nulos.";
        }

        const status =
            byId("collectionStatus");

        const successful =
            toNumeric(
                data.successful_sources
            ) ?? 0;

        const complete =
            toNumeric(
                data.complete_sources
            ) ?? 0;

        const total =
            toNumeric(
                data.total_sources
            ) ?? 0;

        if (status) {
            status.textContent =
                data.is_complete
                    ? (
                        `Coleta completa ` +
                        `(${complete}/${total})`
                    )
                    : (
                        `Coleta parcial ` +
                        `(${successful}/${total} ` +
                        `com algum dado; ` +
                        `${complete}/${total} ` +
                        `completas)`
                    );

            status.className =
                `status ${
                    data.is_complete
                        ? "ok"
                        : "partial"
                }`;
        }

        const collectedAt =
            validTimestamp(data.collected_at)
                ? new Date(
                    data.collected_at
                ).toLocaleString("pt-BR")
                : "horário indisponível";

        const lastUpdate =
            byId("lastUpdate");

        if (lastUpdate) {
            lastUpdate.textContent =
                `Coletado em ${collectedAt} · ` +
                `${toNumeric(
                    data.duration_ms
                ) ?? 0} ms`;
        }
    }

    async function loadDashboard() {
        try {
            const response = await fetch(
                API_URL,
                {
                    headers: {
                        Accept:
                            "application/json",
                    },
                    cache: "no-store",
                }
            );

            const data =
                await response.json();

            if (!response.ok) {
                throw new Error(
                    data.message ||
                    `HTTP ${response.status}`
                );
            }

            showMessage("");

            renderDashboard(data);
        } catch (error) {
            showMessage(
                error.message ||
                "Não foi possível carregar o dashboard.",
                "warning"
            );

            const status =
                byId("collectionStatus");

            if (status) {
                status.textContent =
                    "Sem coleta válida";

                status.className =
                    "status error";
            }
        }
    }

    async function pollTask(taskId) {
        for (
            let attempt = 0;
            attempt < 90;
            attempt += 1
        ) {
            await new Promise(
                (resolve) =>
                    setTimeout(resolve, 2000)
            );

            const response = await fetch(
                `/api/tasks/${
                    encodeURIComponent(taskId)
                }/`,
                {
                    cache: "no-store",
                }
            );

            const data =
                await response.json();

            if (data.ready) {
                if (
                    data.state === "SUCCESS"
                ) {
                    showMessage(
                        "Coleta concluída com os dados que as fontes realmente retornaram.",
                        "warning"
                    );

                    await loadDashboard();

                    return;
                }

                throw new Error(
                    data.error ||
                    `Tarefa finalizada em ${
                        data.state
                    }`
                );
            }
        }

        throw new Error(
            "A tarefa continua em execução. " +
            "O dashboard atualizará automaticamente " +
            "quando houver uma nova coleta."
        );
    }

    async function refreshNow() {
        const button =
            byId("refreshButton");

        if (!button) {
            return;
        }

        button.disabled = true;
        button.textContent =
            "Coletando...";

        showMessage(
            "Coleta síncrona iniciada. Nenhum valor será substituído se uma fonte falhar.",
            "warning"
        );

        try {
            const response = await fetch(
                REFRESH_URL,
                {
                    method: "POST",
                    headers: {
                        "X-CSRFToken":
                            csrfToken(),
                        Accept:
                            "application/json",
                    },
                }
            );

            const data =
                await response.json();

            if (!response.ok) {
                throw new Error(
                    data.message ||
                    `HTTP ${response.status}`
                );
            }

            if (data.completed) {
                await loadDashboard();
                showMessage("Coleta concluída e salva no banco.", "success");
            } else {
                await pollTask(data.task_id);
            }
        } catch (error) {
            showMessage(
                error.message ||
                "Falha ao iniciar a coleta.",
                "error"
            );
        } finally {
            button.disabled = false;
            button.textContent =
                "Atualizar fontes agora";
        }
    }

    document.addEventListener(
        "DOMContentLoaded",
        () => {
            const button =
                byId("refreshButton");

            if (button) {
                button.addEventListener(
                    "click",
                    refreshNow
                );
            }

            bindFrp0Calculator();

            loadDashboard();

            window.setInterval(
                loadDashboard,
                60000
            );
        }
    );
})();