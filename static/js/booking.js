const $ = s => document.querySelector(s);
const fm = n => Math.round(Number(n) || 0).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ' VNĐ';

let selectedQtys = {};
let hasSearched = false;

// ==========================================================================
// 1. KHỞI TẠO PRELOADER, REVEAL NỐI TIẾP & HỆ THỐNG PARALLAX ĐA TẦNG
// ==========================================================================
window.addEventListener('DOMContentLoaded', () => {
  const pl = $('#pl');
  if (pl) {
    setTimeout(() => pl.classList.add('x'), 650);
    setTimeout(() => pl.remove(), 1100);
  }

  initRevealAnimations();
  initFullPageParallax();

  if (document.querySelector('.flow-pill')) {
    activateFlowStep(0);
  }
});

function initRevealAnimations() {
  const revealGroups = [
    'main.tc .sec-head',
    'main.tc .rev-head',
    'main.tc .onsen-tile',
    'main.tc .flow-board',
    'main.tc .eco-card',
    'main.tc .gal-item',
    'main.tc .faq-item',
    'main.tc .cmp-wrap',
  ];

  const targets = document.querySelectorAll(revealGroups.join(', '));
  targets.forEach((el, idx) => {
    el.classList.add('rv');
    const mod = idx % 3;
    if (mod === 1) el.classList.add('rv-d1');
    if (mod === 2) el.classList.add('rv-d2');
  });

  const io = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('in');
        io.unobserve(entry.target);
      }
    });
  }, {
    threshold: 0.1,
    rootMargin: '0px 0px -36px 0px',
  });

  targets.forEach(el => io.observe(el));
}

function initFullPageParallax() {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduceMotion) return;

  const layers = [];
  const register = (selector, range, maxShift, isHeroBg = false) => {
    document.querySelectorAll(selector).forEach(el => {
      el.classList.add('px-layer');
      layers.push({
        el,
        range,
        maxShift,
        isHeroBg,
        currentY: 0,
      });
    });
  };

  // Hero & Thanh đặt vé nhanh
  register('.hbg', 110, 62, true);
  register('.hero .w', -34, 20);
  register('.flt-wrap', -22, 14);

  // Tiêu đề các block
  register('.sec-band .sec-head', -20, 12);
  register('.band-dark .rev-head', -20, 12);

  // Block 1: 3 gói dịch vụ Onsen (lệch pha giữa cột giữa và 2 cột biên + ảnh nền bên trong)
  register('.onsen-tile:nth-child(1)', 26, 15);
  register('.onsen-tile:nth-child(2)', -26, 15);
  register('.onsen-tile:nth-child(3)', 26, 15);
  register('.onsen-tile-media', -24, 14);

  // Block 2: Quy trình 3 bước
  register('.flow-board', 22, 13);

  // Block 3: Hệ sinh thái nghỉ dưỡng
  register('.eco-card:nth-child(1)', 24, 14);
  register('.eco-card:nth-child(2)', -24, 14);
  register('.eco-card:nth-child(3)', 24, 14);

  // Block 4: Đánh giá khách hàng chạy ngang
  register('.mq-wrap', 18, 11);
  register('.mq-pills-wrap', -16, 10);

  // Block 5: Thư viện 7 ảnh (50% ảnh lớn trái và 50% cụm 6 ảnh phải đối nghịch nhẹ)
  register('.gal-main', 28, 16);
  register('.gal-sub-grid', -28, 16);

  // Block 6: Danh sách FAQ
  register('.band-mist .faq-item', 14, 8);

  const ease = 0.16; // Độ trễ mượt ~0.3s, vừa đủ cảm nhận chuyển động mà không bị ì

  function animateParallax() {
    const header = $('header.h');
    if (header) header.classList.toggle('s', window.scrollY > 12);

    if (window.innerWidth > 960) {
      const vh = window.innerHeight || 1;
      const vCenter = vh * 0.5;

      for (let i = 0; i < layers.length; i++) {
        const item = layers[i];
        const rect = item.el.getBoundingClientRect();
        const naturalTop = rect.top - item.currentY;
        const naturalBottom = naturalTop + rect.height;

        // Chỉ tính toán cho các block nằm gần khung nhìn hiện tại
        if (naturalBottom < -220 || naturalTop > vh + 220) continue;

        let targetY = 0;
        if (item.isHeroBg) {
          const heroProgress = Math.min(1, Math.max(0, window.scrollY / Math.max(vh, 560)));
          targetY = Math.min(item.maxShift, heroProgress * item.range);
        } else {
          const elCenter = naturalTop + rect.height * 0.5;
          const progress = Math.max(-1, Math.min(1, (vCenter - elCenter) / vh));
          targetY = Math.max(-item.maxShift, Math.min(item.maxShift, progress * item.range));
        }

        const diff = targetY - item.currentY;
        if (Math.abs(diff) > 0.08) {
          item.currentY += diff * ease;
          item.el.style.translate = `0px ${item.currentY.toFixed(2)}px`;
        }
      }
    }

    requestAnimationFrame(animateParallax);
  }

  requestAnimationFrame(animateParallax);
}

// ==========================================================================
// 2. TRA CỨU VÉ & CHỌN SỐ LƯỢNG TRỰC TIẾP TRÊN TỪNG GÓI DỊCH VỤ
// ==========================================================================
function updateDayLabel(dateStr) {
  const badge = $('#fday-badge');
  if (!badge || !dateStr) return;
  const parts = dateStr.split('-').map(Number);
  const localDate = new Date(parts[0], parts[1] - 1, parts[2]);
  const day = localDate.getDay();
  badge.textContent = (day === 0 || day === 6) ? 'Cuối tuần (T7–CN)' : 'Đầu tuần (T2–T6)';
  if (hasSearched) findTickets(true);
}

function quickPickService(serviceId) {
  selectedQtys[serviceId] = Math.max(1, selectedQtys[serviceId] || 1);
  const flt = $('#flt');
  if (flt) flt.scrollIntoView({ behavior: 'smooth' });
  findTickets(true);
}

async function findTickets(instant = false) {
  const dateInput = $('#fd');
  const resBox = $('#res');
  if (!dateInput || !resBox) return;

  const dateVal = dateInput.value;
  if (!dateVal) {
    resBox.innerHTML = '<div class="al er">Vui lòng chọn ngày đi hợp lệ.</div>';
    return;
  }

  hasSearched = true;
  const fltBox = $('#flt-box');
  if (fltBox) fltBox.classList.add('expanded');

  if (!instant) {
    resBox.innerHTML = '<div class="skl" aria-label="Đang kiểm tra tình trạng vé"></div>';
  }

  try {
    const resp = await fetch(`/api/availability/?date=${encodeURIComponent(dateVal)}`);
    const data = await resp.json();

    if (!resp.ok) {
      resBox.innerHTML = `<div class="al er">${data.error || 'Không thể kiểm tra vé.'}</div>`;
      return;
    }

    if (!instant) await new Promise(r => setTimeout(r, 220));

    data.services.forEach(s => {
      if (!s.is_active || s.available <= 0) {
        selectedQtys[s.id] = 0;
      } else if ((selectedQtys[s.id] || 0) > s.available) {
        selectedQtys[s.id] = s.available;
      }
    });

    window._lastSearchData = data;
    renderFilteredResults();
  } catch (err) {
    resBox.innerHTML = '<div class="al er">Lỗi kết nối máy chủ, vui lòng thử lại.</div>';
  }
}

function changeServiceQty(serviceId, delta) {
  const data = window._lastSearchData;
  if (!data) return;
  const svc = data.services.find(item => item.id === serviceId);
  if (!svc || !svc.is_active) return;

  const current = selectedQtys[serviceId] || 0;
  selectedQtys[serviceId] = Math.max(0, Math.min(svc.available, current + delta));
  renderFilteredResults();
}

function renderFilteredResults() {
  const data = window._lastSearchData;
  const resBox = $('#res');
  if (!data || !resBox) return;

  const cardsHtml = data.services.map(s => {
    const qty = selectedQtys[s.id] || 0;
    const isSel = s.is_active && qty > 0;

    let statusBadge = `<span class="bd ok">Còn ${s.available} / ${s.max_capacity} vé</span>`;
    if (!s.is_active) {
      statusBadge = '<span class="bd no">Tạm ngừng</span>';
    } else if (s.available <= 0) {
      statusBadge = '<span class="bd no">Hết vé</span>';
    }

    const mediaHtml = s.image_url
      ? `<figure class="ph" style="height:135px;padding:0"><img src="${s.image_url}" alt="${s.name}"></figure>`
      : `<figure class="ph" style="height:135px"><span>📷 Ảnh gói dịch vụ ${s.name}</span></figure>`;

    let controlBlock = '';
    if (!s.is_active) {
      controlBlock = `
        <div class="al er" style="margin:0 0 12px;padding:10px 12px;font-size:13px;font-weight:600">
          ${s.inactive_message || 'Gói vé này đang tạm ngừng, hãy lựa chọn vé khác'}
        </div>
        <div class="row">
          <a class="btn s sm" href="/onsen-${s.id}/">Xem chi tiết</a>
        </div>`;
    } else if (s.available <= 0) {
      controlBlock = `
        <div class="al er" style="margin:0 0 12px;padding:10px 12px;font-size:13px">
          Ngày này đã hết vé, vui lòng chọn ngày khác.
        </div>
        <div class="row">
          <a class="btn s sm" href="/onsen-${s.id}/">Xem chi tiết</a>
          <button type="button" class="btn sm" onclick="openCalendarModal(${s.id})">📅 Xem lịch còn vé</button>
        </div>`;
    } else {
      controlBlock = `
        <div class="pkg-qty">
          <div>
            <span style="font-size:13px;font-weight:600;display:block">Số lượng vé</span>
            ${qty > 0 ? `<small style="color:var(--red);font-style:normal;font-weight:600">Tạm tính: ${fm(qty * s.price_adult)}</small>` : '<small>Chọn số vé muốn đặt</small>'}
          </div>
          <div class="st">
            <button type="button" onclick="changeServiceQty(${s.id}, -1)" ${qty <= 0 ? 'disabled' : ''} aria-label="Giảm số vé ${s.name}">−</button>
            <b>${qty}</b>
            <button type="button" onclick="changeServiceQty(${s.id}, 1)" ${qty >= s.available ? 'disabled' : ''} aria-label="Tăng số vé ${s.name}">+</button>
          </div>
        </div>
        <div class="row">
          <a class="btn s sm" href="/onsen-${s.id}/">Xem chi tiết</a>
          <button type="button" class="btn sm" onclick="openCalendarModal(${s.id})">📅 Lịch vé</button>
        </div>`;
    }

    return `
      <article class="cd ${!s.is_active ? 'inactive' : ''} ${isSel ? 'sel' : ''}">
        ${mediaHtml}
        <div class="row" style="justify-content:space-between;margin-top:12px">
          <span class="bd">${s.name}</span>
          ${statusBadge}
        </div>
        <h3 style="margin:10px 0 4px">Gói dịch vụ ${s.name}</h3>
        <div class="pc">${fm(s.price_adult)}</div>
        <small class="ps2">Trẻ em 1–1,4m: ${fm(s.price_child)} · Người Quảng Trị: ${fm(s.price_qt)}</small>
        <p class="sm hl">${s.highlights}</p>
        <div class="act">${controlBlock}</div>
      </article>`;
  }).join('');

  const chosenItems = data.services
    .filter(s => s.is_active && (selectedQtys[s.id] || 0) > 0)
    .map(s => ({ id: s.id, name: s.name, qty: selectedQtys[s.id], subtotal: selectedQtys[s.id] * s.price_adult }));

  const totalTickets = chosenItems.reduce((sum, item) => sum + item.qty, 0);
  const totalEst = chosenItems.reduce((sum, item) => sum + item.subtotal, 0);
  const summaryText = chosenItems.map(i => `${i.name}: ${i.qty} vé`).join(' · ');

  resBox.innerHTML = `
    <div style="margin-top:20px;padding-top:18px;border-top:1px solid #E3E8EC">
      <div class="row" style="justify-content:space-between;margin-bottom:12px">
        <h3 style="margin:0">Danh sách gói dịch vụ ngày ${data.date_display} · ${data.day_label}</h3>
        <span class="sm" style="font-style:normal">Chọn số lượng vé trực tiếp trên từng gói dịch vụ</span>
      </div>
      <div class="g3">${cardsHtml}</div>
      <div class="bar">
        ${totalTickets === 0
          ? '<span class="er">Vui lòng chọn số lượng vé cho ít nhất 1 gói dịch vụ</span>'
          : `<span>Đã chọn <b>${totalTickets} vé</b> (${summaryText}) · Tạm tính: <b style="color:var(--red)">${fm(totalEst)}</b></span>`
        }
        <button type="button" class="btn p" onclick="proceedToBooking()" ${totalTickets > 0 ? '' : 'disabled'}>Tiếp tục đặt vé →</button>
      </div>
    </div>`;
}

function proceedToBooking() {
  const dateVal = $('#fd').value;
  const itemsParam = Object.entries(selectedQtys)
    .filter(([, q]) => q > 0)
    .map(([id, q]) => `${id}:${q}`)
    .join(',');

  const params = new URLSearchParams({
    date: dateVal,
    items: itemsParam,
  });
  window.location.href = `/dat-ve/?${params.toString()}`;
}

// ==========================================================================
// 3. MODAL LỊCH VÉ & THƯ VIỆN ẢNH
// ==========================================================================
function openModal(html) {
  closeModal();
  const ov = document.createElement('div');
  ov.className = 'ov';
  ov.id = 'ov';
  ov.innerHTML = `<div class="md">${html}</div>`;
  ov.onclick = e => { if (e.target === ov) closeModal(); };
  document.body.appendChild(ov);
}

function closeModal() {
  const ov = $('#ov');
  if (ov) ov.remove();
}

async function openCalendarModal(serviceId) {
  openModal('<p>Đang tải lịch ngày còn vé...</p>');
  const resp = await fetch(`/api/calendar/${serviceId}/`);
  const data = await resp.json();

  const headerHtml = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']
    .map(d => `<div>${d}</div>`)
    .join('');

  const gridHtml = data.days.map(d => {
    if (d.is_past) {
      return `
        <button type="button" class="dc past" disabled aria-label="Ngày ${d.short_date} đã trôi qua">
          <b>${d.short_date}</b>
          <small>${d.weekday}</small>
        </button>`;
    }
    const hasTickets = d.available > 0;
    return `
      <button type="button" class="dc ${hasTickets ? '' : 'no'}" ${hasTickets ? `onclick="pickDateFromCal('${d.date}')"` : 'disabled'}>
        <b>${d.short_date}</b>
        <small>${d.weekday}</small>
        <span>${hasTickets ? 'Còn ' + d.available : 'Hết'}</span>
      </button>`;
  }).join('');

  openModal(`
    <h3>Lịch ngày còn vé – ${data.service_name}</h3>
    <p class="sm" style="font-style:normal">Chỉ hiển thị số lượng vé khả dụng từ ngày hôm nay trở đi.</p>
    <div class="dg-head">${headerHtml}</div>
    <div class="dg">${gridHtml}</div>
    <button type="button" class="btn" onclick="closeModal()">Đóng</button>
  `);
}

function pickDateFromCal(isoDate) {
  closeModal();
  const fd = $('#fd');
  if (fd) {
    fd.value = isoDate;
    updateDayLabel(isoDate);
    findTickets();
  }
}

function previewGallery(title, desc) {
  openModal(`
    <h3>${title}</h3>
    <figure class="ph" style="height:240px"><span>📷 ${desc}</span></figure>
    <p class="sm" style="font-style:normal;margin-top:12px">${desc} – Bang Onsen Spa & Resort Quảng Trị.</p>
    <div class="row" style="justify-content:flex-end;margin-top:12px">
      <a class="btn p sm" href="#flt" onclick="closeModal()">Đặt vé trải nghiệm</a>
      <button type="button" class="btn sm" onclick="closeModal()">Đóng</button>
    </div>
  `);
}

function toggleCompareTable(btn) {
  const body = $('#cmp-body');
  if (!body) return;
  body.hidden = !body.hidden;
  btn.querySelector('span:last-child').textContent = body.hidden ? 'Mở bảng so sánh ▼' : 'Thu gọn ▲';
}

// ==========================================================================
// 4. HIỆU ỨNG CHUYỂN ĐỘNG CHẠY NỐI TIẾP SƠ ĐỒ 3 BƯỚC ĐẶT VÉ
// ==========================================================================
const FLOW_STEPS_DATA = [
  {
    badge: 'Bước 1 / 3',
    desc: 'Chọn ngày sử dụng dịch vụ, kiểm tra số vé trống theo thời gian thực và chọn cùng lúc 1 hoặc nhiều gói Onsen phù hợp.',
  },
  {
    badge: 'Bước 2 / 3',
    desc: 'Phân bổ vé theo chiều cao, nhập số CCCD Quảng Trị (044, 045) nhận ưu đãi tự động, áp mã voucher và thanh toán trực tuyến.',
  },
  {
    badge: 'Bước 3 / 3',
    desc: 'Nhận ngay vé điện tử kèm mã QR qua email sau 2 phút. Đưa mã QR quét tại cổng check-in mà không cần xếp hàng chờ đợi.',
  },
];

let currentFlowStep = 0;
let flowTimer = null;

function renderFlowStep(stepIndex, animateBeam = false) {
  const pills = document.querySelectorAll('.flow-pill');
  const conns = document.querySelectorAll('.flow-conn');
  if (!pills.length) return;

  currentFlowStep = stepIndex;
  pills.forEach((p, idx) => {
    p.classList.toggle('is-active', idx === stepIndex);
  });

  conns.forEach((c, idx) => {
    c.classList.remove('is-running', 'is-done');
    void c.offsetWidth;
    if (idx < stepIndex) {
      if (animateBeam && idx === stepIndex - 1) {
        c.classList.add('is-running');
      } else {
        c.classList.add('is-done');
      }
    }
  });

  const badgeEl = $('#fd-badge');
  const descEl = $('#fd-desc');
  if (badgeEl && descEl && FLOW_STEPS_DATA[stepIndex]) {
    badgeEl.textContent = FLOW_STEPS_DATA[stepIndex].badge;
    descEl.textContent = FLOW_STEPS_DATA[stepIndex].desc;
  }
}

function activateFlowStep(stepIndex) {
  renderFlowStep(stepIndex, false);
  if (flowTimer) clearInterval(flowTimer);
  flowTimer = setInterval(() => {
    const next = (currentFlowStep + 1) % FLOW_STEPS_DATA.length;
    renderFlowStep(next, next > 0);
  }, 3200);
}