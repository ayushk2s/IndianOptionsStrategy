# ==========================
# BROKER SETTINGS
# ==========================

BROKERAGE_PER_ORDER = 20.0      # Rs 20 per executed order

# ==========================
# TAXES & CHARGES
# ==========================

STT_OPTION_SELL = 0.0015        # 0.15% on SELL side premium turnover

NSE_TRANSACTION_CHARGE = 0.00035

SEBI_CHARGE_PER_RUPEE = 10 / 10000000

STAMP_DUTY = 0.00003            # 0.003% on BUY side premium turnover

GST = 0.18                      # 18% on brokerage + exchange transaction charge

# ==========================
# SLIPPAGE SETTINGS
# ==========================

NIFTY_ATM_SLIPPAGE = 1.0        # points per side
NIFTY_OTM_SLIPPAGE = 2.0

BANKNIFTY_SLIPPAGE = 1.5

FINNIFTY_SLIPPAGE = 3.0

MIDCPNIFTY_SLIPPAGE = 3.0

# ==========================
# LATENCY BUFFER
# ==========================

LATENCY_BUFFER = 0.25           # extra points per order side

# ==========================
# BACKTEST FILTER
# ==========================

MIN_EXPECTED_EDGE = 5.0         # minimum expected profit per trade

# ==========================
# TOTAL COST CALCULATION
# ==========================

def calculate_total_cost(
    buy_price,
    sell_price,
    quantity,
    brokerage=BROKERAGE_PER_ORDER
):
    """
    Computes all-in transaction cost for one buy+sell pair of a single option leg.
    For multi-leg trades, pass brokerage = BROKERAGE_PER_ORDER * (n_orders // 2)
    so that brokerage_total = BROKERAGE_PER_ORDER * n_orders.

    buy_price  : price at which the option was BOUGHT (per unit)
    sell_price : price at which the option was SOLD  (per unit)
    quantity   : number of units (lot size)
    brokerage  : Rs per order; internally multiplied by 2 for the buy+sell pair
    """
    buy_turnover  = buy_price  * quantity
    sell_turnover = sell_price * quantity

    brokerage_total = brokerage * 2

    stt = sell_turnover * STT_OPTION_SELL

    exchange_charge = (buy_turnover + sell_turnover) * NSE_TRANSACTION_CHARGE

    sebi_charge = (buy_turnover + sell_turnover) * SEBI_CHARGE_PER_RUPEE

    stamp_duty = buy_turnover * STAMP_DUTY

    gst = (brokerage_total + exchange_charge) * GST

    total_cost = (
        brokerage_total
        + stt
        + exchange_charge
        + sebi_charge
        + stamp_duty
        + gst
    )

    return round(total_cost, 2)
