import csv
from django.http import HttpResponse
from .selectors import get_dashboard_overview_data


def export_reconciliation_csv(
    target_date,
    channel_filter=None,
    staff_id=None,
    period='day',
    shift_filter='',
    month=None,
    quarter=None,
    year=None,
):
    """
    Xuất báo cáo doanh thu & đối soát theo bộ lọc ra file CSV tương thích Excel (UTF-8 BOM).
    """
    data = get_dashboard_overview_data(
        target_date=target_date,
        channel_filter=channel_filter,
        staff_id=staff_id,
        period=period,
        shift_filter=shift_filter,
        month=month,
        quarter=quarter,
        year=year,
    )
    summary = data['summary']
    period_info = data['period_info']

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    filename = f"BaoCao_DoanhThu_BangOnsen_{period_info['start_date'].strftime('%Y%m%d')}_{period_info['end_date'].strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    writer.writerow(['BÁO CÁO DOANH THU & ĐỐI SOÁT - BANG ONSEN SPA & RESORT'])
    writer.writerow(['Kỳ báo cáo:', period_info['period_label']])
    writer.writerow(['Từ ngày - Đến ngày:', f"{period_info['start_date'].strftime('%d/%m/%Y')} - {period_info['end_date'].strftime('%d/%m/%Y')}"])
    writer.writerow(['Ca làm việc:', shift_filter or 'Tất cả'])
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

    writer.writerow(['PHIẾU ĐỐI SOÁT CHỐT CA'])
    writer.writerow([
        'Mã ca', 'Ngày làm việc', 'Nhân viên', 'Ca làm việc',
        'Tiền mặt hệ thống', 'Tiền mặt thực nhận', 'Chênh lệch', 'Trạng thái'
    ])
    for shf in data['shift_reports']:
        status_label = 'Khớp 100%' if shf.cash_variance == 0 else f"Chênh lệch {shf.cash_variance:,.0f}đ"
        writer.writerow([
            shf.shift_id,
            shf.shift_date.strftime('%d/%m/%Y'),
            shf.receptionist.full_name,
            shf.get_shift_type_display(),
            f"{shf.cash_revenue:,.0f}",
            f"{shf.actual_cash:,.0f}",
            f"{shf.cash_variance:,.0f}",
            status_label,
        ])

    return response