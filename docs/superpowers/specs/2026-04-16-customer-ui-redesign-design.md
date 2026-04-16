# Customer UI Redesign: High-end Dark SPA Style

## Overview

Redesign the customer-facing page (`frontend/customer.html`) from the current WeChat-green functional style to a premium dark theme with gold accents, reflecting an upscale in-store massage brand identity. Rename all references from "到家按摩" to "到店按摩".

## Scope

- **Only** `frontend/customer.html` — no other pages touched
- Visual redesign only — no functional/logic changes
- Keep: Vue 3, Vant 4, WeChat JS-SDK, OAuth, all existing business logic

## Brand Updates

| Location | Old | New |
|----------|-----|-----|
| Page title (`<title>`) | 到家按摩 | 到店按摩 |
| Header brand name | 到家按摩 | 到店按摩 |
| Header subtitle | 专业技师 上门服务 | 匠心技艺 到店体验 |
| Any other "到家" references | 到家 | 到店 |

## Color System

```
Primary Background:   #1a1a2e   (deep blue-black)
Card Background:      #252540   (dark gray-purple)
Card Hover/Active:    #2d2d4a   (slightly lighter)
Gold Accent:          #c9a96e   (matte gold)
Gold Light:           #e0c48a   (lighter gold for hover states)

Text - Title:         #ffffff
Text - Body:          #b0b0c0
Text - Secondary:     #787890
Text - Price:         #c9a96e   (gold, not red)

Border:               #3a3a5c   (subtle dark border)
Input Background:     #1e1e36

Status Colors (desaturated for dark bg):
  - Success/Completed:  #4caf88
  - Warning/Pending:    #d4a03c
  - Danger/Unpaid:      #c0564a
  - Info/Accepted:      #5b8dd9
```

## Component Designs

### 1. Page Header (Home Tab)

- Gradient: `#1a1a2e` → `#252540` (subtle, not aggressive)
- Brand name: 22px, bold, gold (#c9a96e)
- Subtitle: 13px, #b0b0c0
- Padding: 24px 16px 36px (generous top spacing)
- Optional: thin gold line separator at bottom

### 2. Product Cards (Home Tab)

**Layout change:** Left-right → top-bottom (image above, text below)

- Two-column grid with 10px gap
- Card: #252540 background, 10px border-radius, subtle shadow
- Image: full width, 16:9 aspect ratio, object-fit cover
- Title: 14px, white, bold, single-line ellipsis
- Price: gold (#c9a96e), 16px, bold, ¥ prefix small
- Original price: #787890, line-through
- Duration tag: gold border pill, gold text, small
- Sales: #787890, 11px
- Hover/active: slight scale or border highlight

### 3. Product Detail Popup

- Background: #1a1a2e
- Image: full width, max 300px height
- Title: 20px, white, bold
- Price: gold, 26px, bold
- Original price: #787890, line-through
- Sales + duration: #787890, right-aligned
- Description: #b0b0c0, 14px, line-height 1.8
- Detail images: full width, 8px border-radius
- Bottom CTA button: gold background (#c9a96e), dark text, round, bold
  - Text: "立即下单 · ¥XX"

### 4. Booking Popup

- Background: #252540
- Title: white, bold
- Input fields: #1e1e36 background, #3a3a5c border, white text
- Date selector: selected state = gold border + gold text
- Time slot selector: same gold accent for selected state
- CTA button: gold background, dark text

### 5. Order Cards (Order List)

- Background: #252540
- Title: white, bold
- Status badge: desaturated status colors, pill shape
- Phone + time: #b0b0c0
- Price: gold

### 6. Order Detail

- Header bar: #252540 background, white text
- Back arrow: gold color
- "订单详情" title: white, bold
- Status badge: same desaturated style
- Product card (clickable): gold left border (4px), #252540 bg, subtle gold shadow on hover
- Appointment info: #252540 section, label in white, value in #b0b0c0

### 7. Chat Area

- Chat background: #12122a (slightly darker than main bg)
- User bubble: #3a5a3a (muted green on dark)
- Other bubble: #2d2d4a (dark card color)
- Bubble text: #e0e0e0
- Role label: #787890
- Input bar: #252540 background
- Input field: #1e1e36 bg, #3a3a5c border, white text
- Send button: gold background, dark text

### 8. Messages Tab

- Same card style as order list
- Order ID in white, status in #787890
- Phone + time in #b0b0c0

### 9. Profile Tab ("我的")

- Background: #1a1a2e
- Simple centered layout
- User info in #252540 card with gold accent border-left
- Vant cell group: dark theme override (dark bg, light text)

### 10. Tabbar

- Background: #252540
- Active icon/label: gold (#c9a96e)
- Inactive icon/label: #787890
- Border-top: #3a3a5c

### 11. Loading Mask

- Background: #1a1a2e
- Vant loading spinner: gold color

## Vant Theme Overrides (CSS)

Apply dark theme globally to all Vant components used:
- `van-tabbar`, `van-tabbar-item`
- `van-popup`
- `van-button`
- `van-cell-group`, `van-cell`
- `van-loading`

Override via CSS custom properties and targeted selectors.

## Implementation Notes

- All styles in the existing `<style>` block — no new CSS files
- Use CSS custom properties at `:root` level for the color system (easy future changes)
- Inline styles in template should be migrated to CSS classes where practical
- No JavaScript/logic changes needed
- Test in WeChat in-app browser (primary target)
