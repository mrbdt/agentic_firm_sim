const wsStatus = document.getElementById("wsStatus");

const agentsEl = document.getElementById("agents");
const ceoChatEl = document.getElementById("ceoChat");
const channelChatEl = document.getElementById("channelChat");

const ceoInput = document.getElementById("ceoInput");
const ceoPriority = document.getElementById("ceoPriority");
const ceoSend = document.getElementById("ceoSend");

const channelSelect = document.getElementById("channelSelect");
const chatInput = document.getElementById("chatInput");
const chatSend = document.getElementById("chatSend");

const ordersEl = document.getElementById("orders");
const refreshOrdersBtn = document.getElementById("refreshOrders");

const stateById = new Map();
const messagesByChannel = new Map();

function fmtTs(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString();
}

function renderAgents() {
  const items = Array.from(stateById.values()).sort((a, b) => (a.agent_id > b.agent_id ? 1 : -1));
  agentsEl.innerHTML = "";
  for (const a of items) {
    const div = document.createElement("div");
    div.className = "agent";
    div.innerHTML = \`
      <div class="top">
        <div class="name">\${a.name} <span style="font-weight:400;color:#666">(\${a.title})</span></div>
        <div class="status">\${a.status}</div>
      </div>
      <div class="meta">
        <div><b>Objective:</b> \${escapeHtml(a.current_objective || "")}</div>
        <div><b>Activity:</b> \${escapeHtml(a.current_activity || "")}</div>
        <div><b>Last tool:</b> \${escapeHtml(a.last_tool || "")}</div>
        <div><b>Inbox:</b> \${a.inbox_depth || 0} | <b>Updated:</b> \${a.updated_ts ? fmtTs(a.updated_ts) : ""}</div>
      </div>
      \${a.last_error ? \`<div class="err"><b>Error:</b> \${escapeHtml(a.last_error)}</div>\` : ""}
    \`;
    agentsEl.appendChild(div);
  }
}

function escapeHtml(str) {
  return (str || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function addMessage(m) {
  const ch = m.channel;
  if (!messagesByChannel.has(ch)) messagesByChannel.set(ch, []);
  const arr = messagesByChannel.get(ch);
  arr.push(m);
  // cap
  if (arr.length > 400) arr.splice(0, arr.length - 400);
}

function renderChat(channel, el) {
  const arr = messagesByChannel.get(channel) || [];
  el.innerHTML = "";
  for (const m of arr.slice(-200)) {
    const div = document.createElement("div");
    div.className = "msg";
    const pr = m.priority >= 10 ? "HIGH" : "";
    div.innerHTML = \`
      <div class="hdr">
        <span>\${escapeHtml(m.sender)} \${pr ? "<b style='color:#b00020'>"+pr+"</b>" : ""}</span>
        <span>\${fmtTs(m.ts)}</span>
      </div>
      <div class="body">\${escapeHtml(m.content)}</div>
    \`;
    el.appendChild(div);
  }
  el.scrollTop = el.scrollHeight;
}

async function fetchChannelHistory(channel) {
  const res = await fetch(\`/api/chat/\${encodeURIComponent(channel)}?limit=200\`);
  const data = await res.json();
  const msgs = data.messages || [];
  for (const m of msgs) addMessage(m);
}

async function postChannelMessage(channel, content) {
  await fetch(\`/api/chat/\${encodeURIComponent(channel)}\`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sender: "chairman", content }),
  });
}

async function postToCEO(message, priority) {
  await fetch("/api/chairman/ceo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, priority }),
  });
}

async function refreshOrders() {
  const res = await fetch("/api/orders?limit=200");
  const data = await res.json();
  const orders = data.orders || [];
  ordersEl.innerHTML = "";
  for (const o of orders.slice(-200).reverse()) {
    const div = document.createElement("div");
    div.className = "order";
    div.textContent = \`\${fmtTs(o.ts)} | \${o.side.toUpperCase()} \${o.qty} \${o.symbol} | \${o.status} | \${o.broker_order_id || ""}\`;
    ordersEl.appendChild(div);
  }
}

channelSelect.addEventListener("change", async () => {
  const ch = channelSelect.value;
  await fetchChannelHistory(ch);
  renderChat(ch, channelChatEl);
});

chatSend.addEventListener("click", async () => {
  const ch = channelSelect.value;
  const txt = chatInput.value.trim();
  if (!txt) return;
  chatInput.value = "";
  await postChannelMessage(ch, txt);
});

ceoSend.addEventListener("click", async () => {
  const txt = ceoInput.value.trim();
  if (!txt) return;
  const pr = ceoPriority.value;
  ceoInput.value = "";
  await postToCEO(txt, pr);
});

// initial load
(async () => {
  await fetchChannelHistory("room:chairman");
  await fetchChannelHistory("room:all");
  await fetchChannelHistory(channelSelect.value);
  await refreshOrders();
  renderChat("room:chairman", ceoChatEl);
  renderChat(channelSelect.value, channelChatEl);
})();

refreshOrdersBtn.addEventListener("click", refreshOrders);

// websocket
(function connectWS() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const url = \`\${proto}://\${window.location.host}/ws\`;
  const ws = new WebSocket(url);

  ws.onopen = () => {
    wsStatus.textContent = "WS: connected";
  };
  ws.onclose = () => {
    wsStatus.textContent = "WS: disconnected (reconnecting…)";
    setTimeout(connectWS, 1000);
  };
  ws.onerror = () => {
    wsStatus.textContent = "WS: error";
  };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "snapshot") {
        for (const a of (msg.agents || [])) {
          stateById.set(a.agent_id, a);
        }
        renderAgents();
        return;
      }
      if (msg.type === "state") {
        const a = msg.data;
        stateById.set(a.agent_id, a);
        renderAgents();
        return;
      }
      if (msg.type === "message") {
        const m = msg.data;
        addMessage(m);
        // rerender relevant panes
        if (m.channel === "room:chairman") renderChat("room:chairman", ceoChatEl);
        if (m.channel === channelSelect.value) renderChat(channelSelect.value, channelChatEl);
        return;
      }
    } catch (e) {
      // ignore
    }
  };
})();
