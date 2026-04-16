# Unified Merchant Messaging — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Messages tab with a unified merchant chat view that merges all order messages, plus one new backend endpoint.

**Architecture:** Add `GET /chat/all` backend endpoint to merge all order messages. Frontend adds new refs/functions and rewrites the Messages tab template. Existing order-detail chat untouched.

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3, Vant 4

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `backend/main.py` | Modify | Add `GET /chat/all` endpoint after existing chat endpoints |
| `frontend/customer.html` | Modify | Rewrite Messages tab template, add JS refs/functions, update return, update polling |

---

### Task 1: Add `GET /chat/all` backend endpoint

**Files:**
- Modify: `backend/main.py:497` (insert after existing `send_chat` endpoint, before `# 用户信息` section)

- [ ] **Step 1: Add the new endpoint**

Insert the following code between the `send_chat` endpoint (ends at line 495) and the `# 用户信息` comment (line 498):

```python


@app.get("/chat/all", response_model=list[ChatLogOut])
async def get_all_chat(
    after_id: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """客户：获取所有订单的合并聊天记录"""
    order_ids = select(Order.id).where(Order.customer_id == user.id)
    result = await db.execute(
        select(ChatLog)
        .where(ChatLog.order_id.in_(order_ids), ChatLog.id > after_id)
        .order_by(ChatLog.create_time)
    )
    return result.scalars().all()
```

- [ ] **Step 2: Verify the endpoint registers correctly**

Run: `cd /d/Bob/IdeaProjects/personal/wx-test/backend && python -c "from main import app; routes = [r.path for r in app.routes if hasattr(r,'path')]; print('/chat/all' in routes)"`

Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: add GET /chat/all endpoint for unified messaging"
```

---

### Task 2: Add new JS refs and functions for unified chat

**Files:**
- Modify: `frontend/customer.html` — JS `setup()` function

This task adds the new reactive state and functions. No template changes yet.

- [ ] **Step 1: Add new refs after existing refs (after line 364, `const submitting = ref(false);`)**

Insert after the `const submitting = ref(false);` line:

```javascript
    const allMessages = ref([]);
    const chatActive = ref(false);
    const allMsgInput = ref('');
    const allChatBox = ref(null);
```

- [ ] **Step 2: Add unified chat functions after the existing `sendMessage` function (after line 506)**

Insert after the closing `}` of `async function sendMessage()`:

```javascript
    async function loadAllChat() {
      allMessages.value = await api('/chat/all?after_id=0');
      await nextTick();
      if (allChatBox.value) allChatBox.value.scrollTop = allChatBox.value.scrollHeight;
    }
    async function pollAllChat() {
      if (!chatActive.value) return;
      const lastId = allMessages.value.length ? allMessages.value[allMessages.value.length - 1].id : 0;
      const newMsgs = await api('/chat/all?after_id=' + lastId);
      if (newMsgs.length) {
        allMessages.value.push(...newMsgs);
        await nextTick();
        if (allChatBox.value) allChatBox.value.scrollTop = allChatBox.value.scrollHeight;
      }
    }
    function openChat() {
      chatActive.value = true;
      loadAllChat();
    }
    function closeChat() {
      chatActive.value = false;
      allMessages.value = [];
    }
    async function sendAllChat() {
      if (!allMsgInput.value.trim()) return;
      if (!orders.value.length) { vant.showToast('请先下单后再咨询'); return; }
      const latestOrder = orders.value[0];
      try {
        await api('/chat', {
          method: 'POST',
          body: JSON.stringify({ order_id: latestOrder.id, content: allMsgInput.value })
        });
        allMsgInput.value = '';
        await pollAllChat();
      } catch (e) { vant.showToast('发送失败'); }
    }
```

- [ ] **Step 3: Update the polling logic**

Replace the existing `pollChat` function (lines 405–414):

Old:
```javascript
    async function pollChat() {
      if (!currentOrder.value) return;
      const lastId = messages.value.length ? messages.value[messages.value.length - 1].id : 0;
      const newMsgs = await api(`/chat/${currentOrder.value.id}?after_id=${lastId}`);
      if (newMsgs.length) {
        messages.value.push(...newMsgs);
        await nextTick();
        if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight;
      }
    }
```

New:
```javascript
    async function pollChat() {
      if (currentOrder.value) {
        const lastId = messages.value.length ? messages.value[messages.value.length - 1].id : 0;
        const newMsgs = await api(`/chat/${currentOrder.value.id}?after_id=${lastId}`);
        if (newMsgs.length) {
          messages.value.push(...newMsgs);
          await nextTick();
          if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight;
        }
      } else if (chatActive.value) {
        await pollAllChat();
      }
    }
```

- [ ] **Step 4: Update the return object to expose new refs and functions**

Replace the current return block (lines 528–534):

Old:
```javascript
    return {
      ready, activeTab, goods, orders, user, userId, messages, currentOrder, msgInput,
      chatBox, showBook, bookGood, bookForm, unreadCount, submitting,
      showDetail, detailGood, detailImages, timeSlots, dateOptions,
      openBook, submitOrder, openOrderDetail, viewOrderGood, sendMessage, openDetail, previewImage,
      statusText, statusColor, roleLabel
    };
```

New:
```javascript
    return {
      ready, activeTab, goods, orders, user, userId, messages, currentOrder, msgInput,
      chatBox, showBook, bookGood, bookForm, submitting,
      showDetail, detailGood, detailImages, timeSlots, dateOptions,
      allMessages, chatActive, allMsgInput, allChatBox,
      openBook, submitOrder, openOrderDetail, viewOrderGood, sendMessage, openDetail, previewImage,
      openChat, closeChat, sendAllChat,
      statusText, statusColor, roleLabel
    };
```

Note: removed `unreadCount` (unused), added `allMessages`, `chatActive`, `allMsgInput`, `allChatBox`, `openChat`, `closeChat`, `sendAllChat`.

- [ ] **Step 5: Commit**

```bash
git add frontend/customer.html
git commit -m "feat: add unified chat JS state and functions"
```

---

### Task 3: Rewrite Messages tab template

**Files:**
- Modify: `frontend/customer.html:208-218` (Messages tab section)

- [ ] **Step 1: Replace the Messages tab HTML**

Replace the entire `<!-- 消息Tab：独立消息入口 -->` block (lines 208–218) with:

```html
  <!-- 消息Tab：统一商家聊天 -->
  <div v-show="activeTab === 2">
    <div v-if="!chatActive" style="padding-bottom:60px;">
      <div class="order-card" @click="openChat" style="text-align:center;padding:40px 14px;">
        <div style="font-size:40px;">💬</div>
        <div style="font-size:16px;font-weight:600;color:#ffffff;margin-top:10px;">联系商家</div>
        <div style="font-size:13px;color:#787890;margin-top:4px;">点击进入客服对话</div>
      </div>
    </div>
    <div v-else class="chat-wrap">
      <div class="detail-header">
        <span class="back-arrow" @click="closeChat">‹</span>
        <span style="font-weight:600;color:#ffffff;">商家客服</span>
      </div>
      <div class="chat-messages" ref="allChatBox">
        <div v-if="!allMessages.length" style="text-align:center;padding:40px 0;color:#787890;font-size:13px;">暂无消息</div>
        <div v-for="m in allMessages" :key="m.id"
             :class="['bubble', m.sender_id === userId ? 'bubble-right' : 'bubble-left']"
             style="display:flex;flex-direction:column;">
          <div class="bubble-role">{{ roleLabel(m.sender_role) }}</div>
          <div>{{ m.content }}</div>
        </div>
      </div>
      <div class="chat-input-bar">
        <input v-model="allMsgInput" placeholder="输入消息..." @keyup.enter="sendAllChat">
        <button @click="sendAllChat">发送</button>
      </div>
    </div>
  </div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/customer.html
git commit -m "feat: rewrite messages tab as unified merchant chat"
```

---

### Task 4: Update tabbar badge and cleanup

**Files:**
- Modify: `frontend/customer.html:123` (tabbar badge)

- [ ] **Step 1: Remove unused unread badge from tabbar**

Change line 123 from:
```html
    <van-tabbar-item icon="chat-o" :badge="unreadCount || ''">消息</van-tabbar-item>
```
to:
```html
    <van-tabbar-item icon="chat-o">消息</van-tabbar-item>
```

- [ ] **Step 2: Commit and push**

```bash
git add frontend/customer.html
git commit -m "chore: remove unused unread badge from messages tab"
git push
```

---

## Self-Review

**Spec coverage:**
1. `GET /chat/all` endpoint → Task 1
2. New refs (`allMessages`, `chatActive`, `allMsgInput`, `allChatBox`) → Task 2 Step 1
3. New functions (`loadAllChat`, `pollAllChat`, `openChat`, `closeChat`, `sendAllChat`) → Task 2 Step 2
4. Updated polling to handle both order chat and unified chat → Task 2 Step 3
5. Updated return to expose new state/functions → Task 2 Step 4
6. Messages tab template (entry card + chat view) → Task 3
7. Send message binds to latest order, toast if no orders → Task 2 Step 2 (`sendAllChat`)
8. Remove unread badge → Task 4

**No placeholders** — all steps contain complete code.

**Type consistency** — `allMessages`, `chatActive`, `allMsgInput`, `allChatBox` defined in Task 2 refs, used in Task 2 functions and Task 3 template. `openChat`, `closeChat`, `sendAllChat` defined in Task 2, exposed in return (Task 2 Step 4), used in Task 3 template.
