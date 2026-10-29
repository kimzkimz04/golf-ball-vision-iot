#!/usr/bin/env python3
"""วิเคราะห์ข้อมูลจากโหมด --collect แล้วแนะนำเกณฑ์ใหม่สำหรับ config.py

การใช้งาน:
    python tools/analyze_calibration.py                      # อ่าน config.COLLECT_CSV
    python tools/analyze_calibration.py calibration_data.csv # อ่านไฟล์อื่น

ตั้งชื่อตอนเก็บข้อมูลแบบนี้ เพื่อให้สคริปต์รู้ว่าอันไหนคือลูกกอล์ฟ:
    golf_white / golf_pink / golf_neon     <- ขึ้นต้นด้วย golf_ = ลูกกอล์ฟ
    pingpong_orange / tennis / ring / ...  <- อย่างอื่นทั้งหมด = ไม่ใช่ลูกกอล์ฟ

สิ่งที่รายงาน:
  1. ค่าของแต่ละลูก (รัศมี สี พื้นผิว) แบบ เปอร์เซ็นไทล์ 1 / 50 / 99
  2. เกณฑ์ตัวเดียวที่แยกลูกกอล์ฟออกจากของอื่นได้ดีที่สุด (เหมือนตารางใน README)
  3. ค่าที่แนะนำให้ใส่ใน config.py
  4. ผลตัดสินของโปรแกรมตอนเก็บข้อมูล ถูกกี่ % (บอกว่าเกณฑ์ ณ ตอนนั้นใช้ได้แค่ไหน)
"""

import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import config

# ชื่อคอลัมน์ใน CSV (ดู utils/recorder.py:CSV_HEADER) -> ชื่อสั้นที่ใช้ในรายงาน
FEATURES = {
    "รัศมี": "radius",
    "H": "H", "S": "S", "V": "V",
    "คะแนนพื้นผิว": "texture",
    "ความหนาแน่นขอบ": "edge_density",
    "จุดสะท้อนแสง": "bright_frac",
    "การกระจายความสว่าง": "v_std",
    "คะแนนขอบ": "support",
}


def load(path):
    rows = defaultdict(lambda: defaultdict(list))
    verdicts = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            label = row["ของจริง"].strip()
            if not label or label == "-":
                continue
            for col, name in FEATURES.items():
                rows[label][name].append(float(row[col]))
            verdicts[label].append((row["ผลตัดสิน"], row["สี/เหตุผล"]))
    return {k: {n: np.array(v) for n, v in d.items()} for k, d in rows.items()}, verdicts


def pct(a, q):
    return float(np.percentile(a, q))


def best_threshold(golf, other):
    """หาเส้นแบ่งตัวเดียวที่แยกสองกลุ่มได้ถูกมากที่สุด คืน (ความถูกต้อง, เส้นแบ่ง, ทิศ)"""
    values = np.unique(np.concatenate([golf, other]))
    if len(values) > 400:
        values = np.percentile(values, np.linspace(0, 100, 400))
    total = len(golf) + len(other)
    best = (0.0, 0.0, ">=")
    for t in values:
        for direction in (">=", "<"):
            if direction == ">=":
                correct = np.count_nonzero(golf >= t) + np.count_nonzero(other < t)
            else:
                correct = np.count_nonzero(golf < t) + np.count_nonzero(other >= t)
            acc = correct / total
            if acc > best[0]:
                best = (acc, float(t), direction)
    return best


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else config.COLLECT_CSV
    if not os.path.exists(path):
        print(f"ไม่พบไฟล์ {path} - เก็บข้อมูลก่อนด้วย: python ball_detect.py --collect golf_white")
        return 1

    data, verdicts = load(path)
    if not data:
        print(f"{path} ยังไม่มีข้อมูลที่ติดชื่อไว้")
        return 1

    golf_labels = sorted(k for k in data if k.startswith("golf_"))
    other_labels = sorted(k for k in data if not k.startswith("golf_"))

    print(f"ไฟล์: {path}")
    print(f"ลูกกอล์ฟ: {', '.join(golf_labels) or '-'}")
    print(f"ไม่ใช่ลูกกอล์ฟ: {', '.join(other_labels) or '-'}\n")

    # ---------- 1. ค่าของแต่ละลูก ----------
    print("=" * 96)
    print("1. ค่าที่วัดได้ของแต่ละลูก  (เปอร์เซ็นไทล์ 1 / ค่ากลาง / เปอร์เซ็นไทล์ 99)")
    print("=" * 96)
    cols = ["radius", "H", "S", "V", "texture", "edge_density", "bright_frac", "support"]
    print(f"{'ลูก':<18}{'แถว':>6}  " + "".join(f"{c:>17}" for c in cols))
    for label in golf_labels + other_labels:
        d = data[label]
        cells = []
        for c in cols:
            a = d[c]
            fmt = "{:.0f}" if c in ("radius", "H", "S", "V", "texture") else "{:.2f}"
            cells.append(f"{fmt.format(pct(a, 1))}/{fmt.format(pct(a, 50))}/{fmt.format(pct(a, 99))}")
        print(f"{label:<18}{len(d['radius']):>6}  " + "".join(f"{c:>17}" for c in cells))

    # ---------- 2. เกณฑ์ตัวเดียวที่ดีที่สุด ----------
    if golf_labels and other_labels:
        print("\n" + "=" * 96)
        print("2. ถ้าใช้ค่าเดียวแยก 'ลูกกอล์ฟ' กับ 'ไม่ใช่' จะถูกได้มากสุดเท่าไร")
        print("   (ถ่วงน้ำหนักให้ทุกลูกเท่ากัน ลูกที่เก็บนานกว่าจะไม่ได้เปรียบ)")
        print("=" * 96)
        for c in ["texture", "edge_density", "bright_frac", "v_std", "V", "S", "radius"]:
            # สุ่มให้ทุกลูกมีจำนวนแถวเท่ากัน ไม่งั้นลูกที่เก็บนานจะครอบงำผล
            n = min(len(data[k][c]) for k in golf_labels + other_labels)
            rng = np.random.default_rng(0)
            pick = lambda k: rng.choice(data[k][c], n, replace=False)
            golf = np.concatenate([pick(k) for k in golf_labels])
            other = np.concatenate([pick(k) for k in other_labels])
            acc, t, direction = best_threshold(golf, other)
            print(f"   {c:<14} ลูกกอล์ฟ {direction} {t:<10.3f} ถูก {acc:6.1%}")

    # ---------- 3. ค่าที่แนะนำ ----------
    print("\n" + "=" * 96)
    print("3. ค่าที่แนะนำสำหรับ config.py")
    print("=" * 96)
    if golf_labels:
        lo = min(pct(data[k]["radius"], 1) for k in golf_labels)
        hi = max(pct(data[k]["radius"], 99) for k in golf_labels)
        margin = max(3, round((hi - lo) * 0.15))
        r_lo, r_hi = int(lo - margin), int(hi + margin)
        print(f"GOLF_RADIUS_RANGE = ({r_lo}, {r_hi})     # ลูกกอล์ฟจริง {lo:.0f}-{hi:.0f} px + เผื่อ {margin}")
        for k in other_labels:
            r = data[k]["radius"]
            inside = np.mean((r >= r_lo) & (r <= r_hi))
            note = "  <- ขนาดทับลูกกอล์ฟ ต้องใช้สี/พื้นผิวแยก" if inside > 0.05 else ""
            print(f"      {k:<16} อยู่ในช่วงนี้ {inside:6.1%}{note}")

        all_r = np.concatenate([data[k]["radius"] for k in data])
        print(f"MIN_RADIUS = {max(10, int(pct(all_r, 0.5) * 0.7))}   MAX_RADIUS = {int(pct(all_r, 99.5) * 1.3)}"
              f"     # ครอบทุกลูกที่เก็บมา +30%")

        tex_golf = np.concatenate([data[k]["texture"] for k in golf_labels])
        print(f"GOLF_MIN_TEXTURE: ลูกกอล์ฟต่ำสุด (p1) = {pct(tex_golf, 1):.1f}"
              f"  -> ดูตาราง 2 ว่าแยกได้ดีพอจะเปิดใช้ไหม")

        print("\nช่วงสี (H, S, V) ของลูกกอล์ฟแต่ละสี  p1-p99 เผื่อขอบอีกเล็กน้อย:")
        for k in golf_labels:
            d = data[k]
            h = (max(0, int(pct(d["H"], 1)) - 5), min(179, int(pct(d["H"], 99)) + 5))
            s = (max(0, int(pct(d["S"], 1)) - 20), min(255, int(pct(d["S"], 99)) + 20))
            v = (max(0, int(pct(d["V"], 1)) - 30), 255)
            print(f"   {k:<14} (({h[0]}, {s[0]}, {v[0]}), ({h[1]}, {s[1]}, {v[1]}))")
            if h[1] - h[0] > 90:
                # สีชมพู/แดงอยู่คร่อมรอยต่อของวงล้อสี (179 ต่อกับ 0) ค่ากลางจึงกระโดดไปมา
                low = d["H"][d["H"] < 90]
                high = d["H"][d["H"] >= 90]
                print(f"   {'':<14} ^ H คร่อมรอยต่อ 179/0: ต่ำ {len(low)} แถว"
                      f"{f' ({int(low.min())}-{int(low.max())})' if len(low) else ''}"
                      f" / สูง {len(high)} แถว"
                      f"{f' ({int(high.min())}-{int(high.max())})' if len(high) else ''}"
                      f" -> ใช้ 2 ช่วงแยกกัน หรือดูเฉพาะกลุ่มที่แถวเยอะ")
        print("   หมายเหตุ: H/S/V ใน CSV เป็นค่ากลางของทั้งลูก ส่วนโปรแกรมนับ 'สัดส่วนพิกเซล'"
              " - ใช้เป็นจุดตั้งต้น แล้วทดสอบสดอีกครั้ง")

    # ---------- 4. ผลตัดสินตอนเก็บข้อมูล ----------
    print("\n" + "=" * 96)
    print("4. ผลตัดสินของโปรแกรมตอนเก็บข้อมูล (ด้วยเกณฑ์ใน config.py ณ ตอนนั้น)")
    print("=" * 96)
    for label in golf_labels + other_labels:
        v = verdicts[label]
        want_golf = label.startswith("golf_")
        correct = sum(1 for verdict, _ in v if (verdict == "Golf Ball") == want_golf)
        reasons = defaultdict(int)
        for verdict, why in v:
            reasons[f"{verdict}: {why}"] += 1
        top = ", ".join(f"{k} {n}" for k, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:3])
        print(f"   {label:<16} ถูก {correct / len(v):6.1%}   ({top})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
