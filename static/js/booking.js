const $ = s => document.querySelector(s);
const fm = n => Math.round(n).toLocaleString('vi-VN') + ' ₫';

// Lưu số lượng vé khách chọn riêng cho từng gói: { serviceId: quantity }
let selectedQtys = {};
let hasSearched = false;

window.addEventListener('DOMContentLoaded', () => {
  const pl = $('#pl');
  if (pl) {
    setTimeout(() => pl.classList.add('x'), 750);
    setTimeout(() => pl.remove(), 1250);
  }

  const io = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('in');
        io.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('main.tc .sec, main.tc .cd, main.tc .step-card, main.tc .eco-card, main.tc .gal-item, main.tc .faq-item')
    .forEach(el => {
      el.classList.add('rv');
      io.observe(el);
    });
});

let ticking = false;
window.addEventListener('scroll', () => {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(() => {
    const header = $('header.h');
    if (header) header.classList.toggle('s', window.scrollY > 12);

    const bg = $('.hbg');
    if (bg && window.scrollY < 680) {
      bg.style.transform = `translate3d(0, ${window.scrollY * 0.25}px, 0)`;
    }
    const heroInner = $('.hero > .w');
    if (heroInner && window.scrollY < 680) {
      heroInner.style.transform = `translate3d(0, ${window.scrollY * 0.08}px, 0)`;
    }
    ticking = false;
  });
}, { passive: true });

function updateDayLabel(dateStr) {
  const badge = $('#fday-badge');
  if (!badge || !dateStr) return;
  const day = new Date(dateStr).getDay();
  badge.textContent = (day === 0 || day === 6) ? 'Cuối tuần (T7–CN)' : 'Đầu tuần (T2–T6)';
  if (hasSearched) findTickets(true);
}

// Khi bấm "Đặt vé gói này" ở khu quảng bá bên dưới
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

    if (!instant) await new Promise(r => setTimeout(r, 300));

    // Giới hạn lại số lượng đã chọn nếu vượt quá vé trống hoặc gói đang tạm ngừng
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
  const nextVal = Math.max(0, Math.min(svc.available, current + delta));
  selectedQtys[serviceId] = nextVal;
  renderFilteredResults();
}

function renderFilteredResults() {
  const data = window._lastSearchData;
  const resBox = $('#res');
  if (!data || !resBox) return;

  const cardsHtml = data.services.map(s => {
    const qty = selectedQtys[s.id] || 0;
    const isSel = s.is_active && qty > 0;

    // Trạng thái badge góc phải
    let statusBadge = `<span class="bd ok">Còn ${s.available} vé</span>`;
    if (!s.is_active) {
      statusBadge = '<span class="bd no">Tạm ngừng</span>';
    } else if (s.available <= 0) {
      statusBadge = '<span class="bd no">Hết vé</span>';
    }

    // Khối điều khiển riêng từng gói
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
        <figure class="ph" style="height:135px"><span>📷 Ảnh gói dịch vụ ${s.name}</span></figure>
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

  // Tính tổng số vé khách đã chọn across các gói
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
  window.location.href = `/khai-bao-thong-tin/?${params.toString()}`;
}

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
  const gridHtml = data.days.map(d => `
    <button type="button" class="dc ${d.available ? '' : 'no'}" ${d.available ? `onclick="pickDateFromCal('${d.date}')"` : 'disabled'}>
      <b>${d.short_date}</b>
      <small>${d.weekday}</small>
      <span>${d.available ? 'Còn ' + d.available : 'Hết'}</span>
    </button>`).join('');

  openModal(`
    <h3>Lịch ngày còn vé – ${data.service_name}</h3>
    <p class="sm" style="font-style:normal">Chọn một ngày còn vé để làm mới kết quả tìm kiếm.</p>
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