const posCart = {};
let posCurrentTotal = 0;
let _lastAnimatedTotal = -1;
let _lastVietQrUrl = '';
let _posQrScanner = null;
let _posQrScanning = false;

// Cấu hình tài khoản nhận tiền VietQR động (thay bằng STK thật để quét test trên app ngân hàng)
const POS_VIETQR_CONFIG = {
    bankId: 'MB',
    accountNo: '0123456789',
    accountName: 'BANG ONSEN SPA RESORT',
    template: 'compact2'
};

function posFormatVND(amount) {
    return Math.round(amount).toLocaleString('vi-VN') + ' VNĐ';
}

function posIsValidQtCccd(val) {
    return /^(044|045)\d{9}$/.test((val || '').trim());
}

function posGetTotalPaidTickets() {
    let total = 0;
    for (const svcId in posCart) {
        total += (posCart[svcId].ADULT || 0) + (posCart[svcId].CHILD || 0);
    }
    return total;
}

function posGetPaidOptions() {
    const opts = [];
    const labels = { ADULT: 'Trên 1,4m', CHILD: 'Từ 1m – 1,4m' };
    for (const svcId in posCart) {
        const svc = window.POS_PRICES[svcId];
        if (!svc) continue;
        ['ADULT', 'CHILD'].forEach(t => {
            const qty = posCart[svcId][t] || 0;
            if (qty > 0) {
                opts.push({
                    value: `${svcId}|${t}`,
                    label: `${svc.name} – ${labels[t]} (${posFormatVND(svc.prices[t].qt)})`,
                    qty: qty
                });
            }
        });
    }
    return opts;
}

function posSyncSelectOptions(selectEl, opts) {
    if (!selectEl) return;
    const prev = selectEl.value;
    selectEl.innerHTML = opts.map(o => `<option value="${o.value}">${o.label}</option>`).join('');
    if (opts.some(o => o.value === prev)) {
        selectEl.value = prev;
    } else if (opts.length > 0) {
        selectEl.value = opts[0].value;
    }
}

// Chỉ cho chọn tối đa 1 voucher; bấm lại vào voucher đang chọn sẽ tự bỏ chọn
function posSelectVoucher(checkboxEl) {
    if (checkboxEl.checked) {
        document.querySelectorAll('input[name="voucher_code"]').forEach(el => {
            if (el !== checkboxEl) el.checked = false;
        });
    }
    posRenderSummary();
}

function posAddExtraCccd() {
    const totalPaid = posGetTotalPaidTickets();
    const list = document.getElementById('extraCccdList');
    if (!list) return;

    const currentExtraCount = list.querySelectorAll('.pos-extra-cccd-row').length;
    if (currentExtraCount >= Math.max(0, totalPaid - 1)) return;

    const opts = posGetPaidOptions();
    const row = document.createElement('div');
    row.className = 'pos-extra-cccd-row';
    row.innerHTML = `
        <input type="text" maxlength="12" inputmode="numeric"
               class="pos-input extra-cccd-input" placeholder="Nhập 12 số CCCD đi cùng"
               oninput="posRenderSummary()">
        <select class="pos-input pos-qt-select extra-cccd-target" onchange="posRenderSummary()">
            ${opts.map(o => `<option value="${o.value}">${o.label}</option>`).join('')}
        </select>
        <button type="button" class="pos-remove-cccd-btn" onclick="this.parentElement.remove(); posRenderSummary();" aria-label="Xóa CCCD">×</button>
    `;
    list.appendChild(row);
    posRenderSummary();
}

function posUpdateQty(serviceId, ticketType, delta) {
    if (!window.POS_PRICES || !window.POS_PRICES[serviceId]) return;
    const svc = window.POS_PRICES[serviceId];
    if (!posCart[serviceId]) {
        posCart[serviceId] = { ADULT: 0, CHILD: 0, INFANT: 0 };
    }

    const currentPaid = posCart[serviceId].ADULT + posCart[serviceId].CHILD;
    if (delta > 0 && ticketType !== 'INFANT' && currentPaid >= svc.remaining) {
        alert(`Gói ${svc.name} chỉ còn tối đa ${svc.remaining} vé khả dụng hôm nay.`);
        return;
    }

    const nextVal = Math.max(0, posCart[serviceId][ticketType] + delta);
    posCart[serviceId][ticketType] = nextVal;

    const qtyEl = document.getElementById(`qty-${serviceId}-${ticketType}`);
    if (qtyEl) qtyEl.textContent = nextVal;

    if (posCart[serviceId].ADULT === 0 && posCart[serviceId].CHILD === 0 && posCart[serviceId].INFANT === 0) {
        delete posCart[serviceId];
    }

    posRenderSummary();
}

function posUpdateVietQR() {
    const emptyEl = document.getElementById('vietQrEmpty');
    const wrapEl = document.getElementById('vietQrWrapper');
    const imgEl = document.getElementById('vietQrImg');
    const infoEl = document.getElementById('qrAddInfoText');
    if (!emptyEl || !wrapEl || !imgEl) return;

    const amount = Math.round(posCurrentTotal || 0);
    if (amount <= 0) {
        emptyEl.style.display = 'block';
        wrapEl.style.display = 'none';
        _lastVietQrUrl = '';
        return;
    }

    const phoneVal = (document.getElementById('id_phone')?.value || '').trim();
    const addInfo = phoneVal ? `BANG ONSEN ${phoneVal}` : 'BANG ONSEN VE TAI QUAY';
    const url = `https://img.vietqr.io/image/${POS_VIETQR_CONFIG.bankId}-${POS_VIETQR_CONFIG.accountNo}-${POS_VIETQR_CONFIG.template}.png` +
                `?amount=${amount}&addInfo=${encodeURIComponent(addInfo)}&accountName=${encodeURIComponent(POS_VIETQR_CONFIG.accountName)}`;

    emptyEl.style.display = 'none';
    wrapEl.style.display = 'block';
    if (infoEl) infoEl.textContent = addInfo;

    if (url !== _lastVietQrUrl) {
        _lastVietQrUrl = url;
        imgEl.src = url;
    }
}

function posRenderSummary() {
    if (!window.POS_PRICES) return;

    const totalPaid = posGetTotalPaidTickets();
    const paidOpts = posGetPaidOptions();

    // Cập nhật giá công bố trên thẻ dịch vụ + highlight thẻ đang được chọn
    for (const svcId in window.POS_PRICES) {
        const svc = window.POS_PRICES[svcId];
        ['ADULT', 'CHILD'].forEach(t => {
            const el = document.getElementById(`price-${svcId}-${t}`);
            if (el) el.textContent = posFormatVND(svc.prices[t].normal);
        });
    }

    document.querySelectorAll('.pos-service-card').forEach(card => {
        const svcId = card.getAttribute('data-service-id');
        const q = posCart[svcId];
        const hasQty = q && ((q.ADULT || 0) + (q.CHILD || 0) + (q.INFANT || 0) > 0);
        card.classList.toggle('is-selected', Boolean(hasQty));
    });

    // Đồng bộ dropdown chọn gói cho CCCD chính & phụ
    const mainInput = document.getElementById('id_cccd_number');
    const mainWrap = document.getElementById('mainQtTargetWrap');
    const mainSelect = document.getElementById('mainQtTargetSelect');
    const mainIsQt = mainInput && posIsValidQtCccd(mainInput.value);

    if (mainSelect) posSyncSelectOptions(mainSelect, paidOpts);
    if (mainWrap) {
        mainWrap.style.display = (mainIsQt && paidOpts.length > 0) ? 'block' : 'none';
    }

    const extraSec = document.getElementById('extraCccdSection');
    const addBtn = document.getElementById('addExtraCccdBtn');
    const extraList = document.getElementById('extraCccdList');

    if (extraSec) extraSec.style.display = totalPaid >= 2 ? 'block' : 'none';
    if (extraList && totalPaid < 2) extraList.innerHTML = '';
    if (extraList) {
        extraList.querySelectorAll('.extra-cccd-target').forEach(sel => posSyncSelectOptions(sel, paidOpts));
    }
    if (addBtn && extraList) {
        const currentExtra = extraList.querySelectorAll('.pos-extra-cccd-row').length;
        addBtn.disabled = currentExtra >= Math.max(0, totalPaid - 1);
    }

    // Phân bổ CCCD Quảng Trị theo đúng (service_id, ticket_type) đã chọn
    const seenCccds = new Set();
    const qtAllocated = {};
    const qtAllocationsPayload = [];
    const warnings = [];

    const tryAllocate = (rawCccd, targetVal) => {
        const code = (rawCccd || '').trim();
        if (!posIsValidQtCccd(code) || !targetVal) return;
        if (seenCccds.has(code)) {
            warnings.push('Phát hiện số CCCD bị trùng lặp – mỗi số CCCD chỉ được tính ưu đãi 1 lần.');
            return;
        }
        const [svcId, tType] = targetVal.split('|');
        const maxForBucket = (posCart[svcId] && posCart[svcId][tType]) ? posCart[svcId][tType] : 0;
        const usedInBucket = qtAllocated[targetVal] || 0;

        if (usedInBucket >= maxForBucket) {
            warnings.push('Số lượng CCCD gán cho một loại vé vượt quá số vé đã chọn. Vui lòng chọn sang loại vé khác.');
            return;
        }

        seenCccds.add(code);
        qtAllocated[targetVal] = usedInBucket + 1;
        qtAllocationsPayload.push({ cccd: code, service_id: svcId, ticket_type: tType });
    };

    if (mainIsQt && mainSelect) {
        tryAllocate(mainInput.value, mainSelect.value);
    }
    if (extraList) {
        extraList.querySelectorAll('.pos-extra-cccd-row').forEach(row => {
            const inp = row.querySelector('.extra-cccd-input');
            const sel = row.querySelector('.extra-cccd-target');
            if (inp && sel) tryAllocate(inp.value, sel.value);
        });
    }

    const warnEl = document.getElementById('cccdWarning');
    if (warnEl) {
        if (warnings.length > 0) {
            warnEl.textContent = warnings[0];
            warnEl.style.display = 'block';
        } else {
            warnEl.style.display = 'none';
        }
    }

    const qtSlotsTotal = qtAllocationsPayload.length;
    const tierBadge = document.getElementById('priceTierBadge');
    if (tierBadge) {
        if (qtSlotsTotal > 0 && qtSlotsTotal === totalPaid) {
            tierBadge.textContent = `Ưu đãi QT (${qtSlotsTotal} vé)`;
            tierBadge.className = 'pos-badge-ok';
        } else if (qtSlotsTotal > 0) {
            tierBadge.textContent = `Kết hợp (${qtSlotsTotal} vé QT)`;
            tierBadge.className = 'pos-badge-ok';
        } else {
            tierBadge.textContent = 'Giá công bố';
            tierBadge.className = 'pos-badge-brown';
        }
    }

    // Render chi tiết Hóa đơn tạm tính
    let subtotal = 0;
    let html = '';
    const labels = { ADULT: '>1,4m', CHILD: '1–1,4m', INFANT: '<1m' };

    for (const svcId in posCart) {
        const svc = window.POS_PRICES[svcId];
        const q = posCart[svcId];
        const detailLines = [];
        let svcTotal = 0;

        ['ADULT', 'CHILD'].forEach(t => {
            const qty = q[t] || 0;
            if (qty <= 0) return;
            const qtCount = qtAllocated[`${svcId}|${t}`] || 0;
            const normalCount = qty - qtCount;

            if (qtCount > 0) {
                const sub = svc.prices[t].qt * qtCount;
                svcTotal += sub;
                detailLines.push(
                    `<div class="pos-row-between" style="font-size:12.5px;color:#2E7D32;margin-top:3px;">` +
                        `<span>${qtCount} vé ${labels[t]} (Ưu đãi QT)</span>` +
                        `<span>${posFormatVND(sub)}</span>` +
                    `</div>`
                );
            }
            if (normalCount > 0) {
                const sub = svc.prices[t].normal * normalCount;
                svcTotal += sub;
                detailLines.push(
                    `<div class="pos-row-between" style="font-size:12.5px;color:#5C6B77;margin-top:3px;">` +
                        `<span>${normalCount} vé ${labels[t]} (Giá công bố)</span>` +
                        `<span>${posFormatVND(sub)}</span>` +
                    `</div>`
                );
            }
        });

        if (q.INFANT > 0) {
            detailLines.push(
                `<div class="pos-row-between" style="font-size:12.5px;color:#5C6B77;margin-top:3px;">` +
                    `<span>${q.INFANT} vé ${labels.INFANT}</span>` +
                    `<span>Miễn phí</span>` +
                `</div>`
            );
        }

        subtotal += svcTotal;
        html += `<div class="pos-sum-item" style="display:block;">
            <div class="pos-row-between">
                <strong>${svc.name}</strong>
                <strong>${posFormatVND(svcTotal)}</strong>
            </div>
            <div style="margin-top:4px;">${detailLines.join('')}</div>
        </div>`;
    }

    const summaryList = document.getElementById('summaryItems');
    if (summaryList) {
        summaryList.innerHTML = html || '<p class="pos-note" style="margin:0;">Chưa chọn vé nào.</p>';
    }

    const selectedVoucher = document.querySelector('input[name="voucher_code"]:checked')?.value || '';
    let discount = 0;
    if (selectedVoucher && window.POS_VOUCHERS && window.POS_VOUCHERS[selectedVoucher]) {
        const v = window.POS_VOUCHERS[selectedVoucher];
        discount = v.type === 'Percent' ? (subtotal * v.value / 100) : Math.min(subtotal, v.value);
    }

    posCurrentTotal = Math.max(0, subtotal - discount);

    const subEl = document.getElementById('summarySubtotal');
    const discRow = document.getElementById('summaryDiscountRow');
    const discEl = document.getElementById('summaryDiscount');
    const totEl = document.getElementById('summaryTotal');
    const qrEl = document.getElementById('qrAmountText');

    if (subEl) subEl.textContent = posFormatVND(subtotal);
    if (discRow && discEl) {
        discRow.style.display = discount > 0 ? 'flex' : 'none';
        discEl.textContent = '-' + posFormatVND(discount);
    }
    if (totEl) {
        totEl.textContent = posFormatVND(posCurrentTotal);
        if (posCurrentTotal !== _lastAnimatedTotal) {
            _lastAnimatedTotal = posCurrentTotal;
            totEl.classList.remove('pos-price-pulse');
            void totEl.offsetWidth;
            totEl.classList.add('pos-price-pulse');
        }
    }
    if (qrEl) qrEl.textContent = posFormatVND(posCurrentTotal);

    const cartInput = document.getElementById('cartDataInput');
    if (cartInput) cartInput.value = JSON.stringify(posCart);

    const qtInput = document.getElementById('qtAllocationsInput');
    if (qtInput) qtInput.value = JSON.stringify(qtAllocationsPayload);

    posUpdateVietQR();
    posCalcChange();
}

function posTogglePayment() {
    const pm = document.querySelector('input[name="payment_method"]:checked')?.value || 'CASH';
    const cashSec = document.getElementById('cashSection');
    const qrSec = document.getElementById('qrSection');
    if (cashSec) cashSec.style.display = pm === 'CASH' ? 'block' : 'none';
    if (qrSec) qrSec.style.display = pm === 'BANK_TRANSFER' ? 'block' : 'none';
    posUpdateVietQR();
    posCalcChange();
}

function posCalcChange() {
    const submitBtn = document.getElementById('submitSaleBtn');
    if (!submitBtn) return;

    const hasItems = Object.keys(posCart).length > 0;
    const pm = document.querySelector('input[name="payment_method"]:checked')?.value || 'CASH';
    const changeDisplay = document.getElementById('cashChangeDisplay');

    if (!hasItems) {
        submitBtn.disabled = true;
        if (changeDisplay) changeDisplay.textContent = '';
        return;
    }

    if (pm === 'BANK_TRANSFER') {
        submitBtn.disabled = false;
        return;
    }

    const received = parseFloat(document.getElementById('cashReceivedInput')?.value || '0');
    if (received >= posCurrentTotal) {
        submitBtn.disabled = false;
        changeDisplay.innerHTML = `Tiền thừa trả khách: <span class="pos-text-red">${posFormatVND(received - posCurrentTotal)}</span>`;
    } else {
        submitBtn.disabled = true;
        changeDisplay.innerHTML = '<span class="pos-text-red">Khách chưa đưa đủ tiền mặt.</span>';
    }
}

// ================= CHUYỂN TAB & MÁY QUÉT QR CHECK-IN =================
function posSwitchTab(tabName) {
    if (tabName !== 'checkin') posStopQrScanner();

    const salePanel = document.getElementById('tabSalePanel');
    const checkinPanel = document.getElementById('tabCheckinPanel');
    const saleBtn = document.getElementById('tabBtnSale');
    const checkinBtn = document.getElementById('tabBtnCheckin');
    if (!salePanel || !checkinPanel) return;

    const isCheckin = tabName === 'checkin';
    salePanel.style.display = isCheckin ? 'none' : 'block';
    checkinPanel.style.display = isCheckin ? 'block' : 'none';
    if (saleBtn) saleBtn.classList.toggle('active', !isCheckin);
    if (checkinBtn) checkinBtn.classList.toggle('active', isCheckin);

    const activePanel = isCheckin ? checkinPanel : salePanel;
    activePanel.classList.remove('pos-panel-anim');
    void activePanel.offsetWidth;
    activePanel.classList.add('pos-panel-anim');

    if (isCheckin) {
        const qrInput = document.getElementById('qrCodeInput');
        if (qrInput) qrInput.focus();
    }
}

function _posHandleDecodedQr(decodedText) {
    const code = (decodedText || '').trim();
    if (!code) return;
    const input = document.getElementById('qrCodeInput');
    const form = document.getElementById('qrLookupForm');
    if (input) input.value = code;
    posStopQrScanner().finally(() => {
        if (form) form.submit();
    });
}

async function posStopQrScanner() {
    const wrap = document.getElementById('qrScannerContainer');
    const btn = document.getElementById('toggleScanBtn');
    if (_posQrScanner && _posQrScanning) {
        try {
            await _posQrScanner.stop();
            await _posQrScanner.clear();
        } catch (e) { /* ignore */ }
    }
    _posQrScanning = false;
    if (wrap) wrap.style.display = 'none';
    if (btn) btn.textContent = 'Bật Camera quét QR';
}

async function posToggleQrScanner() {
    if (_posQrScanning) {
        await posStopQrScanner();
        return;
    }

    if (typeof Html5Qrcode === 'undefined') {
        alert('Chưa tải được thư viện quét QR. Vui lòng kiểm tra kết nối mạng và tải lại trang.');
        return;
    }

    const wrap = document.getElementById('qrScannerContainer');
    const btn = document.getElementById('toggleScanBtn');
    const statusEl = document.getElementById('qrScanStatus');

    if (wrap) wrap.style.display = 'block';
    if (btn) btn.textContent = 'Tắt Camera';
    if (statusEl) statusEl.textContent = 'Đang khởi động camera...';

    _posQrScanner = new Html5Qrcode('qrReaderBox');
    const config = { fps: 10, qrbox: { width: 230, height: 230 } };

    try {
        await _posQrScanner.start(
            { facingMode: 'environment' },
            config,
            (decodedText) => _posHandleDecodedQr(decodedText),
            () => {}
        );
        _posQrScanning = true;
        if (statusEl) statusEl.textContent = 'Đưa mã QR trên vé điện tử của khách vào giữa khung hình...';
    } catch (err) {
        try {
            const cameras = await Html5Qrcode.getCameras();
            if (!cameras || cameras.length === 0) throw new Error('Không tìm thấy camera trên thiết bị.');
            await _posQrScanner.start(
                cameras[0].id,
                config,
                (decodedText) => _posHandleDecodedQr(decodedText),
                () => {}
            );
            _posQrScanning = true;
            if (statusEl) statusEl.textContent = 'Đưa mã QR trên vé điện tử của khách vào giữa khung hình...';
        } catch (err2) {
            if (statusEl) statusEl.innerHTML = `<span class="pos-text-red">Không thể mở camera (${err2.message || 'Vui lòng cấp quyền camera hoặc dùng nút Quét từ ảnh QR'}).</span>`;
            _posQrScanning = false;
            if (btn) btn.textContent = 'Bật Camera quét QR';
        }
    }
}

async function posScanQrFile(fileInput) {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    if (typeof Html5Qrcode === 'undefined') {
        alert('Chưa tải được thư viện quét QR.');
        return;
    }

    await posStopQrScanner();
    const wrap = document.getElementById('qrScannerContainer');
    const statusEl = document.getElementById('qrScanStatus');
    if (wrap) wrap.style.display = 'block';
    if (statusEl) statusEl.textContent = 'Đang đọc mã QR từ ảnh...';

    try {
        const fileScanner = new Html5Qrcode('qrReaderBox');
        const decodedText = await fileScanner.scanFile(file, true);
        fileScanner.clear();
        _posHandleDecodedQr(decodedText);
    } catch (err) {
        if (statusEl) statusEl.innerHTML = '<span class="pos-text-red">Không nhận diện được mã QR trong ảnh này. Vui lòng chọn ảnh rõ nét hơn.</span>';
    } finally {
        fileInput.value = '';
    }
}

// ================= ĐỐI SOÁT TIỀN MẶT CUỐI CA =================
function posCalcShiftVariance() {
    const input = document.getElementById('actualCashInput');
    const box = document.getElementById('shiftVarianceBox');
    if (!input || !box) return;

    const raw = input.value.trim();
    if (raw === '') {
        box.style.display = 'none';
        return;
    }

    const systemCash = parseFloat(input.getAttribute('data-system-cash') || '0');
    const actualCash = parseFloat(raw);
    if (isNaN(actualCash) || actualCash < 0) {
        box.style.display = 'none';
        return;
    }

    const diff = actualCash - systemCash;
    box.style.display = 'block';

    if (diff === 0) {
        box.className = 'pos-variance-box pos-variance-ok';
        box.textContent = '✓ Khớp doanh thu tiền mặt (Chênh lệch: 0 VNĐ)';
    } else if (diff > 0) {
        box.className = 'pos-variance-box pos-variance-diff';
        box.textContent = `⚠ Thừa tiền mặt: +${posFormatVND(diff)} (Hệ thống sẽ ghi nhận cảnh báo gửi Quản lý)`;
    } else {
        box.className = 'pos-variance-box pos-variance-diff';
        box.textContent = `⚠ Thiếu tiền mặt: -${posFormatVND(Math.abs(diff))} (Hệ thống sẽ ghi nhận cảnh báo gửi Quản lý)`;
    }
}

// ================= KHỞI TẠO SỰ KIỆN =================
document.addEventListener('DOMContentLoaded', () => {
    const toggleBtn = document.getElementById('togglePasswordBtn');
    const passwordInput = document.getElementById('id_password');
    if (toggleBtn && passwordInput) {
        toggleBtn.addEventListener('click', () => {
            const isHidden = passwordInput.type === 'password';
            passwordInput.type = isHidden ? 'text' : 'password';
            toggleBtn.textContent = isHidden ? 'Ẩn' : 'Hiện';
        });
    }

    const cccdInput = document.getElementById('id_cccd_number');
    if (cccdInput) cccdInput.addEventListener('input', posRenderSummary);

    const phoneInput = document.getElementById('id_phone');
    if (phoneInput) phoneInput.addEventListener('input', posUpdateVietQR);

    document.querySelectorAll('#posSaleForm, #qrLookupForm, #shiftReconcileForm').forEach(form => {
        form.addEventListener('submit', () => {
            const btn = form.querySelector('button[type="submit"]');
            if (btn && !btn.disabled) btn.classList.add('pos-btn-loading');
        });
    });

    posRenderSummary();
});