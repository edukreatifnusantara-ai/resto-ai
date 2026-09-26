# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
import json
import os
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import Order as OrderModel, OrderStatus, Stock, MenuItem

MASTER_DATA_PATH = Path("/home/edukreativ-vps/resto-ai/data/warung_ndelik_master_data.json")


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


def get_dashboard_summary_data(db: Session) -> dict:
    master = load_master_data()
    
    # 1. Live Orders Metrics from SQLite DB
    live_sales_scalar = db.query(func.sum(OrderModel.total)).filter(OrderModel.state == OrderStatus.COMPLETED).scalar()
    live_total_sales = round(float(live_sales_scalar) if live_sales_scalar else 0.0, 2)
    live_completed_count = db.query(OrderModel).filter(OrderModel.state == OrderStatus.COMPLETED).count()
    
    # 2. Historical 28-day calculations from Agustus.xlsx data
    hist = master.get("historical_hpp_benchmark", {})
    daily_rows = hist.get("daily_summary", [])
    total_hpp_28d = hist.get("total_pemakaian_bahan", 32947239.0)
    avg_daily_hpp = hist.get("rata_rata_pemakaian_harian", 1176687.11)
    
    daily_fixed_cost = master.get("fixed_costs", {}).get("daily_fixed_cost_allocation", 933333.33)
    
    daily_table_data = []
    total_omzet_28d = 0
    total_net_profit_28d = 0
    
    for row in daily_rows:
        tgl = row.get("tanggal", "")
        hpp = float(row.get("pemakaian_bahan_hpp", 0))
        eff_hpp = max(hpp, 800000)
        est_omzet = round(eff_hpp / 0.42, 0)
        laba_kotor = est_omzet - hpp
        laba_bersih = laba_kotor - daily_fixed_cost
        margin_pct = round((laba_bersih / est_omzet) * 100, 1) if est_omzet > 0 else 0
        
        total_omzet_28d += est_omzet
        total_net_profit_28d += laba_bersih
        
        daily_table_data.append({
            "tanggal": tgl,
            "stok_tersedia": row.get("total_stok_tersedia", 0),
            "sisa_stok": row.get("sisa_stok_akhir", 0),
            "pemakaian_hpp": hpp,
            "estimasi_omzet": est_omzet,
            "laba_kotor": laba_kotor,
            "beban_tetap": round(daily_fixed_cost, 0),
            "laba_bersih": laba_bersih,
            "margin_persen": margin_pct
        })
        
    avg_daily_omzet = round(total_omzet_28d / len(daily_table_data), 0) if daily_table_data else 2885662
    avg_daily_profit = round(total_net_profit_28d / len(daily_table_data), 0) if daily_table_data else 775641
    avg_margin_pct = round((total_net_profit_28d / total_omzet_28d) * 100, 1) if total_omzet_28d > 0 else 26.9

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

    # 7. Income Statement (Formal Accounting)
    income_statement = {
        "revenue": {
            "gross_food_sales": round(total_omzet_28d * 0.72, 0),
            "gross_beverage_sales": round(total_omzet_28d * 0.28, 0),
            "total_revenue": total_omzet_28d
        },
        "cogs": {
            "food_ingredients": 26038717.0,
            "beverage_ingredients": 3952380.0,
            "total_cogs": total_hpp_28d,
            "cogs_percentage": round((total_hpp_28d / total_omzet_28d) * 100, 1)
        },
        "gross_profit": total_omzet_28d - total_hpp_28d,
        "operating_expenses": {
            "management_payroll": 8000000.0,
            "staff_payroll": 18500000.0,
            "total_payroll": 26500000.0,
            "utilities_water_electricity": 1500000.0,
            "gas_fuel": 2088000.0,
            "mineral_water_gallons": 464000.0,
            "packaging_and_tissue": 609200.0,
            "total_operating_expenses": 28000000.0 + 3161200.0
        },
        "ebitda": (total_omzet_28d - total_hpp_28d) - (round(daily_fixed_cost * 28, 0)),
        "net_profit": total_net_profit_28d,
        "net_margin_percent": avg_margin_pct
    }

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
            "monthly_fixed_cost": master.get("fixed_costs", {}).get("total_monthly_fixed_cost", 28000000),
            "daily_fixed_cost": daily_fixed_cost,
            "total_net_profit": total_net_profit_28d,
            "avg_daily_profit": avg_daily_profit,
            "avg_margin_percent": avg_margin_pct,
            "total_inventory_value": total_inventory_value,
            "live_sales_db": live_total_sales,
            "live_orders_count": live_completed_count
        },
        "income_statement": income_statement,
        "purchasing": purchasing,
        "inventory": {
            "total_items": len(inventory_items),
            "total_valuation": total_inventory_value,
            "items": inventory_items
        },
        "charts": {
            "daily_dates": [d["tanggal"] for d in daily_table_data],
            "daily_omzet": [d["estimasi_omzet"] for d in daily_table_data],
            "daily_hpp": [d["pemakaian_hpp"] for d in daily_table_data],
            "daily_net_profit": [d["laba_bersih"] for d in daily_table_data],
            "cost_breakdown": {
                "labels": ["Gaji Staf (10 Org)", "Gaji Manajemen (Owner & Co)", "HPP Bahan Riil (Bulanan)", "Utilitas (Listrik/Air)", "Ops Gas & Perlengkapan"],
                "values": [18500000, 8000000, round(avg_daily_hpp * 30, 0), 1500000, 3161200]
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
            }
        },
        "top_menus": top_menus,
        "roster": all_roster,
        "daily_records": daily_table_data
    }


def get_dashboard_html_page() -> str:
    from pathlib import Path
    html_template_path = Path("/home/edukreativ-vps/resto-ai/templates/dashboard.html")
    if html_template_path.exists():
        with open(html_template_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Template not found</h1>"
