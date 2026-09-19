# Resto AI Agent — MVP Staging Brief

## Status
This is a local staging sandbox. All data and payment flows are synthetic.
Do not connect WhatsApp, QRIS, bank accounts, real customer data, or production payment providers.
Use visible markers: `DATA DUMMY`, `SIMULASI`, and `TIDAK BERLAKU SEBAGAI PENAWARAN RESMI`.

## Goal
Build a small, testable backend for the previously designed WhatsApp-first resto workflow:
1. owner manages menu, recipes, and opening stock;
2. customer creates an order from menu items;
3. system calculates totals from database data;
4. order moves through explicit payment and kitchen states;
5. synthetic payment confirmation is non-accepting and clearly simulated;
6. paid orders decrement ingredient stock according to recipes;
7. sales, finance, and stock reports are queryable.

## Architecture boundary
- AI/LLM conversation layer is not connected yet; the current WhatsApp adapter is deterministic and command-based.
- A Meta WhatsApp Cloud API webhook adapter is implemented for staging; outbound delivery is dry-run by default and requires explicit credentials to enable.
- Database is the source of truth for prices, order totals, payment state, stock, customer phone ownership, and reports.
- No real payment verification, refunds, discounts, publishing, or production customer-data workflow.
- Use FastAPI, SQLAlchemy, SQLite, and pytest unless a strong reason requires an alternative.

## Required lifecycle states
Order: DRAFT -> PENDING_PAYMENT -> PAID -> SENT_TO_KITCHEN -> PREPARING -> READY -> COMPLETED; support CANCELLED.
Payment: PENDING -> SIMULATED_CONFIRMED or FAILED. Simulated confirmation must never be represented as real settlement.

## Acceptance criteria
- runnable locally with documented commands;
- database schema and seed data are created by an explicit command;
- API or service tests cover menu listing, order total calculation, invalid stock, simulated payment, idempotent payment confirmation, stock deduction, and reports;
- no secrets or external credentials required;
- tests pass;
- README explains what is implemented, what is simulated, and what remains for production.

## Implementation discipline
Keep the first increment narrow and reviewable. Do not add WhatsApp, QRIS, bank, deployment, or multi-agent orchestration in this increment. Return structured errors and preserve audit-friendly state transitions.
