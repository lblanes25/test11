"""Generate dummy Optro AE overview test data.

Creates one file in data/input/:

Optro AE Overview (optro_ae_overview_test_dummy.xlsx):
  One row per audit entity — the audit team's current-state entity narrative
  as entered in Optro (the system of record).

  Two columns:
    AE ID       — matches the entity IDs used throughout the pipeline
    AE Overview — the Optro-sourced entity-level description

  Ten AEs reused from generate_test_data.py:
    AE-1   North America Cards
    AE-2   Treasury Operations
    AE-3   Global Merchant Services
    AE-4   Digital Banking Platform
    AE-5   New Markets Expansion
    AE-6   Enterprise Risk Services
    AE-7   Dormant Entity - Legacy
    AE-8   Investment Products
    AE-9   Cross-Border Operations
    AE-10  Internal Shared Services

  The overviews are authored from the audit team's perspective and intentionally
  differ from the Archer-sourced overviews in the legacy risk data to simulate
  real-world divergence between upstream extract and team-maintained narrative.

Usage:
    python tests/generate_optro_ae_overview_test_data.py
"""

import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"

# ---------------------------------------------------------------------------
# AE overview data
# ---------------------------------------------------------------------------

_ROWS = [
    {
        "AE ID": "AE-1",
        "AE Overview": (
            "North America Cards manages the full lifecycle of the consumer and small-business "
            "credit card portfolio across the U.S. and Canada. The entity is responsible for "
            "product origination, credit underwriting, account servicing, collections, and "
            "fraud operations. The portfolio spans co-brand, proprietary, and affinity card "
            "segments and relies on a network of core processing platforms and third-party "
            "issuer partners. As of the current AERA cycle, the entity faces elevated exposure "
            "in authorization-layer fraud (BIN-attack and account-takeover patterns documented "
            "in recent BMA cycles) and ongoing control gaps in vendor SLA oversight for two "
            "tier-1 payment processors. Sales practices and customer complaint-handling "
            "processes are subject to CFPB examination requirements, with annual attestation "
            "requirements under the Consumer Financial Protection framework. The audit team "
            "notes that conduct risk is a standing area of focus given the entity's direct "
            "customer-facing origination and servicing activity."
        ),
    },
    {
        "AE ID": "AE-2",
        "AE Overview": (
            "Treasury Operations oversees the firm's balance sheet, funding, and liquidity "
            "management activities, including short-term borrowing, investment portfolio "
            "management, and interest rate risk hedging. The entity acts as the central "
            "counterparty for internal funding transfers and manages relationships with "
            "external counterparties for repo, commercial paper, and term borrowing. "
            "The audit team's current assessment reflects a stable control environment for "
            "market and liquidity risk, with primary concern areas in interest rate "
            "sensitivity (DV01 proximity to inner limit flagged in Q4 BMA) and treasury "
            "system access controls. Conduct exposure is limited but present in the context "
            "of trader conduct standards, front-office communication policies, and adherence "
            "to FINRA and applicable exchange conduct requirements."
        ),
    },
    {
        "AE ID": "AE-3",
        "AE Overview": (
            "Global Merchant Services provides merchant acquiring, payment acceptance, and "
            "settlement services across card-present, card-not-present, and e-commerce "
            "channels. The entity manages merchant onboarding, underwriting, tier assignment, "
            "and ongoing risk monitoring for a globally distributed merchant book. Chargeback "
            "management and dispute resolution are core operational functions. The audit team "
            "has documented elevated friendly-fraud chargeback trends in the digital-goods "
            "MCC category and concentration risk in a specific high-volume travel merchant "
            "flagged through BMA monitoring. Conduct risk is present primarily through "
            "merchant-facing sales practices, onboarding standards, and the potential for "
            "manipulation of dispute outcomes. Internal fraud exposure is relevant given "
            "insider access to merchant settlement data and the potential for payment "
            "diversion or kickback arrangements with high-volume accounts."
        ),
    },
    {
        "AE ID": "AE-4",
        "AE Overview": (
            "Digital Banking Platform delivers consumer-facing digital banking capabilities "
            "including mobile app, online banking portal, digital account opening, and API "
            "integrations with fintech partners. The entity owns the customer authentication "
            "and session management infrastructure shared across digital channels. A 3-hour "
            "login outage in August (documented in BMA monitoring) exposed a change-management "
            "gap in the credential-service deployment pipeline. Device-spoofing and social-"
            "engineering fraud vectors are active and documented. The audit team views "
            "conduct risk through the lens of digital sales practices, app-based product "
            "recommendations, and customer disclosure adequacy in digital-first flows. "
            "Internal fraud exposure is noted in the context of privileged access to "
            "customer authentication logs and digital account management systems."
        ),
    },
    {
        "AE ID": "AE-5",
        "AE Overview": (
            "New Markets Expansion is responsible for the firm's entry and ongoing operations "
            "in emerging and non-core geographic markets, including product licensing, "
            "regulatory engagement, and partnership structuring with local issuing and "
            "acquiring partners. The entity has active operations in Brazil, UAE, and India, "
            "each subject to distinct regulatory change cycles (Q1 consumer-protection "
            "disclosures in Brazil, data-residency requirements in UAE, KYC threshold "
            "updates in India). A deteriorating LATAM issuing partner flagged in BMA "
            "monitoring introduces third-party credit concentration risk. Conduct risk "
            "is heightened due to cross-jurisdictional differences in acceptable sales "
            "practices, marketing standards, and product suitability requirements. Internal "
            "fraud exposure is moderate and centers on local partner relationships where "
            "oversight and audit rights may be contractually limited."
        ),
    },
    {
        "AE ID": "AE-6",
        "AE Overview": (
            "Enterprise Risk Services operates the firm's second-line risk management "
            "infrastructure, including the enterprise risk framework, risk appetite "
            "monitoring, operational risk event management, and the risk reporting supply "
            "chain for executive and board audiences. The entity owns the ORE capture and "
            "classification process and produces the consolidated risk appetite dashboard. "
            "BMA monitoring identified an operational-loss trend above appetite threshold "
            "driven by a single large ORE, escalated to the ERC. Conduct risk applies in "
            "the context of how risk information is reported, communicated, and escalated — "
            "including the adequacy and accuracy of risk disclosures to senior leadership "
            "and the board. Internal fraud exposure, while lower probability, is relevant "
            "given insider access to pre-publication risk reports and the ability to "
            "influence classification of operational risk events."
        ),
    },
    {
        "AE ID": "AE-7",
        "AE Overview": (
            "Dormant Entity - Legacy is a legally preserved but operationally inactive "
            "entity maintained for regulatory and historical reporting purposes. The entity "
            "has no active employees, no customer-facing operations, and no ongoing business "
            "activity. Residual administrative functions (statutory filings, dormant account "
            "management) are performed by a shared-services team under a limited-scope "
            "mandate. The audit team has assessed this entity as not applicable for the "
            "majority of AERA risk categories given its dormant status. Risk exposure is "
            "limited to legal and compliance maintenance obligations, with no meaningful "
            "conduct or internal fraud exposure in the current operating state."
        ),
    },
    {
        "AE ID": "AE-8",
        "AE Overview": (
            "Investment Products manages the design, distribution, and lifecycle of "
            "investment and wealth management products offered to consumer and institutional "
            "clients, including mutual funds, separately managed accounts, and structured "
            "products. The entity operates under SEC, FINRA, and applicable state securities "
            "regulations. The audit team's current view highlights conduct risk as a primary "
            "area of focus: suitability standards, fee disclosure, best-execution obligations, "
            "and the potential for conflicts of interest in product selection and distribution "
            "are standing audit themes. Investment product sales practices are subject to "
            "Reg BI compliance requirements. Internal fraud exposure is present through "
            "the handling of client investment instructions, trade execution sequencing, "
            "and access to non-public client portfolio information."
        ),
    },
    {
        "AE ID": "AE-9",
        "AE Overview": (
            "Cross-Border Operations manages the firm's multi-currency settlement, "
            "correspondent banking, and cross-border payment flows, including FX conversion, "
            "AML/sanctions screening, and regulatory reporting to domestic and foreign "
            "supervisors. The entity interfaces with correspondent banks, payment system "
            "operators, and local clearinghouses across more than 30 jurisdictions. "
            "Conduct risk is material in the context of FX pricing practices, transparency "
            "of cross-border fee disclosures to consumer and commercial clients, and "
            "adherence to conduct standards enforced by regulators across multiple "
            "jurisdictions simultaneously. Internal fraud exposure is heightened given "
            "the volume and velocity of cross-border transaction flows, the complexity of "
            "reconciliation across currencies and time zones, and the potential for "
            "diversion or manipulation of correspondent settlement instructions."
        ),
    },
    {
        "AE ID": "AE-10",
        "AE Overview": (
            "Internal Shared Services delivers operational support functions — including "
            "accounts payable, procurement, facilities management, technology asset "
            "management, and HR transaction processing — to business units across the "
            "enterprise on a cost-allocation basis. The entity is the primary consumer "
            "of the firm's enterprise resource planning (ERP) system and owns the "
            "procure-to-pay cycle for non-vendor-of-record expenditures. Conduct risk "
            "is present in procurement practices, expense reimbursement, and the "
            "potential for vendor favoritism or inadequate separation of duties in "
            "purchase approval workflows. Internal fraud exposure is a primary concern "
            "for this entity: the combination of disbursement authority, procurement "
            "control, and asset management creates known vectors for expense fraud, "
            "procurement fraud, and asset misappropriation, which are common internal "
            "fraud patterns in shared-services environments."
        ),
    },
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_optro_ae_overview() -> pd.DataFrame:
    return pd.DataFrame(_ROWS)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = generate_optro_ae_overview()
    out_path = OUTPUT_DIR / "optro_ae_overview_test_dummy.xlsx"
    df.to_excel(out_path, index=False)
    print(f"Created: {out_path}")
    print(f"  Rows: {len(df)}")
    print(f"  Columns: {list(df.columns)}")
    print()
    for _, row in df.iterrows():
        print(f"  {row['AE ID']}: {row['AE Overview'][:80]}...")


if __name__ == "__main__":
    main()
