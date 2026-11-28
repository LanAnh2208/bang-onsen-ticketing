(function () {
  function readJsonScript(id, fallback) {
    const el = document.getElementById(id);
    if (!el) return fallback;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return fallback;
    }
  }

  function fmtVnd(amount) {
    const val = Math.max(0, Math.round(Number(amount) || 0));
    return val.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ' VNĐ';
  }

  function isQuangTriCccd(val) {
    return /^(044|045)\d{9}$/.test((val || '').trim());
  }

  const packages = readJsonScript('rs-packages-data', []);
  const origQtCccds = readJsonScript('rs-orig-qt-cccds-data', []);
  const origQtAlloc = readJsonScript('rs-orig-qt-alloc-data', {});
  let repCccdServiceId = Number(readJsonScript('rs-rep-cccd-service-data', 0)) || 0;
  let extraQtItems = readJsonScript('rs-extra-qt-items-data', []);
  const origCustomer = readJsonScript('rs-orig-customer-data', {});
  const voucherInfo = readJsonScript('rs-voucher-data', { has_voucher: false });
  const oldTotal = Number(readJsonScript('rs-old-total-data', 0)) || 0;

  let activeTab = document.getElementById('rs-tab-btn-info')?.classList.contains('is-active')
    ? 'info'
    : 'tickets';

  let isCompareOpen = false;
  let pollTimer = null;
  let countdownTimer = null;
  let lastPaymentUrl = '';
  let activeTxnId = '';

  window.toggleOrderCompareDrawer = function (forceState) {
    isCompareOpen = typeof forceState === 'boolean' ? forceState : !isCompareOpen;
    const popover = document.getElementById('rs-compare-popover');
    const btn = document.getElementById('rs-compare-toggle-btn');

    if (popover) {
      popover.hidden = !isCompareOpen;
      popover.classList.toggle('is-open', isCompareOpen);
      popover.setAttribute('aria-hidden', isCompareOpen ? 'false' : 'true');
    }
    if (btn) {
      btn.classList.toggle('is-active', isCompareOpen);
      btn.setAttribute('aria-expanded', isCompareOpen ? 'true' : 'false');
      btn.textContent = isCompareOpen ? '✕ Đóng so sánh' : '⇄ So sánh';
    }
  };

  function getPkg(id) {
    return packages.find((p) => Number(p.id) === Number(id));
  }

  function getQty(pkgId, type) {
    const inp = document.getElementById(`${type}_qty_${pkgId}`);
    return inp ? Math.max(0, parseInt(inp.value || '0', 10) || 0) : 0;
  }

  function setQty(pkgId, type, val) {
    const safeVal = Math.max(0, parseInt(val, 10) || 0);
    const inp = document.getElementById(`${type}_qty_${pkgId}`);
    const disp = document.getElementById(`disp-${type}-${pkgId}`);
    if (inp) inp.value = String(safeVal);
    if (disp) disp.textContent = String(safeVal);
  }

  function getTotalsAcrossPackages() {
    let totalAdult = 0;
    let totalChild = 0;
    let totalInfant = 0;
    packages.forEach((p) => {
      totalAdult += getQty(p.id, 'adult');
      totalChild += getQty(p.id, 'child');
      totalInfant += getQty(p.id, 'infant');
    });
    return {
      totalAdult,
      totalChild,
      totalInfant,
      totalPaid: totalAdult + totalChild,
      totalAll: totalAdult + totalChild + totalInfant,
    };
  }

  window.switchRescheduleTab = function (tabName) {
    activeTab = tabName === 'info' ? 'info' : 'tickets';
    const btnT = document.getElementById('rs-tab-btn-tickets');
    const btnI = document.getElementById('rs-tab-btn-info');
    const paneT = document.getElementById('rs-tab-pane-tickets');
    const paneI = document.getElementById('rs-tab-pane-info');
    const footBtn = document.getElementById('rs-foot-switch-btn');

    if (btnT) btnT.classList.toggle('is-active', activeTab === 'tickets');
    if (btnI) btnI.classList.toggle('is-active', activeTab === 'info');

    if (paneT) {
      paneT.hidden = activeTab !== 'tickets';
      paneT.style.display = activeTab === 'tickets' ? '' : 'none';
    }
    if (paneI) {
      paneI.hidden = activeTab !== 'info';
      paneI.style.display = activeTab === 'info' ? '' : 'none';
    }
    if (footBtn) {
      footBtn.textContent =
        activeTab === 'info' ? '← Quay lại điều chỉnh vé' : 'Điều chỉnh thông tin →';
    }
  };

  window.handleFooterTabSwitch = function () {
    switchRescheduleTab(activeTab === 'info' ? 'tickets' : 'info');
  };

  window.adjustRescheduleTicket = function (pkgId, type, delta) {
    const pkg = getPkg(pkgId);
    if (!pkg || !pkg.is_active || pkg.available <= 0) return;

    const curAdult = getQty(pkgId, 'adult');
    const curChild = getQty(pkgId, 'child');
    const curInfant = getQty(pkgId, 'infant');

    let nextAdult = curAdult;
    let nextChild = curChild;
    let nextInfant = curInfant;

    if (type === 'adult') {
      nextAdult = Math.max(0, curAdult + delta);
      if (nextAdult + nextChild > pkg.available) {
        nextAdult = Math.max(0, pkg.available - nextChild);
      }
      setQty(pkgId, 'adult', nextAdult);
    } else if (type === 'child') {
      nextChild = Math.max(0, curChild + delta);
      if (nextAdult + nextChild > pkg.available) {
        nextChild = Math.max(0, pkg.available - nextAdult);
      }
      setQty(pkgId, 'child', nextChild);
    } else if (type === 'infant') {
      nextInfant = Math.max(0, curInfant + delta);
      setQty(pkgId, 'infant', nextInfant);
    }

    const totalPkg = nextAdult + nextChild + nextInfant;
    const autoTotalEl = document.getElementById(`pkg-auto-total-${pkgId}`);
    if (autoTotalEl) {
      autoTotalEl.innerHTML = `Tổng: <b>${totalPkg}</b> vé`;
    }
    const cardEl = document.querySelector(`.ck-mini-card[data-pkg-id="${pkgId}"]`);
    if (cardEl) {
      cardEl.classList.toggle('is-picked', totalPkg > 0);
    }

    renderRepServiceBox();
    renderCompanionRows();
    renderRescheduleSummary();
  };

  window.changeRescheduleDate = async function (newDateStr) {
    if (!newDateStr) return;
    const hiddenDate = document.getElementById('hidden-visit-date');
    if (hiddenDate) hiddenDate.value = newDateStr;

    const formEl = document.getElementById('reschedule-form');
    const availUrl = formEl?.dataset?.availUrl || '/api/check-availability/';
    const orderCode = document.getElementById('hidden-order-code')?.value || '';

    try {
      const url = `${availUrl}?date=${encodeURIComponent(newDateStr)}&exclude_order=${encodeURIComponent(orderCode)}`;
      const res = await fetch(url);
      const data = await res.json();
      if (!res.ok || data.error) {
        showClientError(data.error || 'Không thể tải bảng giá ngày đã chọn.');
        return;
      }

      const dayBadge = document.getElementById('rs-day-badge');
      const invDayBadge = document.getElementById('inv-day-badge');
      const invDateDisp = document.getElementById('inv-date-disp');
      if (dayBadge) dayBadge.textContent = data.day_label || '';
      if (invDayBadge) invDayBadge.textContent = data.day_label || '';
      if (invDateDisp) invDateDisp.textContent = data.date_display || newDateStr;

      (data.services || []).forEach((srv) => {
        const pkg = getPkg(srv.id);
        if (!pkg) return;
        pkg.is_active = Boolean(srv.is_active);
        pkg.available = Number(srv.available || 0);
        pkg.price_adult = Number(srv.price_adult || 0);
        pkg.price_child = Number(srv.price_child || 0);
        pkg.price_qt = Number(srv.price_qt || 0);

        const pAdultEl = document.getElementById(`price-adult-${pkg.id}`);
        const pChildEl = document.getElementById(`price-child-${pkg.id}`);
        const badgeEl = document.getElementById(`avail-badge-${pkg.id}`);
        if (pAdultEl) pAdultEl.textContent = fmtVnd(pkg.price_adult);
        if (pChildEl) pChildEl.textContent = fmtVnd(pkg.price_child);
        if (badgeEl) {
          if (!pkg.is_active) {
            badgeEl.className = 'bd no';
            badgeEl.textContent = 'Tạm ngừng';
          } else if (pkg.available <= 0) {
            badgeEl.className = 'bd no';
            badgeEl.textContent = 'Hết vé';
          } else {
            badgeEl.className = 'bd ok';
            badgeEl.textContent = `Còn ${pkg.available} vé`;
          }
        }
      });

      renderRepServiceBox();
      renderCompanionRows();
      renderRescheduleSummary();
    } catch (e) {
      showClientError('Lỗi kết nối khi cập nhật giá vé theo ngày mới.');
    }
  };

  function getActiveAdultPackages() {
    return packages.filter((p) => p.is_active && getQty(p.id, 'adult') > 0);
  }

  window.renderRepServiceBox = function () {
    const cccdInput = document.getElementById('rs-cust-cccd');
    const hintEl = document.getElementById('rs-rep-cccd-hint');
    const boxEl = document.getElementById('rs-rep-service-box');
    const selectEl = document.getElementById('rs-rep-cccd-service');
    const val = (cccdInput?.value || '').trim();

    if (hintEl) {
      if (!val) {
        hintEl.style.display = 'none';
      } else if (val.length < 12) {
        hintEl.style.display = 'block';
        hintEl.style.color = '#b45309';
        hintEl.textContent = `Đã nhập ${val.length}/12 chữ số CCCD`;
      } else if (isQuangTriCccd(val)) {
        hintEl.style.display = 'block';
        hintEl.style.color = 'var(--ok)';
        hintEl.textContent = '✓ CCCD Quảng Trị hợp lệ (ưu đãi 01 vé người lớn)';
      } else {
        hintEl.style.display = 'block';
        hintEl.style.color = '#64748b';
        hintEl.textContent = 'CCCD 12 số hợp lệ (không thuộc đầu số 044/045)';
      }
    }

    const adultPkgs = getActiveAdultPackages();
    if (!isQuangTriCccd(val) || adultPkgs.length === 0) {
      if (boxEl) boxEl.style.display = 'none';
      updateCccdConfirmVisibility();
      return;
    }

    if (!adultPkgs.some((p) => Number(p.id) === Number(repCccdServiceId))) {
      repCccdServiceId = Number(adultPkgs[0].id);
    }

    if (selectEl) {
      selectEl.innerHTML = adultPkgs
        .map((p) => {
          const selected = Number(p.id) === Number(repCccdServiceId) ? 'selected' : '';
          return `<option value="${p.id}" ${selected}>${p.name} — Giá ưu đãi ${fmtVnd(p.price_qt)} (giá gốc ${fmtVnd(p.price_adult)})</option>`;
        })
        .join('');
    }
    if (boxEl) boxEl.style.display = 'block';
    updateCccdConfirmVisibility();
  };

  window.handleRepServiceChange = function (val) {
    repCccdServiceId = Number(val) || 0;
    renderCompanionRows();
    renderRescheduleSummary();
  };

  function syncHiddenCompanionList() {
    const hiddenEl = document.getElementById('hidden-qt-cccd-list');
    if (!hiddenEl) return;
    const tokens = extraQtItems
      .filter((item) => (item.cccd || '').trim().length > 0)
      .map((item) => `${item.cccd.trim()}:${Number(item.service_id) || 0}`);
    hiddenEl.value = tokens.join(',');
    updateCccdConfirmVisibility();
  }

  function updateCccdConfirmVisibility() {
    const wrap = document.getElementById('rs-cccd-confirm-wrap');
    if (!wrap) return;
    const repVal = (document.getElementById('rs-cust-cccd')?.value || '').trim();
    const hasExtra = extraQtItems.some((item) => (item.cccd || '').trim().length > 0);
    wrap.style.display = repVal || hasExtra ? 'block' : 'none';
  }

  window.renderCompanionRows = function () {
    const boxEl = document.getElementById('rs-extra-cccd-box');
    const listEl = document.getElementById('rs-companion-list');
    const addBtn = document.getElementById('rs-add-cccd-btn');
    if (!boxEl || !listEl) return;

    const totals = getTotalsAcrossPackages();
    const maxExtra = Math.max(0, totals.totalAdult - 1);
    const adultPkgs = getActiveAdultPackages();

    if (totals.totalAll <= 1 || maxExtra <= 0 || adultPkgs.length === 0) {
      extraQtItems = [];
      boxEl.style.display = 'none';
      listEl.innerHTML = '';
      syncHiddenCompanionList();
      return;
    }

    if (extraQtItems.length > maxExtra) {
      extraQtItems = extraQtItems.slice(0, maxExtra);
    }

    boxEl.style.display = 'block';
    if (addBtn) {
      addBtn.disabled = extraQtItems.length >= maxExtra;
      addBtn.style.opacity = extraQtItems.length >= maxExtra ? '0.55' : '1';
    }

    listEl.innerHTML = extraQtItems
      .map((item, idx) => {
        const curSid = adultPkgs.some((p) => Number(p.id) === Number(item.service_id))
          ? Number(item.service_id)
          : Number(adultPkgs[0].id);
        item.service_id = curSid;

        const optionsHtml = adultPkgs
          .map((p) => {
            const sel = Number(p.id) === curSid ? 'selected' : '';
            return `<option value="${p.id}" ${sel}>${p.name} (${fmtVnd(p.price_qt)})</option>`;
          })
          .join('');

        return `
          <div class="rs-companion-row">
            <input type="text"
                   class="ck-inp"
                   maxlength="12"
                   value="${item.cccd || ''}"
                   placeholder="Nhập CCCD người đi cùng (12 số)"
                   oninput="this.value=this.value.replace(/\\D/g,'');updateCompanionCccd(${idx}, this.value)">
            <select class="ck-inp" onchange="updateCompanionService(${idx}, this.value)">
              ${optionsHtml}
            </select>
            <button type="button" class="rs-del-cccd-btn" title="Xóa CCCD này" onclick="removeCompanionRow(${idx})">✕</button>
          </div>
        `;
      })
      .join('');

    syncHiddenCompanionList();
  };

  window.addCompanionRow = function () {
    const totals = getTotalsAcrossPackages();
    const maxExtra = Math.max(0, totals.totalAdult - 1);
    const adultPkgs = getActiveAdultPackages();
    if (extraQtItems.length >= maxExtra || adultPkgs.length === 0) return;

    extraQtItems.push({ cccd: '', service_id: Number(adultPkgs[0].id) });
    renderCompanionRows();
    renderRescheduleSummary();
  };

  window.removeCompanionRow = function (idx) {
    extraQtItems.splice(idx, 1);
    renderCompanionRows();
    renderRescheduleSummary();
  };

  window.updateCompanionCccd = function (idx, val) {
    if (!extraQtItems[idx]) return;
    extraQtItems[idx].cccd = (val || '').replace(/\D/g, '').slice(0, 12);
    syncHiddenCompanionList();
    renderRescheduleSummary();
  };

  window.updateCompanionService = function (idx, sid) {
    if (!extraQtItems[idx]) return;
    extraQtItems[idx].service_id = Number(sid) || 0;
    syncHiddenCompanionList();
    renderRescheduleSummary();
  };

  function showClientError(msg) {
    const errEl = document.getElementById('rs-client-err');
    if (!errEl) return;
    if (!msg) {
      errEl.hidden = true;
      errEl.style.display = 'none';
      errEl.textContent = '';
      return;
    }
    errEl.hidden = false;
    errEl.style.display = 'block';
    errEl.textContent = '⚠ ' + msg;
  }

  function calculateInheritedDiscount(newSubtotal) {
    if (!voucherInfo || !voucherInfo.has_voucher) {
      return 0;
    }
    if (voucherInfo.type === 'PERCENT') {
      const pct = Number(voucherInfo.value || 0);
      let disc = Math.min(newSubtotal, Math.round((newSubtotal * pct) / 100));
      const maxDisc = Number(voucherInfo.max_discount || 0);
      if (maxDisc > 0) {
        disc = Math.min(disc, maxDisc);
      }
      return Math.max(0, disc);
    }
    const fixedVal = Math.round(Number(voucherInfo.value || voucherInfo.fixed_discount || 0));
    return Math.max(0, Math.min(newSubtotal, fixedVal));
  }

  window.renderRescheduleSummary = function () {
    const totals = getTotalsAcrossPackages();
    const invTicketsEl = document.getElementById('inv-total-tickets');
    if (invTicketsEl) {
      invTicketsEl.textContent = `${totals.totalAll} vé`;
    }

    const emailVal = (document.getElementById('rs-cust-email')?.value || '').trim();
    const confirmEmailDisp = document.getElementById('confirm-email-disp');
    if (confirmEmailDisp) confirmEmailDisp.textContent = emailVal;

    // Phân bổ CCCD Quảng Trị hợp lệ theo từng gói vé
    const pkgStates = {};
    packages.forEach((p) => {
      const a = getQty(p.id, 'adult');
      const c = getQty(p.id, 'child');
      const i = getQty(p.id, 'infant');
      pkgStates[p.id] = {
        pkg: p,
        adult: a,
        remAdult: a,
        qtAdult: 0,
        child: c,
        infant: i,
      };
    });

    const seenCccds = new Set();
    const validQtCccds = [];
    const newQtAlloc = {};

    const repCccd = (document.getElementById('rs-cust-cccd')?.value || '').trim();
    if (isQuangTriCccd(repCccd)) {
      let targetSid =
        pkgStates[repCccdServiceId] && pkgStates[repCccdServiceId].remAdult > 0
          ? repCccdServiceId
          : Number(Object.keys(pkgStates).find((sid) => pkgStates[sid].remAdult > 0) || 0);

      if (targetSid && pkgStates[targetSid]) {
        pkgStates[targetSid].remAdult -= 1;
        pkgStates[targetSid].qtAdult += 1;
        seenCccds.add(repCccd);
        validQtCccds.push(repCccd);
        newQtAlloc[String(targetSid)] = (newQtAlloc[String(targetSid)] || 0) + 1;
      }
    }

    extraQtItems.forEach((item) => {
      const code = (item.cccd || '').trim();
      if (!isQuangTriCccd(code) || seenCccds.has(code)) return;

      const prefSid = Number(item.service_id || 0);
      let targetSid =
        pkgStates[prefSid] && pkgStates[prefSid].remAdult > 0
          ? prefSid
          : Number(Object.keys(pkgStates).find((sid) => pkgStates[sid].remAdult > 0) || 0);

      if (targetSid && pkgStates[targetSid]) {
        pkgStates[targetSid].remAdult -= 1;
        pkgStates[targetSid].qtAdult += 1;
        seenCccds.add(code);
        validQtCccds.push(code);
        newQtAlloc[String(targetSid)] = (newQtAlloc[String(targetSid)] || 0) + 1;
      }
    });

    // Hiển thị danh sách gói dịch vụ & từng loại vé, giá từng loại giống trang đặt vé
    let newSubtotal = 0;
    const sumLinesEl = document.getElementById('sum-lines');
    const lineHtmlParts = [];

    packages.forEach((p) => {
      const st = pkgStates[p.id];
      if (!st || (st.adult === 0 && st.child === 0 && st.infant === 0)) return;

      const regAdult = st.adult - st.qtAdult;
      const lineTotal =
        regAdult * p.price_adult + st.qtAdult * p.price_qt + st.child * p.price_child;
      newSubtotal += lineTotal;

      const pkgGuests = st.adult + st.child + st.infant;
      const subRows = [];

      if (regAdult > 0) {
        subRows.push(`
          <div class="ck-inv-subrow">
            <span>${regAdult} × Trên 1,4m (Giá tiêu chuẩn)</span>
            <span>${fmtVnd(regAdult * p.price_adult)}</span>
          </div>
        `);
      }
      if (st.qtAdult > 0) {
        subRows.push(`
          <div class="ck-inv-subrow is-qt">
            <span>${st.qtAdult} × Trên 1,4m (Ưu đãi CCCD Quảng Trị)</span>
            <span>${fmtVnd(st.qtAdult * p.price_qt)}</span>
          </div>
        `);
      }
      if (st.child > 0) {
        subRows.push(`
          <div class="ck-inv-subrow">
            <span>${st.child} × Từ 1m – 1,4m</span>
            <span>${fmtVnd(st.child * p.price_child)}</span>
          </div>
        `);
      }
      if (st.infant > 0) {
        subRows.push(`
          <div class="ck-inv-subrow">
            <span>${st.infant} × Dưới 1m (Miễn phí vé vào)</span>
            <span>0 VNĐ</span>
          </div>
        `);
      }

      lineHtmlParts.push(`
        <div class="ck-inv-group">
          <div class="ck-inv-group-head">
            <strong>${p.name} (${pkgGuests} vé)</strong>
            <b>${fmtVnd(lineTotal)}</b>
          </div>
          ${subRows.join('')}
        </div>
      `);
    });

    if (sumLinesEl) {
      sumLinesEl.innerHTML =
        lineHtmlParts.length > 0
          ? lineHtmlParts.join('')
          : '<div class="sm" style="padding:8px 0">Chưa chọn gói vé nào.</div>';
    }

    // Áp dụng giảm giá kế thừa từ đơn cũ
    const inheritedDiscount = calculateInheritedDiscount(newSubtotal);
    const newTotal = Math.max(0, newSubtotal - inheritedDiscount);
    const diffAmount = newTotal - oldTotal;

    const subEl = document.getElementById('sum-new-subtotal');
    const discEl = document.getElementById('sum-inherited-discount');
    const newTotalEl = document.getElementById('sum-new-total');
    const diffAmountEl = document.getElementById('sum-diff-amount');
    const diffTitleEl = document.getElementById('diff-title-lbl');
    const diffNoteEl = document.getElementById('diff-sub-note');
    const submitBtn = document.getElementById('rs-submit-btn');

    if (subEl) subEl.textContent = fmtVnd(newSubtotal);
    if (discEl) discEl.textContent = `-${fmtVnd(inheritedDiscount)}`;
    if (newTotalEl) newTotalEl.textContent = fmtVnd(newTotal);

    let validationMsg = '';
    if (totals.totalPaid === 0) {
      validationMsg = 'Vui lòng chọn ít nhất 01 vé có tính phí.';
    } else if (diffAmount < 0) {
      validationMsg = voucherInfo.has_voucher
        ? `Vé chỉ được đổi ngang giá hoặc cao hơn số tiền đã thanh toán ở đơn cũ (${fmtVnd(oldTotal)}). Sau giảm giá kế thừa (${voucherInfo.short_badge}: -${fmtVnd(inheritedDiscount)}), giá vé mới sau giảm là ${fmtVnd(newTotal)}, thấp hơn ${fmtVnd(Math.abs(diffAmount))}.`
        : `Vé chỉ được đổi ngang giá hoặc cao hơn giá trị đơn đã thanh toán (${fmtVnd(oldTotal)}). Giá trị đơn mới hiện tại là ${fmtVnd(newTotal)}, thấp hơn ${fmtVnd(Math.abs(diffAmount))}.`;
    }

    if (diffAmount < 0) {
      if (diffTitleEl) diffTitleEl.textContent = 'Chênh lệch so với đơn cũ';
      if (diffAmountEl) {
        diffAmountEl.style.color = 'var(--red)';
        diffAmountEl.textContent = `-${fmtVnd(Math.abs(diffAmount))}`;
      }
      if (diffNoteEl) {
        diffNoteEl.textContent = `Cần chọn gói vé có giá sau giảm từ ${fmtVnd(oldTotal)} trở lên.`;
      }
    } else if (diffAmount === 0) {
      if (diffTitleEl) diffTitleEl.textContent = 'Thanh toán bổ sung';
      if (diffAmountEl) {
        diffAmountEl.style.color = 'var(--ok)';
        diffAmountEl.textContent = '0 VNĐ';
      }
      if (diffNoteEl) {
        diffNoteEl.textContent = 'Đổi ngang giá — không phát sinh thêm chi phí.';
      }
    } else {
      if (diffTitleEl) diffTitleEl.textContent = 'Thanh toán bổ sung';
      if (diffAmountEl) {
        diffAmountEl.style.color = 'var(--red)';
        diffAmountEl.textContent = fmtVnd(diffAmount);
      }
      if (diffNoteEl) {
        diffNoteEl.textContent = 'Thanh toán phần chênh lệch qua cổng VNPAY để hoàn tất đổi vé.';
      }
    }

    showClientError(validationMsg);

    const confirmChecked = Boolean(document.getElementById('chk-confirm-exchange')?.checked);
    const hasAnyCccd =
      Boolean(repCccd) || extraQtItems.some((item) => (item.cccd || '').trim().length > 0);
    const cccdConfirmed = !hasAnyCccd || Boolean(document.getElementById('chk-cccd-confirm')?.checked);

    if (submitBtn) {
      submitBtn.disabled = Boolean(validationMsg) || !confirmChecked || !cccdConfirmed;
      if (diffAmount > 0) {
        submitBtn.textContent = `Thanh toán thêm ${fmtVnd(diffAmount)} →`;
      } else {
        submitBtn.textContent = 'Xác nhận đổi vé →';
      }
    }
  };

  function showPaymentStatusPanel(state, payload) {
    const editorCard = document.getElementById('rs-editor-card');
    const statusPanel = document.getElementById('rs-payment-status-panel');
    const stPending = document.getElementById('rs-pay-state-pending');
    const stSuccess = document.getElementById('rs-pay-state-success');
    const stFailed = document.getElementById('rs-pay-state-failed');

    if (isCompareOpen) {
      window.toggleOrderCompareDrawer(false);
    }

    if (editorCard) {
      editorCard.hidden = true;
      editorCard.style.display = 'none';
    }
    if (statusPanel) {
      statusPanel.hidden = false;
      statusPanel.style.display = 'block';
    }

    [stPending, stSuccess, stFailed].forEach((el) => {
      if (!el) return;
      el.hidden = true;
      el.style.display = 'none';
    });

    if (state === 'pending' && stPending) {
      stPending.hidden = false;
      stPending.style.display = 'block';
      const pendAmt = document.getElementById('rs-pend-amount');
      const reopenLink = document.getElementById('rs-reopen-vnpay-link');
      if (pendAmt && payload.diff_amount_fmt) pendAmt.textContent = payload.diff_amount_fmt;
      if (reopenLink && payload.payment_url) reopenLink.href = payload.payment_url;
    } else if (state === 'success' && stSuccess) {
      stSuccess.hidden = false;
      stSuccess.style.display = 'block';
      const emailEl = document.getElementById('rs-succ-email');
      const qrEl = document.getElementById('rs-succ-qr');
      const dateEl = document.getElementById('rs-succ-date');
      const totalEl = document.getElementById('rs-succ-total');
      const lookupBtn = document.getElementById('rs-succ-lookup-btn');
      if (emailEl) emailEl.textContent = payload.email || '';
      if (qrEl) qrEl.textContent = payload.qr_code || '—';
      if (dateEl) dateEl.textContent = payload.visit_date_display || '—';
      if (totalEl) totalEl.textContent = payload.total_amount_fmt || '—';
      if (lookupBtn && payload.lookup_url) lookupBtn.href = payload.lookup_url;
    } else if (state === 'failed' && stFailed) {
      stFailed.hidden = false;
      stFailed.style.display = 'block';
      const reasonEl = document.getElementById('rs-fail-reason');
      if (reasonEl && payload.message) reasonEl.textContent = payload.message;
    }
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    if (countdownTimer) {
      clearInterval(countdownTimer);
      countdownTimer = null;
    }
  }

  function startExchangeStatusPolling(txnId, orderCode) {
    stopPolling();
    let secondsLeft = 15 * 60;
    const cdEl = document.getElementById('rs-pend-countdown');

    countdownTimer = setInterval(() => {
      secondsLeft = Math.max(0, secondsLeft - 1);
      if (cdEl) {
        const mm = String(Math.floor(secondsLeft / 60)).padStart(2, '0');
        const ss = String(secondsLeft % 60).padStart(2, '0');
        cdEl.textContent = `${mm}:${ss}`;
      }
      if (secondsLeft === 0) {
        stopPolling();
        showPaymentStatusPanel('failed', {
          message: 'Giao dịch thanh toán bổ sung đã hết thời gian giữ 15 phút.',
        });
      }
    }, 1000);

    pollTimer = setInterval(async () => {
      try {
        const res = await fetch(
          `/api/exchange-status/${encodeURIComponent(txnId)}/?order_code=${encodeURIComponent(orderCode)}`
        );
        const data = await res.json();
        if (data.status === 'SUCCESS') {
          stopPolling();
          showPaymentStatusPanel('success', data);
        } else if (data.status === 'FAILED') {
          stopPolling();
          showPaymentStatusPanel('failed', data);
        }
      } catch (e) {
        // Bỏ qua lỗi mạng tạm thời, tiếp tục kiểm tra ở chu kỳ kế tiếp
      }
    }, 3000);
  }

  window.resetExchangePaymentPanel = function () {
    stopPolling();
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
  };

  window.retryExchangePayment = function () {
    if (lastPaymentUrl) {
      window.open(lastPaymentUrl, '_blank', 'noopener');
      showPaymentStatusPanel('pending', { payment_url: lastPaymentUrl });
      const orderCode = document.getElementById('hidden-order-code')?.value || '';
      if (activeTxnId) {
        startExchangeStatusPolling(activeTxnId, orderCode);
      }
    } else {
      resetExchangePaymentPanel();
    }
  };

  document.addEventListener('click', (ev) => {
    if (!isCompareOpen) return;
    const popover = document.getElementById('rs-compare-popover');
    const toggleBtn = document.getElementById('rs-compare-toggle-btn');
    if (popover && !popover.contains(ev.target) && toggleBtn && !toggleBtn.contains(ev.target)) {
      window.toggleOrderCompareDrawer(false);
    }
  });

  document.addEventListener('DOMContentLoaded', () => {
    renderRepServiceBox();
    renderCompanionRows();
    renderRescheduleSummary();

    const formEl = document.getElementById('reschedule-form');
    if (!formEl) return;

    formEl.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      syncHiddenCompanionList();
      showClientError('');

      const submitBtn = document.getElementById('rs-submit-btn');
      const prevText = submitBtn ? submitBtn.textContent : '';
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Đang xử lý yêu cầu đổi vé...';
      }

      try {
        const formData = new FormData(formEl);
        const res = await fetch(formEl.action || window.location.href, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          body: formData,
        });
        const data = await res.json();

        if (!res.ok || !data.ok) {
          if (data.active_tab) {
            switchRescheduleTab(data.active_tab);
          }
          showClientError(data.error || 'Không thể xử lý đổi vé. Vui lòng kiểm tra lại thông tin.');
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = prevText;
          }
          return;
        }

        if (data.requires_payment && data.payment_url) {
          lastPaymentUrl = data.payment_url;
          activeTxnId = data.transaction_id;
          window.open(data.payment_url, '_blank', 'noopener');
          showPaymentStatusPanel('pending', data);
          const orderCode = document.getElementById('hidden-order-code')?.value || '';
          startExchangeStatusPolling(data.transaction_id, orderCode);
        } else if (data.redirect_url) {
          window.location.href = data.redirect_url;
        }
      } catch (e) {
        showClientError('Lỗi kết nối máy chủ khi gửi yêu cầu đổi vé.');
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = prevText;
        }
      }
    });
  });
})();