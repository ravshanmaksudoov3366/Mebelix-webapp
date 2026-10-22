"""Lot hajmini hisoblash: stopga tegsa aynan «risk %» qadar yo'qotiladigan qilib."""
import math


def lot_size(equity, risk_pct, sl_dist, contract_size, min_vol, max_vol, step, tolerance=1.5):
    """(lot, haqiqiy_risk_$, izoh). lot=0 — savdo ochilmaydi.

    sl_dist — kirish va stop orasidagi narx farqi (oltinda dollarda, masalan 6.40).
    contract_size — 1 lotdagi unsiya (XM, ko'p brokerlarda 100).
    Minimal lot ham ko'zlangan riskdan `tolerance` baravardan ko'p xavf tug'dirsa — savdo qilinmaydi.
    """
    if equity <= 0 or sl_dist <= 0 or contract_size <= 0 or step <= 0:
        return 0.0, 0.0, "noto'g'ri ma'lumot"
    risk_money = equity * risk_pct / 100.0
    loss_per_lot = sl_dist * contract_size
    raw = risk_money / loss_per_lot
    vol = math.floor(raw / step + 1e-9) * step
    vol = round(vol, 8)
    if vol < min_vol:
        if min_vol * loss_per_lot <= risk_money * tolerance:
            vol = min_vol
        else:
            need = min_vol * loss_per_lot
            return 0.0, need, (f"hisob kichik: minimal lot ({min_vol}) bilan ham ${need:.2f} xavf, "
                               f"ko'zlangani ${risk_money:.2f}")
    vol = min(vol, max_vol)
    decimals = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    vol = round(vol, decimals)
    return vol, vol * loss_per_lot, "ok"
