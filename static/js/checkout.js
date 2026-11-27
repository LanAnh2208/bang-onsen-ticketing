let PACKAGES = [];
let STATE = {}; // { [pkgId]: { adult: number, child: number, infant: number } }
let CURRENT_STEP = 1;

// Lưu quy tắc Voucher đã áp dụng để tự động tính lại khi đổi vé / CCCD
let ACTIVE_VOUCHER = null;
let VOUCHER_DISCOUNT = 0;

// Trạng thái ưu đãi CCCD Quảng Trị
let repSelectedPkgId = 0;
let companionRows = [];
let companionUidSeq = 1;

// Trạng thái theo dõi tab thanh toán VNPAY
let ACTIVE_PAYMENT_WIN = null;
let ACTIVE_ORDER_CODE = '';
let ACTIVE_VNPAY_URL = '';
let PAYMENT_POLL_TIMER = null;
let PAYMENT_RESULT_HANDLED = false;
let VNPAY_BROADCAST_CHANNEL = null;

function formatVnd(amount) {
  if (typeof fm === 'function') return fm(amount);
  return `${Math.round(Number(amount) || 0).toLocaleString('vi-VN')} VNĐ`;
}

window.addEventListener('DOMContentLoaded', () => {
  const rawJson = document.getElementById('packages-data');
  if (!rawJson) return;

  PACKAGES = JSON.parse(rawJson.textContent || '[]');
  PACKAGES.forEach(pkg => {
    STATE[pkg.id] = {
      adult: pkg.init_qty || 0,
      child: 0,
      infant: 0,
    };
  });

  const cccdInp = document.getElementById('inp-cccd');
  if (cccdInp && cccdInp.value) {
    onRepCccdChange(cccdInp.value);
  } else {
    reconcileAllAndRender();
  }

  const form = document.getElementById('checkout-form');
  if (form) {
    form.addEventListener('submit', handleCheckoutSubmit);
  }

  // 1. Lắng nghe qua BroadcastChannel từ tab VNPAY callback
  if ('BroadcastChannel' in window) {
    VNPAY_BROADCAST_CHANNEL = new BroadcastChannel('bangonsen_vnpay_channel');
    VNPAY_BROADCAST_CHANNEL.onmessage = event => {
      if (event.data && event.data.type === 'VNPAY_RESULT') {
        handleVnpayCallbackPayload(event.data);
      }
    };
  }

  // 2. Lắng nghe qua postMessage
  window.addEventListener('message', event => {
    if (event.origin !== window.location.origin) return;
    if (event.data && event.data.type === 'VNPAY_RESULT') {
      handleVnpayCallbackPayload(event.data);
    }
  });

  // 3. Lắng nghe qua localStorage
  window.addEventListener('storage', event => {
    if (event.key === 'bangonsen_vnpay_result' && event.newValue) {
      try {
        const parsed = JSON.parse(event.newValue);
        if (parsed && parsed.type === 'VNPAY_RESULT') {
          handleVnpayCallbackPayload(parsed);
        }
      } catch (e) {}
    }
  });

  // 4. Kiểm tra ngay khi người dùng chuyển tab quay lại trang đặt vé
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && ACTIVE_ORDER_CODE && !PAYMENT_RESULT_HANDLED) {
      checkOrderStatusOnce(ACTIVE_ORDER_CODE);
    }
  });
  window.addEventListener('focus', () => {
    if (ACTIVE_ORDER_CODE && !PAYMENT_RESULT_HANDLED) {
      checkOrderStatusOnce(ACTIVE_ORDER_CODE);
    }
  });
});

// ==========================================================================
// 1. ĐIỀU HƯỚNG 3 BƯỚC TRONG 1 MÀN HÌNH CỐ ĐỊNH
// ==========================================================================
function showInlineError(msg) {
  const errBox = document.getElementById('ck-client-err');
  if (!errBox) return;
  if (!msg) {
    errBox.hidden = true;
    errBox.style.display = 'none';
    errBox.textContent = '';
  } else {
    errBox.textContent = '⚠ ' + msg;
    errBox.hidden = false;
    errBox.style.display = 'block';
  }
}

function goToCheckoutStep(targetStep) {
  showInlineError('');

  if (targetStep > 1) {
    if (getTotalPaidTickets() <= 0) {
      showInlineError('Vui lòng chọn ít nhất 1 vé có tính phí ở Bước 1 trước khi tiếp tục.');
      targetStep = 1;
    }
  }

  if (targetStep === 3) {
    const step2Err = validateStep2Fields();
    if (step2Err) {
      showInlineError(step2Err);
      if (CURRENT_STEP !== 2) {
        goToCheckoutStep(2);
        showInlineError(step2Err);
      }
      return;
    }
  }

  CURRENT_STEP = targetStep;

  [1, 2, 3].forEach(step => {
    const pane = document.getElementById(`step-pane-${step}`);
    if (pane) pane.classList.toggle('is-active', step === targetStep);

    const tab = document.querySelector(`.ck-step[data-step-tab="${step}"]`);
    if (tab) {
      tab.classList.toggle('active', step === targetStep);
      tab.classList.toggle('done', step < targetStep);
      const numEl = tab.querySelector('.ck-snum');
      if (numEl) numEl.textContent = step < targetStep ? '✓' : String(step);
    }
  });

  const line1 = document.getElementById('sline-1');
  const line2 = document.getElementById('sline-2');
  if (line1) line1.classList.toggle('done', targetStep > 1);
  if (line2) line2.classList.toggle('done', targetStep > 2);

  updateActionButtonsState();
}

function updateActionButtonsState() {
  const step1Ready = getTotalPaidTickets() > 0;
  const step2Err = validateStep2Fields();
  const step2Ready = step1Ready && !step2Err;
  const step3Agree = Boolean(document.getElementById('chk-agree')?.checked);

  const btnStep1Next = document.getElementById('btn-step1-next');
  if (btnStep1Next) btnStep1Next.disabled = !step1Ready;

  const btnStep2Next = document.getElementById('btn-step2-next');
  if (btnStep2Next) btnStep2Next.disabled = !step2Ready;

  const invBtn = document.getElementById('inv-cta-btn');
  const invHint = document.getElementById('inv-cta-hint');
  if (!invBtn) return;

  if (CURRENT_STEP !== 3) {
    invBtn.hidden = true;
    invBtn.style.display = 'none';
    invBtn.disabled = true;
    if (invHint) {
      invHint.hidden = true;
      invHint.style.display = 'none';
      invHint.textContent = '';
    }
    return;
  }

  const allCompleted = step2Ready && step3Agree;
  invBtn.hidden = false;
  invBtn.style.display = 'inline-flex';
  invBtn.disabled = !allCompleted;

  if (invHint) {
    invHint.hidden = false;
    invHint.style.display = 'block';
    invHint.textContent = allCompleted
      ? 'Sẵn sàng mở cổng VNPAY ở tab mới và giữ nguyên thông tin tại trang này.'
      : 'Tick chọn đồng ý quy định ở Bước 3 để kích hoạt nút thanh toán.';
  }
}

// ==========================================================================
// 2. BƯỚC 1: ĐỔI NGÀY ĐI & TÙY CHỈNH SỐ LƯỢNG VÉ CHI TIẾT
// ==========================================================================
async function changeCheckoutDate(newDateIso) {
  if (!newDateIso) return;
  showInlineError('');

  try {
    const resp = await fetch(`/api/availability/?date=${encodeURIComponent(newDateIso)}`);
    const data = await resp.json();
    if (!resp.ok) {
      showInlineError(data.error || 'Ngày đi không hợp lệ.');
      return;
    }

    const hiddenDate = document.getElementById('hidden-visit-date');
    if (hiddenDate) hiddenDate.value = data.date;

    const invDate = document.getElementById('inv-date-disp');
    const dayBadge1 = document.getElementById('ck-day-badge');
    const dayBadge2 = document.getElementById('inv-day-badge');
    if (invDate) invDate.textContent = data.date_display;
    if (dayBadge1) dayBadge1.textContent = data.day_label;
    if (dayBadge2) dayBadge2.textContent = data.day_label;

    data.services.forEach(srv => {
      const pkg = PACKAGES.find(p => p.id === srv.id);
      if (!pkg) return;

      pkg.is_active = srv.is_active;
      pkg.available = srv.available;
      pkg.price_adult = srv.price_adult;
      pkg.price_child = srv.price_child;
      pkg.price_qt = srv.price_qt;

      const pAdultEl = document.getElementById(`price-adult-${pkg.id}`);
      const pChildEl = document.getElementById(`price-child-${pkg.id}`);
      const availBadge = document.getElementById(`avail-badge-${pkg.id}`);
      if (pAdultEl) pAdultEl.textContent = formatVnd(pkg.price_adult);
      if (pChildEl) pChildEl.textContent = formatVnd(pkg.price_child);
      if (availBadge) {
        if (!pkg.is_active) {
          availBadge.className = 'bd no';
          availBadge.textContent = 'Tạm ngừng';
        } else if (pkg.available <= 0) {
          availBadge.className = 'bd no';
          availBadge.textContent = 'Hết vé';
        } else {
          availBadge.className = 'bd ok';
          availBadge.textContent = `Còn ${pkg.available} vé`;
        }
      }

      const st = STATE[pkg.id];
      if (st) {
        if (!pkg.is_active || pkg.available <= 0) {
          st.adult = 0;
          st.child = 0;
          st.infant = 0;
        } else if (st.adult + st.child > pkg.available) {
          st.adult = Math.min(st.adult, pkg.available);
          st.child = Math.max(0, pkg.available - st.adult);
        }
      }
    });

    reconcileAllAndRender();
  } catch (e) {
    showInlineError('Không thể cập nhật dữ liệu vé cho ngày vừa chọn.');
  }
}

function adjustTicket(pkgId, tier, delta) {
  showInlineError('');
  const pkg = PACKAGES.find(p => p.id === pkgId);
  const st = STATE[pkgId];
  if (!pkg || !st || !pkg.is_active || pkg.available <= 0) return;

  const curPaid = st.adult + st.child;

  if (tier === 'adult') {
    if (delta > 0 && curPaid < pkg.available) {
      st.adult += 1;
    } else if (delta < 0 && st.adult > 0) {
      st.adult -= 1;
      if (st.adult + st.child === 0) st.infant = 0;
    }
  } else if (tier === 'child') {
    if (delta > 0 && curPaid < pkg.available) {
      st.child += 1;
    } else if (delta < 0 && st.child > 0) {
      st.child -= 1;
      if (st.adult + st.child === 0) st.infant = 0;
    }
  } else if (tier === 'infant') {
    if (delta > 0) {
      if (curPaid <= 0) {
        showInlineError('Trẻ em dưới 1m miễn phí vé vào cần đi kèm ít nhất 1 vé người lớn / trẻ em.');
        return;
      }
      st.infant = Math.min(10, st.infant + 1);
    } else if (delta < 0 && st.infant > 0) {
      st.infant -= 1;
    }
  }

  reconcileAllAndRender();
}

function getTotalPaidTickets() {
  return PACKAGES.reduce((sum, p) => {
    const st = STATE[p.id];
    return sum + (st ? st.adult + st.child : 0);
  }, 0);
}

function getTotalAdultTickets() {
  return PACKAGES.reduce((sum, p) => {
    const st = STATE[p.id];
    return sum + (st ? st.adult : 0);
  }, 0);
}

// ==========================================================================
// 3. BƯỚC 2: XỬ LÝ NHIỀU CCCD QUẢNG TRỊ & Ô TICK XÁC NHẬN CCCD
// ==========================================================================
function isValidQtCccd(cccdStr) {
  const s = (cccdStr || '').trim();
  return /^\d{12}$/.test(s) && (s.startsWith('044') || s.startsWith('045'));
}

function hasAnyCccdEntered() {
  const repVal = (document.getElementById('inp-cccd')?.value || '').trim();
  if (repVal.length > 0) return true;
  return companionRows.some(r => (r.cccd || '').trim().length > 0);
}

function onRepCccdChange(rawVal) {
  const inp = document.getElementById('inp-cccd');
  const clean = rawVal.replace(/\D/g, '').slice(0, 12);
  if (inp && inp.value !== clean) inp.value = clean;

  if (isValidQtCccd(clean)) {
    if (!repSelectedPkgId) {
      const firstAdultPkg = PACKAGES.find(p => (STATE[p.id]?.adult || 0) > 0);
      if (firstAdultPkg) repSelectedPkgId = firstAdultPkg.id;
    }
  } else {
    repSelectedPkgId = 0;
  }

  reconcileAllAndRender();
}

function onRepPkgSelectChange(val) {
  repSelectedPkgId = Number(val) || 0;
  reconcileAllAndRender();
}

function addCompanionCccdRow() {
  const totalAdults = getTotalAdultTickets();
  const maxCompanions = Math.max(0, totalAdults - 1);
  if (companionRows.length >= maxCompanions) return;

  const defaultPkg = PACKAGES.find(p => (STATE[p.id]?.adult || 0) > 0);
  companionRows.push({
    uid: companionUidSeq++,
    cccd: '',
    pkgId: defaultPkg ? defaultPkg.id : 0,
  });

  reconcileAllAndRender();
}

function removeCompanionCccdRow(uid) {
  companionRows = companionRows.filter(r => r.uid !== uid);
  reconcileAllAndRender();
}

function onCompanionCccdInput(uid, rawVal) {
  const row = companionRows.find(r => r.uid === uid);
  if (!row) return;
  row.cccd = rawVal.replace(/\D/g, '').slice(0, 12);
  reconcileAllAndRender();
}

function onCompanionPkgChange(uid, val) {
  const row = companionRows.find(r => r.uid === uid);
  if (!row) return;
  row.pkgId = Number(val) || 0;
  reconcileAllAndRender();
}

function computeQtAllocation() {
  const seenCccds = new Set();
  const perPkgQtSlots = {};
  PACKAGES.forEach(p => { perPkgQtSlots[p.id] = []; });

  const repCccd = (document.getElementById('inp-cccd')?.value || '').trim();
  const repIsQt = isValidQtCccd(repCccd);

  if (repIsQt) {
    seenCccds.add(repCccd);
    const targetPkg = PACKAGES.find(p => p.id === repSelectedPkgId && (STATE[p.id]?.adult || 0) > 0)
      || PACKAGES.find(p => (STATE[p.id]?.adult || 0) > 0);
    repSelectedPkgId = targetPkg ? targetPkg.id : 0;

    if (repSelectedPkgId && perPkgQtSlots[repSelectedPkgId].length < STATE[repSelectedPkgId].adult) {
      perPkgQtSlots[repSelectedPkgId].push({
        cccd: repCccd,
        role: 'Người đại diện',
      });
    }
  } else {
    repSelectedPkgId = 0;
  }

  const totalAdults = getTotalAdultTickets();
  const maxComp = Math.max(0, totalAdults - 1);
  if (companionRows.length > maxComp) {
    companionRows = companionRows.slice(0, maxComp);
  }

  const rowStatuses = {};
  companionRows.forEach(row => {
    const c = row.cccd.trim();
    if (!c) {
      rowStatuses[row.uid] = { valid: false, error: '' };
      return;
    }
    if (!/^\d{12}$/.test(c)) {
      rowStatuses[row.uid] = { valid: false, error: `Đã nhập ${c.length}/12 chữ số CCCD.` };
      return;
    }
    if (!isValidQtCccd(c)) {
      rowStatuses[row.uid] = { valid: false, error: 'CCCD không thuộc tỉnh Quảng Trị (đầu số 044, 045).' };
      return;
    }
    if (seenCccds.has(c)) {
      rowStatuses[row.uid] = { valid: false, error: 'Số CCCD này đã được sử dụng (không được trùng lặp).' };
      return;
    }

    let chosenPkgId = row.pkgId;
    if (!chosenPkgId || !STATE[chosenPkgId] || perPkgQtSlots[chosenPkgId].length >= STATE[chosenPkgId].adult) {
      const fallback = PACKAGES.find(p => (STATE[p.id]?.adult || 0) > perPkgQtSlots[p.id].length);
      chosenPkgId = fallback ? fallback.id : 0;
      row.pkgId = chosenPkgId;
    }

    if (!chosenPkgId) {
      rowStatuses[row.uid] = { valid: false, error: 'Đã hết vé Trên 1,4m khả dụng để áp ưu đãi.' };
      return;
    }

    seenCccds.add(c);
    perPkgQtSlots[chosenPkgId].push({
      cccd: c,
      role: 'Người đi cùng',
    });
    rowStatuses[row.uid] = { valid: true, error: '' };
  });

  return { repIsQt, perPkgQtSlots, rowStatuses, allUniqueCccds: Array.from(seenCccds) };
}

function renderStep2QtControls(alloc) {
  const repBox = document.getElementById('rep-qt-box');
  const repSelect = document.getElementById('rep-qt-select');
  const extraSec = document.getElementById('extra-qt-section');
  const compListEl = document.getElementById('companion-cccd-list');
  const addBtn = document.getElementById('btn-add-companion-cccd');

  const adultPkgs = PACKAGES.filter(p => (STATE[p.id]?.adult || 0) > 0);
  const totalAdults = getTotalAdultTickets();

  if (repBox && repSelect) {
    if (alloc.repIsQt && adultPkgs.length > 0) {
      repBox.hidden = false;
      repBox.style.display = 'block';
      repSelect.innerHTML = adultPkgs.map(p =>
        `<option value="${p.id}" ${p.id === repSelectedPkgId ? 'selected' : ''}>${p.name} – Trên 1,4m (${formatVnd(p.price_qt)})</option>`
      ).join('');
    } else {
      repBox.hidden = true;
      repBox.style.display = 'none';
      repSelect.innerHTML = '';
    }
  }

  if (extraSec && compListEl) {
    if (totalAdults >= 2) {
      extraSec.hidden = false;
      extraSec.style.display = 'block';
      const maxComp = totalAdults - 1;
      if (addBtn) {
        addBtn.disabled = companionRows.length >= maxComp;
      }

      compListEl.innerHTML = companionRows.map(row => {
        const stInfo = alloc.rowStatuses[row.uid] || { valid: false, error: '' };
        const optionsHtml = adultPkgs.map(p =>
          `<option value="${p.id}" ${p.id === row.pkgId ? 'selected' : ''}>${p.name} – Trên 1,4m (${formatVnd(p.price_qt)})</option>`
        ).join('');

        return `
          <div class="ck-comp-item">
            <div class="ck-comp-row">
              <input type="text" class="ck-inp" style="margin:0" maxlength="12" inputmode="numeric"
                     placeholder="Nhập 12 số CCCD đi cùng" value="${row.cccd}"
                     oninput="onCompanionCccdInput(${row.uid}, this.value)">
              <select class="ck-inp" style="margin:0" onchange="onCompanionPkgChange(${row.uid}, this.value)">
                ${optionsHtml}
              </select>
              <button type="button" class="ck-comp-del" onclick="removeCompanionCccdRow(${row.uid})" title="Xóa CCCD này">✕</button>
            </div>
            ${stInfo.error ? `<div class="er" style="margin-top:4px">${stInfo.error}</div>` : ''}
            ${stInfo.valid ? `<div style="color:var(--ok);font-size:12px;font-weight:600;margin-top:4px">✓ Đã áp ưu đãi cho 01 vé Trên 1,4m</div>` : ''}
          </div>`;
      }).join('');
    } else {
      extraSec.hidden = true;
      extraSec.style.display = 'none';
      compListEl.innerHTML = '';
    }
  }

  const cccdConfirmBox = document.getElementById('cccd-confirm-box');
  const chkCccdConfirm = document.getElementById('chk-cccd-confirm');
  const cccdConfirmHint = document.getElementById('cccd-confirm-hint');
  const anyCccd = hasAnyCccdEntered();

  if (cccdConfirmBox) {
    cccdConfirmBox.hidden = !anyCccd;
    cccdConfirmBox.style.display = anyCccd ? 'block' : 'none';
    if (!anyCccd && chkCccdConfirm) {
      chkCccdConfirm.checked = false;
    }
    if (cccdConfirmHint && chkCccdConfirm) {
      cccdConfirmHint.hidden = chkCccdConfirm.checked;
      cccdConfirmHint.style.display = chkCccdConfirm.checked ? 'none' : 'block';
    }
  }
}

// ==========================================================================
// 4. ĐỒNG BỘ GIAO DIỆN, TỰ ĐỘNG TÍNH LẠI VOUCHER & HÓA ĐƠN TẠM TÍNH
// ==========================================================================
function calculateAutoVoucherDiscount(netSubtotal) {
  if (!ACTIVE_VOUCHER || netSubtotal <= 0) return 0;

  let disc = 0;
  if (ACTIVE_VOUCHER.type === 'PERCENT') {
    const raw = Math.floor((netSubtotal * ACTIVE_VOUCHER.value) / 100);
    disc = ACTIVE_VOUCHER.max_discount > 0
      ? Math.min(ACTIVE_VOUCHER.max_discount, raw)
      : raw;
  } else {
    disc = ACTIVE_VOUCHER.value;
  }
  return Math.max(0, Math.min(netSubtotal, disc));
}

function reconcileAllAndRender() {
  const alloc = computeQtAllocation();
  renderStep2QtControls(alloc);

  const hiddenList = document.getElementById('hidden-qt-cccd-list');
  if (hiddenList) hiddenList.value = alloc.allUniqueCccds.join(',');

  let sumLinesHtml = '';
  let subtotalAfterQt = 0;
  let totalQtSavings = 0;
  let totalAllTickets = 0;

  PACKAGES.forEach(pkg => {
    const st = STATE[pkg.id];
    if (!st) return;

    const paidQty = st.adult + st.child;
    const totalPkgTickets = paidQty + st.infant;
    totalAllTickets += totalPkgTickets;

    const qtSlots = alloc.perPkgQtSlots[pkg.id] || [];
    const qtAdultQty = qtSlots.length;
    const regAdultQty = Math.max(0, st.adult - qtAdultQty);

    const cardEl = document.querySelector(`.ck-mini-card[data-pkg-id="${pkg.id}"]`);
    if (cardEl) cardEl.classList.toggle('is-picked', totalPkgTickets > 0);

    const autoTotalEl = document.getElementById(`pkg-auto-total-${pkg.id}`);
    if (autoTotalEl) autoTotalEl.innerHTML = `Tổng: <b>${totalPkgTickets}</b> vé`;

    const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };

    setTxt(`disp-adult-${pkg.id}`, st.adult);
    setTxt(`disp-child-${pkg.id}`, st.child);
    setTxt(`disp-infant-${pkg.id}`, st.infant);

    setVal(`adult_qty_${pkg.id}`, st.adult);
    setVal(`child_qty_${pkg.id}`, st.child);
    setVal(`infant_qty_${pkg.id}`, st.infant);
    setVal(`qt_adult_qty_${pkg.id}`, qtAdultQty);

    if (totalPkgTickets > 0) {
      const regAdultCost = regAdultQty * pkg.price_adult;
      const qtAdultCost = qtAdultQty * pkg.price_qt;
      const childCost = st.child * pkg.price_child;
      const pkgLineTotal = regAdultCost + qtAdultCost + childCost;

      subtotalAfterQt += pkgLineTotal;
      totalQtSavings += qtAdultQty * Math.max(0, pkg.price_adult - pkg.price_qt);

      let detailRows = '';
      if (regAdultQty > 0) {
        detailRows += `
          <div class="ck-inv-subrow">
            <span>${regAdultQty} × Trên 1,4m (Giá tiêu chuẩn)</span>
            <span>${formatVnd(regAdultCost)}</span>
          </div>`;
      }
      if (qtAdultQty > 0) {
        const cccdTags = qtSlots.map(s => `***${s.cccd.slice(-4)}`).join(', ');
        detailRows += `
          <div class="ck-inv-subrow is-qt">
            <span>${qtAdultQty} × Trên 1,4m <em>(Ưu đãi CCCD ${cccdTags})</em></span>
            <b>${formatVnd(qtAdultCost)}</b>
          </div>`;
      }
      if (st.child > 0) {
        detailRows += `
          <div class="ck-inv-subrow">
            <span>${st.child} × Từ 1m – 1,4m</span>
            <span>${formatVnd(childCost)}</span>
          </div>`;
      }
      if (st.infant > 0) {
        detailRows += `
          <div class="ck-inv-subrow">
            <span>${st.infant} × Dưới 1m (Miễn phí)</span>
            <span>0 VNĐ</span>
          </div>`;
      }

      sumLinesHtml += `
        <div class="ck-inv-group">
          <div class="ck-inv-group-head">
            <strong>${pkg.name} (${totalPkgTickets} vé)</strong>
            <b>${formatVnd(pkgLineTotal)}</b>
          </div>
          ${detailRows}
        </div>`;
    }
  });

  const invTicketsEl = document.getElementById('inv-total-tickets');
  if (invTicketsEl) invTicketsEl.textContent = `${totalAllTickets} vé`;

  const sumLinesEl = document.getElementById('sum-lines');
  if (sumLinesEl) {
    sumLinesEl.innerHTML = sumLinesHtml || '<p class="sm" style="font-style:normal;margin:12px 0">Chưa có vé nào được chọn.</p>';
  }

  VOUCHER_DISCOUNT = calculateAutoVoucherDiscount(subtotalAfterQt);
  if (ACTIVE_VOUCHER) {
    const msgEl = document.getElementById('voucher-msg');
    if (msgEl) {
      msgEl.innerHTML = `<span style="color:var(--ok);font-weight:600">✓ ${ACTIVE_VOUCHER.label} (-${formatVnd(VOUCHER_DISCOUNT)})</span>`;
    }
  }

  const grandTotal = Math.max(0, subtotalAfterQt - VOUCHER_DISCOUNT);

  const subEl = document.getElementById('sum-subtotal');
  const qtSaveRow = document.getElementById('sum-qt-save-row');
  const qtSaveEl = document.getElementById('sum-qt-save');
  const discRow = document.getElementById('sum-discount-row');
  const discLbl = document.getElementById('sum-discount-lbl');
  const discEl = document.getElementById('sum-discount');
  const totEl = document.getElementById('sum-total');

  if (subEl) subEl.textContent = formatVnd(subtotalAfterQt + totalQtSavings);
  if (qtSaveRow && qtSaveEl) {
    qtSaveRow.hidden = totalQtSavings <= 0;
    qtSaveEl.textContent = `-${formatVnd(totalQtSavings)}`;
  }
  if (discRow && discEl) {
    discRow.hidden = VOUCHER_DISCOUNT <= 0;
    if (discLbl && ACTIVE_VOUCHER) {
      discLbl.textContent = `Giảm giá Voucher (${ACTIVE_VOUCHER.code})`;
    }
    discEl.textContent = `-${formatVnd(VOUCHER_DISCOUNT)}`;
  }
  if (totEl) totEl.textContent = formatVnd(grandTotal);

  updateActionButtonsState();
}

// ==========================================================================
// 5. BƯỚC 3: KIỂM TRA VOUCHER & THANH TOÁN QUA VNPAY Ở TAB MỚI
// ==========================================================================
function onVoucherInputChange(rawCode) {
  const clean = rawCode.trim().toUpperCase();
  if (ACTIVE_VOUCHER && clean !== ACTIVE_VOUCHER.code) {
    ACTIVE_VOUCHER = null;
    VOUCHER_DISCOUNT = 0;
    const msgEl = document.getElementById('voucher-msg');
    if (msgEl) {
      msgEl.innerHTML = clean
        ? '<span style="color:#5f6d79">Nhấn nút <b>Áp dụng</b> để kiểm tra mã ưu đãi vừa nhập.</span>'
        : '';
    }
    reconcileAllAndRender();
  }
}

async function applyVoucherCode() {
  const inp = document.getElementById('inp-voucher');
  const msgEl = document.getElementById('voucher-msg');
  if (!inp || !msgEl) return;

  const code = inp.value.trim().toUpperCase();
  inp.value = code;

  const alloc = computeQtAllocation();
  let currentNet = 0;
  PACKAGES.forEach(pkg => {
    const st = STATE[pkg.id];
    if (!st) return;
    const qtQty = (alloc.perPkgQtSlots[pkg.id] || []).length;
    const regQty = Math.max(0, st.adult - qtQty);
    currentNet += regQty * pkg.price_adult + qtQty * pkg.price_qt + st.child * pkg.price_child;
  });

  if (!code) {
    ACTIVE_VOUCHER = null;
    VOUCHER_DISCOUNT = 0;
    msgEl.innerHTML = '<span style="color:var(--red)">Vui lòng nhập mã giảm giá.</span>';
    reconcileAllAndRender();
    return;
  }

  msgEl.textContent = 'Đang kiểm tra mã ưu đãi...';
  try {
    const resp = await fetch(`/api/apply-voucher/?code=${encodeURIComponent(code)}&subtotal=${currentNet}`);
    const data = await resp.json();
    if (data.valid) {
      ACTIVE_VOUCHER = {
        code: data.code || code,
        type: data.discount_type || 'FIXED',
        value: Number(data.discount_value ?? data.discount ?? 0),
        max_discount: Number(data.max_discount ?? data.discount ?? 0),
        label: data.label || `Áp dụng mã ${code}`,
      };
      VOUCHER_DISCOUNT = calculateAutoVoucherDiscount(currentNet);
      msgEl.innerHTML = `<span style="color:var(--ok);font-weight:600">✓ ${ACTIVE_VOUCHER.label} (-${formatVnd(VOUCHER_DISCOUNT)})</span>`;
    } else {
      ACTIVE_VOUCHER = null;
      VOUCHER_DISCOUNT = 0;
      msgEl.innerHTML = `<span style="color:var(--red)">✕ ${data.message || 'Mã không hợp lệ'}</span>`;
    }
  } catch (e) {
    ACTIVE_VOUCHER = null;
    VOUCHER_DISCOUNT = 0;
    msgEl.innerHTML = '<span style="color:var(--red)">Không thể kiểm tra mã lúc này.</span>';
  }
  reconcileAllAndRender();
}

function validateStep2Fields() {
  const name = (document.getElementById('inp-name')?.value || '').trim();
  const phone = (document.getElementById('inp-phone')?.value || '').trim();
  const email = (document.getElementById('inp-email')?.value || '').trim();
  const cccd = (document.getElementById('inp-cccd')?.value || '').trim();

  if (!name) return 'Vui lòng nhập họ và tên khách hàng.';
  if (!/^0\d{9}$/.test(phone)) return 'Số điện thoại phải gồm đúng 10 chữ số bắt đầu bằng số 0.';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return 'Vui lòng nhập địa chỉ email hợp lệ để nhận mã vé QR.';
  if (cccd && !/^\d{12}$/.test(cccd)) return 'Số CCCD người đại diện phải gồm đúng 12 chữ số.';

  const alloc = computeQtAllocation();
  for (const row of companionRows) {
    const st = alloc.rowStatuses[row.uid];
    if (row.cccd.trim() && st && st.error) {
      return st.error;
    }
  }

  if (hasAnyCccdEntered()) {
    const chkCccd = document.getElementById('chk-cccd-confirm');
    if (!chkCccd || !chkCccd.checked) {
      return 'Vui lòng tick xác nhận số CCCD đã nhập là chính xác và sẵn sàng xuất trình để nhân viên kiểm tra khi check-in.';
    }
  }

  return '';
}

// ==========================================================================
// 6. QUẢN LÝ HỘP THOẠI & ĐỒNG BỘ TAB THANH TOÁN VNPAY
// ==========================================================================
function openVnpayStatusModal({ badgeText, badgeClass, title, desc, actionsHtml }) {
  const modal = document.getElementById('vnpay-status-modal');
  const badgeEl = document.getElementById('vnpay-modal-badge');
  const titleEl = document.getElementById('vnpay-modal-title');
  const descEl = document.getElementById('vnpay-modal-desc');
  const actionsEl = document.getElementById('vnpay-modal-actions');
  if (!modal) return;

  if (badgeEl) {
    badgeEl.className = `bd ${badgeClass || ''}`.trim();
    badgeEl.textContent = badgeText || '';
  }
  if (titleEl) titleEl.textContent = title || '';
  if (descEl) descEl.textContent = desc || '';
  if (actionsEl) actionsEl.innerHTML = actionsHtml || '';

  modal.hidden = false;
  modal.style.display = 'flex';
}

function closeVnpayStatusModal() {
  const modal = document.getElementById('vnpay-status-modal');
  if (!modal) return;
  modal.hidden = true;
  modal.style.display = 'none';
}

function stopPaymentMonitoring() {
  if (PAYMENT_POLL_TIMER) {
    clearInterval(PAYMENT_POLL_TIMER);
    PAYMENT_POLL_TIMER = null;
  }
}

function openBlankPaymentTab() {
  const win = window.open('', 'vnpay_payment_tab');
  if (win) {
    try {
      win.document.open();
      win.document.write(
        '<!doctype html><html><head><meta charset="utf-8"><title>Đang kết nối VNPAY...</title></head>' +
        '<body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f8fafc;color:#0f172a">' +
        '<div style="text-align:center"><h3>Đang kết nối cổng thanh toán VNPAY...</h3><p style="color:#475569">Vui lòng chờ trong giây lát và không đóng cửa sổ này.</p></div>' +
        '</body></html>'
      );
      win.document.close();
    } catch (e) {}
  }
  return win;
}

async function checkOrderStatusOnce(orderCode) {
  if (!orderCode || PAYMENT_RESULT_HANDLED) return;
  try {
    const resp = await fetch(`/api/order-payment-status/${encodeURIComponent(orderCode)}/`);
    const data = await resp.json();
    if (!resp.ok || !data.ok) return;

    if (data.state === 'success') {
      handleVnpayCallbackPayload({
        type: 'VNPAY_RESULT',
        status: 'success',
        order_code: orderCode,
        message: data.message,
        lookup_url: data.lookup_url,
      });
    } else if (data.state === 'failed' || data.state === 'expired') {
      handleVnpayCallbackPayload({
        type: 'VNPAY_RESULT',
        status: 'failed',
        order_code: orderCode,
        message: data.message,
        lookup_url: data.lookup_url,
      });
    }
  } catch (e) {}
}

function markManualPaymentCancelled() {
  if (!ACTIVE_ORDER_CODE) return;
  handleVnpayCallbackPayload({
    type: 'VNPAY_RESULT',
    status: 'failed',
    order_code: ACTIVE_ORDER_CODE,
    message: 'Giao dịch thanh toán VNPAY đã bị đóng hoặc hủy trước khi hoàn tất.',
    lookup_url: `/tra-cuu/?q=${encodeURIComponent(ACTIVE_ORDER_CODE)}`,
  });
}

function startPaymentMonitoring(orderCode, vnpayUrl, payWin) {
  stopPaymentMonitoring();
  PAYMENT_RESULT_HANDLED = false;
  ACTIVE_ORDER_CODE = orderCode;
  ACTIVE_VNPAY_URL = vnpayUrl;
  ACTIVE_PAYMENT_WIN = payWin;

  openVnpayStatusModal({
    badgeText: `Đơn #${orderCode} · Đang chờ thanh toán`,
    badgeClass: '',
    title: 'Đang chờ thanh toán qua cổng VNPAY',
    desc: 'Cửa sổ thanh toán VNPAY đang mở ở tab mới (giữ chỗ trong 15 phút). Hệ thống sẽ giữ trạng thái chờ cho đến khi bạn hoàn tất thanh toán hoặc hết thời gian.',
    actionsHtml: `
      <button type="button" class="btn s sm" onclick="markManualPaymentCancelled()">Đã tắt tab / Hủy giao dịch</button>
      <a href="${vnpayUrl}" target="vnpay_payment_tab" class="btn p sm">Mở lại tab VNPAY</a>
    `,
  });

  PAYMENT_POLL_TIMER = setInterval(() => {
    if (PAYMENT_RESULT_HANDLED) {
      stopPaymentMonitoring();
      return;
    }
    checkOrderStatusOnce(orderCode);
  }, 2000);
}

function handleVnpayCallbackPayload(payload) {
  if (!payload || PAYMENT_RESULT_HANDLED) return;
  if (ACTIVE_ORDER_CODE && payload.order_code && payload.order_code !== ACTIVE_ORDER_CODE) return;

  PAYMENT_RESULT_HANDLED = true;
  stopPaymentMonitoring();

  try {
    if (ACTIVE_PAYMENT_WIN && !ACTIVE_PAYMENT_WIN.closed) {
      ACTIVE_PAYMENT_WIN.close();
    }
  } catch (e) {}

  const targetLookupUrl = payload.lookup_url || `/tra-cuu/?q=${encodeURIComponent(payload.order_code || ACTIVE_ORDER_CODE)}`;

  if (payload.status === 'success') {
    openVnpayStatusModal({
      badgeText: '✓ Thanh toán thành công',
      badgeClass: 'ok',
      title: 'Đặt vé & Thanh toán hoàn tất!',
      desc: `${payload.message || 'Giao dịch VNPAY thành công.'} Hệ thống đang chuyển sang trang thông tin chi tiết của vé...`,
      actionsHtml: `
        <a href="${targetLookupUrl}" class="btn p">Xem chi tiết vé ngay →</a>
      `,
    });

    setTimeout(() => {
      window.location.href = targetLookupUrl;
    }, 1500);
    return;
  }

  openVnpayStatusModal({
    badgeText: '✕ Thanh toán chưa thành công',
    badgeClass: 'no',
    title: 'Giao dịch VNPAY chưa hoàn tất',
    desc: `${payload.message || 'Thanh toán chưa thành công.'} Toàn bộ thông tin đặt vé bạn đã nhập vẫn được giữ nguyên. Bạn muốn thanh toán lại hay quay về trang chủ?`,
    actionsHtml: `
      <a href="/" class="btn s">Về trang chủ</a>
      <button type="button" class="btn p" onclick="retryVnpayFromModal()">Thanh toán lại qua VNPAY →</button>
    `,
  });
}

async function retryVnpayFromModal() {
  const payWin = openBlankPaymentTab();

  if (ACTIVE_ORDER_CODE) {
    try {
      const resp = await fetch(`/thanh-toan/${encodeURIComponent(ACTIVE_ORDER_CODE)}/vnpay/?ajax=1`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      const data = await resp.json();

      if (resp.ok && data.ok) {
        if (data.already_paid) {
          if (payWin && !payWin.closed) payWin.close();
          window.location.href = data.lookup_url;
          return;
        }
        if (payWin && !payWin.closed) {
          payWin.location.href = data.vnpay_url;
          payWin.focus();
        }
        startPaymentMonitoring(data.order_code, data.vnpay_url, payWin);
        return;
      }
    } catch (e) {}
  }

  try {
    const form = document.getElementById('checkout-form');
    const formData = new FormData(form);
    const resp = await fetch(window.location.pathname, {
      method: 'POST',
      body: formData,
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    const data = await resp.json();

    if (!resp.ok || !data.ok) {
      if (payWin && !payWin.closed) payWin.close();
      closeVnpayStatusModal();
      showInlineError(data.error || 'Không thể khởi tạo lại giao dịch VNPAY.');
      return;
    }

    if (payWin && !payWin.closed) {
      payWin.location.href = data.vnpay_url;
      payWin.focus();
    }
    startPaymentMonitoring(data.order_code, data.vnpay_url, payWin);
  } catch (err) {
    if (payWin && !payWin.closed) payWin.close();
    closeVnpayStatusModal();
    showInlineError('Lỗi kết nối máy chủ khi tạo lại giao dịch VNPAY.');
  }
}

async function handleCheckoutSubmit(e) {
  e.preventDefault();
  showInlineError('');

  if (getTotalPaidTickets() <= 0) {
    goToCheckoutStep(1);
    showInlineError('Vui lòng chọn ít nhất 1 vé có tính phí.');
    return;
  }

  const s2Err = validateStep2Fields();
  if (s2Err) {
    goToCheckoutStep(2);
    showInlineError(s2Err);
    return;
  }

  const agree = document.getElementById('chk-agree')?.checked;
  if (!agree) {
    goToCheckoutStep(3);
    showInlineError('Vui lòng tick chọn đồng ý quy định giữ vé 15 phút trước khi thanh toán.');
    return;
  }

  const form = document.getElementById('checkout-form');
  const submitBtn = document.getElementById('inv-cta-btn');
  if (submitBtn) submitBtn.disabled = true;

  const payWin = openBlankPaymentTab();

  try {
    const formData = new FormData(form);
    const resp = await fetch(window.location.pathname, {
      method: 'POST',
      body: formData,
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
      },
    });
    const data = await resp.json();

    if (!resp.ok || !data.ok) {
      if (payWin && !payWin.closed) payWin.close();
      showInlineError(data.error || 'Không thể khởi tạo đơn đặt vé, vui lòng kiểm tra lại.');
      updateActionButtonsState();
      return;
    }

    if (data.zero_amount) {
      if (payWin && !payWin.closed) payWin.close();
      handleVnpayCallbackPayload({
        type: 'VNPAY_RESULT',
        status: 'success',
        order_code: data.order_code,
        message: data.message,
        lookup_url: data.lookup_url,
      });
      return;
    }

    if (payWin && !payWin.closed) {
      payWin.location.href = data.vnpay_url;
      payWin.focus();
    }
    startPaymentMonitoring(data.order_code, data.vnpay_url, payWin);
  } catch (err) {
    if (payWin && !payWin.closed) payWin.close();
    showInlineError('Lỗi kết nối máy chủ, vui lòng thử lại.');
  } finally {
    updateActionButtonsState();
  }
}