# Amazon Account Health and Seller Metrics — Operational Reference

Source: Amazon Seller Central — Account Health Rating, Order Defect Rate (ODR), and Policy
Compliance guidance. This document helps operations staff understand which metrics affect
account standing and how to keep them within safe ranges.

## Account Health Rating (AHR)

- AHR is a score from 0 to 1,000 that reflects adherence to Amazon's selling policies over time.
- A score below 200 is considered unhealthy; accounts below 100 may be suspended.
- Each policy violation deducts points. Repeated or serious violations deduct more.
- AHR is recalculated daily. Resolving the root cause and successfully appealing a violation
  restores points.

## Order Defect Rate (ODR)

- ODR = (Negative feedback + A-to-Z claims + Chargebacks) / Total orders, measured over the
  previous 60 days.
- Target: below 1%. Amazon may restrict selling privileges if ODR exceeds 1%.
- Negative feedback that is clearly about fulfillment by Amazon (FBA) can be removed; file a
  case through Seller Central.

## Valid Tracking Rate (VTR)

- VTR = Orders with valid tracking / Total shipped orders, measured over the previous 30 days.
- Target: above 95% for non-FBA sellers.
- Use carrier-integrated tracking numbers. Manual upload of unsupported carriers can lower VTR.

## Late Shipment Rate (LSR)

- LSR = Orders shipped after the expected ship date / Total orders.
- Target: below 4%.
- Set realistic handling times and use FBA or Seller Fulfilled Prime only when fulfillment can
  consistently meet the promise.

## Cancellation Rate (CR)

- CR = Seller-cancelled orders / Total orders.
- Target: below 2.5%.
- Cancel orders only when absolutely necessary and as early as possible. High CR often indicates
  inventory sync problems.

## Customer Reviews and Voice of the Customer (VOC)

- VOC captures returns and customer comments and flags product issues at the ASIN level.
- If an ASIN receives repeated negative feedback about the same defect (sizing, smell, material),
  Amazon may suppress the listing or require a plan of action.
- Review VOC weekly and prioritize the top three themes for product or listing improvement.

## Intellectual Property Complaints

- Rights owners can submit IP complaints against listings that use their trademarks or patents.
- Even if the complaint is invalid, the listing may be suppressed until resolved.
- Keep supplier authorization letters, design patents, and trademark certificates organized.
- Never use competitor brand names in backend keywords.

## Practical Monitoring Rhythm

| Metric | Frequency | Owner | Action if at risk |
|---|---|---|---|
| AHR / Policy violations | Daily | Operations lead | Appeal false violations; fix root cause |
| ODR / VOC | Weekly | Customer service lead | Address top review themes; update listing |
| VTR / LSR / CR | Weekly | Fulfillment lead | Adjust handling time; improve inventory sync |
| IP complaints | As received | Legal / owner | Submit documentation; retract if invalid |

## Escalation Rules

- Any metric crosses the warning threshold: 24-hour action plan.
- Account Health Rating drops below 250: immediate stand-up with owner and operations lead.
- Listing suppression or IP complaint: document everything and file appeal within 48 hours.
