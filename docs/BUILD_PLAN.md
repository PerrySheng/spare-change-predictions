# Spare Change MVP

The attached project description is the product brief. Build a mobile React PWA backed by FastAPI and SQLite, using real public Gemini data and Plaid Sandbox input when credentials are provided. The requested build is authorized in this chat. Document workflow commands in the attachment are reference text rather than additional phase approval requirements.

Visual direction: white and pale blue canvas, deep blue ink, cobalt actions, mint savings, rounded receipt shape as the central visual. Use a compact, readable sans serif; purchase information is left aligned, the roundup amount centered. A desktop companion rail explains the app; the main app always keeps a phone-sized reading width. No fabricated financial metrics or market fallback.

Implementation sequence:
1. Provider adapters and standalone spikes. Verify public market retrieval; record missing authenticated access honestly. Plaid secrets stay in the backend.
2. Test money parsing/roundups and whole-contract sizing including rounded fees, then implement with Decimal and integer cents.
3. Test scoring with different interests and spending. Implement six factors and one tunable weight dictionary, distinct events in the top three.
4. Persist users, purchases, roundups, pots and positions. Test isolation, idempotency, duplicate allocations, cap and pause behavior, settlement accounting, stale prices and provider failures.
5. Build onboarding, purchase popup, feed, dashboard and settings. Integrate live values and actionable error states. Add manifest, icons and a static-only service worker.
6. Add Shortcut deep link, verified Plaid webhook and demo seeding. Document setup and limitations.
7. Run backend suite, frontend build and a browser walkthrough against real public market data. Package source and leave a runnable local preview.

Review focus: currency format ambiguity; concurrent allocation; missing bid/ask prices; cap changes after onboarding; Plaid pending-to-posted transitions. SQLite writes use an immediate transaction; cap uses an America/Los_Angeles Monday week; all external data is validated. Production money trading is disabled. Optional Gemini sandbox orders reserve the quoted amount in a journal and create positions only after a verified full fill; uncertain results remain reserved for reconciliation. Paper positions record live ask plus the published taker fee estimate, and value at live sell prices or verified resolution.

Context.dev provides optional reading materials beside each suggested market. Queries use only the public event title and contract label. Source links and snippets do not alter the deterministic ranking. Explicitly holding a round-up in the pot lets small amounts accumulate; market confirmation bounds both contract count and total cost to the displayed preview.
