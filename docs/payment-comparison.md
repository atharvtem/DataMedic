# Using the measured comparison

1. Select a purchase date and click **Load payment comparison**.
2. Read the selected day's payment sum, the previous seven calendar days' daily mean, the percentage change, and the chart/table. This is a database measurement, not an LLM claim.
3. Click **Investigate measured date** to examine the cause. Optional context is not an arbitrary SQL question. The agent separately fetches its own evidence and pays its normal tool-point costs; manual previews are outside that budget.

For the seeded August 15 incident: 34,971.28 recorded payments versus 43,881.59 prior daily average, a 20.31% decrease; 288 orders and 100 without payment rows. Try August 14 and August 16 to see different measured values. Dates without orders are flagged; missing calendar days contribute zero to the mean, which may reflect missing source coverage rather than genuine zero activity.

Only August 15 has synthetic operations evidence. Other dates can show a change but often cannot receive a supported cause. A decrease by itself is not an anomaly detector or proof of an ingestion problem. The diagnostic scope remains the seeded missing-payment scenario.

The final follow-up describes manual source reconciliation and possible repair. The application has read-only tool access and does not restore records. Hypothesis and escalation explanations are now shown alongside the result.

Validation: Decimal calculation matched recorded daily values; Streamlit AppTest exercised loading a comparison and submitting the resulting investigation with fixture-backed tool responses.
