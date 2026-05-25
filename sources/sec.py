from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

import db


class SECSourceError(RuntimeError):
    pass


class RequestsJSONClient:
    def get_json(self, url: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={"User-Agent": "local-financial-database contact@example.com"},
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


class SECSource:
    source_name = "SEC CompanyFacts"
    source_confidence = "official"
    COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    COMPANYFACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    CONCEPT_MAP = {
        "Revenues": ("income_statement", "revenue"),
        "RevenueFromContractWithCustomerExcludingAssessedTax": (
            "income_statement",
            "revenue",
        ),
        "CostOfRevenue": ("income_statement", "cost_of_revenue"),
        "CostOfGoodsAndServicesSold": ("income_statement", "cost_of_revenue"),
        "GrossProfit": ("income_statement", "gross_profit"),
        "OperatingIncomeLoss": ("income_statement", "operating_income"),
        "OperatingExpenses": ("income_statement", "operating_expenses"),
        "ResearchAndDevelopmentExpense": (
            "income_statement",
            "research_and_development",
        ),
        "SellingGeneralAndAdministrativeExpense": (
            "income_statement",
            "selling_general_and_administrative",
        ),
        "GeneralAndAdministrativeExpense": (
            "income_statement",
            "general_and_administrative",
        ),
        "SellingAndMarketingExpense": ("income_statement", "selling_and_marketing"),
        "InterestExpenseNonOperating": ("income_statement", "interest_expense"),
        "InterestIncomeExpenseNonOperatingNet": (
            "income_statement",
            "net_interest_income_expense",
        ),
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": (
            "income_statement",
            "pretax_income",
        ),
        "IncomeTaxExpenseBenefit": ("income_statement", "income_tax_expense"),
        "NetIncomeLoss": ("income_statement", "net_income"),
        "EarningsPerShareBasic": ("income_statement", "earnings_per_share_basic"),
        "EarningsPerShareDiluted": ("income_statement", "earnings_per_share_diluted"),
        "WeightedAverageNumberOfSharesOutstandingBasic": (
            "income_statement",
            "weighted_average_shares_basic",
        ),
        "WeightedAverageNumberOfDilutedSharesOutstanding": (
            "income_statement",
            "weighted_average_shares_diluted",
        ),
        "Assets": ("balance_sheet", "total_assets"),
        "AssetsCurrent": ("balance_sheet", "current_assets"),
        "CashAndCashEquivalentsAtCarryingValue": (
            "balance_sheet",
            "cash_and_cash_equivalents",
        ),
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": (
            "balance_sheet",
            "cash_cash_equivalents_and_restricted_cash",
        ),
        "ShortTermInvestments": ("balance_sheet", "short_term_investments"),
        "MarketableSecuritiesCurrent": ("balance_sheet", "marketable_securities"),
        "AccountsReceivableNetCurrent": ("balance_sheet", "accounts_receivable"),
        "InventoryNet": ("balance_sheet", "inventory"),
        "PrepaidExpenseAndOtherAssetsCurrent": (
            "balance_sheet",
            "prepaid_expenses_and_other_current_assets",
        ),
        "PropertyPlantAndEquipmentNet": (
            "balance_sheet",
            "property_plant_and_equipment_net",
        ),
        "Goodwill": ("balance_sheet", "goodwill"),
        "IntangibleAssetsNetExcludingGoodwill": (
            "balance_sheet",
            "intangible_assets_net",
        ),
        "OtherAssetsCurrent": ("balance_sheet", "other_current_assets"),
        "OtherAssetsNoncurrent": ("balance_sheet", "other_noncurrent_assets"),
        "Liabilities": ("balance_sheet", "total_liabilities"),
        "LiabilitiesCurrent": ("balance_sheet", "current_liabilities"),
        "AccountsPayableCurrent": ("balance_sheet", "accounts_payable"),
        "AccruedLiabilitiesCurrent": ("balance_sheet", "accrued_liabilities"),
        "ContractWithCustomerLiabilityCurrent": (
            "balance_sheet",
            "current_contract_liabilities",
        ),
        "LongTermDebtCurrent": ("balance_sheet", "current_long_term_debt"),
        "LongTermDebtNoncurrent": ("balance_sheet", "long_term_debt"),
        "OperatingLeaseLiabilityCurrent": (
            "balance_sheet",
            "current_operating_lease_liability",
        ),
        "OperatingLeaseLiabilityNoncurrent": (
            "balance_sheet",
            "noncurrent_operating_lease_liability",
        ),
        "DeferredRevenueCurrent": ("balance_sheet", "deferred_revenue_current"),
        "DeferredRevenueNoncurrent": ("balance_sheet", "deferred_revenue_noncurrent"),
        "DeferredTaxLiabilitiesNoncurrent": (
            "balance_sheet",
            "deferred_tax_liabilities_noncurrent",
        ),
        "StockholdersEquity": ("balance_sheet", "total_equity"),
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": (
            "balance_sheet",
            "total_equity",
        ),
        "RetainedEarningsAccumulatedDeficit": (
            "balance_sheet",
            "retained_earnings",
        ),
        "AccumulatedOtherComprehensiveIncomeLossNetOfTax": (
            "balance_sheet",
            "accumulated_other_comprehensive_income_loss",
        ),
        "NetCashProvidedByUsedInOperatingActivities": (
            "cash_flow",
            "operating_cash_flow",
        ),
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations": (
            "cash_flow",
            "operating_cash_flow",
        ),
        "NetCashProvidedByUsedInInvestingActivities": (
            "cash_flow",
            "investing_cash_flow",
        ),
        "NetCashProvidedByUsedInFinancingActivities": (
            "cash_flow",
            "financing_cash_flow",
        ),
        "PaymentsToAcquirePropertyPlantAndEquipment": (
            "cash_flow",
            "capital_expenditure",
        ),
        "PaymentsToAcquireBusinessesNetOfCashAcquired": (
            "cash_flow",
            "business_acquisitions_net",
        ),
        "PaymentsToAcquireInvestments": ("cash_flow", "purchases_of_investments"),
        "ProceedsFromSaleAndMaturityOfInvestments": (
            "cash_flow",
            "proceeds_from_investments",
        ),
        "PaymentsOfDividends": ("cash_flow", "dividends_paid"),
        "PaymentsForRepurchaseOfCommonStock": (
            "cash_flow",
            "share_repurchases",
        ),
        "ProceedsFromIssuanceOfCommonStock": (
            "cash_flow",
            "proceeds_from_common_stock_issuance",
        ),
        "ProceedsFromIssuanceOfLongTermDebt": (
            "cash_flow",
            "proceeds_from_long_term_debt",
        ),
        "RepaymentsOfLongTermDebt": ("cash_flow", "repayments_of_long_term_debt"),
        "DepreciationDepletionAndAmortization": (
            "cash_flow",
            "depreciation_depletion_and_amortization",
        ),
        "ShareBasedCompensation": ("cash_flow", "share_based_compensation"),
        "IncreaseDecreaseInAccountsReceivable": (
            "cash_flow",
            "change_in_accounts_receivable",
        ),
        "IncreaseDecreaseInInventories": ("cash_flow", "change_in_inventory"),
        "IncreaseDecreaseInAccountsPayable": (
            "cash_flow",
            "change_in_accounts_payable",
        ),
        "CashAndCashEquivalentsPeriodIncreaseDecrease": (
            "cash_flow",
            "net_change_in_cash_and_cash_equivalents",
        ),
    }

    def __init__(
        self,
        *,
        client: Any | None = None,
        ticker_mapping: dict[str, Any] | list[dict[str, Any]] | None = None,
        fetched_at: str | None = None,
    ) -> None:
        self.client = client or RequestsJSONClient()
        self._ticker_mapping = ticker_mapping
        self.fetched_at = fetched_at

    @classmethod
    def companyfacts_url(cls, cik: str) -> str:
        return cls.COMPANYFACTS_URL_TEMPLATE.format(cik=cik)

    def _load_ticker_mapping(self):
        if self._ticker_mapping is not None:
            return self._ticker_mapping
        try:
            self._ticker_mapping = self.client.get_json(self.COMPANY_TICKERS_URL)
        except Exception as exc:
            raise SECSourceError(f"failed to load SEC ticker mapping: {exc}") from exc
        return self._ticker_mapping

    def resolve_cik(self, symbol: str) -> str:
        normalized_symbol = symbol.upper()
        mapping = self._load_ticker_mapping()
        entries = mapping.values() if isinstance(mapping, dict) else mapping
        for entry in entries:
            if str(entry.get("ticker", "")).upper() == normalized_symbol:
                return str(entry["cik_str"]).zfill(10)
        raise SECSourceError(f"SEC CIK not found for symbol {normalized_symbol}")

    def fetch_company_facts(self, symbol: str) -> tuple[str, dict[str, Any]]:
        cik = self.resolve_cik(symbol)
        url = self.companyfacts_url(cik)
        try:
            return url, self.client.get_json(url)
        except Exception as exc:
            raise SECSourceError(f"failed to fetch SEC CompanyFacts for {symbol}: {exc}") from exc

    def fetch(self, company) -> dict[str, Any]:
        source_url, companyfacts = self.fetch_company_facts(company.symbol)
        facts = self._companyfacts_to_facts(companyfacts)
        return {
            "company_symbol": company.symbol,
            "market": company.market,
            "source": self.source_name,
            "source_url": source_url,
            "source_confidence": self.source_confidence,
            "fetched_at": self.fetched_at or db.utc_now(),
            "facts": facts,
            "payload": companyfacts,
        }

    def _companyfacts_to_facts(self, companyfacts: dict[str, Any]) -> list[dict[str, Any]]:
        us_gaap = companyfacts.get("facts", {}).get("us-gaap", {})
        facts = []
        for concept, (statement_type, line_item) in self.CONCEPT_MAP.items():
            concept_payload = us_gaap.get(concept)
            if not concept_payload:
                continue
            for unit, rows in concept_payload.get("units", {}).items():
                for row in rows:
                    if "val" not in row:
                        continue
                    report_period = self._report_period(row)
                    facts.append(
                        {
                            "statement_type": statement_type,
                            "report_period": report_period,
                            "fiscal_year": row.get("fy"),
                            "fiscal_period": row.get("fp"),
                            "line_item": line_item,
                            "raw_line_item": concept,
                            "value": row.get("val"),
                            "unit": unit,
                            "currency": unit if len(unit) == 3 else None,
                            "quality_status": "trusted",
                            "freshness_status": "unknown",
                            "validation_status": "trusted",
                        }
                    )
        return facts

    def _report_period(self, row: dict[str, Any]) -> str:
        fy = row.get("fy")
        fp = str(row.get("fp") or "").upper()
        if fy and fp:
            if fp in {"FY", "CY"}:
                return f"{fy}FY"
            if fp.startswith("Q") and fp[1:].isdigit():
                return f"{fy}{fp}"
        return row.get("end") or str(fy)
