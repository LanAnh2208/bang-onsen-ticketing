import csv
from django.http import HttpResponse
from .selectors import get_dashboard_overview_data


def export_reconciliation_csv(target_date, channel_filter=None, staff_id=None):
    """
    Xuất báo cáo doanh thu & đối soát cuối ngày ra file CSV tương thích Excel (UTF-8 BOM).
    """
    data = get_dashboard_overview_data(target_date, channel_filter, staff_id)
    summary = data['summary']

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    filename = f"BaoCao_DoanhThu_BangOnsen_{target_date.strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    writer.writerow(['BÁO CÁO DOANH THU & ĐỐI SOÁT CUỐI NGÀY - BANG ONSEN SPA & RESORT'])
    writer.writerow(['Ngày báo cáo:', target_date.strftime('%d/%m/%Y')])
    writer.writerow([])
    writer.writerow(['CHỈ TIÊU TỔNG HỢP', 'GIÁ TRỊ (VNĐ / VÉ)'])
    writer.writerow(['Tổng doanh thu thực thu', f"{summary['total_revenue']:,.0f}"])
    writer.writerow(['Tổng số vé đã xuất', summary['total_tickets']])
    writer.writerow(['Doanh thu tại quầy (POS)', f"{summary['pos_revenue']:,.0f}"])
    writer.writerow(['Doanh thu trực tuyến (Online)', f"{summary['online_revenue']:,.0f}"])
    writer.writerow(['Thực thu Tiền mặt', f"{summary['cash_revenue']:,.0f}"])
    writer.writerow(['Thực thu Không tiền mặt (CK/Thẻ/Ví)', f"{summary['non_cash_revenue']:,.0f}"])
    writer.writerow([])

    writer.writerow(['ĐỐI SOÁT DOANH THU THEO NHÂN VIÊN LỄ TÂN (POS)'])
    writer.writerow([
        'Mã NV', 'Họ và tên', 'Số đơn', 'Số vé',
        'Tiền mặt (VNĐ)', 'Chuyển khoản (VNĐ)', 'Thẻ / Ví điện tử (VNĐ)', 'Tổng thực thu (VNĐ)'
    ])
    for row in data['staff_reconciliation']:
        writer.writerow([
            row['created_by__account_id'] or 'N/A',
            row['created_by__full_name'] or row['created_by__username'] or 'Khách Online',
            row['order_count'],
            row['ticket_count'] or 0,
            f"{(row['cash_total'] or 0):,.0f}",
            f"{(row['transfer_total'] or 0):,.0f}",
            f"{(row['card_ewallet_total'] or 0):,.0f}",
            f"{(row['total_collected'] or 0):,.0f}",
        ])
    writer.writerow([])

    writer.writerow(['PHIẾU ĐỐI SOÁT CHỐT CA CUỐI NGÀY'])
    writer.writerow([
        'Mã ca', 'Nhân viên', 'Ca làm việc',
        'Tiền mặt hệ thống', 'Tiền mặt thực nhận', 'Chênh lệch', 'Trạng thái'
    ])
    for shf in data['shift_reports']:
        status_label = 'Khớp 100%' if shf.cash_variance == 0 else f"Chênh lệch {shf.cash_variance:,.0f}đ"
        writer.writerow([
            shf.shift_id,
            shf.receptionist.full_name,
            shf.get_shift_type_display(),
            f"{shf.cash_revenue:,.0f}",
            f"{shf.actual_cash:,.0f}",
            f"{shf.cash_variance:,.0f}",
            status_label
        ])

    return response