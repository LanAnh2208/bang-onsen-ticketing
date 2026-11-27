let RS_PACKAGES = [];
let RS_STATE = {};
let RS_ORIG_QT_CCCDS = [];
let RS_ORIG_QT_ALLOC = {};
let RS_REP_SERVICE_ID = 0;
let RS_COMPANIONS = []; // [{ cccd: '045...', serviceId: 2 }]
let RS_ORIG_CUSTOMER = {};
let RS_VOUCHER = {};
let RS_OLD_TOTAL = 0;
let RS_ACTIVE_TAB = 'tickets';
let RS_CURRENT_DIFF = 0;

let RS_POLL_TIMER = null;
let RS_COUNTDOWN_TIMER = null;
let RS_ACTIVE_TXN_ID = null;

function rsFmt(amount) {
  if (typeof fm === 'function') return fm(amount);
  return `${Math.round(Number(amount) || 0).toLocaleString('vi-VN')} VNĐ`;
}

function isValidQtCccd(code) {
  const clean = String(code || '').trim();
  return /^\d{12}$/.test(clean) && (clean.startsWith('044') || clean.startsWith('045'));
}

window.addEventListener('DOMContentLoaded', () => {
  const pkgEl = document.getElementById('rs-packages-data');
  if (!pkgEl) return;

  RS_PACKAGES = JSON.parse(pkgEl.textContent || '[]');
  RS_ORIG_QT_CCCDS = JSON.parse(document.getElementById('rs-orig-qt-cccds-data')?.textContent || '[]');
  RS_ORIG_QT_ALLOC = JSON.parse(document.getElementById('rs-orig-qt-alloc-data')?.textContent || '{}');
  RS_REP_SERVICE_ID = Number(document.getElementById('rs-rep-cccd-service-data')?.textContent || 0);
  const initExtraItems = JSON.parse(document.getElementById('rs-extra-qt-items-data')?.textContent || '[]');
  RS_ORIG_CUSTOMER = JSON.parse(document.getElementById('rs-orig-customer-data')?.textContent || '{}');
  RS_VOUCHER = JSON.parse(document.getElementById('rs-voucher-data')?.textContent || '{}');
  RS_OLD_TOTAL = Number(document.getElementById('rs-old-total-data')?.textContent || 0);

  const infoPane = document.getElementById('rs-tab-pane-info');
  RS_ACTIVE_TAB = (infoPane && !infoPane.hidden) ? 'info' : 'tickets';

  RS_PACKAGES.forEach(pkg => {
    RS_STATE[pkg.id] = {
      adult: pkg.init_adult || 0,
      child: pkg.init_child || 0,
      infant: pkg.init_infant || 0,
    };
  });

  RS_COMPANIONS = (initExtraItems || []).map(item => ({
    cccd: String(item.cccd || '').trim(),
    serviceId: Number(item.service_id || 0),
  }));

  const form = document.getElementById('reschedule-form');
  if (form) {
    form.addEventListener('submit', handleRescheduleSubmit);
  }

  renderRepServiceBox();
  renderCompanionRows();
  renderRescheduleSummary();
});

function stopExchangePolling() {
  if (RS_POLL_TIMER) {
    clearInterval(RS_POLL_TIMER);
    RS_POLL_TIMER = null;
  }
  if (RS_COUNTDOWN_TIMER) {
    clearInterval(RS_COUNTDOWN_TIMER);
    RS_COUNTDOWN_TIMER = null;
  }
}

function showExchangePaymentPanel(stateName, payload = {}) {
  const editorCard = document.getElementById('rs-editor-card');
  const statusPanel = document.getElementById('rs-payment-status-panel');
  const pendingBox = document.getElementById('rs-pay-state-pending');
  const successBox = document.getElementById('rs-pay-state-success');
  const failedBox = document.getElementById('rs-pay-state-failed');
  const submitBtn = document.getElementById('rs-submit-btn');

  if (editorCard) {
    editorCard.hidden = true;
    editorCard.style.display = 'none';
  }
  if (statusPanel) {
    statusPanel.hidden = false;
    statusPanel.style.display = 'block';
  }

  [pendingBox, successBox, failedBox].forEach(el => {
    if (el) {
      el.hidden = true;
      el.style.display = 'none';
    }
  });

  if (stateName === 'PENDING') {
    if (pendingBox) {
      pendingBox.hidden = false;
      pendingBox.style.display = 'block';
    }
    const amtEl = document.getElementById('rs-pend-amount');
    const reopenLink = document.getElementById('rs-reopen-vnpay-link');
    if (amtEl) amtEl.textContent = payload.diff_amount_fmt || rsFmt(RS_CURRENT_DIFF);
    if (reopenLink && payload.payment_url) {
      reopenLink.href = payload.payment_url;
    }
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Đang chờ thanh toán VNPAY...';
    }
  } else if (stateName === 'SUCCESS') {
    if (successBox) {
      successBox.hidden = false;
      successBox.style.display = 'block';
    }
    const emailEl = document.getElementById('rs-succ-email');
    const qrEl = document.getElementById('rs-succ-qr');
    const dateEl = document.getElementById('rs-succ-date');
    const totalEl = document.getElementById('rs-succ-total');
    const lookupBtn = document.getElementById('rs-succ-lookup-btn');

    if (emailEl) emailEl.textContent = payload.email || '';
    if (qrEl) qrEl.textContent = payload.qr_code || 'Đã cập nhật';
    if (dateEl) dateEl.textContent = payload.visit_date_display || '';
    if (totalEl) totalEl.textContent = payload.total_amount_fmt || '';
    if (lookupBtn && payload.lookup_url) lookupBtn.href = payload.lookup_url;

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = '✓ Đã hoàn tất đổi vé';
    }
  } else if (stateName === 'FAILED') {
    if (failedBox) {
      failedBox.hidden = false;
      failedBox.style.display = 'block';
    }
    const failReasonEl = document.getElementById('rs-fail-reason');
    if (failReasonEl && payload.message) {
      failReasonEl.textContent = payload.message;
    }
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = `Thử thanh toán lại ${rsFmt(RS_CURRENT_DIFF)} →`;
    }
  }
}

function resetExchangePaymentPanel() {
  stopExchangePolling();
  RS_ACTIVE_TXN_ID = null;

  const editorCard = document.getElementById('rs-editor-card');
  const statusPanel = document.getElementById('rs-payment-status-panel');
  if (statusPanel) {
    statusPanel.hidden = true;
    statusPanel.style.display = 'none';
  }
  if (editorCard) {
    editorCard.hidden = false;
    editorCard.style.display = 'block';
  }
  renderRescheduleSummary();
}

function startExchangePolling(txnId, orderCode) {
  stopExchangePolling();
  RS_ACTIVE_TXN_ID = txnId;

  let secondsLeft = 15 * 60;
  const countdownEl = document.getElementById('rs-pend-countdown');

  RS_COUNTDOWN_TIMER = setInterval(() => {
    secondsLeft -= 1;
    if (countdownEl) {
      const m = String(Math.max(0, Math.floor(secondsLeft / 60))).padStart(2, '0');
      const s = String(Math.max(0, secondsLeft % 60)).padStart(2, '0');
      countdownEl.textContent = `${m}:${s}`;
    }
    if (secondsLeft <= 0) {
      stopExchangePolling();
      showExchangePaymentPanel('FAILED', {
        message: 'Phiên thanh toán bổ sung (15 phút) đã hết hạn. Vui lòng thực hiện thanh toán lại.',
      });
    }
  }, 1000);

  const checkStatus = async () => {
    try {
      const resp = await fetch(`/api/exchange-status/${encodeURIComponent(txnId)}/?order_code=${encodeURIComponent(orderCode)}`, {
        cache: 'no-store',
      });
      const data = await resp.json();
      if (data.status === 'SUCCESS') {
        stopExchangePolling();
        showExchangePaymentPanel('SUCCESS', data);
      } else if (data.status === 'FAILED') {
        stopExchangePolling();
        showExchangePaymentPanel('FAILED', data);
      }
    } catch (e) {
      // Bỏ qua lỗi mạng tạm thời, tiếp tục poll ở chu kỳ kế tiếp
    }
  };

  RS_POLL_TIMER = setInterval(checkStatus, 2500);
}

async function handleRescheduleSubmit(e) {
  // Nếu không cần thanh toán bổ sung (đổi ngang giá), submit form bình thường
  if (RS_CURRENT_DIFF <= 0) return;

  e.preventDefault();
  showRescheduleError('');

  const form = e.currentTarget;
  const orderCode = document.getElementById('hidden-order-code')?.value || '';
  const submitBtn = document.getElementById('rs-submit-btn');

  // Mở tab trống đồng bộ ngay trong sự kiện click để không bị trình duyệt chặn popup
  const paymentTab = window.open('about:blank', '_blank');
  if (paymentTab && paymentTab.document) {
    paymentTab.document.write(
      '<p style="font-family:sans-serif;padding:24px;color:#334155">Đang kết nối cổng thanh toán VNPAY, vui lòng chờ...</p>'
    );
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Đang khởi tạo giao dịch VNPAY...';
  }

  try {
    const resp = await fetch(form.action || window.location.href, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: new FormData(form),
    });

    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      if (paymentTab && !paymentTab.closed) paymentTab.close();
      if (data.active_tab) switchRescheduleTab(data.active_tab);
      showRescheduleError(data.error || 'Không thể khởi tạo thanh toán bổ sung.');
      renderRescheduleSummary();
      return;
    }

    if (data.requires_payment && data.payment_url) {
      if (paymentTab && !paymentTab.closed) {
        paymentTab.location.href = data.payment_url;
      }
      showExchangePaymentPanel('PENDING', data);
      startExchangePolling(data.transaction_id, orderCode);
    }
  } catch (err) {
    if (paymentTab && !paymentTab.closed) paymentTab.close();
    showRescheduleError('Lỗi kết nối máy chủ khi tạo giao dịch VNPAY. Vui lòng thử lại.');
    renderRescheduleSummary();
  }
}

function retryExchangePayment() {
  const form = document.getElementById('reschedule-form');
  if (!form) return;
  form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
}

function switchRescheduleTab(tabName) {
  RS_ACTIVE_TAB = (tabName === 'info') ? 'info' : 'tickets';
  const isInfo = (RS_ACTIVE_TAB === 'info');

  const paneTickets = document.getElementById('rs-tab-pane-tickets');
  const paneInfo = document.getElementById('rs-tab-pane-info');
  const btnTickets = document.getElementById('rs-tab-btn-tickets');
  const btnInfo = document.getElementById('rs-tab-btn-info');
  const footSwitchBtn = document.getElementById('rs-foot-switch-btn');

  if (paneTickets) {
    paneTickets.hidden = isInfo;
    paneTickets.style.display = isInfo ? 'none' : 'block';
  }
  if (paneInfo) {
    paneInfo.hidden = !isInfo;
    paneInfo.style.display = isInfo ? 'block' : 'none';
  }
  if (btnTickets) btnTickets.classList.toggle('is-active', !isInfo);
  if (btnInfo) btnInfo.classList.toggle('is-active', isInfo);
  if (footSwitchBtn) {
    footSwitchBtn.textContent = isInfo ? '← Quay lại điều chỉnh vé' : 'Điều chỉnh thông tin →';
  }
}

function handleFooterTabSwitch() {
  switchRescheduleTab(RS_ACTIVE_TAB === 'tickets' ? 'info' : 'tickets');
}

function showRescheduleError(msg) {
  const box = document.getElementById('rs-client-err');
  if (!box) return;
  if (!msg) {
    box.hidden = true;
    box.style.display = 'none';
    box.textContent = '';
  } else {
    box.textContent = '⚠ ' + msg;
    box.hidden = false;
    box.style.display = 'block';
  }
}

function getTicketCounts() {
  let totalAdultTickets = 0;
  let totalChildTickets = 0;
  let totalInfantTickets = 0;

  RS_PACKAGES.forEach(pkg => {
    const st = RS_STATE[pkg.id];
    if (!st) return;
    totalAdultTickets += st.adult || 0;
    totalChildTickets += st.child || 0;
    totalInfantTickets += st.infant || 0;
  });

  const totalPaidTickets = totalAdultTickets + totalChildTickets;
  const totalAllTickets = totalPaidTickets + totalInfantTickets;
  return { totalAdultTickets, totalChildTickets, totalInfantTickets, totalPaidTickets, totalAllTickets };
}

function renderRepServiceBox() {
  const box = document.getElementById('rs-rep-service-box');
  const sel = document.getElementById('rs-rep-cccd-service');
  if (!box || !sel) return;

  const repVal = (document.getElementById('rs-cust-cccd')?.value || '').trim();
  const adultPackages = RS_PACKAGES.filter(p => (RS_STATE[p.id]?.adult || 0) > 0);

  if (!isValidQtCccd(repVal) || adultPackages.length === 0) {
    box.style.display = 'none';
    sel.innerHTML = '';
    return;
  }

  box.style.display = 'block';

  const validRepPkg = adultPackages.find(p => p.id === Number(RS_REP_SERVICE_ID)) || adultPackages[0];
  RS_REP_SERVICE_ID = validRepPkg ? validRepPkg.id : 0;

  sel.innerHTML = adultPackages.map(pkg => {
    const selectedAttr = (pkg.id === RS_REP_SERVICE_ID) ? 'selected' : '';
    return `<option value="${pkg.id}" ${selectedAttr}>${pkg.name} – Trên 1,4m (${rsFmt(pkg.price_qt)})</option>`;
  }).join('');
}

function handleRepServiceChange(serviceId) {
  RS_REP_SERVICE_ID = Number(serviceId || 0);
  renderCompanionRows();
  renderRescheduleSummary();
}

function resolveEffectiveRepServiceId() {
  const repVal = (document.getElementById('rs-cust-cccd')?.value || '').trim();
  if (!isValidQtCccd(repVal)) return 0;

  const adultPackages = RS_PACKAGES.filter(p => (RS_STATE[p.id]?.adult || 0) > 0);
  if (adultPackages.length === 0) return 0;

  const chosen = adultPackages.find(p => p.id === Number(RS_REP_SERVICE_ID)) || adultPackages[0];
  RS_REP_SERVICE_ID = chosen.id;
  return chosen.id;
}

function getRemainingAdultSlotsMap(excludeIdx = -1) {
  const remaining = {};
  RS_PACKAGES.forEach(p => {
    remaining[p.id] = RS_STATE[p.id]?.adult || 0;
  });

  const repServiceId = resolveEffectiveRepServiceId();
  if (repServiceId && (remaining[repServiceId] || 0) > 0) {
    remaining[repServiceId] -= 1;
  }

  RS_COMPANIONS.forEach((item, idx) => {
    if (idx === excludeIdx) return;
    const sid = Number(item.serviceId || 0);
    if ((remaining[sid] || 0) > 0) {
      remaining[sid] -= 1;
    }
  });

  return remaining;
}

function getNextAvailableServiceId() {
  const remaining = getRemainingAdultSlotsMap(-1);
  const nextPkg = RS_PACKAGES.find(p => (remaining[p.id] || 0) > 0);
  if (nextPkg) return nextPkg.id;

  const fallbackPkg = RS_PACKAGES.find(p => (RS_STATE[p.id]?.adult || 0) > 0);
  return fallbackPkg ? fallbackPkg.id : (RS_PACKAGES[0]?.id || 0);
}

function addCompanionRow() {
  showRescheduleError('');
  const { totalAdultTickets, totalAllTickets } = getTicketCounts();
  const maxCompanionSlots = Math.max(0, totalAdultTickets - 1);

  if (totalAllTickets <= 1 || maxCompanionSlots <= 0) return;
  if (RS_COMPANIONS.length >= maxCompanionSlots) return;

  RS_COMPANIONS.push({
    cccd: '',
    serviceId: getNextAvailableServiceId(),
  });
  renderCompanionRows();
  renderRescheduleSummary();
}

function removeCompanionRow(idx) {
  showRescheduleError('');
  RS_COMPANIONS.splice(idx, 1);
  renderCompanionRows();
  renderRescheduleSummary();
}

function updateCompanionCccd(idx, rawVal) {
  if (!RS_COMPANIONS[idx]) return;
  RS_COMPANIONS[idx].cccd = String(rawVal || '').replace(/\D/g, '').slice(0, 12);
  syncHiddenCompanionInput();
  renderRescheduleSummary();
}

function updateCompanionService(idx, serviceId) {
  if (!RS_COMPANIONS[idx]) return;
  RS_COMPANIONS[idx].serviceId = Number(serviceId || 0);
  renderCompanionRows();
  renderRescheduleSummary();
}

function syncHiddenCompanionInput() {
  const hiddenList = document.getElementById('hidden-qt-cccd-list');
  if (!hiddenList) return;
  const serialized = RS_COMPANIONS
    .filter(item => item.cccd.trim().length > 0)
    .map(item => `${item.cccd.trim()}:${item.serviceId || getNextAvailableServiceId()}`);
  hiddenList.value = serialized.join(',');
}

function renderCompanionRows() {
  const container = document.getElementById('rs-companion-list');
  if (!container) {
    syncHiddenCompanionInput();
    return;
  }

  const adultPackages = RS_PACKAGES.filter(p => (RS_STATE[p.id]?.adult || 0) > 0);
  const selectablePackages = adultPackages.length > 0 ? adultPackages : RS_PACKAGES.filter(p => p.is_active);

  const runningRemaining = {};
  RS_PACKAGES.forEach(p => {
    runningRemaining[p.id] = RS_STATE[p.id]?.adult || 0;
  });

  const repServiceId = resolveEffectiveRepServiceId();
  if (repServiceId && (runningRemaining[repServiceId] || 0) > 0) {
    runningRemaining[repServiceId] -= 1;
  }

  RS_COMPANIONS.forEach(item => {
    const curSid = Number(item.serviceId || 0);
    if ((runningRemaining[curSid] || 0) > 0) {
      runningRemaining[curSid] -= 1;
    } else {
      const nextAvailablePkg = selectablePackages.find(p => (runningRemaining[p.id] || 0) > 0);
      if (nextAvailablePkg) {
        item.serviceId = nextAvailablePkg.id;
        runningRemaining[nextAvailablePkg.id] -= 1;
      } else if (selectablePackages[0]) {
        item.serviceId = selectablePackages[0].id;
      }
    }
  });

  container.innerHTML = RS_COMPANIONS.map((item, idx) => {
    const slotsForThisRow = getRemainingAdultSlotsMap(idx);

    const optionsHtml = selectablePackages.map(pkg => {
      const isSelected = (pkg.id === item.serviceId);
      const hasSlot = (slotsForThisRow[pkg.id] || 0) > 0;
      const selAttr = isSelected ? 'selected' : '';
      const disAttr = (!isSelected && !hasSlot) ? 'disabled' : '';
      const fullTag = (!isSelected && !hasSlot) ? ' – Đã đủ suất' : '';
      return `<option value="${pkg.id}" ${selAttr} ${disAttr}>${pkg.name} – Trên 1,4m (${rsFmt(pkg.price_qt)})${fullTag}</option>`;
    }).join('');

    return `
      <div class="rs-companion-row">
        <input type="text" class="ck-inp" maxlength="12"
               value="${item.cccd}"
               placeholder="Nhập 12 số CCCD đi cùng"
               oninput="this.value=this.value.replace(/\\D/g,'');updateCompanionCccd(${idx}, this.value)">
        <select class="ck-inp" onchange="updateCompanionService(${idx}, this.value)">
          ${optionsHtml}
        </select>
        <button type="button" class="rs-del-cccd-btn" onclick="removeCompanionRow(${idx})" title="Xóa CCCD này">✕</button>
      </div>`;
  }).join('');

  syncHiddenCompanionInput();
}

function getQtAllocationsByService() {
  const { totalAdultTickets, totalAllTickets } = getTicketCounts();
  const repVal = (document.getElementById('rs-cust-cccd')?.value || '').trim();
  const seen = new Set();
  const allocByService = {};
  const orderedValidCccds = [];

  const remainingAdultsByService = {};
  RS_PACKAGES.forEach(p => {
    remainingAdultsByService[p.id] = RS_STATE[p.id]?.adult || 0;
  });

  const repServiceId = resolveEffectiveRepServiceId();
  if (isValidQtCccd(repVal) && repServiceId && (remainingAdultsByService[repServiceId] || 0) > 0) {
    seen.add(repVal);
    orderedValidCccds.push(repVal);
    remainingAdultsByService[repServiceId] -= 1;
    allocByService[repServiceId] = (allocByService[repServiceId] || 0) + 1;
  }

  if (totalAllTickets > 1 && totalAdultTickets > 1) {
    const maxSlots = totalAdultTickets - 1;
    RS_COMPANIONS.slice(0, maxSlots).forEach(item => {
      const code = (item.cccd || '').trim();
      if (!isValidQtCccd(code) || seen.has(code)) return;

      let chosenPkgId = Number(item.serviceId || 0);
      if ((remainingAdultsByService[chosenPkgId] || 0) <= 0) {
        const fallbackPkg = RS_PACKAGES.find(p => (remainingAdultsByService[p.id] || 0) > 0);
        chosenPkgId = fallbackPkg ? fallbackPkg.id : 0;
      }

      if (chosenPkgId && (remainingAdultsByService[chosenPkgId] || 0) > 0) {
        seen.add(code);
        orderedValidCccds.push(code);
        remainingAdultsByService[chosenPkgId] -= 1;
        allocByService[chosenPkgId] = (allocByService[chosenPkgId] || 0) + 1;
      }
    });
  }

  return { allocByService, orderedValidCccds };
}

function syncCustomerInputsState() {
  const { totalAdultTickets, totalAllTickets } = getTicketCounts();
  const nameVal = (document.getElementById('rs-cust-name')?.value || '').trim();
  const phoneVal = (document.getElementById('rs-cust-phone')?.value || '').trim();
  const emailVal = (document.getElementById('rs-cust-email')?.value || '').trim();
  const repCccdVal = (document.getElementById('rs-cust-cccd')?.value || '').trim();

  const extraBox = document.getElementById('rs-extra-cccd-box');
  const addBtn = document.getElementById('rs-add-cccd-btn');
  const allowExtraBox = (totalAllTickets > 1 && totalAdultTickets > 1);

  if (extraBox) {
    extraBox.style.display = allowExtraBox ? 'block' : 'none';
  }
  if (!allowExtraBox && RS_COMPANIONS.length > 0) {
    RS_COMPANIONS = [];
    renderCompanionRows();
  } else if (allowExtraBox) {
    const maxSlots = totalAdultTickets - 1;
    if (RS_COMPANIONS.length > maxSlots) {
      RS_COMPANIONS = RS_COMPANIONS.slice(0, maxSlots);
      renderCompanionRows();
    }
    if (addBtn) {
      addBtn.disabled = (RS_COMPANIONS.length >= maxSlots);
    }
  }

  const confirmEmailEl = document.getElementById('confirm-email-disp');
  if (confirmEmailEl) {
    confirmEmailEl.textContent = emailVal || RS_ORIG_CUSTOMER.email || '';
  }

  const hintEl = document.getElementById('rs-rep-cccd-hint');
  if (hintEl) {
    if (!repCccdVal) {
      hintEl.style.display = 'none';
    } else if (repCccdVal.length < 12) {
      hintEl.style.display = 'block';
      hintEl.style.color = '#64748b';
      hintEl.textContent = `Đã nhập ${repCccdVal.length}/12 chữ số CCCD...`;
    } else if (isValidQtCccd(repCccdVal)) {
      hintEl.style.display = 'block';
      hintEl.style.color = 'var(--ok)';
      hintEl.textContent = '✓ CCCD Quảng Trị hợp lệ (đầu số 044/045).';
    } else {
      hintEl.style.display = 'block';
      hintEl.style.color = '#64748b';
      hintEl.textContent = 'CCCD tỉnh khác (không thuộc 044/045) – áp dụng giá tiêu chuẩn.';
    }
  }

  const nonEmptyCompanions = allowExtraBox
    ? RS_COMPANIONS.map(c => (c.cccd || '').trim()).filter(Boolean)
    : [];
  const allCompanionsValidFormat = nonEmptyCompanions.every(c => /^\d{12}$/.test(c));

  const hasAnyCccd = repCccdVal.length > 0 || nonEmptyCompanions.length > 0;
  const confirmWrap = document.getElementById('rs-cccd-confirm-wrap');
  const confirmChk = document.getElementById('chk-cccd-confirm');
  if (confirmWrap) {
    confirmWrap.style.display = hasAnyCccd ? 'block' : 'none';
  }
  if (!hasAnyCccd && confirmChk) {
    confirmChk.checked = false;
  }

  const isCustomerValid = (
    nameVal.length > 0 &&
    /^0\d{9}$/.test(phoneVal) &&
    emailVal.includes('@') &&
    emailVal.includes('.') &&
    (repCccdVal === '' || /^\d{12}$/.test(repCccdVal)) &&
    allCompanionsValidFormat &&
    (!hasAnyCccd || Boolean(confirmChk?.checked))
  );

  return {
    nameVal,
    phoneVal,
    emailVal,
    isCustomerValid,
  };
}

function hasRescheduleChanged(custState, orderedValidCccds, allocByService) {
  const origDate = document.getElementById('hidden-orig-date')?.value || '';
  const curDate = document.getElementById('hidden-visit-date')?.value || '';
  if (origDate && curDate && origDate !== curDate) return true;

  const qtyChanged = RS_PACKAGES.some(pkg => {
    const st = RS_STATE[pkg.id] || { adult: 0, child: 0, infant: 0 };
    return (
      st.adult !== (pkg.init_adult || 0) ||
      st.child !== (pkg.init_child || 0) ||
      st.infant !== (pkg.init_infant || 0)
    );
  });
  if (qtyChanged) return true;

  const qtChanged = (
    orderedValidCccds.length !== RS_ORIG_QT_CCCDS.length ||
    orderedValidCccds.some((v, idx) => v !== RS_ORIG_QT_CCCDS[idx])
  );
  if (qtChanged) return true;

  const allocChanged = RS_PACKAGES.some(pkg => {
    const oldCnt = Number(RS_ORIG_QT_ALLOC[String(pkg.id)] || 0);
    const newCnt = Number(allocByService[pkg.id] || 0);
    return oldCnt !== newCnt;
  });
  if (allocChanged) return true;

  if (
    custState.nameVal !== (RS_ORIG_CUSTOMER.full_name || '') ||
    custState.phoneVal !== (RS_ORIG_CUSTOMER.phone || '') ||
    custState.emailVal.toLowerCase() !== (RS_ORIG_CUSTOMER.email || '').toLowerCase()
  ) {
    return true;
  }

  return false;
}

async function changeRescheduleDate(newDateIso) {
  if (!newDateIso) return;
  showRescheduleError('');
  const orderCode = document.getElementById('hidden-order-code')?.value || '';

  try {
    const resp = await fetch(`/api/availability/?date=${encodeURIComponent(newDateIso)}&exclude_order=${encodeURIComponent(orderCode)}`);
    const data = await resp.json();
    if (!resp.ok) {
      showRescheduleError(data.error || 'Ngày sử dụng mới không hợp lệ.');
      return;
    }

    const hiddenDate = document.getElementById('hidden-visit-date');
    if (hiddenDate) hiddenDate.value = data.date;

    const invDate = document.getElementById('inv-date-disp');
    const dayBadge1 = document.getElementById('rs-day-badge');
    const dayBadge2 = document.getElementById('inv-day-badge');
    if (invDate) invDate.textContent = data.date_display;
    if (dayBadge1) dayBadge1.textContent = data.day_label;
    if (dayBadge2) dayBadge2.textContent = data.day_label;

    data.services.forEach(srv => {
      const pkg = RS_PACKAGES.find(p => p.id === srv.id);
      if (!pkg) return;

      pkg.is_active = srv.is_active;
      pkg.available = srv.available;
      pkg.price_adult = srv.price_adult;
      pkg.price_child = srv.price_child;
      pkg.price_qt = srv.price_qt;

      const pAdultEl = document.getElementById(`price-adult-${pkg.id}`);
      const pChildEl = document.getElementById(`price-child-${pkg.id}`);
      const availBadge = document.getElementById(`avail-badge-${pkg.id}`);
      if (pAdultEl) pAdultEl.textContent = rsFmt(pkg.price_adult);
      if (pChildEl) pChildEl.textContent = rsFmt(pkg.price_child);
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

      const st = RS_STATE[pkg.id];
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

    renderRepServiceBox();
    renderCompanionRows();
    renderRescheduleSummary();
  } catch (e) {
    showRescheduleError('Không thể tải giá vé cho ngày mới.');
  }
}

function adjustRescheduleTicket(pkgId, tier, delta) {
  showRescheduleError('');
  const pkg = RS_PACKAGES.find(p => p.id === pkgId);
  const st = RS_STATE[pkgId];
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
        showRescheduleError('Trẻ em dưới 1m miễn phí vé cần đi kèm ít nhất 01 vé có tính phí.');
        return;
      }
      st.infant = Math.min(10, st.infant + 1);
    } else if (delta < 0 && st.infant > 0) {
      st.infant -= 1;
    }
  }

  renderRepServiceBox();
  renderCompanionRows();
  renderRescheduleSummary();
}

function renderRescheduleSummary() {
  renderRepServiceBox();
  const custState = syncCustomerInputsState();
  const { allocByService, orderedValidCccds } = getQtAllocationsByService();

  let sumLinesHtml = '';
  let newSubtotal = 0;
  let totalPaidTickets = 0;
  let totalAllTickets = 0;

  RS_PACKAGES.forEach(pkg => {
    const st = RS_STATE[pkg.id];
    if (!st) return;

    const paidQty = st.adult + st.child;
    const pkgAllQty = paidQty + st.infant;
    totalPaidTickets += paidQty;
    totalAllTickets += pkgAllQty;

    const qtAdultQty = Math.min(st.adult, allocByService[pkg.id] || 0);
    const regAdultQty = Math.max(0, st.adult - qtAdultQty);

    const cardEl = document.querySelector(`.ck-mini-card[data-pkg-id="${pkg.id}"]`);
    if (cardEl) cardEl.classList.toggle('is-picked', pkgAllQty > 0);

    const autoTotalEl = document.getElementById(`pkg-auto-total-${pkg.id}`);
    if (autoTotalEl) autoTotalEl.innerHTML = `Tổng: <b>${pkgAllQty}</b> vé`;

    const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };

    setTxt(`disp-adult-${pkg.id}`, st.adult);
    setTxt(`disp-child-${pkg.id}`, st.child);
    setTxt(`disp-infant-${pkg.id}`, st.infant);

    setVal(`adult_qty_${pkg.id}`, st.adult);
    setVal(`child_qty_${pkg.id}`, st.child);
    setVal(`infant_qty_${pkg.id}`, st.infant);

    if (pkgAllQty > 0) {
      const regCost = regAdultQty * pkg.price_adult;
      const qtCost = qtAdultQty * pkg.price_qt;
      const childCost = st.child * pkg.price_child;
      const lineTotal = regCost + qtCost + childCost;

      newSubtotal += lineTotal;

      let subRows = '';
      if (regAdultQty > 0) {
        subRows += `<div class="ck-inv-subrow"><span>${regAdultQty} × Trên 1,4m (Giá tiêu chuẩn)</span><span>${rsFmt(regCost)}</span></div>`;
      }
      if (qtAdultQty > 0) {
        subRows += `<div class="ck-inv-subrow is-qt"><span>${qtAdultQty} × Trên 1,4m <em>(Ưu đãi CCCD Quảng Trị)</em></span><b>${rsFmt(qtCost)}</b></div>`;
      }
      if (st.child > 0) {
        subRows += `<div class="ck-inv-subrow"><span>${st.child} × Từ 1m – 1,4m</span><span>${rsFmt(childCost)}</span></div>`;
      }
      if (st.infant > 0) {
        subRows += `<div class="ck-inv-subrow"><span>${st.infant} × Dưới 1m (Miễn phí)</span><span>0 VNĐ</span></div>`;
      }

      sumLinesHtml += `
        <div class="ck-inv-group">
          <div class="ck-inv-group-head">
            <strong>${pkg.name} (${pkgAllQty} vé)</strong>
            <b>${rsFmt(lineTotal)}</b>
          </div>
          ${subRows}
        </div>`;
    }
  });

  const invTicketsEl = document.getElementById('inv-total-tickets');
  if (invTicketsEl) invTicketsEl.textContent = `${totalAllTickets} vé`;

  const sumLinesEl = document.getElementById('sum-lines');
  if (sumLinesEl) {
    sumLinesEl.innerHTML = sumLinesHtml || '<p class="sm" style="font-style:normal;margin:10px 0">Chưa có vé nào được chọn.</p>';
  }

  let appliedDiscount = 0;
  if (RS_VOUCHER && RS_VOUCHER.has_voucher && newSubtotal > 0) {
    if (RS_VOUCHER.type === 'PERCENT') {
      appliedDiscount = Math.min(newSubtotal, Math.round(newSubtotal * RS_VOUCHER.value / 100));
    } else {
      appliedDiscount = Math.min(newSubtotal, Number(RS_VOUCHER.fixed_discount || 0));
    }
  }

  const newGrandTotal = Math.max(0, newSubtotal - appliedDiscount);
  const diffAmount = newGrandTotal - RS_OLD_TOTAL;
  RS_CURRENT_DIFF = diffAmount;
  const isChanged = hasRescheduleChanged(custState, orderedValidCccds, allocByService);

  const newTotalEl = document.getElementById('sum-new-total');
  if (newTotalEl) newTotalEl.textContent = rsFmt(newGrandTotal);

  const diffCard = document.getElementById('diff-summary-card');
  const diffTitle = document.getElementById('diff-title-lbl');
  const diffAmountEl = document.getElementById('sum-diff-amount');
  const diffNoteEl = document.getElementById('diff-sub-note');
  const submitBtn = document.getElementById('rs-submit-btn');

  if (diffCard && diffTitle && diffAmountEl && diffNoteEl && submitBtn) {
    const exchangeConfirmed = Boolean(document.getElementById('chk-confirm-exchange')?.checked);
    const canSubmit = totalPaidTickets > 0 && isChanged && custState.isCustomerValid && exchangeConfirmed;

    if (diffAmount < 0) {
      diffCard.style.background = '#fef2f2';
      diffCard.style.borderColor = '#fca5a5';
      diffTitle.style.color = '#991b1b';
      diffTitle.textContent = 'Không hỗ trợ đổi thấp giá hơn';
      diffAmountEl.style.color = 'var(--red)';
      diffAmountEl.textContent = `-${rsFmt(Math.abs(diffAmount))}`;
      diffNoteEl.textContent = `Vé chỉ được đổi ngang giá hoặc cao hơn đơn đã thanh toán (${rsFmt(RS_OLD_TOTAL)}). Vui lòng chọn thêm vé hoặc nâng gói dịch vụ.`;
      submitBtn.textContent = 'Giá trị vé mới phải ≥ đơn cũ';
      submitBtn.disabled = true;
    } else if (diffAmount > 0) {
      diffCard.style.background = '#fff5f5';
      diffCard.style.borderColor = '#fecaca';
      diffTitle.style.color = '#991b1b';
      diffTitle.textContent = 'Tổng cần thanh toán bổ sung';
      diffAmountEl.style.color = 'var(--red)';
      diffAmountEl.textContent = rsFmt(diffAmount);
      diffNoteEl.textContent = 'Cổng VNPAY sẽ mở ở tab mới để thanh toán phần chênh lệch này.';
      submitBtn.textContent = `Thanh toán bổ sung ${rsFmt(diffAmount)} qua VNPAY →`;
      submitBtn.disabled = !canSubmit;
    } else {
      diffCard.style.background = '#f0fdf4';
      diffCard.style.borderColor = '#bbf7d0';
      diffTitle.style.color = '#166534';
      diffTitle.textContent = 'Tổng cần thanh toán bổ sung';
      diffAmountEl.style.color = 'var(--ok)';
      diffAmountEl.textContent = '0 VNĐ (Đổi ngang giá)';
      diffNoteEl.textContent = isChanged
        ? 'Không phát sinh chi phí bổ sung. Hệ thống sẽ hủy mã QR cũ và cấp mã QR mới.'
        : 'Hãy thay đổi ngày sử dụng, gói dịch vụ, số lượng vé hoặc thông tin khách hàng.';
      submitBtn.textContent = 'Xác nhận đổi vé & Cấp mã QR mới →';
      submitBtn.disabled = !canSubmit;
    }
  }
}