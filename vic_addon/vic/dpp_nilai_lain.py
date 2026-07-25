"""DPP Nilai Lain buat PPN 12% (PMK 131/2024).

Mulai 2025 tarif PPN jadi 12%, tapi buat barang/jasa umum dasar pengenaan pajaknya pakai
DPP Nilai Lain = 11/12 x nilai transaksi, jadi PPN yang dibayar tetap setara 11%:

	Net Total                    10.000
	DPP Nilai Lain = 11/12 x     10.000  =  9.167
	PPN 12% x 9.167                      =  1.100   (sama dengan 11% x 10.000)

Di ERPNext, baris pajaknya tetap pakai `On Net Total` rate 11 (hasil rupiahnya identik dan
perhitungan per item, item-wise tax breakup, sampai GL entry tetap logika bawaan). Field
DPP Nilai Lain di sini dipakai buat print / e-Faktur / laporan pajak.
"""

from frappe.utils import flt

# PMK 131/2024: DPP Nilai Lain = 11/12 x nilai transaksi.
# Kalau aturannya berubah (misal balik ke 12% penuh), ganti rasio ini jadi 1.
DPP_NILAI_LAIN_RATIO = 11 / 12

DPP_NILAI_LAIN_DOCTYPES = (
	"Sales Order",
	"Sales Invoice",
	"Purchase Order",
	"Purchase Invoice",
)


def get_dpp_nilai_lain(net_total):
	return flt(net_total) * DPP_NILAI_LAIN_RATIO


def set_dpp_nilai_lain(doc, method=None):
	"""Hitung DPP Nilai Lain dari net total (hook `validate`, setelah total dihitung ERPNext)."""
	doc.custom_dpp_nilai_lain = flt(
		get_dpp_nilai_lain(doc.net_total), doc.precision("custom_dpp_nilai_lain")
	)
	doc.custom_base_dpp_nilai_lain = flt(
		get_dpp_nilai_lain(doc.base_net_total), doc.precision("custom_base_dpp_nilai_lain")
	)
