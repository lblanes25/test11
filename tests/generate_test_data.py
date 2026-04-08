"""Generate comprehensive dummy test data for the Risk Taxonomy Transformer.

Creates three files in data/input/ designed to exercise every code path:

ENTITIES (10):
  AE-1: Fully documented, all pillars rated, rich rationale with dimension parsing
  AE-2: Treasury — many N/A pillars, minimal sub-risks
  AE-3: Vague Operational rationale (triggers all-candidates review)
  AE-4: Control contradictions (Well Controlled + High/Critical findings)
  AE-5: Sparse data — triggers review items across multiple pillars
  AE-6: Everything applicable — keywords match every multi-target L2
  AE-7: Everything N/A — all pillars rated Not Applicable
  AE-8: Dimension parsing edge cases (various L:H, abbreviation formats)
  AE-9: Dedup stress test — multiple pillars map to same L2s with different ratings
  AE-10: Auxiliary risk and application flag test entity

FINDINGS EDGE CASES:
  - Approved + all statuses (Open, In Validation, In Sustainability, Closed, Cancelled, Not Started)
  - Not approved (In Progress, Pending L1 Review, Pending L2 Review)
  - Blank severity
  - Multi-value L2 (newline separated)
  - L2 names needing normalization (L1 prefix, aliases, slight misspellings)
  - Control contradiction triggers (Well Controlled + High/Critical)

SUB-RISK EDGE CASES:
  - Multi-value L1 (newline separated)
  - Blank L1 category
  - Keywords matching multiple L2s
  - No keyword matches at all
  - Sub-risk with nan description
"""

import pandas as pd
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "input"

NO_RATIONALE_PILLARS = ("Information Technology", "Information Security", "Third Party")

PILLARS = [
    "Credit", "Market", "Strategic & Business", "Funding & Liquidity",
    "Reputational", "Model", "Third Party", "Financial Reporting",
    "External Fraud", "Information Technology", "Information Security",
    "Operational", "Compliance", "Country",
]


def _make_entity(eid, name, team, status, overview, overall_ir, overall_rr,
                 pillar_data, audit_leader="", pga="",
                 primary_it="", secondary_it="",
                 primary_tp="", secondary_tp="",
                 axp_aux="", aenb_aux="",
                 last_engagement_rating="", last_audit_completion_date=""):
    """Build one entity row dict."""
    row = {
        "Audit Entity ID": eid,
        "Audit Entity Name": name,
        "Audit Entity Status": status,
        "Audit Leader": audit_leader,
        "PGA/ASL": pga,
        "Core Audit Team": team,
        "Audit Entity Overview": overview,
        "Audit Entity Overall Inherent Risk Rating": overall_ir,
        "Audit Entity Overall Residual Risk Rating": overall_rr,
        "Last Engagement Rating": last_engagement_rating,
        "Last Audit Completion Date": last_audit_completion_date,
    }
    for pillar in PILLARS:
        data = pillar_data.get(pillar, {})
        row[f"{pillar} Inherent Risk"] = data.get("rating", "Not Applicable")
        row[f"{pillar} Control Assessment"] = data.get("control", "Not Applicable")
        if pillar not in NO_RATIONALE_PILLARS:
            row[f"{pillar} Inherent Risk Rationale"] = data.get("rationale", "")
            row[f"{pillar} Control Assessment Rationale"] = data.get("control_rationale", "")

    row["PRIMARY IT APPLICATIONS (MAPPED)"] = primary_it
    row["SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)"] = secondary_it
    row["PRIMARY TLM THIRD PARTY ENGAGEMENT"] = primary_tp
    row["SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)"] = secondary_tp
    row["AXP Auxiliary Risk Dimensions"] = axp_aux
    row["AENB Auxiliary Risk Dimensions"] = aenb_aux
    return row


# =============================================================================
# ENTITY DATA
# =============================================================================

ENTITIES = [
    # --- AE-1: Fully documented, rich rationale, dimension parsing ---
    _make_entity(
        "AE-1", "North America Cards", "Team Alpha", "Active",
        "Largest consumer cards portfolio in NAM.",
        "High", "Medium",
        {
            "Credit": {
                "rating": "High",
                "rationale": (
                    "Consumer credit exposure is high. Likelihood is high, impact is critical. "
                    "Cardmember default rates trending upward in small business segment. "
                    "Retail personal lending concentrated in high-balance individual accounts."
                ),
                "control": "Moderately Controlled",
                "control_rationale": "Monthly monitoring in place. Portfolio limits enforced.",
            },
            "Market": {
                "rating": "Medium",
                "rationale": (
                    "Interest rate sensitivity is medium. Repricing risk on variable-rate products. "
                    "Yield curve flattening creates NII pressure. No significant FX exposure."
                ),
                "control": "Well Controlled",
                "control_rationale": "Hedging program effective.",
            },
            "Strategic & Business": {
                "rating": "Medium",
                "rationale": (
                    "Earnings outlook is medium. Revenue growth constrained by competitive pressure. "
                    "Fee income declining. Product diversification efforts underway. "
                    "Capital adequacy meets requirements. CCAR stress test passed."
                ),
                "control": "Well Controlled",
                "control_rationale": "Strategic planning process well controlled.",
            },
            "Funding & Liquidity": {
                "rating": "Low",
                "rationale": "Liquidity position is low risk. Cash flow stable. Deposit base diversified.",
                "control": "Well Controlled",
                "control_rationale": "Liquidity controls well controlled.",
            },
            "Reputational": {
                "rating": "Medium",
                "rationale": "Reputation risk medium. Brand perception stable. Stakeholder trust maintained.",
                "control": "Moderately Controlled",
                "control_rationale": "Media monitoring in place.",
            },
            "Model": {
                "rating": "High",
                "rationale": "Model risk high. Validation backlog for 3 models. Algorithm performance drifting. MRM review pending.",
                "control": "Insufficiently Controlled",
                "control_rationale": "MRM team understaffed. Backtest schedule not met.",
            },
            "Third Party": {"rating": "Medium", "control": "Moderately Controlled"},
            "Financial Reporting": {
                "rating": "Low",
                "rationale": "Financial reporting risk low. GAAP compliance maintained. No restatements. SEC filing on time.",
                "control": "Well Controlled",
                "control_rationale": "Automated reporting controls.",
            },
            "External Fraud": {
                "rating": "High",
                "rationale": "External fraud risk high. Account takeover attempts increasing. Identity theft schemes detected. Counterfeit card activity rising.",
                "control": "Moderately Controlled",
                "control_rationale": "Fraud detection systems operational but gaps in digital channel.",
            },
            "Information Technology": {"rating": "High", "control": "Moderately Controlled"},
            "Information Security": {"rating": "High", "control": "Moderately Controlled"},
            "Operational": {
                "rating": "High",
                "rationale": (
                    "Operational risk is high. Likelihood is high, impact is high. "
                    "Process execution has gaps. Business continuity plan tested but disaster recovery "
                    "needs improvement. Employee attrition in technology workforce exceeding targets. "
                    "Conduct training completed. Privacy compliance program operational. "
                    "Data risk from volume growth in transaction processing."
                ),
                "control": "Moderately Controlled",
                "control_rationale": "Controls moderately controlled across operational areas.",
            },
            "Compliance": {
                "rating": "Medium",
                "rationale": (
                    "Compliance risk medium. Regulatory examination findings resolved. "
                    "Enterprise compliance program effective. Consumer protection adequate. "
                    "Financial crimes monitoring operational. AML/BSA requirements met. "
                    "Prudential oversight satisfactory. KYC procedures followed."
                ),
                "control": "Well Controlled",
                "control_rationale": "Compliance controls well controlled.",
            },
            "Country": {
                "rating": "Low",
                "rationale": "Country risk low. Domestic operations only.",
                "control": "Well Controlled",
                "control_rationale": "N/A — domestic only.",
            },
        },
        audit_leader="J. Smith", pga="S. Williams",
        primary_it="App-100\nApp-101", secondary_it="App-200",
        primary_tp="Vendor-A", secondary_tp="Vendor-B\nVendor-C",
        axp_aux="Operational - Third Party\nProcessing, Execution and Change",
        aenb_aux="Credit - Commercial",
        last_engagement_rating="Satisfactory",
        last_audit_completion_date="2025-09-15",
    ),

    # --- AE-2: Treasury — many N/A pillars ---
    _make_entity(
        "AE-2", "Treasury Operations", "Team Bravo", "Active",
        "Internal treasury and funding operations.",
        "Low", "Low",
        {
            "Credit": {"rating": "Not Applicable", "rationale": "N/A — no lending.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Market": {
                "rating": "High",
                "rationale": (
                    "Interest rate risk is high. Repricing risk on treasury portfolio. "
                    "Yield curve sensitivity elevated. FX exposure from international funding. "
                    "Currency volatility in emerging markets. Price risk from position taking."
                ),
                "control": "Moderately Controlled",
                "control_rationale": "Hedging partially effective.",
            },
            "Strategic & Business": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Funding & Liquidity": {
                "rating": "High",
                "rationale": "Liquidity risk high. Funding concentration. Cash flow volatility. Borrowing capacity stretched. Obligation management critical.",
                "control": "Moderately Controlled",
                "control_rationale": "Liquidity monitoring daily.",
            },
            "Reputational": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Model": {
                "rating": "Medium",
                "rationale": "Model risk medium. Treasury models validated annually. Methodology sound. Algorithm performance stable.",
                "control": "Well Controlled",
                "control_rationale": "Model governance framework in place.",
            },
            "Third Party": {"rating": "Not Applicable", "control": "Not Applicable"},
            "Financial Reporting": {
                "rating": "Medium",
                "rationale": "Financial reporting risk medium. Regulatory report timeliness adequate. GAAP accounting compliant. 10-K and 10-Q on schedule.",
                "control": "Well Controlled",
                "control_rationale": "Automated controls.",
            },
            "External Fraud": {"rating": "Not Applicable", "rationale": "N/A — no customer-facing channels.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Information Technology": {"rating": "Low", "control": "Well Controlled"},
            "Information Security": {"rating": "Low", "control": "Well Controlled"},
            "Operational": {
                "rating": "Low",
                "rationale": "Operational risk low. Processes automated. Settlement reconciliation effective. No significant manual processing.",
                "control": "Well Controlled",
                "control_rationale": "Controls well controlled.",
            },
            "Compliance": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Country": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
        },
        audit_leader="M. Johnson", pga="S. Williams",
        primary_it="App-300",
        last_engagement_rating="Requires Attention",
        last_audit_completion_date="2025-03-01",
    ),

    # --- AE-3: Vague Operational rationale (triggers all-candidates review) ---
    _make_entity(
        "AE-3", "Global Merchant Services", "Team Charlie", "Active",
        "Merchant acquiring and payment acceptance.",
        "High", "Medium",
        {
            "Credit": {
                "rating": "Medium",
                "rationale": "Commercial credit exposure to merchant portfolio. Corporate counterpart risk from large merchants.",
                "control": "Moderately Controlled",
                "control_rationale": "Credit monitoring in place.",
            },
            "Market": {
                "rating": "Low",
                "rationale": "Market risk low. Minimal exposure.",
                "control": "Well Controlled",
                "control_rationale": "No active positions.",
            },
            "Strategic & Business": {
                "rating": "Medium",
                "rationale": "Earnings pressure from fee compression. Revenue stable but margin declining.",
                "control": "Moderately Controlled",
                "control_rationale": "Strategic review ongoing.",
            },
            "Funding & Liquidity": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Reputational": {
                "rating": "Medium",
                "rationale": "Reputation risk medium. Brand exposure through merchant relationships. Media coverage neutral. Stakeholder trust stable.",
                "control": "Well Controlled",
                "control_rationale": "PR monitoring active.",
            },
            "Model": {"rating": "Not Applicable", "rationale": "N/A — no proprietary models.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Third Party": {"rating": "High", "control": "Insufficiently Controlled"},
            "Financial Reporting": {
                "rating": "Low",
                "rationale": "Financial reporting low. Standard accounting processes. Regulatory report on time.",
                "control": "Well Controlled",
                "control_rationale": "Automated.",
            },
            "External Fraud": {
                "rating": "Critical",
                "rationale": "External fraud risk critical. Counterfeit card schemes increasing. Account takeover via merchant channels. Identity theft through payment terminals. Fraud detection gaps.",
                "control": "Insufficiently Controlled",
                "control_rationale": "Fraud controls gaps in new payment methods.",
            },
            "Information Technology": {"rating": "Medium", "control": "Moderately Controlled"},
            "Information Security": {"rating": "High", "control": "Moderately Controlled"},
            # INTENTIONALLY VAGUE — should trigger no_evidence_all_candidates
            "Operational": {
                "rating": "High",
                "rationale": "The overall risk level is elevated across the entity.",
                "control": "New/Not Tested Yet",
                "control_rationale": "New controls being implemented.",
            },
            "Compliance": {
                "rating": "High",
                "rationale": (
                    "Compliance risk high. AML monitoring gaps identified. Sanctions screening incomplete. "
                    "Financial crime exposure from cross-border transactions. KYC procedures need updating. "
                    "Consumer complaint handling under review. Fair lending analysis pending. "
                    "Prudential regulatory commitments tracked but behind schedule."
                ),
                "control": "Moderately Controlled",
                "control_rationale": "Compliance program in place but needs enhancement.",
            },
            "Country": {
                "rating": "High",
                "rationale": "Country risk high. Operations in 15 markets. Geopolitical exposure significant.",
                "control": "Moderately Controlled",
                "control_rationale": "Country risk monitoring quarterly.",
            },
        },
        audit_leader="A. Williams", pga="R. Patel",
        primary_it="App-400\nApp-401\nApp-402", secondary_it="App-500",
        primary_tp="Vendor-D\nVendor-E", secondary_tp="Vendor-F",
        axp_aux="Prudential & Bank Admin Compliance\nOperational - Third Party\nProcessing, Execution and Change",
        last_engagement_rating="Satisfactory",
        last_audit_completion_date="2024-06-15",
    ),

    # --- AE-4: Control contradictions ---
    _make_entity(
        "AE-4", "Digital Banking Platform", "Team Delta", "Active",
        "Digital-first banking platform.",
        "High", "High",
        {
            "Credit": {
                "rating": "Medium",
                "rationale": "Consumer credit card exposure. Small business lending growing. Cardmember defaults stable.",
                "control": "Well Controlled",
                "control_rationale": "Strong credit monitoring.",
            },
            "Market": {
                "rating": "Low",
                "rationale": "Market risk low. No trading activities.",
                "control": "Well Controlled",
                "control_rationale": "No active market risk.",
            },
            "Strategic & Business": {
                "rating": "High",
                "rationale": "Earnings risk high. Revenue dependent on fee income. Capital allocation focused on tech. CCAR stress test adequate.",
                "control": "Moderately Controlled",
                "control_rationale": "Strategic oversight improving.",
            },
            "Funding & Liquidity": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Reputational": {
                "rating": "High",
                "rationale": "Reputation risk high. Digital brand exposure. Social media amplification. Stakeholder trust sensitive.",
                "control": "Moderately Controlled",
                "control_rationale": "Social media monitoring.",
            },
            "Model": {
                "rating": "Medium",
                "rationale": "Model risk medium. Credit scoring and fraud models in production. Validation current. Model governance adequate.",
                "control": "Well Controlled",
                "control_rationale": "MRM program effective.",
            },
            "Third Party": {"rating": "High", "control": "Well Controlled"},  # CONTRADICTION — open High finding
            "Financial Reporting": {
                "rating": "Low",
                "rationale": "Financial reporting low risk. Standard processes.",
                "control": "Well Controlled",
                "control_rationale": "Standard processes.",
            },
            "External Fraud": {
                "rating": "Critical",
                "rationale": "External fraud critical. Account takeover surge in digital channels. Fraud scheme sophistication increasing. Identity theft via synthetic IDs.",
                "control": "Well Controlled",  # CONTRADICTION — open Critical finding
                "control_rationale": "Fraud controls in place but tested before digital surge.",
            },
            "Information Technology": {"rating": "High", "control": "Well Controlled"},  # CONTRADICTION
            "Information Security": {"rating": "Critical", "control": "Well Controlled"},  # CONTRADICTION
            "Operational": {
                "rating": "Medium",
                "rationale": (
                    "Operational risk medium. Process execution effective for core products. "
                    "Business continuity tested. Human capital stable. Workforce retention adequate. "
                    "Conduct program in place. Privacy controls adequate."
                ),
                "control": "Well Controlled",
                "control_rationale": "Operational controls well managed.",
            },
            "Compliance": {
                "rating": "Medium",
                "rationale": (
                    "Compliance risk medium. Regulatory program effective. Consumer protection adequate. "
                    "Fair lending current. Financial crimes monitoring operational. Prudential requirements met."
                ),
                "control": "Well Controlled",
                "control_rationale": "Compliance well controlled.",
            },
            "Country": {"rating": "Not Applicable", "rationale": "N/A — domestic only.", "control": "Not Applicable", "control_rationale": "N/A."},
        },
        audit_leader="R. Chen", pga="R. Patel",
        primary_it="App-600\nApp-601", secondary_it="App-700\nApp-701",
        primary_tp="Vendor-G", secondary_tp="Vendor-H",
        aenb_aux="Operational - Data\nInformation and Cyber Security",
        last_engagement_rating="Needs Improvement",
        last_audit_completion_date="2025-11-01",
    ),

    # --- AE-5: Sparse data — many review items ---
    _make_entity(
        "AE-5", "New Markets Expansion", "Team Alpha", "Active",
        "New market entry initiative — early stage.",
        "High", "High",
        {
            "Credit": {
                "rating": "Medium",
                "rationale": "Credit exposure building. Portfolio small but growing.",
                "control": "New/Not Tested Yet",
                "control_rationale": "Controls under development.",
            },
            "Market": {
                "rating": "Medium",
                "rationale": "Some exposure exists.",  # VAGUE
                "control": "New/Not Tested Yet",
                "control_rationale": "Controls new.",
            },
            "Strategic & Business": {
                "rating": "High",
                "rationale": "Significant earnings risk. Revenue uncertain. Capital investment substantial.",
                "control": "Moderately Controlled",
                "control_rationale": "Strategic oversight from leadership.",
            },
            "Funding & Liquidity": {
                "rating": "Medium",
                "rationale": "Liquidity adequate. Funding through parent. Cash flow limited. Borrowing available.",
                "control": "Well Controlled",
                "control_rationale": "Parent entity provides liquidity.",
            },
            "Reputational": {
                "rating": "Medium",
                "rationale": "Brand risk from market entry. Stakeholder expectations high. Media coverage pending.",
                "control": "New/Not Tested Yet",
                "control_rationale": "PR plan being developed.",
            },
            "Model": {"rating": "Not Applicable", "rationale": "N/A — no models yet.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Third Party": {"rating": "High", "control": "New/Not Tested Yet"},
            "Financial Reporting": {
                "rating": "Medium",
                "rationale": "Regulatory reporting for new market. SEC requirements apply. Financial statement preparation underway.",
                "control": "Moderately Controlled",
                "control_rationale": "Reporting framework being established.",
            },
            "External Fraud": {
                "rating": "High",
                "rationale": "Fraud risk high. New market channels untested. Identity theft controls being built.",
                "control": "New/Not Tested Yet",
                "control_rationale": "Fraud controls under development.",
            },
            "Information Technology": {"rating": "High", "control": "New/Not Tested Yet"},
            "Information Security": {"rating": "High", "control": "New/Not Tested Yet"},
            # INTENTIONALLY VAGUE
            "Operational": {
                "rating": "High",
                "rationale": "Overall operational risk is high for this new initiative.",
                "control": "New/Not Tested Yet",
                "control_rationale": "Controls being developed.",
            },
            "Compliance": {
                "rating": "High",
                "rationale": "Compliance risk high. Regulatory landscape unfamiliar. Requirements being mapped. Prudential commitments TBD.",
                "control": "New/Not Tested Yet",
                "control_rationale": "Compliance program being built.",
            },
            "Country": {
                "rating": "High",
                "rationale": "Country risk high. Entering 3 new markets with different regulatory regimes.",
                "control": "Moderately Controlled",
                "control_rationale": "Country risk assessment completed.",
            },
        },
        audit_leader="K. Patel", pga="S. Williams",
        primary_tp="Vendor-I",
        last_engagement_rating="Requires Attention",
        last_audit_completion_date="2024-01-15",
    ),

    # --- AE-6: Everything applicable — keywords match broadly ---
    _make_entity(
        "AE-6", "Enterprise Risk Services", "Team Bravo", "Active",
        "Cross-functional risk services across the enterprise.",
        "Medium", "Low",
        {
            "Credit": {
                "rating": "Medium",
                "rationale": "Consumer and small business lending exposure. Commercial corporate counterpart risk. Default rates monitored. Non-payment tracking in place.",
                "control": "Well Controlled",
                "control_rationale": "Comprehensive credit monitoring.",
            },
            "Market": {
                "rating": "Medium",
                "rationale": "Interest rate repricing risk on portfolio. Yield curve sensitivity moderate. FX currency exposure from international operations. Price risk from equity market positions.",
                "control": "Well Controlled",
                "control_rationale": "Full hedging program.",
            },
            "Strategic & Business": {
                "rating": "Medium",
                "rationale": "Earnings stable. Revenue diversified. Fee income growing. Capital adequacy strong. Capital allocation optimized. CCAR compliant. Stress test passed.",
                "control": "Well Controlled",
                "control_rationale": "Strong strategic governance.",
            },
            "Funding & Liquidity": {
                "rating": "Low",
                "rationale": "Liquidity strong. Cash flow positive. Funding diversified. Deposit base stable. Borrowing capacity ample. Obligation management effective.",
                "control": "Well Controlled",
                "control_rationale": "Robust liquidity management.",
            },
            "Reputational": {
                "rating": "Low",
                "rationale": "Reputation strong. Brand well-regarded. Media coverage positive. Stakeholder trust high. Public perception favorable.",
                "control": "Well Controlled",
                "control_rationale": "Active reputation management.",
            },
            "Model": {
                "rating": "Low",
                "rationale": "Model risk low. All models validated. Backtest current. Model governance strong. Algorithm performance within tolerance. MRM fully staffed.",
                "control": "Well Controlled",
                "control_rationale": "Comprehensive MRM program.",
            },
            "Third Party": {"rating": "Low", "control": "Well Controlled"},
            "Financial Reporting": {
                "rating": "Low",
                "rationale": "Financial reporting excellent. GAAP compliant. SEC filing automated. No material misstatements. Regulatory report on time. 10-K and 10-Q current.",
                "control": "Well Controlled",
                "control_rationale": "Fully automated reporting.",
            },
            "External Fraud": {
                "rating": "Low",
                "rationale": "External fraud risk low. Account takeover controls effective. Identity theft detection strong. Fraud scheme monitoring operational. Counterfeit detection in place.",
                "control": "Well Controlled",
                "control_rationale": "Comprehensive fraud program.",
            },
            "Information Technology": {"rating": "Low", "control": "Well Controlled"},
            "Information Security": {"rating": "Low", "control": "Well Controlled"},
            "Operational": {
                "rating": "Low",
                "rationale": (
                    "Operational risk low. Process execution strong. Transaction settlement on time. "
                    "Reconciliation automated. Business continuity plan tested. BCP disaster recovery current. "
                    "Employee retention high. Workforce stable. Training complete. Talent pipeline strong. "
                    "Conduct program effective. Ethics training current. Privacy program compliant. "
                    "GDPR requirements met. Personal data handling controlled. "
                    "Data governance effective. Data quality high. Data management mature."
                ),
                "control": "Well Controlled",
                "control_rationale": "All operational controls well managed.",
            },
            "Compliance": {
                "rating": "Low",
                "rationale": (
                    "Compliance risk low. Prudential oversight strong. Regulatory examination clean. "
                    "Enterprise compliance program effective. Consumer protection robust. "
                    "Fair lending analysis current. UDAAP risk managed. CRA compliance met. "
                    "Financial crimes monitoring comprehensive. AML/BSA program strong. "
                    "Sanctions screening complete. OFAC requirements met. KYC procedures followed."
                ),
                "control": "Well Controlled",
                "control_rationale": "Comprehensive compliance program.",
            },
            "Country": {
                "rating": "Low",
                "rationale": "Country risk low. Stable operating environment.",
                "control": "Well Controlled",
                "control_rationale": "Monitoring in place.",
            },
        },
        audit_leader="J. Smith", pga="R. Patel",
        primary_it="App-800", secondary_it="App-801\nApp-802",
        primary_tp="Vendor-J", secondary_tp="Vendor-K",
        axp_aux="Data\nThird Party\nHuman Capital",
        aenb_aux="Processing, Execution and Change\nFraud (External and Internal)",
        last_engagement_rating="Satisfactory",
        last_audit_completion_date="2025-07-01",
    ),

    # --- AE-7: Everything N/A ---
    _make_entity(
        "AE-7", "Dormant Entity - Legacy", "Team Charlie", "Inactive",
        "Legacy entity pending decommission.",
        "Not Applicable", "Not Applicable",
        {pillar: {"rating": "Not Applicable", "rationale": "N/A — dormant entity.",
                  "control": "Not Applicable", "control_rationale": "N/A."}
         if pillar not in NO_RATIONALE_PILLARS
         else {"rating": "Not Applicable", "control": "Not Applicable"}
         for pillar in PILLARS},
        audit_leader="M. Johnson", pga="S. Williams",
        last_engagement_rating="Unsatisfactory",
        last_audit_completion_date="2025-12-01",
    ),

    # --- AE-8: Dimension parsing edge cases ---
    _make_entity(
        "AE-8", "Investment Products", "Team Delta", "Active",
        "Investment and wealth management products.",
        "Medium", "Medium",
        {
            "Credit": {
                "rating": "Medium",
                # Standard format
                "rationale": "Credit risk is medium. Likelihood is low, impact is high. Consumer lending portfolio stable.",
                "control": "Moderately Controlled",
                "control_rationale": "Credit controls adequate.",
            },
            "Market": {
                "rating": "High",
                # Abbreviation format
                "rationale": "Market risk assessment: L: Medium, I: Critical. Interest rate sensitivity elevated. FX currency exposure moderate. Price risk from equity market holdings.",
                "control": "Moderately Controlled",
                "control_rationale": "Market risk controls in place.",
            },
            "Strategic & Business": {
                "rating": "Medium",
                # Parenthetical format
                "rationale": "Earnings outlook moderate. Likelihood(medium) and impact(low). Revenue from fee income stable. Capital adequacy within requirements.",
                "control": "Well Controlled",
                "control_rationale": "Strategic planning effective.",
            },
            "Funding & Liquidity": {
                "rating": "Low",
                "rationale": "Liquidity position stable. Cash flow adequate. Deposit base diversified.",
                "control": "Well Controlled",
                "control_rationale": "Liquidity well managed.",
            },
            "Reputational": {
                "rating": "Medium",
                # Impact subtypes
                "rationale": "Reputation risk medium. Financial impact is low. Reputational impact is high. Regulatory impact is medium. Consumer impact is low. Brand perception stable.",
                "control": "Moderately Controlled",
                "control_rationale": "Reputation monitoring active.",
            },
            "Model": {
                "rating": "High",
                "rationale": "Model risk high. Pricing models require validation. Algorithm methodology under review. Model governance gap identified.",
                "control": "Moderately Controlled",
                "control_rationale": "MRM team reviewing.",
            },
            "Third Party": {"rating": "Medium", "control": "Moderately Controlled"},
            "Financial Reporting": {
                "rating": "Low",
                "rationale": "Financial reporting risk low. GAAP compliant. Accounting processes automated.",
                "control": "Well Controlled",
                "control_rationale": "Automated.",
            },
            "External Fraud": {
                "rating": "Medium",
                "rationale": "Fraud risk medium. Account takeover attempts stable. Identity theft controls in place.",
                "control": "Moderately Controlled",
                "control_rationale": "Fraud monitoring operational.",
            },
            "Information Technology": {"rating": "Medium", "control": "Moderately Controlled"},
            "Information Security": {"rating": "Medium", "control": "Moderately Controlled"},
            "Operational": {
                "rating": "Medium",
                # Dash format for dimensions
                "rationale": "Operational risk - likelihood - low, impact - medium. Process execution adequate. Business continuity tested. Employee workforce stable.",
                "control": "Moderately Controlled",
                "control_rationale": "Controls adequate.",
            },
            "Compliance": {
                "rating": "Medium",
                "rationale": "Compliance risk medium. Regulatory program adequate. Consumer protection in place. Prudential oversight current.",
                "control": "Moderately Controlled",
                "control_rationale": "Compliance program adequate.",
            },
            "Country": {
                "rating": "Low",
                "rationale": "Country risk low. Domestic focus.",
                "control": "Well Controlled",
                "control_rationale": "Standard monitoring.",
            },
        },
        audit_leader="A. Williams", pga="R. Patel",
        primary_it="App-900",
        axp_aux="Model\nEarnings",
        last_engagement_rating="",
        last_audit_completion_date="",
    ),

    # --- AE-9: Dedup stress test — overlapping pillar mappings ---
    _make_entity(
        "AE-9", "Cross-Border Operations", "Team Alpha", "Active",
        "Cross-border payment and settlement operations.",
        "High", "High",
        {
            "Credit": {
                "rating": "High",
                "rationale": "Consumer and commercial credit exposure. Cardmember defaults elevated. Corporate counterpart risk from institutional clients. Wholesale lending growing.",
                "control": "Moderately Controlled",
                "control_rationale": "Credit monitoring active.",
            },
            "Market": {
                "rating": "High",
                "rationale": "Interest rate repricing risk high. Yield curve sensitivity. Foreign exchange currency exposure significant. Price risk from dealing and position taking.",
                "control": "Moderately Controlled",
                "control_rationale": "Hedging partial.",
            },
            "Strategic & Business": {
                "rating": "Medium",
                "rationale": "Earnings pressure moderate. Revenue stable. Capital adequacy maintained. Capital allocation under review.",
                "control": "Moderately Controlled",
                "control_rationale": "Strategic planning ongoing.",
            },
            "Funding & Liquidity": {
                "rating": "Medium",
                "rationale": "Liquidity adequate. Funding diversified. Cash flow from operations stable. Obligation management effective.",
                "control": "Moderately Controlled",
                "control_rationale": "Liquidity monitored daily.",
            },
            "Reputational": {
                "rating": "Medium",
                "rationale": "Reputation risk medium. Brand exposure in multiple markets. Media coverage neutral.",
                "control": "Moderately Controlled",
                "control_rationale": "PR monitoring active.",
            },
            "Model": {
                "rating": "Medium",
                "rationale": "Model risk medium. FX pricing models validated. Algorithm performance acceptable. Model governance in place.",
                "control": "Well Controlled",
                "control_rationale": "MRM program effective.",
            },
            "Third Party": {"rating": "High", "control": "Moderately Controlled"},
            "Financial Reporting": {
                "rating": "Medium",
                "rationale": "Financial reporting risk medium. Multi-jurisdiction regulatory reporting. GAAP and IFRS reconciliation required. SEC filing complex.",
                "control": "Moderately Controlled",
                "control_rationale": "Reporting controls being enhanced.",
            },
            "External Fraud": {
                "rating": "High",
                "rationale": "Fraud risk high. Cross-border fraud schemes. Account takeover through international channels. Counterfeit activity in emerging markets.",
                "control": "Moderately Controlled",
                "control_rationale": "Fraud detection operational but coverage gaps in new markets.",
            },
            "Information Technology": {"rating": "High", "control": "Moderately Controlled"},
            "Information Security": {"rating": "High", "control": "Moderately Controlled"},
            "Operational": {
                "rating": "High",
                "rationale": (
                    "Operational risk high. Settlement process execution critical. Transaction reconciliation "
                    "across time zones. Business continuity plan needs multi-region update. Disaster recovery "
                    "tested for primary site only. Workforce hiring challenges in APAC. Employee retention below target. "
                    "Conduct training rolled out globally. Privacy compliance across jurisdictions — GDPR, CCPA, "
                    "local regulations. Personal data handling complex. Data governance across borders. "
                    "Data quality varies by region."
                ),
                "control": "Moderately Controlled",
                "control_rationale": "Controls operational but fragmented across regions.",
            },
            "Compliance": {
                "rating": "High",
                "rationale": (
                    "Compliance risk high. Multi-jurisdiction regulatory requirements. Prudential oversight complex. "
                    "Enterprise compliance program spanning 12 countries. Consumer protection standards vary. "
                    "Fair lending applicable in US operations. Financial crimes risk elevated — AML monitoring "
                    "across jurisdictions, sanctions screening for all corridors, OFAC requirements, KYC in "
                    "multiple regulatory frameworks. Bribery and corruption risk in certain markets."
                ),
                "control": "Moderately Controlled",
                "control_rationale": "Compliance program in place but needs harmonization.",
            },
            "Country": {
                "rating": "Critical",
                "rationale": "Country risk critical. Operations in 20+ markets including emerging economies. Geopolitical instability in several key markets.",
                "control": "Moderately Controlled",
                "control_rationale": "Country risk monitoring quarterly.",
            },
        },
        audit_leader="L. Park", pga="R. Patel",
        primary_it="App-1000\nApp-1001\nApp-1002", secondary_it="App-1100\nApp-1101",
        primary_tp="Vendor-L\nVendor-M", secondary_tp="Vendor-N\nVendor-O\nVendor-P",
        axp_aux="Operational - Data\nFinancial crimes\nFX and Price",
        aenb_aux="Privacy\nPrudential & Bank Admin Compliance",
        last_engagement_rating="Satisfactory",
        last_audit_completion_date="2025-10-01",
    ),

    # --- AE-10: Application and auxiliary flag test ---
    _make_entity(
        "AE-10", "Internal Shared Services", "Team Charlie", "Active",
        "Shared services for internal operations.",
        "Low", "Low",
        {
            "Credit": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Market": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Strategic & Business": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Funding & Liquidity": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Reputational": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Model": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Third Party": {"rating": "Not Applicable", "control": "Not Applicable"},  # N/A but has engagements tagged
            "Financial Reporting": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "External Fraud": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Information Technology": {"rating": "Not Applicable", "control": "Not Applicable"},  # N/A but has apps tagged
            "Information Security": {"rating": "Not Applicable", "control": "Not Applicable"},  # N/A but has apps tagged
            "Operational": {
                "rating": "Low",
                "rationale": "Operational risk low. Internal processes stable. Employee workforce adequate.",
                "control": "Well Controlled",
                "control_rationale": "Controls well managed.",
            },
            "Compliance": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
            "Country": {"rating": "Not Applicable", "rationale": "N/A.", "control": "Not Applicable", "control_rationale": "N/A."},
        },
        # Has apps and engagements tagged despite N/A ratings — should trigger flags
        audit_leader="M. Davis", pga="S. Williams",
        primary_it="App-1200\nApp-1201\nApp-1202",
        secondary_it="App-1300",
        primary_tp="Vendor-Q\nVendor-R",
        secondary_tp="Vendor-S",
        # Auxiliary risks that should flag additional L2s
        axp_aux="Operational - Third Party\nData\nHuman Capital",
        aenb_aux="Conduct\nPrivacy\nFair Lending / Regulation B",  # includes unmappable value
        last_engagement_rating="Requires Attention",
        last_audit_completion_date="2024-09-01",
    ),
]

legacy_df = pd.DataFrame(ENTITIES)
timestamp = datetime.now().strftime("%m%d%Y%I%M%p")
filename = f"legacy_risk_data_{timestamp}.xlsx"
legacy_df.to_excel(OUTPUT_DIR / filename, index=False)
print(f"Created {filename}: {len(legacy_df)} entities, {len(legacy_df.columns)} columns")

# =============================================================================
# SUB-RISK DESCRIPTIONS
# =============================================================================
SUB_RISKS = [
    # AE-1: Good coverage
    ("AE-1", "Credit", "CR-101", "Consumer Default", "Consumer credit card default risk from high-balance cardmember accounts in personal retail segment", "High"),
    ("AE-1", "Credit", "CR-102", "SB Concentration", "Small business lending concentration in retail sector with individual cardmember exposure", "Medium"),
    ("AE-1", "Operational", "OP-101", "Manual Recon", "Manual transaction reconciliation process prone to human error and control failure", "Medium"),
    ("AE-1", "Operational", "OP-102", "BCP Gap", "Business continuity plan not tested for pandemic scenario, disaster recovery needs improvement", "High"),
    ("AE-1", "Operational", "OP-103", "Attrition", "Employee attrition and retention challenges in technology workforce, hiring below targets", "Medium"),
    ("AE-1", "Operational", "OP-104", "Privacy Gap", "Privacy compliance program gaps, personal data handling procedures need updating, GDPR exposure", "Medium"),
    ("AE-1", "Information Technology", "IT-101", "Legacy Platform", "Legacy platform stability risk from aging infrastructure, system capacity constraints", "High"),
    ("AE-1", "Information Technology", "IT-102", "Data Gov", "Data governance gaps in customer data management, data quality issues in reporting", "Medium"),
    ("AE-1", "Compliance", "CO-101", "AML Program", "AML monitoring program effective. BSA requirements met. Sanctions screening operational.", "Low"),

    # AE-2: Minimal (treasury)
    ("AE-2", "Market", "MK-201", "Rate Risk", "Interest rate repricing risk on treasury portfolio, yield curve sensitivity, basis risk", "High"),

    # AE-3: Compliance coverage but NO Operational sub-risks
    ("AE-3", "Credit", "CR-301", "Merchant Credit", "Commercial merchant credit exposure, corporate counterpart risk from large merchants", "Medium"),
    ("AE-3", "Compliance", "CO-301", "AML Gaps", "AML monitoring gaps in cross-border transactions, suspicious activity detection delayed, financial crime exposure", "High"),
    ("AE-3", "Compliance", "CO-302", "Consumer Protection", "Consumer complaint handling under review, fair lending analysis pending, UDAAP risk", "Medium"),
    ("AE-3", "Compliance", "CO-303", "Prudential", "Prudential regulatory commitment tracking behind schedule, enterprise compliance program gaps, examination readiness", "Medium"),
    # Multi-value L1
    ("AE-3", "External Fraud\nOperational", "EF-301", "Terminal Fraud", "Counterfeit card scheme through payment terminals, fraud detection gaps in merchant channels", "High"),

    # AE-4: Control contradiction support
    ("AE-4", "External Fraud", "EF-401", "Digital Fraud", "Account takeover surge in digital channels, identity theft via synthetic IDs, fraud scheme sophistication", "High"),
    ("AE-4", "Information Technology", "IT-401", "Platform Perf", "Technology platform performance issues, system capacity risk during peak, application stability", "High"),
    ("AE-4", "Information Technology", "IT-402", "Data Pipeline", "Data quality issues in transaction processing pipeline, data management controls insufficient", "Medium"),
    ("AE-4", "Strategic & Business", "SB-401", "Fee Dependency", "Revenue heavily dependent on fee income, earnings concentration risk, pricing pressure", "High"),

    # AE-5: Very sparse
    ("AE-5", "Credit", "CR-501", "New Mkt Credit", "Credit exposure building in new markets, portfolio characteristics unknown", "Medium"),

    # AE-6: Rich sub-risks matching many L2s
    ("AE-6", "Operational", "OP-601", "Settlement", "Settlement and transaction reconciliation process, execution controls, change management procedures", "Low"),
    ("AE-6", "Operational", "OP-602", "BCP/DR", "Business continuity and disaster recovery, outage resilience, crisis management, facilities preparedness", "Low"),
    ("AE-6", "Operational", "OP-603", "People", "Talent retention and hiring, workforce culture, training and succession planning, employee compensation", "Low"),
    ("AE-6", "Compliance", "CO-601", "Fin Crimes", "Financial crime monitoring, money laundering detection, AML/BSA compliance, sanctions screening, OFAC, KYC", "Low"),

    # AE-8: No useful keywords — should produce no matches
    ("AE-8", "Operational", "OP-801", "General", "General operational matters are being addressed by the team as appropriate.", "Medium"),

    # AE-9: Rich cross-border sub-risks
    ("AE-9", "Compliance", "CO-901", "Multi-Juris AML", "Anti-money laundering across 12 jurisdictions, BSA compliance, sanctions screening for all corridors, OFAC, KYC frameworks", "High"),
    ("AE-9", "Compliance", "CO-902", "Cross-Border Consumer", "Consumer protection standards vary by jurisdiction, fair lending in US, UDAAP, client protection internationally", "Medium"),
    ("AE-9", "Operational", "OP-901", "FX Settlement", "Cross-border settlement and transaction execution, reconciliation across time zones, processing errors", "High"),
    ("AE-9", "Operational", "OP-902", "Global Privacy", "Privacy compliance across GDPR, CCPA, local regulations, personal data handling, consent management, data subject rights", "High"),

    # Edge case: blank L1 — should be filtered out
    ("AE-9", "", "OP-903", "Blank L1", "This sub-risk has no L1 category assigned.", "Medium"),
    # Edge case: nan description
    ("AE-9", "Operational", "OP-904", "No Desc", "", "Low"),
]

sub_risk_rows = []
for eid, l1, risk_id, title, desc, rating in SUB_RISKS:
    sub_risk_rows.append({
        "Audit Entity": eid,
        "Key Risk ID": risk_id,
        "Key Risk Title": title,
        "Key Risk Description": desc,
        "Level 1 Risk Category": l1,
        "Inherent Risk Rating": rating,
    })

sub_risk_df = pd.DataFrame(sub_risk_rows)
timestamp = datetime.now().strftime("%m%d%Y%I%M%p")
sub_risk_df.to_excel(OUTPUT_DIR / f"sub_risk_descriptions_{timestamp}.xlsx", index=False)
print(f"Created sub_risk_descriptions_{timestamp}.xlsx: {len(sub_risk_df)} sub-risks")

# =============================================================================
# FINDINGS
# =============================================================================
FINDINGS = [
    # (entity, finding_id, l2_risks, severity, status, name, leader, approval, description, engagement, source, remediation)

    # AE-1: Standard findings
    ("AE-1", "F-1001", "Data\nTechnology", "High", "Open",
     "Data quality controls missing", "J. Smith", "Approved",
     "Data quality controls not applied during onboarding.", "2025 Cards Audit", "Fieldwork", "2026-06-30"),
    ("AE-1", "F-1002", "Model", "High", "Open",
     "Model validation overdue", "J. Smith", "Approved",
     "Two models past validation due date.", "2025 Cards Model Review", "Fieldwork", "2026-05-15"),
    # Closed — should not trigger contradiction
    ("AE-1", "F-1003", "Technology", "High", "Closed",
     "Legacy migration completed", "J. Smith", "Approved",
     "Previously identified legacy migration risk remediated.", "2024 Cards IT Review", "Fieldwork", "2025-12-31"),
    # Blank severity — should be excluded
    ("AE-1", "F-1004", "Human Capital", "", "Open",
     "Workforce gap identified", "J. Smith", "Approved",
     "Severity not yet assessed.", "2025 Cards HR Review", "Fieldwork", ""),

    # AE-3: Multiple findings confirming applicability
    ("AE-3", "F-3001", "Fraud (External and Internal)", "High", "Open",
     "Payment terminal fraud gap", "A. Williams", "Approved",
     "Counterfeit fraud through terminals not detected.", "2025 GMS Fraud", "Fieldwork", "2026-04-30"),
    ("AE-3", "F-3002", "Third Party", "High", "Open",
     "Critical vendor assessment overdue", "A. Williams", "Approved",
     "Tier-1 vendor risk assessment 6 months overdue.", "2025 GMS Vendor", "Fieldwork", "2026-03-31"),
    ("AE-3", "F-3003", "Financial crimes", "High", "In Sustainability",
     "AML monitoring gap", "A. Williams", "Approved",
     "AML rules not updated for cross-border merchant flows.", "2025 GMS Compliance", "Continuous Monitoring", "2026-05-31"),
    ("AE-3", "F-3004", "Privacy", "Medium", "Open",
     "Merchant data handling non-compliant", "A. Williams", "Approved",
     "PII handling does not meet privacy requirements.", "2025 GMS Privacy", "Fieldwork", "2026-07-31"),
    # Cancelled — should be inactive
    ("AE-3", "F-3005", "Data", "High", "Cancelled",
     "Data migration withdrawn", "A. Williams", "Approved",
     "Finding withdrawn after reassessment.", "2025 GMS Data", "Fieldwork", ""),

    # AE-4: Control contradiction triggers
    ("AE-4", "F-4001", "Fraud (External and Internal)", "Critical", "Open",
     "Synthetic identity fraud", "R. Chen", "Approved",
     "Synthetic identity fraud bypassing digital controls.", "2025 Digital Fraud", "Fieldwork", "2026-04-15"),
    ("AE-4", "F-4002", "Third Party", "High", "In Validation",
     "Payment processor SLA breach", "R. Chen", "Approved",
     "Primary processor SLA breached 4 times.", "2025 Digital Vendor", "Fieldwork", "2026-05-01"),
    ("AE-4", "F-4003", "Technology", "High", "Open",
     "Platform outage", "R. Chen", "Approved",
     "4-hour outage during peak.", "2025 Digital IT", "Fieldwork", "2026-03-31"),
    ("AE-4", "F-4004", "Information and Cyber Security", "High", "Open",
     "API vulnerability", "R. Chen", "Approved",
     "Critical API vulnerability in mobile app.", "2025 Digital Cyber", "Fieldwork", "2026-04-30"),
    # Not approved — should be filtered
    ("AE-4", "F-4005", "Human Capital", "High", "Not Started",
     "Talent retention risk", "R. Chen", "Pending L1 Review",
     "Draft finding.", "2026 Digital HR", "Fieldwork", ""),

    # AE-5: Minimal finding
    ("AE-5", "F-5001", "Processing, Execution and Change", "Medium", "Open",
     "New market process errors", "K. Patel", "Approved",
     "Manual onboarding process producing errors.", "2025 New Markets", "Fieldwork", "2026-06-30"),
    # Blank severity
    ("AE-5", "F-5002", "Data", "", "Open",
     "Data classification gaps", "K. Patel", "Approved",
     "Not yet assessed.", "2025 New Markets Data", "Fieldwork", ""),

    # AE-6: No findings — clean entity

    # AE-9: Findings with L2 names needing normalization
    ("AE-9", "F-9001", "Operational - Processing, Execution and Change", "High", "Open",
     "Cross-border settlement errors", "L. Park", "Approved",
     "Settlement errors in APAC corridor.", "2025 Cross-Border Ops", "Fieldwork", "2026-05-31"),
    ("AE-9", "F-9002", "Operational - Third Party", "Medium", "In Validation",
     "Correspondent bank oversight gap", "L. Park", "Approved",
     "Correspondent bank due diligence overdue.", "2025 Cross-Border Vendor", "Fieldwork", "2026-04-30"),
    ("AE-9", "F-9003", "Financial crimes", "High", "Open",
     "Multi-jurisdiction AML gap", "L. Park", "Approved",
     "AML monitoring not harmonized across jurisdictions.", "2025 Cross-Border Compliance", "Fieldwork", "2026-06-15"),
    # L2 name with alias
    ("AE-9", "F-9004", "Cyber Security", "Medium", "Open",
     "Regional SOC coverage gap", "L. Park", "Approved",
     "Security operations center coverage insufficient in APAC.", "2025 Cross-Border Cyber", "Fieldwork", "2026-07-31"),
    # Multi-value with mixed normalization
    ("AE-9", "F-9005", "Operational - Data\nPrivacy", "Medium", "In Sustainability",
     "Cross-border data handling", "L. Park", "Approved",
     "Data handling and privacy compliance across jurisdictions.", "2025 Cross-Border Data", "Continuous Monitoring", "2026-08-31"),

    # Not approved with various statuses
    ("AE-9", "F-9006", "Technology", "High", "Not Started",
     "Infrastructure modernization", "L. Park", "In Progress",
     "Draft finding.", "2026 Cross-Border IT", "Fieldwork", ""),
    ("AE-9", "F-9007", "Model", "Medium", "Not Started",
     "FX model review", "L. Park", "Pending L2 Review",
     "Draft finding pending review.", "2026 Cross-Border Model", "Fieldwork", ""),

    # AE-10: Finding for entity with N/A pillars
    ("AE-10", "F-10001", "Human Capital", "Medium", "Open",
     "Shared services staffing gap", "M. Davis", "Approved",
     "Staffing levels below target.", "2025 Shared Services", "Fieldwork", "2026-05-31"),
]

findings_rows = []
for (eid, fid, l2, sev, status, name, leader, approval, desc, engagement, source, remediation) in FINDINGS:
    findings_rows.append({
        "Audit Entity ID": eid,
        "Finding ID": fid,
        "Risk Dimension Categories": l2,
        "Final Reportable Finding Risk Rating": sev,
        "Finding Status": status,
        "Finding Name": name,
        "Audit Leader": leader,
        "Finding Approval Status": approval,
        "Finding Description": desc,
        "Audit Engagement Name": engagement,
        "Source": source,
        "Actual Remediation Date": remediation,
    })

findings_df = pd.DataFrame(findings_rows)
timestamp = datetime.now().strftime("%m%d%Y%I%M%p")
findings_df.to_excel(OUTPUT_DIR / f"findings_data_{timestamp}.xlsx", index=False)
print(f"Created findings_data_{timestamp}.xlsx: {len(findings_df)} findings")

# Print scenario summary
print(f"\n{'='*60}")
print("TEST SCENARIOS:")
print(f"{'='*60}")
print(f"Entities: {len(ENTITIES)}")
print(f"  AE-1:  Full coverage, dimension parsing, all evidence types")
print(f"  AE-2:  Treasury, many N/A, minimal sub-risks")
print(f"  AE-3:  Vague Operational (all-candidates review), rich Compliance")
print(f"  AE-4:  Control contradictions (Well Controlled + High/Critical findings)")
print(f"  AE-5:  Sparse data, multiple review items")
print(f"  AE-6:  Everything applicable, keywords match broadly")
print(f"  AE-7:  Everything N/A (dormant entity)")
print(f"  AE-8:  Dimension parsing edge cases (L:H, parenthetical, subtypes)")
print(f"  AE-9:  Dedup stress, rich cross-border, L2 normalization in findings")
print(f"  AE-10: N/A pillars with apps/engagements tagged + auxiliary flags")
print(f"Sub-risks: {len(SUB_RISKS)}")
print(f"  Includes: multi-value L1, blank L1, no-keyword match, blank description")
print(f"Findings: {len(FINDINGS)}")
print(f"  Includes: all statuses, not-approved variants, blank severity,")
print(f"  multi-value L2, L1-prefixed L2, alias L2, cancelled, closed")
print(f"{'='*60}")
