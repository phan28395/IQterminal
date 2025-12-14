# Phase 1 — Watchlist “Added” Feedback in Ticker Suggestions

## Goal
When typing a ticker symbol, the suggestions panel should clearly show which tickers are already in the watchlist, and provide immediate visual feedback when a ticker is added.

## What changed
- Added an explicit **Add** indicator column in the suggestions table:
  - `[+]` = not in watchlist
  - `[x]` = already added / now in watchlist
- When a suggestion is added to the watchlist, the row is updated in-place:
  - The indicator flips from `[+]` → `[x]`
  - The row text turns green so it’s obvious it’s already tracked
- Suggestions table columns are now created with stable keys (`add`, `symbol`, `name`, `exchange`, `cik`) so cell updates are reliable.

## Notes
- The check indicator uses ASCII (`[x]`) for compatibility with Windows terminals that may not render Unicode checkmarks consistently. If you prefer a Unicode check, it can be swapped later.

## Files touched
- `src/financial_terminal/app.py`

## Quick test
1. Run the app.
2. Type a ticker in the sidebar input to show suggestions.
3. Click a suggestion:
   - It gets added to the watchlist
   - The indicator switches to `[x]`
   - The row turns green

