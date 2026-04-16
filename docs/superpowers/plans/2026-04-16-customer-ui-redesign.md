# Customer UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform `frontend/customer.html` from WeChat-green functional style to a premium dark theme with gold accents, and rebrand "到家按摩" to "到店按摩".

**Architecture:** Single-file CSS + HTML template overhaul. All styles remain in the `<style>` block. CSS custom properties define the color system. Inline styles updated to match dark theme. Zero JavaScript changes.

**Tech Stack:** Vue 3, Vant 4, CSS custom properties, existing HTML structure

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `frontend/customer.html` | Modify | All changes in this single file |

The file has 3 sections — only 2 are touched:
1. **`<style>` block** (lines 11–36) — full replacement with dark theme CSS
2. **HTML `<body>` template** (lines 38–213) — inline style color updates + product grid layout change
3. **`<script>` block** (lines 215+) — **not touched**

---

### Task 1: Replace `<style>` block with dark theme CSS

**Files:**
- Modify: `frontend/customer.html:11-36` (the `<style>` block)

This task replaces the entire `<style>` block content. The new CSS includes:
- `:root` CSS custom properties for the full color system
- Dark theme overrides for `body`, `.loading-mask`
- New `.good-card` grid layout (was flex left-right, now vertical card for 2-col grid)
- Dark `.order-card`, `.order-status`, `.chat-*` styles
- Vant component overrides (tabbar, popup, button, cell, loading)

- [ ] **Step 1: Replace `<style>` block (lines 11–36) with the following**

Replace everything between `<style>` and `</style>` (inclusive of those tags) with:

```html
<style>
:root {
  --bg-primary: #1a1a2e;
  --bg-card: #252540;
  --bg-card-hover: #2d2d4a;
  --bg-input: #1e1e36;
  --bg-chat: #12122a;
  --gold: #c9a96e;
  --gold-light: #e0c48a;
  --text-title: #ffffff;
  --text-body: #b0b0c0;
  --text-secondary: #787890;
  --border: #3a3a5c;
  --status-success: #4caf88;
  --status-warning: #d4a03c;
  --status-danger: #c0564a;
  --status-info: #5b8dd9;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg-primary); font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: var(--text-body); }

/* Loading */
.loading-mask { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: var(--bg-primary); display: flex; align-items: center; justify-content: center; z-index: 9999; }

/* Product Grid */
.good-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 10px; }
.good-card { background: var(--bg-card); border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,.25); cursor: pointer; transition: transform .15s, box-shadow .15s; }
.good-card:active { transform: scale(.97); box-shadow: 0 1px 4px rgba(0,0,0,.35); }
.good-card img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }
.good-card-info { padding: 10px; }
.good-card-title { font-size: 14px; font-weight: 600; color: var(--text-title); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.good-card-bottom { display: flex; align-items: baseline; justify-content: space-between; margin-top: 6px; }
.good-card-price { color: var(--gold); font-size: 16px; font-weight: 700; }
.good-card-price .unit { font-size: 11px; }
.good-card-original { font-size: 11px; color: var(--text-secondary); text-decoration: line-through; margin-left: 4px; }
.good-card-tag { border: 1px solid var(--gold); color: var(--gold); font-size: 10px; padding: 1px 6px; border-radius: 10px; }
.good-card-meta { font-size: 11px; color: var(--text-secondary); margin-top: 4px; }

/* Order */
.order-card { background: var(--bg-card); margin: 10px; border-radius: 10px; padding: 14px; box-shadow: 0 2px 8px rgba(0,0,0,.25); cursor: pointer; }
.order-status { display: inline-block; font-size: 12px; padding: 2px 10px; border-radius: 10px; color: #fff; }

/* Chat */
.chat-wrap { display: flex; flex-direction: column; height: 100vh; background: var(--bg-chat); }
.chat-messages { flex: 1; overflow-y: auto; padding: 10px; }
.bubble { max-width: 70%; padding: 10px 14px; border-radius: 12px; margin-bottom: 10px; font-size: 14px; line-height: 1.5; word-break: break-all; color: #e0e0e0; }
.bubble-left { background: var(--bg-card-hover); align-self: flex-start; border-bottom-left-radius: 4px; }
.bubble-right { background: #3a5a3a; align-self: flex-end; border-bottom-right-radius: 4px; }
.bubble-role { font-size: 11px; color: var(--text-secondary); margin-bottom: 2px; }
.chat-input-bar { display: flex; padding: 8px 10px; background: var(--bg-card); border-top: 1px solid var(--border); }
.chat-input-bar input { flex: 1; border: 1px solid var(--border); border-radius: 20px; padding: 8px 14px; font-size: 14px; outline: none; background: var(--bg-input); color: var(--text-title); }
.chat-input-bar input::placeholder { color: var(--text-secondary); }
.chat-input-bar button { margin-left: 8px; border: none; background: var(--gold); color: var(--bg-primary); border-radius: 20px; padding: 0 20px; font-size: 14px; font-weight: 600; }

/* Detail popup */
.detail-popup { background: var(--bg-primary); }
.detail-popup .detail-title { font-size: 20px; font-weight: 700; color: var(--text-title); }
.detail-popup .detail-price { color: var(--gold); font-size: 26px; font-weight: 700; }
.detail-popup .detail-original { font-size: 14px; color: var(--text-secondary); text-decoration: line-through; }
.detail-popup .detail-meta { font-size: 13px; color: var(--text-secondary); }
.detail-popup .detail-desc { font-size: 14px; color: var(--text-body); line-height: 1.8; white-space: pre-wrap; }
.detail-popup .detail-img { width: 100%; border-radius: 8px; }
.detail-cta { position: fixed; bottom: 0; left: 0; right: 0; padding: 12px 16px; background: var(--bg-primary); border-top: 1px solid var(--border); }

/* Booking popup */
.book-popup { background: var(--bg-card); }
.book-popup input[type="tel"] { width: 100%; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; font-size: 14px; outline: none; background: var(--bg-input); color: var(--text-title); }
.book-popup input::placeholder { color: var(--text-secondary); }

/* Order detail header */
.detail-header { background: var(--bg-card); padding: 10px 14px; border-bottom: 1px solid var(--border); display: flex; align-items: center; }
.detail-header .back-arrow { font-size: 20px; cursor: pointer; margin-right: 10px; color: var(--gold); }

/* Product card in order detail (clickable) */
.order-good-card { background: var(--bg-card); padding: 12px 14px; border-bottom: 1px solid var(--border); display: flex; gap: 12px; cursor: pointer; border-left: 4px solid var(--gold); }
.order-good-card:active { background: var(--bg-card-hover); }

/* Appointment info */
.appt-info { background: var(--bg-card); padding: 12px 14px; border-bottom: 1px solid var(--border); }
.appt-info .label { color: var(--text-title); }
.appt-info .value { color: var(--text-body); }

/* Profile */
.profile-section { padding: 30px 16px; }

/* Vant dark overrides */
.van-tabbar { background: var(--bg-card) !important; border-top: 1px solid var(--border) !important; }
.van-tabbar-item--active { color: var(--gold) !important; }
.van-tabbar-item { color: var(--text-secondary) !important; background: transparent !important; }
.van-popup--bottom { background: var(--bg-primary) !important; }
.van-button--primary { background: var(--gold) !important; border-color: var(--gold) !important; color: var(--bg-primary) !important; font-weight: 600 !important; }
.van-cell-group--inset { background: var(--bg-card) !important; margin: 0 !important; border-radius: 10px !important; overflow: hidden; }
.van-cell { background: var(--bg-card) !important; color: var(--text-body) !important; }
.van-cell__title { color: var(--text-body) !important; }
.van-cell__value { color: var(--text-title) !important; }
.van-cell::after { border-color: var(--border) !important; }
.van-loading__text { color: var(--gold) !important; }
.van-loading__spinner .van-loading__dot { background: var(--gold) !important; }
</style>
```

- [ ] **Step 2: Verify no syntax errors**

Check that the `<style>` block is properly closed with `</style>` and the rest of the HTML file is intact.

- [ ] **Step 3: Commit**

```bash
git add frontend/customer.html
git commit -m "style: dark theme CSS foundation with gold accent color system"
```

---

### Task 2: Update home tab — header + product grid layout

**Files:**
- Modify: `frontend/customer.html:54-77` (home tab section)

Changes:
1. Header: rebrand text + dark gradient background
2. Product cards: change from flex layout to 2-column grid (`good-grid` wrapper + `good-card` vertical cards)

- [ ] **Step 1: Replace the home tab section (lines 54–77)**

Replace the entire `<div v-show="activeTab === 0" ...>` block (from line 54 to line 77, the closing `</div>`) with:

```html
  <!-- 首页：商品列表 -->
  <div v-show="activeTab === 0" style="padding-bottom:60px;">
    <div style="background:linear-gradient(180deg,#1a1a2e,#252540);padding:24px 16px 36px;">
      <div style="font-size:22px;font-weight:700;color:#c9a96e;">到店按摩</div>
      <div style="font-size:13px;color:#b0b0c0;margin-top:4px;">匠心技艺 到店体验</div>
      <div style="height:1px;background:linear-gradient(90deg,transparent,#c9a96e,transparent);margin-top:16px;opacity:.4;"></div>
    </div>
    <div class="good-grid">
      <div v-for="g in goods" :key="g.id" class="good-card" @click="openDetail(g)">
        <img :src="g.img_url || 'https://via.placeholder.com/300x170/252540/787890?text=No+Image'" loading="lazy">
        <div class="good-card-info">
          <div class="good-card-title">{{ g.title }}</div>
          <div class="good-card-bottom">
            <div>
              <span class="good-card-price"><span class="unit">¥</span>{{ (g.price/100).toFixed(0) }}</span>
              <span class="good-card-original" v-if="g.original_price">¥{{ (g.original_price/100).toFixed(0) }}</span>
            </div>
            <span class="good-card-tag">{{ g.duration }}分钟</span>
          </div>
          <div class="good-card-meta">已售 {{ g.sales || 0 }}</div>
        </div>
      </div>
    </div>
  </div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/customer.html
git commit -m "style: dark home tab header + two-column product grid"
```

---

### Task 3: Update order list + order detail + messages tab HTML

**Files:**
- Modify: `frontend/customer.html:79-145` (order tab + messages tab)

Changes:
1. Order list cards: dark colors, gold price
2. Order detail header: dark background, gold back arrow
3. Order detail product card: gold left border, dark bg
4. Appointment info: dark theme labels
5. Messages tab: dark theme cards

- [ ] **Step 1: Replace the order tab + messages tab section (lines 79–145)**

Replace from `<!-- 订单Tab：列表 / 详情切换 -->` through the end of the messages tab `</div>` (line 145) with:

```html
  <!-- 订单Tab：列表 / 详情切换 -->
  <div v-show="activeTab === 1">
    <!-- 订单列表视图 -->
    <div v-if="!currentOrder" style="padding-bottom:60px;">
      <div v-if="!orders.length" style="text-align:center;padding:60px 0;color:#787890;">暂无订单</div>
      <div v-for="o in orders" :key="o.id" class="order-card" @click="openOrderDetail(o)">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="font-weight:600;color:#ffffff;">{{ o.good_title || '商品' }}</span>
          <span class="order-status" :style="{background: statusColor(o.status)}">{{ statusText(o.status) }}</span>
        </div>
        <div style="font-size:13px;color:#b0b0c0;margin-top:8px;">
          {{ o.phone }} · {{ o.appointment_time }}
        </div>
        <div style="font-size:15px;color:#c9a96e;margin-top:6px;font-weight:600;">¥{{ (o.total_fee/100).toFixed(0) }}</div>
      </div>
    </div>
    <!-- 订单详情视图 -->
    <div v-else class="chat-wrap">
      <div class="detail-header">
        <span class="back-arrow" @click="currentOrder=null">‹</span>
        <span style="font-weight:600;color:#ffffff;">订单详情</span>
        <span class="order-status" :style="{background: statusColor(currentOrder.status),marginLeft:'auto'}">{{ statusText(currentOrder.status) }}</span>
      </div>
      <!-- 商品信息（可点击查看详情） -->
      <div class="order-good-card" @click="viewOrderGood(currentOrder)">
        <img v-if="currentOrder.good_img_url" :src="currentOrder.good_img_url" style="width:70px;height:70px;border-radius:8px;object-fit:cover;flex-shrink:0;">
        <div style="flex:1;min-width:0;">
          <div style="font-size:15px;font-weight:600;color:#ffffff;">{{ currentOrder.good_title || '商品' }}</div>
          <div style="font-size:13px;color:#787890;margin-top:2px;">{{ currentOrder.good_duration }}分钟</div>
          <div style="display:flex;align-items:baseline;gap:6px;margin-top:4px;">
            <span style="color:#c9a96e;font-size:16px;font-weight:700;">¥{{ (currentOrder.total_fee/100).toFixed(0) }}</span>
          </div>
        </div>
        <span style="color:#c9a96e;align-self:center;font-size:14px;">›</span>
      </div>
      <!-- 预约信息 -->
      <div class="appt-info">
        <div style="font-size:13px;"><span class="label">手机号：</span><span class="value">{{ currentOrder.phone }}</span></div>
        <div style="font-size:13px;margin-top:4px;"><span class="label">预约时间：</span><span class="value">{{ currentOrder.appointment_time }}</span></div>
      </div>
      <div class="chat-messages" ref="chatBox">
        <div v-if="!messages.length" style="text-align:center;padding:40px 0;color:#787890;font-size:13px;">暂无消息</div>
        <div v-for="m in messages" :key="m.id"
             :class="['bubble', m.sender_id === userId ? 'bubble-right' : 'bubble-left']"
             style="display:flex;flex-direction:column;">
          <div class="bubble-role">{{ roleLabel(m.sender_role) }}</div>
          <div>{{ m.content }}</div>
        </div>
      </div>
      <div class="chat-input-bar">
        <input v-model="msgInput" placeholder="输入消息..." @keyup.enter="sendMessage">
        <button @click="sendMessage">发送</button>
      </div>
    </div>
  </div>

  <!-- 消息Tab：独立消息入口 -->
  <div v-show="activeTab === 2" style="padding-bottom:60px;">
    <div v-if="!orders.length" style="text-align:center;padding:60px 0;color:#787890;">暂无消息</div>
    <div v-for="o in orders" :key="'msg-'+o.id" class="order-card" @click="openOrderDetail(o); activeTab=1">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="font-weight:600;color:#ffffff;">订单 {{ o.id.slice(-8) }}</span>
        <span style="font-size:12px;color:#787890;">{{ statusText(o.status) }}</span>
      </div>
      <div style="font-size:13px;color:#b0b0c0;margin-top:6px;">{{ o.phone }} · {{ o.appointment_time }}</div>
    </div>
  </div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/customer.html
git commit -m "style: dark theme order list, order detail, chat area, messages tab"
```

---

### Task 4: Update profile tab HTML

**Files:**
- Modify: `frontend/customer.html` — the "我的" section

- [ ] **Step 1: Replace the profile section**

Replace the `<!-- 我的 -->` block with:

```html
  <!-- 我的 -->
  <div v-show="activeTab === 3" class="profile-section">
    <van-cell-group inset>
      <van-cell title="用户" :value="user.nickname || '未设置'" />
      <van-cell title="角色" :value="user.role" />
    </van-cell-group>
  </div>
```

Note: The content is almost identical — the dark theme comes from the Vant CSS overrides in Task 1. This step just ensures the class is applied.

- [ ] **Step 2: Commit**

```bash
git add frontend/customer.html
git commit -m "style: dark theme profile tab"
```

---

### Task 5: Update product detail + booking popups

**Files:**
- Modify: `frontend/customer.html` — the two `van-popup` blocks

Changes:
1. Product detail: dark bg, gold price, gold CTA button
2. Booking: dark bg, dark input fields, gold selection states

- [ ] **Step 1: Replace the product detail popup**

Replace the `<!-- 商品详情弹窗 -->` `van-popup` block with:

```html
  <!-- 商品详情弹窗 -->
  <van-popup v-model:show="showDetail" position="bottom" round :style="{ minHeight: '70%' }">
    <div class="detail-popup" style="max-height:85vh;overflow-y:auto;">
      <div v-if="detailGood" style="padding-bottom:80px;">
        <img :src="detailGood.img_url" style="width:100%;max-height:300px;object-fit:cover;">
        <div style="padding:16px;">
          <div class="detail-title">{{ detailGood.title }}</div>
          <div style="display:flex;align-items:baseline;gap:8px;margin-top:8px;">
            <span class="detail-price">¥{{ (detailGood.price/100).toFixed(0) }}</span>
            <span v-if="detailGood.original_price" class="detail-original">¥{{ (detailGood.original_price/100).toFixed(0) }}</span>
            <span class="detail-meta" style="margin-left:auto;">已售 {{ detailGood.sales || 0 }} · {{ detailGood.duration }}分钟</span>
          </div>
          <div class="detail-desc" style="margin-top:16px;">{{ detailGood.description }}</div>
          <div v-if="detailImages.length" style="margin-top:16px;">
            <div v-for="(img, i) in detailImages" :key="i" style="margin-bottom:8px;">
              <img :src="img" class="detail-img" @click="previewImage(i)">
            </div>
          </div>
        </div>
        <div class="detail-cta">
          <van-button type="primary" block round @click="showDetail=false;openBook(detailGood)">立即下单 · ¥{{ (detailGood.price/100).toFixed(0) }}</van-button>
        </div>
      </div>
    </div>
  </van-popup>
```

- [ ] **Step 2: Replace the booking popup**

Replace the `<!-- 下单弹窗 -->` `van-popup` block with:

```html
  <!-- 下单弹窗 -->
  <van-popup v-model:show="showBook" position="bottom" round :style="{ minHeight: '50%' }">
    <div class="book-popup" style="padding:20px;">
      <div style="font-size:16px;font-weight:600;margin-bottom:16px;color:#ffffff;">下单 {{ bookGood?.title }}</div>
      <div style="margin-bottom:12px;">
        <div style="font-size:13px;color:#b0b0c0;margin-bottom:4px;">手机号 *</div>
        <input v-model="bookForm.phone" type="tel" placeholder="请输入手机号">
      </div>
      <div style="margin-bottom:12px;">
        <div style="font-size:13px;color:#b0b0c0;margin-bottom:6px;">选择日期 *</div>
        <div style="display:flex;gap:8px;">
          <div v-for="d in dateOptions" :key="d.value" @click="bookForm.date=d.value"
               :style="{flex:1,textAlign:'center',padding:'10px 0',borderRadius:8,border: bookForm.date===d.value?'2px solid #c9a96e':'1px solid #3a3a5c',color:bookForm.date===d.value?'#c9a96e':'#b0b0c0',fontWeight:bookForm.date===d.value?600:400,fontSize:13,cursor:'pointer',background:bookForm.date===d.value?'rgba(201,169,110,.1)':'transparent'}">
            {{ d.label }}
          </div>
        </div>
      </div>
      <div style="margin-bottom:16px;">
        <div style="font-size:13px;color:#b0b0c0;margin-bottom:6px;">选择时段 *</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;">
          <div v-for="s in timeSlots" :key="s" @click="bookForm.timeSlot=s"
               :style="{padding:'8px 14px',borderRadius:8,border:bookForm.timeSlot===s?'2px solid #c9a96e':'1px solid #3a3a5c',color:bookForm.timeSlot===s?'#c9a96e':'#b0b0c0',fontWeight:bookForm.timeSlot===s?600:400,fontSize:13,cursor:'pointer',background:bookForm.timeSlot===s?'rgba(201,169,110,.1)':'transparent'}">
            {{ s }}
          </div>
        </div>
      </div>
      <van-button type="primary" block round @click="submitOrder" :loading="submitting" :disabled="!bookForm.phone || !bookForm.timeSlot">
        确认下单 · ¥{{ ((bookGood?.price||0)/100).toFixed(0) }}
      </van-button>
    </div>
  </van-popup>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/customer.html
git commit -m "style: dark theme product detail and booking popups"
```

---

### Task 6: Update page title + loading mask + final brand replacement

**Files:**
- Modify: `frontend/customer.html:6` (title), `41-43` (loading mask), scan for any remaining "到家" references

- [ ] **Step 1: Update `<title>` tag**

Change line 6 from:
```html
<title>到家按摩</title>
```
to:
```html
<title>到店按摩</title>
```

- [ ] **Step 2: Update loading mask text**

The loading mask uses `正在登录...` — no brand reference, but verify the dark background from Task 1 CSS applies correctly. No HTML change needed.

- [ ] **Step 3: Scan for any remaining "到家" references**

Search the entire file for "到家" and replace with "到店". The main ones are the `<title>` (step 1) and the header (handled in Task 2). Verify no others exist.

- [ ] **Step 4: Commit**

```bash
git add frontend/customer.html
git commit -m "style: rebrand 到家按摩 → 到店按摩 in page title"
```

---

## Self-Review

**Spec coverage check:**
1. Color system → Task 1 (CSS custom properties)
2. Page header → Task 2
3. Product cards grid → Task 2
4. Product detail popup → Task 5
5. Booking popup → Task 5
6. Order cards → Task 3
7. Order detail → Task 3
8. Chat area → Task 1 (CSS) + Task 3 (HTML)
9. Messages tab → Task 3
10. Profile tab → Task 4
11. Tabbar → Task 1 (Vant overrides)
12. Loading mask → Task 1 (CSS)
13. Brand replacement → Tasks 2, 6

**No placeholders found** — all steps contain complete code.

**Type consistency** — CSS class names defined in Task 1 (`good-grid`, `good-card`, `good-card-info`, `good-card-title`, `good-card-bottom`, `good-card-price`, `good-card-original`, `good-card-tag`, `good-card-meta`, `detail-header`, `back-arrow`, `order-good-card`, `appt-info`, `detail-popup`, `detail-title`, `detail-price`, `detail-original`, `detail-meta`, `detail-desc`, `detail-img`, `detail-cta`, `book-popup`, `profile-section`) are consistently used in Tasks 2–5.
