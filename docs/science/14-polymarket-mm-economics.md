# 14 — Polymarket F1 Prop Market-Making: Economics

*Quant research brief. Date: 2026-06-01. Live data pulled from Gamma + CLOB APIs for Monaco GP 2026-06-07.*

---

## Executive verdict

**Market-making Polymarket's F1 prop markets is negative-to-zero EV for a retail maker with no pricing edge. Do not build this.**

Three independent reasons, each sufficient on its own:

1. **There is no LP-reward income on these markets.** The Monaco winner and pole markets carry the *config* fields `rewardsMinSize: 50` / `rewardsMaxSpread: 4.5`, but the live CLOB object reports **`rewards.rates: null`**, and the markets are **absent from `clob.polymarket.com/sampling-markets`** (the canonical "currently earning rewards" list). Verified: 0 of the Monaco markets appear in that list. The only F1 markets funded at all are season-long championship props, and even those carry a placeholder `rewards_daily_rate: 0.001` (≈$0/day). So the "$50 resting within 4.5¢" mechanic is *armed but unfunded* — quoting it pays nothing.

2. **Maker-rebate income is real but tiny, and it is a pro-rata split you'll lose to incumbents.** The rebate pool on a market = 25% of taker fees collected *on that market*. Taker fees are capped at 0.75% of notional (peak, at p=0.50) and fall toward the tails. On the Monaco winner event's entire cumulative life ($152k volume), the total taker fees ever generated are on the order of $400–700, of which 25% (~$100–175) is the *lifetime* rebate pool split across *all* makers. That is a one-time-ish trickle, not a yield.

3. **Adverse selection on a news-gapping binary dominates any half-spread capture.** The only liquid sub-market (Leclerc, mid ≈ 0.305) is quoted **0.29 / 0.32 = 3¢ wide**, not 0.2¢. The 0.2¢ figure in the brief is only true on the dead longshot tails (e.g. Gasly at 0.002, bid 0.001/ask 0.003) where there is no flow to earn from. A binary that jumps 20–50 points on quali/grid-penalty/crash news means a resting maker is the one filled *exactly when wrong*. With no model edge, expected adverse-selection cost > expected half-spread.

**Bottom line: rebates ≈ pennies, rewards = $0 (unfunded), adverse selection = the dominant term and it's negative. EV is negative for a retail maker with no edge.** It only flips positive under conditions that don't currently hold (see §6).

---

## 1. Decoded fee math (`sports_fees_v2`)

`feeSchedule: {exponent: 1, rate: 0.03, takerOnly: true, rebateRate: 0.25}`

### (a) What a TAKER pays — VERIFIED

```
fee = C × feeRate × p × (1 − p)          (exponent = 1, so (p(1−p))^1 = p(1−p))
    = C × 0.03 × p × (1 − p)
```
- `C` = number of shares filled, `p` = share price (the outcome's probability, 0–1).
- It is **NOT 3% of notional, spread, or winnings.** It's `3% × p(1−p)` of shares — a fee curve that peaks at the 50/50 point and decays to zero at the 1¢/99¢ tails.
- **Peak fee = 0.75¢ per share at p = 0.50** → i.e. **$0.75 per 100 shares**, which is the official table value. As a % of *notional* (price × shares), peak effective fee = `0.03 × (1−p)` at p=0.50 = **0.75% of notional**. (One secondary source cited 1.80%; that is wrong/legacy — the $0.75/100-share table and `rate 0.03` both pin it to 0.75%.)
- `takerOnly: true` → **makers are never charged this fee.** Only the aggressor pays. (Sell/maker orders pay 0.)
- Effective on Leclerc (p≈0.305): a taker pays `0.03 × 0.305 × 0.695` = **0.636¢ per share** = ~2.1% of the 30¢ notional. Non-trivial — this is why takers prefer to rest.

### (b) What a MAKER receives — `rebateRate: 0.25` — VERIFIED

- **25% of the taker fees collected *in that specific market*** are redistributed to makers daily.
- Split **pro-rata by fee-equivalent generated**, using the *same* curve:
  `your_rebate = (your_fee_equivalent / total_fee_equivalent) × (0.25 × market_taker_fees)`.
- Competition is **per-market**, daily distribution, **$1 USDC minimum payout** (sub-$1 accruals are dropped — a real friction on thin F1 markets).
- This is NOT a fixed bps rebate. If incumbents capture most maker fills, your share of the already-tiny 25% pool rounds to nothing.

### (c) `makerBaseFee` / `takerBaseFee: 1000` — INFERRED (legacy)

- These are the **legacy per-order base-fee fields (basis points) from the original CLOB**, present on every market object and on the CLOB `/markets` response. They are **not referenced anywhere in the current fee docs** and are **superseded by `feeSchedule`/`sports_fees_v2`**. `1000` is a default placeholder, not an active 10% charge — if it were live, every trade would cost 10% and the market would be dead. Treat as inert legacy. (Could not find a doc explicitly deprecating them; inference is from: docs describe only the `feeSchedule` formula, makers verifiably pay 0, and the value is identical/static across all markets.)

---

## 2. Decoded LP-rewards mechanics

### The scoring formula — VERIFIED

Per-minute, per-market, each maker order scores by a quadratic in its distance from the (size-adjusted) midpoint:

```
S(v, s) = ((v − s) / v)²            for s ≤ v, else 0
score   = S(v, s) × order_size       summed over your bid + ask orders
```
- `v` = `max_spread` = **4.5¢** (`rewardsMaxSpread`). Orders wider than 4.5¢ from mid score 0.
- `s` = your order's spread (¢) from the size-cutoff-adjusted mid.
- `min_size` = **$50** (`rewardsMinSize`): orders below $50 are ignored for scoring.
- **Two-sided requirement:** for mid in [0.10, 0.90], single-sided liquidity scores at a *reduced* rate (÷ c, c≈3.0); for mid in the tails [0,0.10) or (0.90,1], liquidity **must be two-sided** to score at all. (The Monaco favorites at 0.05–0.31 mostly need true two-sided quotes; longshots in the tail need two-sided or score nothing.)
- **Daily split:** `Q_final = Q_yours / Σ Q_all`, times the market's reward pool. Pro-rata by score share, midnight-UTC epoch, $1 min payout.

### The Monaco winner market's ACTUAL reward budget — VERIFIED = **$0 (unfunded)**

- `clob.polymarket.com/markets/<conditionId>` → `rewards: {rates: null, min_size: 50, max_spread: 4.5}`.
- Gamma object `clobRewards` field → **`None`**.
- Monaco winner + pole markets: **0 hits in `clob.polymarket.com/sampling-markets`** (the list of markets actively paying rewards).
- For calibration, of the 1000 markets in `sampling-markets` that *are* earning: **median `rewards_daily_rate` = $1/day**, top-5 = $200–500/day. F1 *race* props get none; only season-long championship markets are listed, and at the $0.001/day placeholder.

**Conclusion: the rewards program is configured on these markets but funded at $0. Quoting within 4.5¢ × $50 earns nothing today.**

---

## 3. MM EV model — Monaco WINNER market (the only liquid one)

Framing (per HFT convention):
```
EV_maker = rebate_income + reward_income + half_spread × uninformed_fill_$
           − adverse_selection × informed_fill_$ − inventory_to_resolution_risk
```

### Inputs (live / measured)
- Liquid sub-market = **Leclerc**, mid ≈ 0.305, book **0.29 / 0.32 (3¢ wide)**, ~$3.0k resting at best bid, ~$0.7k–16k on asks. Incumbents are **not** at 0.2¢ here; 3¢ is the real favorite spread. (0.2¢ only on dead 0.002 longshots.)
- Tick = 1¢ on favorites (0.1¢ on longshots). On a 1¢-tick market you literally cannot make tighter than 1¢; the half-spread ceiling is 0.5¢.
- Event cumulative volume = **$152k** over ~3 weeks ≈ **$7k/day**, concentrated in the favorite. Call it ~$3–4k/day of *taker* flow on Leclerc.
- `reward_income = 0` (verified §2).

### Term-by-term (per $1,000 of resting two-sided quote, per day)

- **Reward income:** $0 (unfunded). 
- **Rebate income:** pool = 0.25 × taker-fees-on-this-market-today. Daily taker fees on Leclerc ≈ `$3.5k × 0.03 × 0.305 × 0.695` ≈ **$22/day**; pool = 0.25 × $22 ≈ **$5.5/day split across ALL makers**. The book shows ≥$20k resting across makers, so a $1k quote ≈ 5% of size → **~$0.10–0.30/day** rebate, gated by the $1 min payout (you may get $0 until it accrues). Call it **+$0.20/day per $1k**.
- **Half-spread on uninformed flow:** at best you quote 1¢ inside (0.5¢ half-spread). If ~30% of the $3.5k/day flow is uninformed and you capture your size-share (~5%), uninformed $ filled ≈ `$3.5k × 0.30 × 0.05` ≈ $53/day × 0.5¢/share... on ~$53 notional ≈ **+$0.27/day**. Generously **+$0.30/day per $1k**.
- **Adverse selection:** the other ~70% of flow is at least weakly informed, and the binary gaps. Even a *single* 5–10pt repricing on grid/quali news while you're resting $1k means a mark-to-market loss of `$1k/0.30 shares × 0.05–0.10` ≈ **$170–340 per event**, hitting maybe a few times across a race weekend. Amortized to a per-day figure over the ~10-day quoting window with ~3 such gaps: **−$50 to −$100/day per $1k of two-sided quote** unless you pull quotes faster than the bots (you won't — secondsDelay=3 and incumbents co-locate).
- **Inventory-to-resolution risk:** any unhedged share held into the green flag is a 0/1 lottery. Binary variance is maximal near p=0.3. Not a daily bleed but a fat tail.

### Net
```
EV ≈ +0.20 (rebate) + 0.30 (half-spread) + 0 (rewards) − ~50 to 100 (adverse selection)
   ≈ −$50 to −$100 per $1,000 of resting two-sided quote per day
```
**Strongly negative**, dominated entirely by adverse selection. The income terms are ~$0.50/day per $1k — three orders of magnitude too small to matter. The model is *insensitive* to the rebate/half-spread assumptions; it's an adverse-selection story.

### What would make it positive?
- You'd need either (a) **reward income** large enough to pay you to hold inventory through gaps — i.e. a funded `rewards_daily_rate` of roughly **$50–150/day** *and* a small enough field of competing makers that your score share × pool exceeds your adverse-selection bleed; or (b) a **genuine pricing edge** (you reprice on news faster/better than incumbents). Neither holds: rewards = $0, and we have **no demonstrated edge** on winner/pole (efficient) — SC merely *matches* our historical estimate (no edge), and SC/constructor markets are dead ($5 / $71 liquidity, ~$0 volume → no flow to earn from regardless).

---

## 4. Specifically: at what reward rate / flow does it flip? — INFERRED

For a retail maker holding $1k of two-sided quote, break-even needs reward income ≈ adverse-selection bleed ≈ **$50–100/day per $1k quoted**, *after* dividing the pool by the number of competing makers. On a market with ~$20k of competing maker depth, your $1k = ~5% score share, so the market's **funded pool would need to be ~$1,000–2,000/day** for your slice to clear the bleed — **higher than the top-5 reward rate (~$500/day) on the entire platform.** That reward level does not exist on F1 markets and is unlikely to. **It does not flip positive at any realistic reward rate**, because incumbent bots already quote it to the 1¢ tick on favorites and to 0.2¢ on longshots — they would absorb the pool before you, and they reprice faster on the news that drives the adverse selection.

---

## 5. The verdict (concrete)

| Market | Liquidity | Flow | Reward pool | MM verdict |
|---|---|---|---|---|
| Monaco **winner** (favorites) | ~$187k | ~$7k/day | **$0 (unfunded)** | **Negative-EV.** Bot-dominated, 1¢ tick, news-gapping. No edge → adverse selection wins. |
| Monaco winner (longshot tails) | thin | ~$0 | $0 | Zero income (no flow); 0.2¢ spread is cosmetic. |
| Monaco **pole** | ~$3k | <$1k/day | $0 | Negative/zero — same dynamics, less flow. |
| Safety car / constructor-1st | $5 / $71 | ~$0 | $0 | **Dead.** No flow to make. |

**It is not a real opportunity for retail.** It's a **bot-dominated, currently-unfunded grind** whose only positive terms (rebate + half-spread) total ~$0.50/day per $1k and are swamped by adverse selection on a binary that gaps on news you can't react to faster than incumbents.

### It would flip positive only if ALL of:
1. **Polymarket funds the LP-reward pool on the specific F1 race market** (today: $0). Watch `sampling-markets` / `rewards.rates` going non-null — they fund select markets around big events. Realistic budget even then is ~$1/day median, occasionally $200–500/day on hero markets — **still below the ~$1–2k/day your slice would need.**
2. **You have a real, faster-than-incumbent repricing edge** on the news (quali times, grid penalties, weather) — i.e. you cancel-and-replace before the bots. We have **no such edge** today, and `secondsDelay: 3` + retail latency works against you.
3. **You quote a *less-contested* market** — but every less-contested F1 market here (SC, constructor, pole) is also a *no-flow* market, so there's nothing to earn. The contestation and the flow are the same thing.

The realistic path to +EV is **not** market-making; it's **taking** when our model has a calibrated edge (e.g. if SC ever diverges materially from market) and the taker fee (0.03·p·(1−p), ≤0.75%) is smaller than the edge — i.e. use the markets as a *price-taker* on genuine mispricings, not as a *maker* farming a non-existent rebate.

---

## 6. Sources

**Verified from official Polymarket docs/help/API:**
- Trading fees + formula (`fee = C × feeRate × p × (1−p)`, rate 0.03, peak $0.75/100 shares at p=0.5, started 2026-03-30): https://help.polymarket.com/en/articles/13364478-trading-fees and https://docs.polymarket.com/trading/fees
- Maker rebates (25% of taker fees, per-market pro-rata by fee-equivalent, daily, $1 min): https://docs.polymarket.com/developers/market-makers/maker-rebates-program and https://help.polymarket.com/en/articles/13364471-maker-rebates-program
- Liquidity rewards scoring (`S(v,s)=((v−s)/v)²·size`, two-sided ÷c rule, max_spread/min_size, daily pro-rata): https://docs.polymarket.com/market-makers/liquidity-rewards and https://help.polymarket.com/en/articles/13364466-liquidity-rewards
- Live market data (Gamma): `https://gamma-api.polymarket.com/events?slug=f1-monaco-grand-prix-winner-2026-06-07` (28 neg-risk sub-markets; `feeType: sports_fees_v2`; `clobRewards: null`)
- Live reward config (CLOB): `https://clob.polymarket.com/markets/<conditionId>` → `rewards: {rates: null, min_size: 50, max_spread: 4.5}`
- **Reward funding status (decisive):** `https://clob.polymarket.com/sampling-markets` → Monaco winner/pole **absent** (0 hits); across 1000 earning markets median daily rate $1, max $500; only season-long F1 championship props funded, at $0.001/day.
- Live Leclerc book: `https://clob.polymarket.com/book?token_id=...` → 0.29/0.32, ~$3k best bid.

**Inferred (stated as such above):**
- `makerBaseFee/takerBaseFee: 1000` = legacy bps fields, inert/superseded by `feeSchedule` (not documented as active; identical static value across all markets; makers verifiably pay 0).
- The EV magnitudes in §3–4 are my estimates from the measured flow/spread/budget, not Polymarket figures.
