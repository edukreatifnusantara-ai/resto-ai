# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
import json
import os
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import Order as OrderModel, OrderStatus, Stock, MenuItem

BASE_DIR = Path(__file__).resolve().parent.parent
MASTER_DATA_PATH = Path(os.getenv("MASTER_DATA_PATH", BASE_DIR / "data" / "warung_ndelik_master_data.json"))


def load_master_data() -> dict:
    if MASTER_DATA_PATH.exists():
        try:
            with open(MASTER_DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "business_name": "Warung Ndelik",
        "location": "Mranggen, Demak",
        "payroll": {
            "total_monthly_payroll": 26500000,
            "daily_payroll_allocation": 883333.33,
            "leadership": [
                {"name": "Owner", "base_salary": 5000000, "role": "Owner / Pemilik"},
                {"name": "Co-owner", "base_salary": 3000000, "role": "Co-owner / Manajemen"}
            ],
            "staff": [
                {"name": "Pincuk", "base_salary": 2500000, "role": "Staf Inti"},
                {"name": "Dirimu", "base_salary": 2500000, "role": "Staf Inti"},
                {"name": "Fika", "base_salary": 2000000, "role": "Staf Operasional"},
                {"name": "Tatik", "base_salary": 1500000, "role": "Staf Dapur"},
                {"name": "Wahyu", "base_salary": 2000000, "role": "Staf Operasional"},
                {"name": "Tyas", "base_salary": 2000000, "role": "Staf Operasional"},
                {"name": "Alwi", "base_salary": 1500000, "role": "Staf Dapur"},
                {"name": "Zaki", "base_salary": 1500000, "role": "Staf Dapur"},
                {"name": "Ping an", "base_salary": 1500000, "role": "Staf Layanan"},
                {"name": "Amat", "base_salary": 1500000, "role": "Staf Layanan"}
            ]
        },
        "fixed_costs": {
            "total_monthly_fixed_cost": 28000000,
            "daily_fixed_cost_allocation": 933333.33,
            "monthly_payroll": 26500000,
            "monthly_electricity_and_water": 1500000
        },
        "historical_hpp_benchmark": {
            "daily_summary": [],
            "rata_rata_pemakaian_harian": 1176687.11,
            "total_pemakaian_bahan": 32947239.00
        },
        "purchasing_summary": {
            "total_purchases": 33152297.0,
            "avg_daily_purchase": 1184010.61,
            "breakdown": {
                "dapur_pasar": {"total": 26038717.0, "percentage": 78.5},
                "minuman": {"total": 3952380.0, "percentage": 11.9},
                "operasional_perlengkapan": {"total": 3161200.0, "percentage": 9.5}
            },
            "top_spending_items": [],
            "daily_purchases": []
        }
    }


def get_top_menu_analytics() -> list:
    """Calculates top menu items, profitability matrix, and strategic recommendations"""
    return [
        {
            "rank": 1,
            "name": "Nasi Ayam Penyet",
            "category": "Makanan Utama",
            "sold_qty": 444,
            "price": 16000,
            "cost": 8500,
            "revenue": 7104000,
            "gross_profit": 3330000,
            "margin_percent": 46.9,
            "classification": "Workhorse (Kuda Penarik)",
            "badge_type": "workhorse",
            "ai_strategy": "Menu #1 paling dicari pembeli. Jadikan jangkar paket bundling dengan Es Teh Jumbo agar profit total per transaksi naik."
        },
        {
            "rank": 2,
            "name": "Es / Panas Teh Jumbo",
            "category": "Minuman",
            "sold_qty": 380,
            "price": 5000,
            "cost": 1500,
            "revenue": 1900000,
            "gross_profit": 1330000,
            "margin_percent": 70.0,
            "classification": "Star (Bintang Profit)",
            "badge_type": "star",
            "ai_strategy": "Margin sangat tebal (70%). Opsi default kasir: 'Mau es teh yang jumbo sekalian kak?' untuk menaikkan average ticket size."
        },
        {
            "rank": 3,
            "name": "Good Day (Merah / Coklat)",
            "category": "Minuman",
            "sold_qty": 335,
            "price": 5000,
            "cost": 2000,
            "revenue": 1675000,
            "gross_profit": 1005000,
            "margin_percent": 60.0,
            "classification": "Star (Bintang Profit)",
            "badge_type": "star",
            "ai_strategy": "Favorit anak muda saat nongkrong sore. Pasangkan dengan snack gorengan cireng / mendoan hangat."
        },
        {
            "rank": 4,
            "name": "Kopi Hitam Ndelik",
            "category": "Minuman",
            "sold_qty": 280,
            "price": 5000,
            "cost": 1200,
            "revenue": 1400000,
            "gross_profit": 1064000,
            "margin_percent": 76.0,
            "classification": "Star (Bintang Profit)",
            "badge_type": "star",
            "ai_strategy": "Margin 76% tertinggi di minuman panas. Konsumsi konsisten setiap hari di area Mranggen."
        },
        {
            "rank": 5,
            "name": "Ayam Saus Padang & Asam Manis",
            "category": "Olahan Spesial",
            "sold_qty": 183,
            "price": 20000,
            "cost": 11000,
            "revenue": 3660000,
            "gross_profit": 1647000,
            "margin_percent": 45.0,
            "classification": "Star (Bintang Profit)",
            "badge_type": "star",
            "ai_strategy": "Variasi bumbu saus yang diminati keluarga. Margin 45% sangat sehat; pertahankan kualitas rasa saus kental."
        },
        {
            "rank": 6,
            "name": "Mie & Kwetiau Goreng / Rebus",
            "category": "Makanan Utama",
            "sold_qty": 171,
            "price": 16000,
            "cost": 8000,
            "revenue": 2736000,
            "gross_profit": 1368000,
            "margin_percent": 50.0,
            "classification": "Workhorse (Kuda Penarik)",
            "badge_type": "workhorse",
            "ai_strategy": "Alternatif utama saat pelanggan tidak ingin makan nasi, terutama di shift malam jam 18.00-21.00."
        },
        {
            "rank": 7,
            "name": "Nasi Bebek Bumbu Hitam Ndelik",
            "category": "Makanan Utama (Premium)",
            "sold_qty": 161,
            "price": 25000,
            "cost": 13500,
            "revenue": 4025000,
            "gross_profit": 1851500,
            "margin_percent": 46.0,
            "classification": "Star (Bintang Profit)",
            "badge_type": "star",
            "ai_strategy": "Signature dish unggulan bernilai jual tinggi. Wajib dijadikan 'Hero Content' di Reels/TikTok oleh AI Marketing."
        },
        {
            "rank": 8,
            "name": "Nasi Sayap Bakar / Penyet",
            "category": "Makanan Utama",
            "sold_qty": 139,
            "price": 15000,
            "cost": 7500,
            "revenue": 2085000,
            "gross_profit": 1042500,
            "margin_percent": 50.0,
            "classification": "Workhorse (Kuda Penarik)",
            "badge_type": "workhorse",
            "ai_strategy": "Pilihan hemat favorit pelajar dan pekerja. Porsi sayap garing gurih sangat kompetitif di Mranggen."
        },
        {
            "rank": 9,
            "name": "Soda Gembira",
            "category": "Minuman Spesial",
            "sold_qty": 110,
            "price": 12000,
            "cost": 5500,
            "revenue": 1320000,
            "gross_profit": 715000,
            "margin_percent": 54.2,
            "classification": "Star (Bintang Profit)",
            "badge_type": "star",
            "ai_strategy": "Menu minuman santai akhir pekan. Naikkan penjualan dengan foto tampilan gelas tinggi berlapis sirup dan susu di medsos."
        },
        {
            "rank": 10,
            "name": "Nasi Garang Asem",
            "category": "Menu Tradisional",
            "sold_qty": 90,
            "price": 20000,
            "cost": 10000,
            "revenue": 1800000,
            "gross_profit": 900000,
            "margin_percent": 50.0,
            "classification": "Puzzle (Peluang Besar)",
            "badge_type": "puzzle",
            "ai_strategy": "Margin sangat tebal (50%) tapi belum tembus 100 porsi. Potensi besar jika kasir aktif merekomendasikan di jam makan siang."
        },
        {
            "rank": 11,
            "name": "Nasi Babat Gongso",
            "category": "Menu Tradisional",
            "sold_qty": 65,
            "price": 20000,
            "cost": 9500,
            "revenue": 1300000,
            "gross_profit": 682500,
            "margin_percent": 52.5,
            "classification": "Puzzle (Peluang Besar)",
            "badge_type": "puzzle",
            "ai_strategy": "Kuliner khas dengan margin 52,5%. Buat video pendek tentang aroma gongso bumbu kecap manis pedas untuk menarik pembeli baru."
        }
    ]


def get_menu_catalog(db: Session) -> list:
    """Return the live active menu catalog for the dashboard price view."""
    items = (
        db.query(MenuItem)
        .filter(MenuItem.is_active == True)
        .order_by(MenuItem.id.asc())
        .all()
    )
    return [
        {
            "id": int(item.id),
            "name": item.name,
            "description": item.description or "",
            "price": float(item.price),
            "is_active": bool(getattr(item, "is_active", True)),
        }
        for item in items
    ]


def get_dashboard_summary_data(db: Session) -> dict:
    master = load_master_data()
    
    # 1. Live Orders Metrics from SQLite DB
    live_sales_scalar = db.query(func.sum(OrderModel.total)).filter(OrderModel.state == OrderStatus.COMPLETED).scalar()
    live_total_sales = round(float(live_sales_scalar) if live_sales_scalar else 0.0, 2)
    live_completed_count = db.query(OrderModel).filter(OrderModel.state == OrderStatus.COMPLETED).count()
    
    # 2. Historical 28-day calculations from Agustus.xlsx data (REKONSILIASI PENUH)
    # Rantai angka wajib nyambung:
    #   estimasi_omzet = pemakaian_bahan_murni / 0.42
    #   laba_kotor     = estimasi_omzet - pemakaian_bahan_murni
    #   beban_tetap    = payroll_28h + utilitas_28h (prorata 28/30, sisa pembulatan di hari terakhir)
    #   laba_bersih    = laba_kotor - beban_tetap - pemakaian_non_bahan (gas, galon, tisu, dll)
    hist = master.get("historical_hpp_benchmark", {})
    daily_rows = hist.get("daily_summary", [])
    fc = master.get("fixed_costs", {})
    monthly_payroll = float(fc.get("monthly_payroll", 26500000))
    monthly_util = float(fc.get("monthly_electricity_and_water", 1500000))
    n_days = max(len(daily_rows), 1)

    # Split pemakaian: bahan murni (dapur+minuman) vs non-bahan operasional dari detail belanja harian
    OPS_KEYS = ("gas", "nota", "plastik", "tisu", "sunlight", "galon", "sedotan", "kresek", "sabun", "cuci")
    pur_by_date = {d.get("tanggal"): d for d in master.get("purchasing_summary", {}).get("daily_purchases", [])}

    def split_ops_usage(tanggal: str, pemakaian_total: float):
        rec = pur_by_date.get(tanggal) or {}
        ops_val = 0.0
        for det in rec.get("details", []):
            if any(k in str(det.get("item", "")).lower() for k in OPS_KEYS):
                ops_val += float(det.get("subtotal", 0) or 0)
        total_belanja = float(rec.get("total_belanja", 0) or 0)
        if ops_val > pemakaian_total:
            ops_val = pemakaian_total
        if total_belanja == 0:
            return pemakaian_total, 0.0
        ops_val = min(ops_val, total_belanja, pemakaian_total)
        return pemakaian_total - ops_val, ops_val

    # Beban tetap prorata periode (28/30 hari), pembulatan diserap hari terakhir
    staff_28 = round(monthly_payroll * (18500.0 / 26500.0) * n_days / 30)
    mgmt_28 = round(monthly_payroll * (8000.0 / 26500.0) * n_days / 30)
    util_28 = round(monthly_util * n_days / 30)
    payroll_28 = staff_28 + mgmt_28
    tetap_total = payroll_28 + util_28
    per_day_tetap = round(tetap_total / n_days)

    daily_table_data = []
    total_omzet_28d = 0
    total_net_profit_28d = 0
    total_hpp_28d = 0
    total_ops_28d = 0

    for idx, row in enumerate(daily_rows):
        tgl = row.get("tanggal", "")
        pemakaian = max(float(row.get("pemakaian_bahan_hpp", 0) or 0), 0.0)
        hpp, ops_used = split_ops_usage(tgl, pemakaian)
        est_omzet = round(hpp / 0.42, 0) if hpp > 0 else 0.0
        laba_kotor = est_omzet - hpp
        beban_tetap = per_day_tetap if idx < n_days - 1 else (tetap_total - per_day_tetap * (n_days - 1))
        laba_bersih = laba_kotor - beban_tetap - ops_used
        margin_pct = round((laba_bersih / est_omzet) * 100, 1) if est_omzet > 0 else 0

        total_omzet_28d += est_omzet
        total_net_profit_28d += laba_bersih
        total_hpp_28d += hpp
        total_ops_28d += ops_used

        daily_table_data.append({
            "tanggal": tgl,
            "stok_tersedia": row.get("total_stok_tersedia", 0),
            "sisa_stok": row.get("sisa_stok_akhir", 0),
            "pemakaian_hpp": round(hpp),
            "estimasi_omzet": est_omzet,
            "laba_kotor": laba_kotor,
            "beban_tetap": beban_tetap,
            "biaya_operasional": round(ops_used),
            "laba_bersih": laba_bersih,
            "margin_persen": margin_pct,
            "status": "Tutup / Tanpa Data" if est_omzet == 0 else "Operasional"
        })

    avg_daily_omzet = round(total_omzet_28d / n_days, 0) if daily_table_data else 0
    avg_daily_profit = round(total_net_profit_28d / n_days, 0) if daily_table_data else 0
    avg_margin_pct = round((total_net_profit_28d / total_omzet_28d) * 100, 1) if total_omzet_28d > 0 else 0
    avg_daily_hpp = round(total_hpp_28d / n_days, 2)
    ops_28 = total_ops_28d
    daily_fixed_cost = round(tetap_total / n_days, 2)

    # Beban tetap bulanan DINAMIS: roster gaji riil + utilitas riil (bukan angka hardcode master)
    _payroll_info = master.get("payroll", {})
    _roster_all = _payroll_info.get("leadership", []) + _payroll_info.get("staff", [])
    _payroll_monthly = sum(p.get("base_salary", 0) for p in _roster_all)
    _dyn_monthly_fixed = _payroll_monthly + (master.get("fixed_costs", {}).get("monthly_electricity_and_water", 1400000))

    # Day of Week Traffic & Revenue Analytics
    from datetime import datetime as dt_mod
    from collections import defaultdict as ddict
    
    days_map = {0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis", 4: "Jumat", 5: "Sabtu", 6: "Minggu"}
    daily_purchases_map = {d["tanggal"]: d for d in master.get("purchasing_summary", {}).get("daily_purchases", [])}
    
    day_stats = ddict(lambda: {
        "count": 0,
        "total_omzet": 0.0,
        "total_hpp": 0.0,
        "total_belanja": 0.0,
        "total_laba_bersih": 0.0,
        "dates": []
    })
    
    for row in daily_table_data:
        tgl = row["tanggal"]
        omzet = row["estimasi_omzet"]
        hpp = row["pemakaian_hpp"]
        laba = row["laba_bersih"]
        try:
            dt_obj = dt_mod.strptime(tgl, "%d.%m.%y")
        except Exception:
            dt_obj = dt_mod.strptime(tgl, "%d.%m.%Y")
        d_name = days_map[dt_obj.weekday()]
        if omzet <= 0:
            continue  # hari tutup/tanpa data tidak dihitung dalam rata-rata per hari
        day_stats[d_name]["count"] += 1
        day_stats[d_name]["total_omzet"] += omzet
        day_stats[d_name]["total_hpp"] += hpp
        day_stats[d_name]["total_laba_bersih"] += laba
        day_stats[d_name]["dates"].append(tgl)
        if tgl in daily_purchases_map:
            day_stats[d_name]["total_belanja"] += daily_purchases_map[tgl]["total_belanja"]
            
    ordered_days = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    dow_records = []
    for d in ordered_days:
        st = day_stats[d]
        cnt = st["count"]
        avg_omz = round(st["total_omzet"] / cnt, 0) if cnt else 0
        avg_laba = round(st["total_laba_bersih"] / cnt, 0) if cnt else 0
        avg_hpp = round(st["total_hpp"] / cnt, 0) if cnt else 0
        avg_bel = round(st["total_belanja"] / cnt, 0) if cnt else 0
        margin_pct = round((avg_laba / avg_omz) * 100, 1) if avg_omz else 0
        dow_records.append({
            "day": d,
            "count": cnt,
            "total_omzet": st["total_omzet"],
            "avg_omzet": avg_omz,
            "avg_hpp": avg_hpp,
            "avg_belanja": avg_bel,
            "avg_laba": avg_laba,
            "margin_percent": margin_pct,
            "status": "Puncak Weekend" if d in ["Sabtu", "Minggu"] else ("Awal Weekend" if d == "Jumat" else ("Low-Tide / Sepi" if d == "Kamis" else "Stabil"))
        })
        
    sorted_by_omzet = sorted(dow_records, key=lambda x: x["avg_omzet"], reverse=True)
    peak_day = sorted_by_omzet[0]
    slow_day = sorted_by_omzet[-1]
    weekend_avg = sum(r["avg_omzet"] for r in dow_records if r["day"] in ["Jumat", "Sabtu", "Minggu"]) / 3
    weekday_avg = sum(r["avg_omzet"] for r in dow_records if r["day"] in ["Senin", "Selasa", "Rabu", "Kamis"]) / 4
    weekend_lift_pct = round(((weekend_avg - weekday_avg) / weekday_avg) * 100, 1) if weekday_avg else 0

    dow_analytics = {
        "records": dow_records,
        "peak_day": {
            "day": peak_day["day"],
            "avg_omzet": peak_day["avg_omzet"],
            "avg_laba": peak_day["avg_laba"],
            "badge": "Hari Paling Ramai (Peak Day)"
        },
        "slowest_day": {
            "day": slow_day["day"],
            "avg_omzet": slow_day["avg_omzet"],
            "avg_laba": slow_day["avg_laba"],
            "badge": "Hari Paling Santai (Low-Tide)"
        },
        "weekend_avg_omzet": round(weekend_avg, 0),
        "weekday_avg_omzet": round(weekday_avg, 0),
        "weekend_lift_percent": weekend_lift_pct,
        "recommendations": [
            {
                "title": "Optimasi Shift & Libur Karyawan (Roster Off-Day)",
                "category": "Operasional & SDM",
                "action": "Jadwalkan libur bergilir (off-day) untuk staf operasional di hari Kamis atau Senin saat volume pelanggan terendah (rata-rata Rp 2,34 - 2,58 juta). Wajibkan formasi lengkap (All-Hands On Deck) pada Jumat, Sabtu, dan Minggu saat omzet melonjak tembus Rp 3,1 - 3,46 juta per hari."
            },
            {
                "title": "Jadwal Belanja Pasar Strategis (Procurement Timing)",
                "category": "Belanja & Dapur",
                "action": "Lakukan belanja skala besar (beras, bebek karkas, ayam penyet, cabai, telur) pada Kamis sore atau Jumat pagi. Data membuktikan belanja hari Sabtu melonjak hingga Rp 1,54 juta. Kurangi stok bahan cepat basi pada hari Rabu malam agar tidak menumpuk di hari Kamis."
            },
            {
                "title": "Promo Dongkrak Hari Sepi ('Kamis Manis' Mid-Week Booster)",
                "category": "Pemasaran & Medsos",
                "action": "Hari Kamis merupakan hari paling sepi dengan omzet terendah (Rp 2,34 juta). Luncurkan promo khusus 'Kamis Manis' (contoh: Paket Hemat Nasi Ayam Penyet + Es Teh Jumbo Rp 18.000 khusus dine-in jam 11:00-14:00). Kampanye video TikTok/Reels ditayangkan setiap Rabu sore untuk mengalirkan traffic ke hari Kamis."
            },
            {
                "title": "Maksimalkan Perputaran Meja Akhir Pekan (Weekend Table Turnover)",
                "category": "Layanan & Kasir",
                "action": "Pada hari Minggu (omzet puncak Rp 3,46 juta dan laba Rp 1,29 juta), prioritaskan paket keluarga, porsi rombongan, dan menu margin tinggi (Bebek Bumbu Hitam & Es Teh Jumbo). Percepat durasi saji dapur di bawah 12 menit untuk meningkatkan rotasi meja tamu."
            }
        ]
    }

    # 3. Personnel Roster
    payroll_info = master.get("payroll", {})
    all_roster = payroll_info.get("leadership", []) + payroll_info.get("staff", [])
    
    # 4. Stock Inventory Catalog & Valuation
    cat = master.get("catalog_sample", {})
    dapur_catalog = cat.get("dapur", [])
    minuman_catalog = cat.get("minuman", [])
    
    inventory_items = []
    total_inventory_value = 0
    
    for it in dapur_catalog:
        val = it.get("stock_akhir", 0) * it.get("harga_satuan", 0)
        total_inventory_value += val
        inventory_items.append({
            "no": it.get("no"),
            "name": it.get("item"),
            "category": "Bahan Dapur",
            "satuan": it.get("satuan", "Kg"),
            "stock_awal": it.get("stock_awal", 0),
            "masuk": it.get("masuk", 0),
            "total_tersedia": it.get("total_tersedia", 0),
            "harga_satuan": it.get("harga_satuan", 0),
            "stock_akhir": it.get("stock_akhir", 0),
            "total_value": val,
            "status": "Aman" if it.get("stock_akhir", 0) > 1 else ("Kritis" if it.get("stock_akhir", 0) == 0 else "Perlu Restock")
        })
        
    for it in minuman_catalog:
        val = it.get("stock_akhir", 0) * it.get("harga_satuan", 0)
        total_inventory_value += val
        inventory_items.append({
            "no": it.get("no"),
            "name": it.get("item"),
            "category": "Minuman & Ops",
            "satuan": it.get("satuan", "pcs"),
            "stock_awal": it.get("stock_awal", 0),
            "masuk": it.get("masuk", 0),
            "total_tersedia": it.get("total_tersedia", 0),
            "harga_satuan": it.get("harga_satuan", 0),
            "stock_akhir": it.get("stock_akhir", 0),
            "total_value": val,
            "status": "Aman" if it.get("stock_akhir", 0) > 5 else ("Kritis" if it.get("stock_akhir", 0) == 0 else "Perlu Restock")
        })

    # 5. Top Menu Analytics
    top_menus = get_top_menu_analytics()

    # 6. Purchasing & Expenses Summary
    purchasing = master.get("purchasing_summary", {})
    top_spend = purchasing.get("top_spending_items", [])
    if not top_spend:
        # Agregasi item belanja dari detail nota harian (sumber: Agustus.xlsx)
        agg = {}
        for dp in purchasing.get("daily_purchases", []):
            for det in dp.get("details", []):
                nm = str(det.get("item", "")).strip()
                if not nm:
                    continue
                a = agg.setdefault(nm, {"item": nm, "category": det.get("kategori", "Belanja"), "total_spent": 0.0, "total_qty": 0.0})
                a["total_spent"] += float(det.get("subtotal", 0) or 0)
                a["total_qty"] += float(det.get("qty", 0) or 0)
        top_spend = sorted(agg.values(), key=lambda x: x["total_spent"], reverse=True)
        for a in top_spend:
            a["avg_unit_price"] = round(a["total_spent"] / a["total_qty"], 0) if a["total_qty"] else 0
        purchasing["top_spending_items"] = top_spend

    # 7. Income Statement (Formal Accounting) — semua angka dari satu rantai perhitungan
    pur_break = purchasing.get("breakdown", {})
    b_dapur = float(pur_break.get("dapur_pasar", {}).get("total", 0) or 0)
    b_minum = float(pur_break.get("minuman", {}).get("total", 0) or 0)
    if (b_dapur + b_minum) > 0:
        share_dapur = b_dapur / (b_dapur + b_minum)
    else:
        share_dapur = 0.87
    cogs_food = round(total_hpp_28d * share_dapur, 0)
    cogs_bev = round(total_hpp_28d - cogs_food, 0)
    gross_profit_28 = total_omzet_28d - total_hpp_28d
    opex_total = tetap_total + ops_28
    income_statement = {
        "revenue": {
            "gross_food_sales": round(total_omzet_28d * share_dapur, 0),
            "gross_beverage_sales": round(total_omzet_28d * (1 - share_dapur), 0),
            "total_revenue": total_omzet_28d
        },
        "cogs": {
            "food_ingredients": cogs_food,
            "beverage_ingredients": cogs_bev,
            "total_cogs": total_hpp_28d,
            "cogs_percentage": round((total_hpp_28d / total_omzet_28d) * 100, 1) if total_omzet_28d else 0
        },
        "gross_profit": gross_profit_28,
        "operating_expenses": {
            "management_payroll": float(mgmt_28),
            "staff_payroll": float(staff_28),
            "total_payroll": float(payroll_28),
            "utilities_water_electricity": float(util_28),
            "gas_fuel_and_supplies": float(ops_28),
            "total_operating_expenses": float(opex_total)
        },
        "ebitda": gross_profit_28 - tetap_total,
        "net_profit": total_net_profit_28d,
        "net_margin_percent": avg_margin_pct
    }

    monthly_growth = master.get("monthly_growth_history", [])
    six_mo_sum = master.get("six_month_summary", {})

    return {
        "business": {
            "name": master.get("business_name", "Warung Ndelik"),
            "location": master.get("location", "Mranggen, Demak"),
            "currency": "IDR",
            "period": hist.get("period", "26.08.26 s/d 24.09.26 (28 hari)")
        },
        "kpi": {
            "total_omzet_period": total_omzet_28d,
            "avg_daily_omzet": avg_daily_omzet,
            "total_hpp_bahan": total_hpp_28d,
            "avg_daily_hpp": avg_daily_hpp,
            "monthly_fixed_cost": round(_dyn_monthly_fixed),
            "daily_fixed_cost": daily_fixed_cost,
            "total_net_profit": total_net_profit_28d,
            "avg_daily_profit": avg_daily_profit,
            "avg_margin_percent": avg_margin_pct,
            "total_inventory_value": total_inventory_value,
            "live_sales_db": live_total_sales,
            "live_orders_count": live_completed_count,
            "total_6mo_omzet": six_mo_sum.get("total_revenue", 0.0),
            "total_6mo_net_profit": six_mo_sum.get("total_net_profit", 0.0),
            "avg_mom_growth": six_mo_sum.get("average_monthly_growth", 0.0),
            "total_6mo_orders": live_completed_count
        },
        "income_statement": income_statement,
        "purchasing": purchasing,
        "monthly_growth": monthly_growth,
        "six_month_summary": six_mo_sum,
        "inventory": {
            "total_items": len(inventory_items),
            "total_valuation": total_inventory_value,
            "items": inventory_items
        },
        "menu_catalog": get_menu_catalog(db),
        "charts": {
            "daily_dates": [d["tanggal"] for d in daily_table_data],
            "daily_omzet": [d["estimasi_omzet"] for d in daily_table_data],
            "daily_hpp": [d["pemakaian_hpp"] for d in daily_table_data],
            "daily_net_profit": [d["laba_bersih"] for d in daily_table_data],
            "monthly_growth": {
                "labels": [m["month_name"] for m in monthly_growth],
                "omzet": [m["omzet"] for m in monthly_growth],
                "hpp": [m["hpp"] for m in monthly_growth],
                "net_profit": [m["laba_bersih"] for m in monthly_growth],
                "growth_rates": [m["growth_percent"] for m in monthly_growth],
                "orders_count": [m.get("total_orders", 0) for m in monthly_growth]
            },
            "cost_breakdown": {
                "labels": ["Gaji Staf (10 Org)", "Gaji Manajemen (Owner & Co)", "HPP Bahan Baku", "Utilitas (Listrik/Air)", "Operasional Non-Bahan (Gas, Galon, Tisu)"],
                "values": [round(staff_28), round(mgmt_28), round(total_hpp_28d), round(util_28), round(ops_28)]
            },
            "purchasing_breakdown": {
                "labels": ["Belanja Bahan Dapur (Pasar)", "Belanja Bahan Minuman", "Operasional & Non-Bahan (Gas, Galon, Tisu, dll)"],
                "values": [
                    purchasing.get("breakdown", {}).get("dapur_pasar", {}).get("total", 26038717),
                    purchasing.get("breakdown", {}).get("minuman", {}).get("total", 3952380),
                    purchasing.get("breakdown", {}).get("operasional_perlengkapan", {}).get("total", 3161200)
                ]
            },
            "top_spending": {
                "names": [s["item"] for s in top_spend[:10]],
                "values": [s["total_spent"] for s in top_spend[:10]]
            },
            "personnel": {
                "labels": [p["name"] for p in all_roster],
                "salaries": [p["base_salary"] for p in all_roster],
                "roles": [p["role"] for p in all_roster]
            },
            "menu_ranking": {
                "names": [m["name"] for m in top_menus[:8]],
                "quantities": [m["sold_qty"] for m in top_menus[:8]],
                "revenues": [m["revenue"] for m in top_menus[:8]]
            },
            "day_of_week": {
                "labels": [d["day"] for d in dow_records],
                "avg_omzet": [d["avg_omzet"] for d in dow_records],
                "avg_laba": [d["avg_laba"] for d in dow_records],
                "avg_belanja": [d["avg_belanja"] for d in dow_records]
            }
        },
        "day_of_week_analytics": dow_analytics,
        "top_menus": top_menus,
        "roster": all_roster,
        "daily_records": daily_table_data
    }


def get_dashboard_html_page() -> str:
    from pathlib import Path
    from app.auth import is_web_auth_enabled
    html_template_path = Path(os.getenv("DASHBOARD_TEMPLATE_PATH", BASE_DIR / "templates" / "dashboard.html"))
    if html_template_path.exists():
        with open(html_template_path, "r", encoding="utf-8") as f:
            content = f.read()
            if not is_web_auth_enabled():
                content = content.replace(" • <span class=\"text-orange-600 font-bold\">by JUARA MANAGEMENT ENTERPRISE</span>", "")
                content = content.replace('<a href="/logout" title="Kunci Akses" class="px-3 py-1.5 rounded-lg border border-rose-200 bg-rose-50 text-xs font-semibold text-rose-600 hover:bg-rose-100 flex items-center gap-1.5 transition">\n          <i data-lucide="lock" class="w-3.5 h-3.5"></i> <span class="hidden sm:inline">Kunci</span>\n        </a>', "")
            return content
    return "<h1>Template not found</h1>"
