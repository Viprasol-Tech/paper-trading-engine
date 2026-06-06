# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[SemVer](https://semver.org/).

## [0.2.0] - 2025

### Added
- **Limit orders** via `PaperEngine.submit_limit_order(...)` with marketable
  detection, price improvement for the taker, and resting non-marketable orders.
- **Partial fills**: `Order` tracks `filled_qty`/`remaining`/`status`, and
  `PaperEngine.fill_resting_order(...)` drives a resting order to completion as
  liquidity arrives. Orders can be cancelled with `cancel_order(...)`.
- **Pluggable fee models** (`fees` module): `ZeroFee`, `PercentageFee`,
  `PerShareFee` (with per-order minimum), and `FlatFee`.
- **Slippage models**: `NoSlippage`, `PercentageSlippage`, and `FixedSlippage`
  applied to market-order fills.
- **Short selling**: positions are now signed; with `allow_short=True` sells can
  open/extend shorts, and positions may flip long↔short through zero.
- **Unrealized PnL** and **`total_pnl(...)`** (realized + unrealized − fees) on
  the engine, plus per-position `unrealized_pnl(...)`.
- **Multiple accounts / portfolios** (`portfolio` module): `Portfolio` groups
  named engines and produces a consolidated `PnLReport` with per-account and
  per-position detail and return %.
- **Order book matching helper** (`orderbook` module): `OrderBook` with
  price-time priority, partial fills, market/limit crossing, best bid/ask,
  spread, mid, depth, and cancellation.
- **CLI subcommands**: `demo`, `report` (portfolio PnL), and `book` (order book
  matching), alongside `version`.

### Changed
- `Position` reworked around a single signed `apply(...)` method supporting long,
  short, reduce, close, and flip cases (the `add`/`reduce` API is preserved).
- `PaperEngine` accepts `fee_model`/`slippage_model`/`allow_short`; the legacy
  `fee_rate` argument continues to work.

## [0.1.0] - 2025

### Added
- Initial release of paper-trading-engine: Simulated paper-trading / execution engine with positions and PnL.
