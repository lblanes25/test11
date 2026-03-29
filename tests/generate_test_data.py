"""Generate dummy test data for the Risk Taxonomy Transformer.

Creates three files in data/input/ with column names matching the actual
source files. Filenames include a datetime suffix matching the real pattern.

Designed to exercise a wide variety of scenarios:
  - Direct 1:1 mappings
  - Multi-target evidence matches (high and medium confidence)
  - Default no evidence (flagged for review)
  - Source N/A pillars
  - Findings-confirmed applicability
  - Control contradiction flags
  - Dedup from multiple legacy sources
  - Country overlay flags
  - Dimension parsing from rationale (likelihood/impact)
  - No rationale pillars (IT, InfoSec, Third Party)
  - Multi-value L1 and L2 fields (newline-separated)
  - Blank severity, unapproved findings, closed findings
"""

import pandas as pd
import random
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "input"

NO_RATIONALE_PILLARS = ("Information Technology", "Information Security", "Third Party")

random.seed(42)

PILLARS = [
    "Credit", "Market", "Strategic & Business", "Funding & Liquidity",
    "Reputational", "Model", "Third Party", "Financial Reporting",
    "External Fraud", "Information Technology", "Information Security",
    "Operational", "Compliance", "Country",
]

AUDIT_TEAMS = ["Team Alpha", "Team Bravo", "Team Charlie", "Team Delta"]

# =============================================================================
# File 1: legacy_risk_data_{datetime}.xlsx
#
# 10 entities designed to produce specific scenarios
# =============================================================================

ENTITY_DATA = [
    # --- AE-1: Well-documented entity, most pillars rated, rich rationale ---
    {
        "Audit Entity ID": "AE-1", "Audit Entity Name": "North America Cards",
        "Audit Entity Status": "Active", "Core Audit Team": "Team Alpha",
        "Audit Entity Overview": "Largest consumer cards portfolio in NAM.",
        "Audit Entity Overall Inherent Risk Rating": "High",
        "Audit Entity Overall Residual Risk Rating": "Medium",
        "Credit Inherent Risk": "High",
        "Credit Inherent Risk Rationale": (
            "Consumer credit exposure is high. Likelihood is high, impact is critical. "
            "Cardmember default rates trending upward in small business segment. "
            "Retail personal lending concentrated in high-balance individual accounts."
        ),
        "Credit Control Assessment": "Moderately Controlled",
        "Credit Control Assessment Rationale": "Controls are moderately controlled. Monthly monitoring in place.",
        "Market Inherent Risk": "Medium",
        "Market Inherent Risk Rationale": (
            "Interest rate sensitivity is medium. Repricing risk on variable-rate products. "
            "Yield curve flattening creates NII pressure. No significant FX exposure."
        ),
        "Market Control Assessment": "Well Controlled",
        "Market Control Assessment Rationale": "Controls well controlled. Hedging program effective.",
        "Strategic & Business Inherent Risk": "Medium",
        "Strategic & Business Inherent Risk Rationale": (
            "Earnings outlook is medium. Revenue growth constrained by competitive pressure. "
            "Fee income declining. Product diversification efforts underway."
        ),
        "Strategic & Business Control Assessment": "Well Controlled",
        "Strategic & Business Control Assessment Rationale": "Strategic planning process well controlled.",
        "Funding & Liquidity Inherent Risk": "Low",
        "Funding & Liquidity Inherent Risk Rationale": "Liquidity position is low risk. Cash flow stable. Deposit base diversified.",
        "Funding & Liquidity Control Assessment": "Well Controlled",
        "Funding & Liquidity Control Assessment Rationale": "Liquidity controls well controlled.",
        "Reputational Inherent Risk": "Medium",
        "Reputational Inherent Risk Rationale": "Reputation risk medium. Brand perception stable. Stakeholder trust maintained.",
        "Reputational Control Assessment": "Moderately Controlled",
        "Reputational Control Assessment Rationale": "Media monitoring in place.",
        "Model Inherent Risk": "High",
        "Model Inherent Risk Rationale": "Model risk is high. Validation backlog for 3 models. Algorithm performance drifting.",
        "Model Control Assessment": "Insufficiently Controlled",
        "Model Control Assessment Rationale": "MRM team understaffed. Backtest schedule not met.",
        "Third Party Inherent Risk": "Medium",
        "Third Party Control Assessment": "Moderately Controlled",
        "Financial Reporting Inherent Risk": "Low",
        "Financial Reporting Inherent Risk Rationale": "Financial reporting risk low. GAAP compliance maintained. No restatements.",
        "Financial Reporting Control Assessment": "Well Controlled",
        "Financial Reporting Control Assessment Rationale": "Automated reporting controls effective.",
        "External Fraud Inherent Risk": "High",
        "External Fraud Inherent Risk Rationale": "External fraud risk high. Account takeover attempts increasing. Identity theft schemes detected.",
        "External Fraud Control Assessment": "Moderately Controlled",
        "External Fraud Control Assessment Rationale": "Fraud detection systems operational but gaps in digital channel.",
        "Information Technology Inherent Risk": "High",
        "Information Technology Control Assessment": "Moderately Controlled",
        "Information Security Inherent Risk": "High",
        "Information Security Control Assessment": "Moderately Controlled",
        "Operational Inherent Risk": "High",
        "Operational Inherent Risk Rationale": (
            "Operational risk is high. Likelihood is high, impact is high. "
            "Process execution has gaps. Business continuity plan tested but disaster recovery "
            "needs improvement. Employee attrition in technology workforce exceeding targets. "
            "Conduct training completed. Privacy compliance program operational. "
            "Data risk from volume growth in transaction processing."
        ),
        "Operational Control Assessment": "Moderately Controlled",
        "Operational Control Assessment Rationale": "Controls moderately controlled across operational areas.",
        "Compliance Inherent Risk": "Medium",
        "Compliance Inherent Risk Rationale": (
            "Compliance risk medium. Regulatory examination findings resolved. "
            "Enterprise compliance program effective. Consumer protection adequate. "
            "Financial crimes monitoring operational. AML/BSA requirements met. "
            "Prudential oversight satisfactory."
        ),
        "Compliance Control Assessment": "Well Controlled",
        "Compliance Control Assessment Rationale": "Compliance controls well controlled.",
        "Country Inherent Risk": "Low",
        "Country Inherent Risk Rationale": "Country risk low. Domestic operations only.",
        "Country Control Assessment": "Well Controlled",
        "Country Control Assessment Rationale": "N/A — domestic only.",
        "PRIMARY IT APPLICATIONS (MAPPED)": "App-100\nApp-101",
        "SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)": "App-200",
        "PRIMARY TLM THIRD PARTY ENGAGEMENT": "Vendor-A",
        "SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)": "Vendor-B\nVendor-C",
    },

    # --- AE-2: Many pillars N/A, minimal rationale ---
    {
        "Audit Entity ID": "AE-2", "Audit Entity Name": "Treasury Operations",
        "Audit Entity Status": "Active", "Core Audit Team": "Team Bravo",
        "Audit Entity Overview": "Internal treasury and funding operations.",
        "Audit Entity Overall Inherent Risk Rating": "Low",
        "Audit Entity Overall Residual Risk Rating": "Low",
        "Credit Inherent Risk": "Not Applicable",
        "Credit Inherent Risk Rationale": "Not applicable — no lending activities.",
        "Credit Control Assessment": "Not Applicable",
        "Credit Control Assessment Rationale": "N/A.",
        "Market Inherent Risk": "High",
        "Market Inherent Risk Rationale": (
            "Interest rate risk is high. Repricing risk on treasury portfolio. "
            "Yield curve sensitivity. FX exposure from international funding. "
            "Currency volatility in emerging markets. Price risk from position taking."
        ),
        "Market Control Assessment": "Moderately Controlled",
        "Market Control Assessment Rationale": "Hedging partially effective.",
        "Strategic & Business Inherent Risk": "Not Applicable",
        "Strategic & Business Inherent Risk Rationale": "N/A.",
        "Strategic & Business Control Assessment": "Not Applicable",
        "Strategic & Business Control Assessment Rationale": "N/A.",
        "Funding & Liquidity Inherent Risk": "High",
        "Funding & Liquidity Inherent Risk Rationale": "Liquidity risk high. Funding concentration. Cash flow volatility. Borrowing capacity stretched.",
        "Funding & Liquidity Control Assessment": "Moderately Controlled",
        "Funding & Liquidity Control Assessment Rationale": "Liquidity monitoring daily.",
        "Reputational Inherent Risk": "Not Applicable",
        "Reputational Inherent Risk Rationale": "N/A.",
        "Reputational Control Assessment": "Not Applicable",
        "Reputational Control Assessment Rationale": "N/A.",
        "Model Inherent Risk": "Medium",
        "Model Inherent Risk Rationale": "Model risk medium. Treasury models validated annually. Methodology sound.",
        "Model Control Assessment": "Well Controlled",
        "Model Control Assessment Rationale": "Model governance framework in place.",
        "Third Party Inherent Risk": "Not Applicable",
        "Third Party Control Assessment": "Not Applicable",
        "Financial Reporting Inherent Risk": "Medium",
        "Financial Reporting Inherent Risk Rationale": "Financial reporting risk medium. Regulatory report timeliness adequate. GAAP accounting compliant.",
        "Financial Reporting Control Assessment": "Well Controlled",
        "Financial Reporting Control Assessment Rationale": "Automated controls.",
        "External Fraud Inherent Risk": "Not Applicable",
        "External Fraud Inherent Risk Rationale": "N/A — no customer-facing channels.",
        "External Fraud Control Assessment": "Not Applicable",
        "External Fraud Control Assessment Rationale": "N/A.",
        "Information Technology Inherent Risk": "Low",
        "Information Technology Control Assessment": "Well Controlled",
        "Information Security Inherent Risk": "Low",
        "Information Security Control Assessment": "Well Controlled",
        "Operational Inherent Risk": "Low",
        "Operational Inherent Risk Rationale": "Operational risk low. Processes automated. No significant manual processing.",
        "Operational Control Assessment": "Well Controlled",
        "Operational Control Assessment Rationale": "Controls well controlled.",
        "Compliance Inherent Risk": "Not Applicable",
        "Compliance Inherent Risk Rationale": "N/A.",
        "Compliance Control Assessment": "Not Applicable",
        "Compliance Control Assessment Rationale": "N/A.",
        "Country Inherent Risk": "Not Applicable",
        "Country Inherent Risk Rationale": "N/A.",
        "Country Control Assessment": "Not Applicable",
        "Country Control Assessment Rationale": "N/A.",
        "PRIMARY IT APPLICATIONS (MAPPED)": "App-300",
        "SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)": "",
        "PRIMARY TLM THIRD PARTY ENGAGEMENT": "",
        "SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)": "",
    },

    # --- AE-3: Operational pillar with vague rationale (should trigger low confidence / review) ---
    {
        "Audit Entity ID": "AE-3", "Audit Entity Name": "Global Merchant Services",
        "Audit Entity Status": "Active", "Core Audit Team": "Team Charlie",
        "Audit Entity Overview": "Merchant acquiring and payment acceptance services.",
        "Audit Entity Overall Inherent Risk Rating": "High",
        "Audit Entity Overall Residual Risk Rating": "Medium",
        "Credit Inherent Risk": "Medium",
        "Credit Inherent Risk Rationale": "Commercial credit exposure to merchant portfolio. Corporate counterpart risk from large merchants.",
        "Credit Control Assessment": "Moderately Controlled",
        "Credit Control Assessment Rationale": "Credit monitoring in place.",
        "Market Inherent Risk": "Low",
        "Market Inherent Risk Rationale": "Market risk low. Minimal interest rate or FX exposure.",
        "Market Control Assessment": "Well Controlled",
        "Market Control Assessment Rationale": "No active positions.",
        "Strategic & Business Inherent Risk": "Medium",
        "Strategic & Business Inherent Risk Rationale": "Earnings pressure from fee compression. Revenue stable but margin declining.",
        "Strategic & Business Control Assessment": "Moderately Controlled",
        "Strategic & Business Control Assessment Rationale": "Strategic review ongoing.",
        "Funding & Liquidity Inherent Risk": "Not Applicable",
        "Funding & Liquidity Inherent Risk Rationale": "N/A.",
        "Funding & Liquidity Control Assessment": "Not Applicable",
        "Funding & Liquidity Control Assessment Rationale": "N/A.",
        "Reputational Inherent Risk": "Medium",
        "Reputational Inherent Risk Rationale": "Reputation risk medium. Brand exposure through merchant relationships. Media coverage neutral.",
        "Reputational Control Assessment": "Well Controlled",
        "Reputational Control Assessment Rationale": "PR monitoring active.",
        "Model Inherent Risk": "Not Applicable",
        "Model Inherent Risk Rationale": "N/A — no proprietary models.",
        "Model Control Assessment": "Not Applicable",
        "Model Control Assessment Rationale": "N/A.",
        "Third Party Inherent Risk": "High",
        "Third Party Control Assessment": "Insufficiently Controlled",
        "Financial Reporting Inherent Risk": "Low",
        "Financial Reporting Inherent Risk Rationale": "Financial reporting low. Standard accounting processes.",
        "Financial Reporting Control Assessment": "Well Controlled",
        "Financial Reporting Control Assessment Rationale": "Automated.",
        "External Fraud Inherent Risk": "Critical",
        "External Fraud Inherent Risk Rationale": "External fraud risk critical. Counterfeit card schemes increasing. Account takeover via merchant channels. Identity theft through payment terminals.",
        "External Fraud Control Assessment": "Insufficiently Controlled",
        "External Fraud Control Assessment Rationale": "Fraud detection gaps in new payment methods.",
        "Information Technology Inherent Risk": "Medium",
        "Information Technology Control Assessment": "Moderately Controlled",
        "Information Security Inherent Risk": "High",
        "Information Security Control Assessment": "Moderately Controlled",
        # INTENTIONALLY VAGUE — should trigger default_no_evidence / review
        "Operational Inherent Risk": "High",
        "Operational Inherent Risk Rationale": "The overall risk level is elevated across the entity.",
        "Operational Control Assessment": "New/Not Tested Yet",
        "Operational Control Assessment Rationale": "New controls being implemented.",
        "Compliance Inherent Risk": "High",
        "Compliance Inherent Risk Rationale": (
            "Compliance risk high. AML monitoring gaps identified. Sanctions screening incomplete. "
            "Financial crime exposure from cross-border transactions. KYC procedures need updating. "
            "Consumer complaint handling under review. Fair lending analysis pending. "
            "Prudential regulatory commitments tracked but behind schedule."
        ),
        "Compliance Control Assessment": "Moderately Controlled",
        "Compliance Control Assessment Rationale": "Compliance program in place but needs enhancement.",
        "Country Inherent Risk": "High",
        "Country Inherent Risk Rationale": "Country risk high. Operations in 15 markets. Regulatory environment variable.",
        "Country Control Assessment": "Moderately Controlled",
        "Country Control Assessment Rationale": "Country risk monitoring quarterly.",
        "PRIMARY IT APPLICATIONS (MAPPED)": "App-400\nApp-401\nApp-402",
        "SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)": "App-500",
        "PRIMARY TLM THIRD PARTY ENGAGEMENT": "Vendor-D\nVendor-E",
        "SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)": "Vendor-F",
    },

    # --- AE-4: Control contradictions — Well Controlled but open High findings ---
    {
        "Audit Entity ID": "AE-4", "Audit Entity Name": "Digital Banking Platform",
        "Audit Entity Status": "Active", "Core Audit Team": "Team Delta",
        "Audit Entity Overview": "Digital-first banking platform for consumer and small business.",
        "Audit Entity Overall Inherent Risk Rating": "High",
        "Audit Entity Overall Residual Risk Rating": "High",
        "Credit Inherent Risk": "Medium",
        "Credit Inherent Risk Rationale": "Consumer credit card exposure. Small business lending growing. Cardmember defaults stable.",
        "Credit Control Assessment": "Well Controlled",
        "Credit Control Assessment Rationale": "Strong credit monitoring.",
        "Market Inherent Risk": "Low",
        "Market Inherent Risk Rationale": "Market risk low. No trading activities.",
        "Market Control Assessment": "Well Controlled",
        "Market Control Assessment Rationale": "No active market risk.",
        "Strategic & Business Inherent Risk": "High",
        "Strategic & Business Inherent Risk Rationale": (
            "Earnings risk high. Revenue heavily dependent on fee income from digital products. "
            "Capital allocation focused on technology buildout. CCAR stress test adequate."
        ),
        "Strategic & Business Control Assessment": "Moderately Controlled",
        "Strategic & Business Control Assessment Rationale": "Strategic oversight improving.",
        "Funding & Liquidity Inherent Risk": "Not Applicable",
        "Funding & Liquidity Inherent Risk Rationale": "N/A.",
        "Funding & Liquidity Control Assessment": "Not Applicable",
        "Funding & Liquidity Control Assessment Rationale": "N/A.",
        "Reputational Inherent Risk": "High",
        "Reputational Inherent Risk Rationale": "Reputation risk high. Digital brand exposure. Social media amplification risk.",
        "Reputational Control Assessment": "Moderately Controlled",
        "Reputational Control Assessment Rationale": "Social media monitoring.",
        "Model Inherent Risk": "Medium",
        "Model Inherent Risk Rationale": "Model risk medium. Credit scoring and fraud models in production. Validation current.",
        "Model Control Assessment": "Well Controlled",
        "Model Control Assessment Rationale": "MRM program effective.",
        "Third Party Inherent Risk": "High",
        "Third Party Control Assessment": "Well Controlled",  # CONTRADICTION — open High finding
        "Financial Reporting Inherent Risk": "Low",
        "Financial Reporting Inherent Risk Rationale": "Financial reporting low risk.",
        "Financial Reporting Control Assessment": "Well Controlled",
        "Financial Reporting Control Assessment Rationale": "Standard processes.",
        "External Fraud Inherent Risk": "Critical",
        "External Fraud Inherent Risk Rationale": "External fraud critical. Account takeover surge in digital channels. Fraud scheme sophistication increasing.",
        "External Fraud Control Assessment": "Well Controlled",  # CONTRADICTION — open High finding
        "External Fraud Control Assessment Rationale": "Fraud controls in place but tested before digital surge.",
        "Information Technology Inherent Risk": "High",
        "Information Technology Control Assessment": "Well Controlled",  # CONTRADICTION — open High finding
        "Information Security Inherent Risk": "Critical",
        "Information Security Control Assessment": "Well Controlled",  # CONTRADICTION — open High finding
        "Operational Inherent Risk": "Medium",
        "Operational Inherent Risk Rationale": (
            "Operational risk medium. Process execution effective for core products. "
            "Business continuity tested. Human capital stable. "
            "Conduct program in place. Privacy controls adequate."
        ),
        "Operational Control Assessment": "Well Controlled",
        "Operational Control Assessment Rationale": "Operational controls well managed.",
        "Compliance Inherent Risk": "Medium",
        "Compliance Inherent Risk Rationale": (
            "Compliance risk medium. Regulatory program effective. "
            "Consumer protection adequate. Fair lending current. "
            "Financial crimes monitoring operational. Prudential requirements met."
        ),
        "Compliance Control Assessment": "Well Controlled",
        "Compliance Control Assessment Rationale": "Compliance well controlled.",
        "Country Inherent Risk": "Not Applicable",
        "Country Inherent Risk Rationale": "N/A — domestic only.",
        "Country Control Assessment": "Not Applicable",
        "Country Control Assessment Rationale": "N/A.",
        "PRIMARY IT APPLICATIONS (MAPPED)": "App-600\nApp-601",
        "SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)": "App-700\nApp-701",
        "PRIMARY TLM THIRD PARTY ENGAGEMENT": "Vendor-G",
        "SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)": "Vendor-H",
    },

    # --- AE-5: Sparse data — minimal rationale, few sub-risks, should produce many review items ---
    {
        "Audit Entity ID": "AE-5", "Audit Entity Name": "New Markets Expansion",
        "Audit Entity Status": "Active", "Core Audit Team": "Team Alpha",
        "Audit Entity Overview": "New market entry initiative — early stage.",
        "Audit Entity Overall Inherent Risk Rating": "High",
        "Audit Entity Overall Residual Risk Rating": "High",
        "Credit Inherent Risk": "Medium",
        "Credit Inherent Risk Rationale": "Credit exposure building. Portfolio small but growing.",
        "Credit Control Assessment": "New/Not Tested Yet",
        "Credit Control Assessment Rationale": "Controls under development.",
        "Market Inherent Risk": "Medium",
        "Market Inherent Risk Rationale": "Some exposure exists.",
        "Market Control Assessment": "New/Not Tested Yet",
        "Market Control Assessment Rationale": "Controls new.",
        "Strategic & Business Inherent Risk": "High",
        "Strategic & Business Inherent Risk Rationale": "Significant earnings risk. Revenue uncertain. Capital investment substantial.",
        "Strategic & Business Control Assessment": "Moderately Controlled",
        "Strategic & Business Control Assessment Rationale": "Strategic oversight from leadership.",
        "Funding & Liquidity Inherent Risk": "Medium",
        "Funding & Liquidity Inherent Risk Rationale": "Liquidity adequate. Funding through parent. Cash flow from operations limited.",
        "Funding & Liquidity Control Assessment": "Well Controlled",
        "Funding & Liquidity Control Assessment Rationale": "Parent entity provides liquidity.",
        "Reputational Inherent Risk": "Medium",
        "Reputational Inherent Risk Rationale": "Brand risk from market entry. Stakeholder expectations high.",
        "Reputational Control Assessment": "New/Not Tested Yet",
        "Reputational Control Assessment Rationale": "PR plan being developed.",
        "Model Inherent Risk": "Not Applicable",
        "Model Inherent Risk Rationale": "N/A — no models in production yet.",
        "Model Control Assessment": "Not Applicable",
        "Model Control Assessment Rationale": "N/A.",
        "Third Party Inherent Risk": "High",
        "Third Party Control Assessment": "New/Not Tested Yet",
        "Financial Reporting Inherent Risk": "Medium",
        "Financial Reporting Inherent Risk Rationale": "Regulatory reporting for new market. SEC requirements apply.",
        "Financial Reporting Control Assessment": "Moderately Controlled",
        "Financial Reporting Control Assessment Rationale": "Reporting framework being established.",
        "External Fraud Inherent Risk": "High",
        "External Fraud Inherent Risk Rationale": "Fraud risk high. New market channels untested. Identity theft controls being built.",
        "External Fraud Control Assessment": "New/Not Tested Yet",
        "External Fraud Control Assessment Rationale": "Fraud controls under development.",
        "Information Technology Inherent Risk": "High",
        "Information Technology Control Assessment": "New/Not Tested Yet",
        "Information Security Inherent Risk": "High",
        "Information Security Control Assessment": "New/Not Tested Yet",
        # INTENTIONALLY VAGUE — no useful keywords
        "Operational Inherent Risk": "High",
        "Operational Inherent Risk Rationale": "Overall operational risk is high for this new initiative.",
        "Operational Control Assessment": "New/Not Tested Yet",
        "Operational Control Assessment Rationale": "Controls being developed across all areas.",
        "Compliance Inherent Risk": "High",
        "Compliance Inherent Risk Rationale": "Compliance risk high. Regulatory landscape unfamiliar. Requirements being mapped.",
        "Compliance Control Assessment": "New/Not Tested Yet",
        "Compliance Control Assessment Rationale": "Compliance program being built.",
        "Country Inherent Risk": "High",
        "Country Inherent Risk Rationale": "Country risk high. Entering 3 new markets with different regulatory regimes.",
        "Country Control Assessment": "Moderately Controlled",
        "Country Control Assessment Rationale": "Country risk assessment completed.",
        "PRIMARY IT APPLICATIONS (MAPPED)": "",
        "SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)": "",
        "PRIMARY TLM THIRD PARTY ENGAGEMENT": "Vendor-I",
        "SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)": "",
    },
]

legacy_df = pd.DataFrame(ENTITY_DATA)
timestamp = datetime.now().strftime("%m%d%Y%I%M%p")
filename = f"legacy_risk_data_{timestamp}.xlsx"
legacy_df.to_excel(OUTPUT_DIR / filename, index=False)
print(f"Created {filename}: {len(legacy_df)} entities, {len(legacy_df.columns)} columns")

# =============================================================================
# File 2: sub_risk_descriptions_{datetime}.xlsx
# =============================================================================
SUB_RISKS = [
    # AE-1: Good coverage
    ("AE-1", "Credit", "CR-101", "Consumer Default Risk",
     "Consumer credit card default risk from high-balance cardmember accounts in personal retail segment", "High"),
    ("AE-1", "Credit", "CR-102", "Small Business Concentration",
     "Small business lending concentration in retail sector with individual cardmember exposure", "Medium"),
    ("AE-1", "Operational", "OP-101", "Manual Reconciliation Error",
     "Manual transaction reconciliation process prone to human error and control failure", "Medium"),
    ("AE-1", "Operational", "OP-102", "BCP Gap",
     "Business continuity plan not tested for pandemic scenario, disaster recovery needs improvement", "High"),
    ("AE-1", "Operational", "OP-103", "Workforce Attrition",
     "Employee attrition and retention challenges in technology workforce, hiring below targets", "Medium"),
    ("AE-1", "Operational", "OP-104", "Privacy Program Gap",
     "Privacy compliance program gaps, personal data handling procedures need updating, GDPR exposure", "Medium"),
    ("AE-1", "Information Technology", "IT-101", "Legacy Platform",
     "Legacy platform stability risk from aging infrastructure, system capacity constraints", "High"),
    ("AE-1", "Information Technology", "IT-102", "Data Governance",
     "Data governance gaps in customer data management, data quality issues in reporting", "Medium"),
    ("AE-1", "Compliance", "CO-101", "AML Program",
     "AML monitoring program effective. BSA requirements met. Sanctions screening operational.", "Low"),

    # AE-2: Minimal sub-risks (treasury)
    ("AE-2", "Market", "MK-201", "Rate Sensitivity",
     "Interest rate repricing risk on treasury portfolio, yield curve sensitivity, basis risk", "High"),

    # AE-3: Good Compliance coverage but intentionally NO Operational sub-risks
    ("AE-3", "Credit", "CR-301", "Merchant Credit",
     "Commercial merchant credit exposure, corporate counterpart risk from large merchants", "Medium"),
    ("AE-3", "Compliance", "CO-301", "AML Gaps",
     "AML monitoring gaps in cross-border merchant transactions, suspicious activity detection delayed, financial crime exposure", "High"),
    ("AE-3", "Compliance", "CO-302", "Consumer Protection",
     "Consumer complaint handling under review, fair lending analysis pending for new products, UDAAP risk", "Medium"),
    ("AE-3", "Compliance", "CO-303", "Prudential Tracking",
     "Prudential regulatory commitment tracking behind schedule, enterprise compliance program gaps, examination readiness", "Medium"),
    # Multi-value L1
    ("AE-3", "External Fraud\nOperational", "EF-301", "Payment Terminal Fraud",
     "Counterfeit card scheme through payment terminals, fraud detection gaps in merchant channels", "High"),

    # AE-4: Sub-risks that should trigger control contradiction awareness
    ("AE-4", "External Fraud", "EF-401", "Digital Channel Fraud",
     "Account takeover surge in digital channels, identity theft via synthetic IDs, fraud scheme sophistication", "High"),
    ("AE-4", "Information Technology", "IT-401", "Platform Performance",
     "Technology platform performance issues, system capacity risk during peak, application stability concerns", "High"),
    ("AE-4", "Information Technology", "IT-402", "Data Pipeline",
     "Data quality issues in transaction processing pipeline, data management controls insufficient", "Medium"),
    ("AE-4", "Strategic & Business", "SB-401", "Fee Income Dependency",
     "Revenue heavily dependent on fee income, earnings concentration risk, pricing pressure", "High"),

    # AE-5: Very sparse — should produce more review items
    ("AE-5", "Credit", "CR-501", "New Market Credit",
     "Credit exposure building in new markets, portfolio characteristics unknown", "Medium"),
]

sub_risk_rows = []
for eid, l1_category, risk_id, title, desc, rating in SUB_RISKS:
    sub_risk_rows.append({
        "Audit Entity ID": eid,
        "Key Risk ID": risk_id,
        "Key Risk Title": title,
        "Key Risk Description": desc,
        "Level 1 Risk Category": l1_category,
        "Inherent Risk Rating": rating,
    })

sub_risk_df = pd.DataFrame(sub_risk_rows)
timestamp = datetime.now().strftime("%m%d%Y%I%M%p")
sub_risk_df.to_excel(OUTPUT_DIR / f"sub_risk_descriptions_{timestamp}.xlsx", index=False)
print(f"Created sub_risk_descriptions_{timestamp}.xlsx: {len(sub_risk_df)} sub-risks")

# =============================================================================
# File 3: findings_data_{datetime}.xlsx
# =============================================================================
FINDINGS = [
    # AE-1: Findings that confirm applicability and test dedup
    ("AE-1", "F-1001", "Data\nTechnology", "High", "Open",
     "Data quality controls missing in customer onboarding",
     "J. Smith", "Approved",
     "Data quality controls not applied during onboarding, incomplete records in downstream systems.",
     "2025 Cards Annual Audit", "Fieldwork", "2026-06-30"),
    ("AE-1", "F-1002", "Model", "High", "Open",
     "Credit scoring model validation overdue",
     "J. Smith", "Approved",
     "Two credit scoring models past validation due date. Algorithm performance drifting.",
     "2025 Cards Model Review", "Fieldwork", "2026-05-15"),

    # AE-3: Findings that should trigger control contradiction (Well Controlled + High finding)
    ("AE-3", "F-3001", "Fraud (External and Internal)", "High", "Open",
     "Payment terminal fraud detection gap",
     "A. Williams", "Approved",
     "Counterfeit card fraud through merchant payment terminals not detected by current controls.",
     "2025 GMS Fraud Assessment", "Fieldwork", "2026-04-30"),
    ("AE-3", "F-3002", "Third Party", "High", "Open",
     "Critical vendor risk assessment overdue",
     "A. Williams", "Approved",
     "Tier-1 payment processor vendor risk assessment 6 months overdue.",
     "2025 GMS Vendor Review", "Fieldwork", "2026-03-31"),
    ("AE-3", "F-3003", "Financial crimes", "High", "In Sustainability",
     "Cross-border AML monitoring gap",
     "A. Williams", "Approved",
     "AML transaction monitoring rules not updated for cross-border merchant flows.",
     "2025 GMS Compliance Review", "Continuous Monitoring", "2026-05-31"),
    ("AE-3", "F-3004", "Privacy", "Medium", "Open",
     "Merchant data handling non-compliant",
     "A. Williams", "Approved",
     "Merchant PII handling does not meet updated privacy regulation requirements.",
     "2025 GMS Privacy Review", "Fieldwork", "2026-07-31"),

    # AE-4: Control contradiction scenarios — Well Controlled + High/Critical findings
    ("AE-4", "F-4001", "Fraud (External and Internal)", "Critical", "Open",
     "Synthetic identity fraud in digital onboarding",
     "R. Chen", "Approved",
     "Synthetic identity fraud bypassing digital onboarding controls. Account takeover rate 3x baseline.",
     "2025 Digital Banking Fraud Review", "Fieldwork", "2026-04-15"),
    ("AE-4", "F-4002", "Third Party", "High", "In Validation",
     "Payment processor SLA breach",
     "R. Chen", "Approved",
     "Primary payment processor SLA breached 4 times in Q4. No remediation plan from vendor.",
     "2025 Digital Banking Vendor Review", "Fieldwork", "2026-05-01"),
    ("AE-4", "F-4003", "Technology", "High", "Open",
     "Platform outage during peak period",
     "R. Chen", "Approved",
     "Digital banking platform experienced 4-hour outage during peak transaction period.",
     "2025 Digital Banking IT Review", "Fieldwork", "2026-03-31"),
    ("AE-4", "F-4004", "Information and Cyber Security", "High", "Open",
     "API vulnerability in mobile banking",
     "R. Chen", "Approved",
     "Critical API vulnerability in mobile banking application. Unauthorized access possible.",
     "2025 Digital Banking Cyber Review", "Fieldwork", "2026-04-30"),

    # AE-5: Minimal findings
    ("AE-5", "F-5001", "Processing, Execution and Change", "Medium", "Open",
     "New market onboarding process errors",
     "K. Patel", "Approved",
     "Manual onboarding process for new market producing data entry errors.",
     "2025 New Markets Readiness Review", "Fieldwork", "2026-06-30"),

    # Edge cases
    # Closed finding — should NOT trigger control contradiction
    ("AE-1", "F-1003", "Technology", "High", "Closed",
     "Legacy system migration completed",
     "J. Smith", "Approved",
     "Previously identified legacy migration risk has been remediated.",
     "2024 Cards IT Review", "Fieldwork", "2025-12-31"),

    # Cancelled finding — should be excluded
    ("AE-3", "F-3005", "Data", "High", "Cancelled",
     "Data migration finding withdrawn",
     "A. Williams", "Approved",
     "Finding withdrawn after reassessment.",
     "2025 GMS Data Review", "Fieldwork", ""),

    # Not yet approved — should be filtered out
    ("AE-4", "F-4005", "Human Capital", "High", "Not Started",
     "Digital talent retention risk",
     "R. Chen", "Pending L1 Review",
     "Draft finding — talent retention risk in digital engineering team.",
     "2026 Digital Banking HR Review", "Fieldwork", ""),

    # Blank severity — should be excluded
    ("AE-5", "F-5002", "Data", "", "Open",
     "Data classification gaps",
     "K. Patel", "Approved",
     "Data classification incomplete — severity not yet assessed.",
     "2025 New Markets Data Review", "Fieldwork", ""),
]

findings_rows = []
for (eid, fid, l2_risks, severity, status, name, leader,
     approval, description, engagement, source, remediation) in FINDINGS:
    findings_rows.append({
        "Audit Entity ID": eid,
        "Finding ID": fid,
        "Risk Dimension Categories": l2_risks,
        "Final Reportable Finding Risk Rating": severity,
        "Finding Status": status,
        "Finding Name": name,
        "Audit Leader": leader,
        "Finding Approval Status": approval,
        "Finding Description": description,
        "Audit Engagement Name": engagement,
        "Source": source,
        "Actual Remediation Date": remediation,
    })

findings_df = pd.DataFrame(findings_rows)
timestamp = datetime.now().strftime("%m%d%Y%I%M%p")
findings_df.to_excel(OUTPUT_DIR / f"findings_data_{timestamp}.xlsx", index=False)
print(f"Created findings_data_{timestamp}.xlsx: {len(findings_df)} findings")
print(f"  Expected filters:")
print(f"  - 1 not approved (F-4005) -> excluded")
print(f"  - 1 blank severity (F-5002) -> excluded")
print(f"  - 1 closed (F-1003) -> included but won't trigger contradiction")
print(f"  - 1 cancelled (F-3005) -> included but inactive status")
print(f"  Expected scenarios:")
print(f"  - AE-1: findings confirm Data+Technology+Model, dedup with crosswalk")
print(f"  - AE-3: vague Operational rationale -> review items; findings confirm Fraud+Third Party+Financial crimes+Privacy")
print(f"  - AE-4: Well Controlled + High/Critical findings -> control contradiction flags")
print(f"  - AE-5: sparse data -> review items for Operational L2s")
print(f"  - AE-2: many N/A pillars, minimal findings")

print("\nDone! All test data files created in data/input/")
