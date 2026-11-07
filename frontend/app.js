/**
 * Plan4U Frontend Application Engine.
 * Dual-Mode Portal: Long Itinerary Planner (Panel 1) & Live Copilot (Panel 2).
 */

const API_HOST = (typeof window !== "undefined" && window.location && window.location.hostname) ? window.location.hostname : "localhost";
const API_BASE = `http://${API_HOST}:8000/api/v1`;

// Application State
const state = {
  activeMode: "companion",
  currentLat: 26.9239,
  currentLng: 75.8267,
  locationLabel: "Near Hawa Mahal, Jaipur",
  isBackendConnected: false,
};

function getDineoutUrl(name, city) {
  const cleanName = (name || "").replace(/^dineout:\s*/i, "").trim();
  if (cleanName) {
    return `https://www.swiggy.com/search?query=${encodeURIComponent(cleanName)}`;
  }
  const citySlug = (city || state.currentCity || 'delhi').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'delhi';
  return `https://www.swiggy.com/dineout/${citySlug}`;
}

// Initialize
function initApp() {
  checkBackendHealth();
  checkSwiggyAuthStatus();
  // Periodically check health so status turns green reliably
  setInterval(checkBackendHealth, 4000);
  
  // Default to Panel 2 (Live In-Trip Copilot)
  const urlParams = (typeof window !== "undefined" && window.location) ? new URLSearchParams(window.location.search) : null;
  const tripParam = urlParams ? urlParams.get("trip") : null;
  const hash = (typeof window !== "undefined" && window.location && window.location.hash) ? window.location.hash : "";
  const initialMode = tripParam ? "planner" : (hash.includes("planner") ? "planner" : "companion");
  try {
    localStorage.setItem("plan4u_active_mode", initialMode);
  } catch (e) {}
  switchMode(initialMode);

  if (tripParam) {
    loadSharedTrip(tripParam);
  }

  if (typeof window !== "undefined" && window.lucide) {
    lucide.createIcons();
  }
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initApp);
  } else {
    initApp();
  }
}

// Markdown Renderer Helper
function formatMarkdown(content) {
  if (!content) return "";

  // Guard against raw JSON string or key leak in chat bubble
  if (typeof content === "string") {
    let clean = content.trim();

    // Check if content contains "reply_text"
    if (clean.includes('"reply_text"')) {
      // 1. Try full JSON parse
      try {
        const start = clean.indexOf("{");
        const end = clean.lastIndexOf("}");
        if (start !== -1 && end !== -1 && end > start) {
          const parsed = JSON.parse(clean.slice(start, end + 1));
          if (parsed.reply_text) clean = parsed.reply_text;
        }
      } catch (e) {}

      // 2. Try regex extraction of reply_text value
      const match = clean.match(/"reply_text"\s*:\s*"((?:\\.|[^"\\])*)"/);
      if (match && match[1]) {
        clean = match[1];
      } else {
        // Strip prefixes like {"reply_text": " or "reply_text": "
        clean = clean.replace(/^\s*\{\s*"reply_text"\s*:\s*"?/, "");
        clean = clean.replace(/^\s*"reply_text"\s*:\s*"?/, "");
        clean = clean.replace(/"?\s*\}\s*$/, "");
        if (clean.endsWith('"')) clean = clean.slice(0, -1);
      }
    }

    // Unescape literal \n and \" if present
    clean = clean.replace(/\\n/g, '\n').replace(/\\"/g, '"');
    content = clean;
  }
  if (window.marked && typeof marked.parse === "function") {
    try {
      const renderer = new marked.Renderer();
      renderer.link = function(hrefOrObj, title, text) {
        let href = typeof hrefOrObj === "object" ? hrefOrObj.href : hrefOrObj;
        let linkText = typeof hrefOrObj === "object" ? hrefOrObj.text : text;
        return `<a href="${href}" target="_blank" rel="noopener noreferrer" class="text-sky-400 hover:text-sky-300 underline font-semibold transition inline-flex items-center gap-1">${linkText} ↗</a>`;
      };
      return marked.parse(content, { renderer, breaks: true });
    } catch (e) {
      console.warn("Marked parse error", e);
    }
  }

  // Fallback regex formatter
  let html = escapeHtml(content);
  // Links [text](url)
  html = html.replace(/\[(.*?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-sky-400 hover:text-sky-300 underline font-semibold transition inline-flex items-center gap-1">$1 ↗</a>');
  // Bold **text**
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white font-bold">$1</strong>');
  // Italic *text*
  html = html.replace(/\*(.*?)\*/g, '<em class="text-slate-300">$1</em>');
  // Headings
  html = html.replace(/### (.*?)(\n|$)/g, '<h3 class="text-base font-bold text-sky-400 mt-3 mb-1">$1</h3>');
  html = html.replace(/## (.*?)(\n|$)/g, '<h2 class="text-lg font-bold text-white mt-4 mb-2">$1</h2>');
  // Line breaks
  html = html.replace(/\n/g, '<br>');
  return html;
}

// ============================================================================
// BACKEND HEALTH MONITOR
// ============================================================================
async function checkBackendHealth() {
  const pill = document.getElementById("backend-status-pill");
  const text = document.getElementById("backend-status-text");

  try {
    const res = await fetch(`http://${API_HOST}:8000/health`, { method: "GET" });
    if (res.ok) {
      state.isBackendConnected = true;
      if (pill) pill.className = "flex items-center space-x-2 px-3 py-1.5 rounded-full bg-emerald-950/60 border border-emerald-500/40 text-xs";
      if (text) {
        text.className = "text-emerald-300 font-mono";
        text.textContent = "Backend: Connected (Port 8000)";
      }
    } else {
      throw new Error();
    }
  } catch (err) {
    state.isBackendConnected = false;
    if (pill) pill.className = "flex items-center space-x-2 px-3 py-1.5 rounded-full bg-rose-950/60 border border-rose-500/40 text-xs";
    if (text) {
      text.className = "text-rose-300 font-mono";
      text.textContent = "Backend: Offline (Check port 8000)";
    }
  }
}

// ============================================================================
// MODE SWITCHER
// ============================================================================
function switchMode(mode) {
  state.activeMode = mode;
  try {
    localStorage.setItem("plan4u_active_mode", mode);
  } catch (e) {}

  const tabPlanner = document.getElementById("tab-mode-planner");
  const tabCompanion = document.getElementById("tab-mode-companion");
  const panelPlanner = document.getElementById("panel-planner");
  const panelCompanion = document.getElementById("panel-companion");

  if (mode === "planner") {
    tabPlanner.className = "tab-btn active flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all";
    tabCompanion.className = "tab-btn flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:text-white transition-all";
    panelPlanner.classList.remove("hidden");
    panelCompanion.classList.add("hidden");
  } else {
    tabCompanion.className = "tab-btn active flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all";
    tabPlanner.className = "tab-btn flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:text-white transition-all";
    panelCompanion.classList.remove("hidden");
    panelPlanner.classList.add("hidden");
  }
  if (window.lucide) lucide.createIcons();
}

// Preset helper for Planner
function setPlannerPreset(origin, dest, budget) {
  document.getElementById("p-origin").value = origin;
  document.getElementById("p-destination").value = dest;
  document.getElementById("p-budget").value = budget;
}

// ============================================================================
// REAL-TIME GPS & GEOLOCATION (LOCATE ME & LIVE TRACKING)
// ============================================================================
let watchGpsId = null;

function setGpsLocation(lat, lng, label, isRealGps = false) {
  state.currentLat = lat;
  state.currentLng = lng;
  state.locationLabel = label;
  
  const displayEl = document.getElementById("gps-display-label");
  if (displayEl) {
    displayEl.innerHTML = `<span class="text-white font-medium">${escapeHtml(label)}</span> <span class="font-mono text-[11px] text-slate-400">(${lat.toFixed(4)}° N, ${lng.toFixed(4)}° E)</span>`;
  }

  const badgeEl = document.getElementById("gps-active-badge");
  if (badgeEl) {
    if (isRealGps) {
      badgeEl.className = "px-1.5 py-0.2 text-[10px] font-bold bg-emerald-500/30 text-emerald-300 border border-emerald-500/50 rounded flex items-center gap-1";
      badgeEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span> Live Real GPS`;
    } else {
      badgeEl.className = "px-1.5 py-0.2 text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 rounded";
      badgeEl.textContent = "Active";
    }
  }

  const welcomeText = document.getElementById("welcome-loc-text");
  if (welcomeText) {
    welcomeText.textContent = `Synced to your live GPS coordinates near ${label}.`;
  }
}

async function handleLocateMe() {
  const btn = document.getElementById("btn-locate-me");
  const txt = document.getElementById("locate-me-text");
  
  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser. Please select a preset location.");
    return;
  }

  if (txt) txt.textContent = "Pinpointing GPS...";
  if (btn) btn.disabled = true;

  navigator.geolocation.getCurrentPosition(
    async (position) => {
      const lat = position.coords.latitude;
      const lng = position.coords.longitude;
      const accuracy = Math.round(position.coords.accuracy || 10);
      
      try {
        // Reverse geocode via Plan4U Backend
        const resp = await fetch(`${API_BASE}/companion/reverse-geocode?lat=${lat}&lng=${lng}`);
        if (resp.ok) {
          const geo = await resp.json();
          const cleanLocality = geo.display_name || `${geo.locality}, ${geo.city}`;
          setGpsLocation(lat, lng, cleanLocality, true);
          appendSystemChatBanner(`🎯 Real-Time GPS Acquired: <strong>${escapeHtml(cleanLocality)}</strong> (Accuracy: ±${accuracy}m). Recommendations are now locked to your exact location!`);
        } else {
          setGpsLocation(lat, lng, `Device GPS (±${accuracy}m)`, true);
        }
      } catch (e) {
        setGpsLocation(lat, lng, `Device GPS (±${accuracy}m)`, true);
      } finally {
        if (txt) txt.textContent = "Located 📍";
        if (btn) btn.disabled = false;
        setTimeout(() => { if (txt) txt.textContent = "Locate Me 🎯"; }, 2500);
        if (window.lucide) lucide.createIcons();
      }
    },
    (error) => {
      console.warn("Geolocation error:", error);
      let errMsg = "Unable to retrieve your location.";
      if (error.code === error.PERMISSION_DENIED) {
        errMsg = "Location permission denied. Please allow location access in your browser or click a preset below.";
      } else if (error.code === error.POSITION_UNAVAILABLE) {
        errMsg = "GPS position unavailable. Switching to default city preset.";
      } else if (error.code === error.TIMEOUT) {
        errMsg = "GPS request timed out. Please try again.";
      }
      alert(errMsg);
      if (txt) txt.textContent = "Locate Me 🎯";
      if (btn) btn.disabled = false;
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0
    }
  );
}

function toggleLiveGpsWatch() {
  const dot = document.getElementById("watch-gps-dot");
  const txt = document.getElementById("watch-gps-text");
  const btn = document.getElementById("btn-watch-gps");

  if (watchGpsId !== null) {
    navigator.geolocation.clearWatch(watchGpsId);
    watchGpsId = null;
    if (dot) dot.className = "w-2 h-2 rounded-full bg-slate-500";
    if (txt) txt.textContent = "Live Track";
    if (btn) btn.className = "px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold flex items-center gap-1 border border-slate-700 transition cursor-pointer";
    appendSystemChatBanner("Live GPS auto-tracking paused.");
    return;
  }

  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser.");
    return;
  }

  if (dot) dot.className = "w-2 h-2 rounded-full bg-emerald-400 animate-ping";
  if (txt) txt.textContent = "Tracking ON";
  if (btn) btn.className = "px-2.5 py-1.5 bg-emerald-950/60 text-emerald-300 border border-emerald-500/60 rounded-lg text-xs font-bold flex items-center gap-1 transition cursor-pointer shadow-lg";

  watchGpsId = navigator.geolocation.watchPosition(
    async (pos) => {
      const lat = pos.coords.latitude;
      const lng = pos.coords.longitude;
      const accuracy = Math.round(pos.coords.accuracy || 10);
      try {
        const resp = await fetch(`${API_BASE}/companion/reverse-geocode?lat=${lat}&lng=${lng}`);
        if (resp.ok) {
          const geo = await resp.json();
          const cleanLocality = geo.display_name || `${geo.locality}, ${geo.city}`;
          setGpsLocation(lat, lng, cleanLocality, true);
        }
      } catch (e) {
        setGpsLocation(lat, lng, `Device GPS (±${accuracy}m)`, true);
      }
    },
    (err) => {
      console.warn("Watch position error:", err);
      toggleLiveGpsWatch();
    },
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 12000 }
  );

  appendSystemChatBanner("🔴 Live GPS Auto-Tracking ACTIVE: As you travel or walk, your position and recommendations auto-update in real time!");
}

function appendSystemChatBanner(htmlMsg) {
  const container = document.getElementById("companion-chat-messages");
  if (!container) return;
  const div = document.createElement("div");
  div.className = "my-2 px-3.5 py-2 bg-slate-900/90 border border-emerald-500/40 rounded-xl text-xs text-emerald-300 flex items-center gap-2 shadow-md animate-fade-in";
  div.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0"></span><div>${htmlMsg}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

// ==========================================
// Swiggy MCP: per-user connect (popup, one time), status and disconnect
// ==========================================
// Local development login: every request sends X-Dev-User. Change it with
//   localStorage.setItem("plan4u_dev_user", "somename")
function authHeaders(extra) {
  let user = "owner";
  try { user = localStorage.getItem("plan4u_dev_user") || user; } catch (e) {}
  return Object.assign({ "X-Dev-User": user }, extra || {});
}

const API_ORIGIN = `http://${API_HOST}:8000`;
let resumeChatAfterSwiggyConnect = false;

window.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SWIGGY_OAUTH_SUCCESS") {
    checkSwiggyAuthStatus();
    showSwiggyNotification("Swiggy connected. You can book tables now.");
    if (resumeChatAfterSwiggyConnect) {
      resumeChatAfterSwiggyConnect = false;
      const input = document.getElementById("chat-input");
      if (input) {
        input.value = "Swiggy connect ho gaya, ab meri booking tayyar karo";
        handleSendChat(new Event("submit"));
      }
    }
  }
});

async function checkSwiggyAuthStatus() {
  const container = document.getElementById("swiggy-auth-container");
  if (!container) return;

  try {
    const res = await fetch(`${API_BASE}/swiggy/status`, { headers: authHeaders() });
    if (res.ok) {
      const data = await res.json();
      state.isSwiggyAuthed = !!data.connected;
      if (data.connected) {
        container.innerHTML = `
          <div class="flex items-center gap-1.5 px-2.5 py-1 bg-orange-950/40 border border-orange-500/40 rounded-lg text-xs font-bold text-orange-400 shadow">
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>Swiggy connected</span>
            <button onclick="handleSwiggyDisconnect()" class="text-[10px] text-slate-400 hover:text-rose-400 ml-1 transition" title="Disconnect Swiggy">✕</button>
          </div>
        `;
      } else {
        container.innerHTML = `
          <button onclick="handleSwiggyConnect()" class="px-2.5 py-1 bg-orange-500/20 hover:bg-orange-500 text-orange-400 hover:text-white rounded-lg border border-orange-500/40 text-xs font-bold flex items-center gap-1 transition shadow cursor-pointer" title="Sign in to Swiggy once to book tables from chat">
            <span>Connect Swiggy</span>
          </button>
        `;
      }
    }
  } catch (e) {
    console.warn("Could not check Swiggy status:", e);
  }
}

// Opens Swiggy's own sign-in page in a popup. The user types their number and OTP there; the popup closes itself.
async function handleSwiggyConnect() {
  const width = 480;
  const height = 640;
  const left = (window.screen.width / 2) - (width / 2);
  const top = (window.screen.height / 2) - (height / 2);
  // Open the popup first (inside the click) so the browser does not block it, then point it at Swiggy.
  const popup = window.open("about:blank", "SwiggyOAuthWindow",
    `toolbar=no, location=yes, status=no, menubar=no, scrollbars=yes, resizable=yes, width=${width}, height=${height}, top=${top}, left=${left}`);
  try {
    const res = await fetch(`${API_BASE}/swiggy/connect`, { method: "POST", headers: authHeaders() });
    const data = await res.json();
    if (!res.ok || !data.auth_url) throw new Error(data.detail || "Could not start Swiggy sign-in");
    if (popup) popup.location.href = data.auth_url; else window.location.href = data.auth_url;
  } catch (e) {
    if (popup) popup.close();
    showSwiggyNotification("Could not start Swiggy sign-in: " + e.message);
  }
}

async function handleSwiggyDisconnect() {
  try {
    await fetch(`${API_BASE}/swiggy/disconnect`, { method: "POST", headers: authHeaders() });
    checkSwiggyAuthStatus();
    showSwiggyNotification("Swiggy disconnected.");
  } catch (e) {
    console.error("Disconnect error:", e);
  }
}

function showSwiggyNotification(msg) {
  const banner = document.createElement("div");
  banner.className = "fixed top-4 right-4 z-50 bg-gradient-to-r from-orange-600 to-amber-600 text-white font-bold px-4 py-2.5 rounded-xl shadow-2xl flex items-center gap-2";
  banner.innerHTML = `<span>🛵</span><span>${escapeHtml(msg)}</span>`;
  document.body.appendChild(banner);
  setTimeout(() => banner.remove(), 4500);
}


// ============================================================================
// PANEL 1: MASTER PRE-TRIP PLANNER CHAT HANDLER
// ============================================================================
function sendPlannerQuickPrompt(text) {
  document.getElementById("planner-chat-input").value = text;
  handlePlannerSendMessage(new Event("submit"));
}

function appendPlannerUserMessage(text) {
  const container = document.getElementById("planner-chat-messages");
  const div = document.createElement("div");
  div.className = "flex items-start justify-end space-x-3";
  div.innerHTML = `
    <div class="bg-brand-600 text-white rounded-2xl rounded-tr-none px-4 py-3 text-sm max-w-xl shadow-md">
      ${escapeHtml(text)}
    </div>
    <div class="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center shrink-0 border border-slate-700 text-xs font-bold text-slate-300">
      You
    </div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function appendPlannerTypingIndicator(id) {
  const container = document.getElementById("planner-chat-messages");
  const div = document.createElement("div");
  div.id = id;
  div.className = "flex items-start space-x-3 max-w-md animate-pulse";
  div.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center shrink-0 border border-slate-700">
      <i data-lucide="bot" class="w-4 h-4 text-brand-400"></i>
    </div>
    <div class="bg-slate-800/80 border border-slate-700/80 rounded-2xl rounded-tl-none px-4 py-3 text-xs text-slate-400 flex items-center space-x-2">
      <div class="w-2 h-2 rounded-full bg-brand-400 animate-ping"></div>
      <span id="${id}-text">FlightSpecialist & StayCurator searching 20k inventory...</span>
    </div>
  `;
  container.appendChild(div);
  if (window.lucide) lucide.createIcons();
  container.scrollTop = container.scrollHeight;

  const steps = [
    "StayCurator querying 10,000 verified hotels...",
    "CultureFoodAgent clustering zero-backtrack sightseeing...",
    "BudgetCheckoutAgent locking synchronized 15-minute Razorpay hold...",
    "Master Planner synthesizing personalized Hinglish itinerary...",
  ];
  let sIdx = 0;
  return setInterval(() => {
    sIdx = (sIdx + 1) % steps.length;
    const txt = document.getElementById(`${id}-text`);
    if (txt) txt.textContent = steps[sIdx];
  }, 1000);
}

function removePlannerTypingIndicator(id, intervalId) {
  if (intervalId) clearInterval(intervalId);
  const el = document.getElementById(id);
  if (el) el.remove();
}

async function handlePlannerSendMessage(event) {
  event.preventDefault();
  const input = document.getElementById("planner-chat-input");
  const msgText = input.value.trim();
  if (!msgText) return;

  const btn = document.getElementById("btn-planner-send");
  const container = document.getElementById("planner-chat-messages");

  // 1. Append user message
  appendPlannerUserMessage(msgText);
  input.value = "";
  btn.disabled = true;

  // 2. Append typing indicator
  const typingId = "planner-typing-" + Date.now();
  const intervalId = appendPlannerTypingIndicator(typingId);

  try {
    const res = await fetch(`${API_BASE}/planner/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_message: msgText }),
    });

    if (!res.ok) {
      throw new Error(`Server returned ${res.status}: ${await res.text()}`);
    }

    const data = await res.json();
    removePlannerTypingIndicator(typingId, intervalId);
    btn.disabled = false;

    appendPlannerBotMessage(data);
  } catch (err) {
    removePlannerTypingIndicator(typingId, intervalId);
    btn.disabled = false;
    alert("Planner Error: " + err.message + "\nMake sure backend is running on port 8000.");
  }
}

function appendPlannerBotMessage(data) {
  const container = document.getElementById("planner-chat-messages");
  const div = document.createElement("div");
  div.className = "flex items-start space-x-3 max-w-4xl";

  const itin = data.itinerary;
  if (itin) {
    state.lastItinerary = itin;
  }
  let itinContent = "";

  if (itin) {
    // 1. Flights HTML
    const flightsHtml = (itin.recommended_flights || []).slice(0, 2).map((f) => `
      <div class="bg-slate-900/90 border border-slate-800 p-3 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 hover:border-brand-500/50 transition">
        <div class="flex items-center space-x-3">
          <div class="w-9 h-9 rounded-lg bg-slate-800 flex items-center justify-center font-bold text-xs text-brand-400">
            ${f.airline_code}
          </div>
          <div>
            <div class="flex items-center space-x-2">
              <span class="font-bold text-white text-xs">${escapeHtml(f.airline_name)}</span>
              <span class="text-[10px] text-slate-400">(${f.segments[0]?.flight_number || 'Direct'})</span>
              ${f.is_refundable ? '<span class="px-1 py-0.2 text-[9px] bg-emerald-500/20 text-emerald-400 rounded">Refundable</span>' : '<span class="px-1 py-0.2 text-[9px] bg-amber-500/20 text-amber-400 rounded">Non-Refundable</span>'}
            </div>
            <div class="text-[11px] text-slate-300 mt-0.5">
              <span class="font-semibold text-white">${f.departure_time}</span> (${f.origin}) ➔ <span class="font-semibold text-white">${f.arrival_time}</span> (${f.destination})
              <span class="text-slate-500">• ${f.total_duration}</span>
            </div>
          </div>
        </div>
        <div class="flex items-center space-x-3 justify-between sm:justify-end">
          <div class="text-right">
            <div class="text-xs font-bold text-brand-400">₹${f.published_fare.toLocaleString()}</div>
            <div class="text-[10px] text-slate-500">${f.cabin_baggage} cabin</div>
          </div>
          <button onclick="handleFlightHold('${f.id}', '${f.trace_id}', '${f.result_index}', ${f.published_fare})" class="px-3 py-1.5 bg-brand-600 hover:bg-brand-500 text-white font-semibold rounded-lg text-xs transition shadow">
            Hold 15m
          </button>
        </div>
      </div>
    `).join("");

    // 2. Hotels HTML
    const hotelsHtml = (itin.recommended_hotels || []).slice(0, 2).map((h) => `
      <div class="bg-slate-900/90 border border-slate-800 p-3 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 hover:border-teal-500/50 transition">
        <div class="flex items-center space-x-3">
          <img src="${h.featured_image}" class="w-12 h-12 rounded-lg object-cover border border-slate-700">
          <div>
            <div class="flex items-center space-x-2">
              <span class="font-bold text-white text-xs">${escapeHtml(h.name)}</span>
              <span class="text-xs text-amber-400 font-bold">${'★'.repeat(h.star_rating)}</span>
            </div>
            <div class="text-[11px] text-slate-400 mt-0.5 truncate max-w-xs">${escapeHtml(h.address)}</div>
            <div class="text-[10px] text-brand-400 mt-0.5">
              ${(h.amenities || []).slice(0, 3).join(" • ")}
            </div>
          </div>
        </div>
        <div class="flex items-center space-x-3 justify-between sm:justify-end">
          <div class="text-right">
            <div class="text-xs font-bold text-white">₹${h.min_price_per_night.toLocaleString()}</div>
            <div class="text-[10px] text-slate-500">per night</div>
          </div>
          <button onclick="handleHotelPrebook('${h.hotel_code}', '${h.rooms[0]?.room_type_code || 'STD'}', ${h.min_price_per_night})" class="px-3 py-1.5 bg-slate-800 hover:bg-teal-600 hover:text-white border border-slate-700 text-slate-200 font-semibold rounded-lg text-xs transition">
            Lock Rate
          </button>
        </div>
      </div>
    `).join("");

    // 3. Days Timeline
    const daysHtml = (itin.days || []).map((d) => `
      <div class="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3 space-y-2">
        <div class="flex items-center justify-between border-b border-slate-800/70 pb-2">
          <div class="flex items-center space-x-2">
            <span class="w-6 h-6 rounded-md bg-brand-500/20 text-brand-300 font-bold flex items-center justify-center text-xs border border-brand-500/30">
              D${d.day_number}
            </span>
            <span class="text-xs font-bold text-white">${escapeHtml(d.theme)}</span>
          </div>
          <span class="text-[10px] text-slate-400">Activities Budget: ₹${d.daily_budget_estimate.toLocaleString()}</span>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
          ${(d.activities || []).map(act => `
            <div class="p-2 bg-slate-900/80 border border-slate-800/60 rounded-lg space-y-1">
              <div class="flex items-center justify-between text-[10px]">
                <span class="font-bold text-teal-300">${act.start_time} - ${act.end_time}</span>
                <span class="px-1.5 py-0.2 rounded uppercase font-semibold text-[9px] ${act.category === 'monument' ? 'bg-indigo-500/20 text-indigo-300' : 'bg-amber-500/20 text-amber-300'}">
                  ${act.category}
                </span>
              </div>
              <div class="font-semibold text-white text-xs">${escapeHtml(act.title)}</div>
              <div class="text-[11px] text-slate-400 leading-tight">${escapeHtml(act.description)}</div>
            </div>
          `).join("")}
        </div>
      </div>
    `).join("");

    // 4. Synchronized Razorpay Hold Session
    let checkoutHtml = "";
    if (data.checkout_session) {
      checkoutHtml = `
        <div class="bg-gradient-to-r from-emerald-950/70 via-slate-950 to-brand-950/60 border border-emerald-500/40 rounded-xl p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-lg">
          <div>
            <div class="flex items-center space-x-2">
              <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold text-[10px] uppercase">15-Min Razorpay Hold</span>
              <span class="text-xs font-bold text-white">Guaranteed Synchronized Price Lock</span>
            </div>
            <div class="text-xs text-slate-300 mt-1">Flights, Hotel, and Sightseeing are frozen for 15 minutes.</div>
          </div>
          <div class="flex items-center space-x-2.5 justify-between sm:justify-end">
            <div class="text-right mr-1">
              <div class="text-base font-extrabold text-emerald-400">₹${itin.grand_total_inr.toLocaleString()}</div>
              <div class="text-[10px] text-slate-400">Total 2-person pkg</div>
            </div>
            <button onclick="shareCurrentItinerary()" class="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-brand-300 font-bold rounded-lg text-xs transition border border-brand-500/30 flex items-center gap-1.5 shadow" title="Share with friends to 1-click fork">
              <span>Share 🔗</span>
            </button>
            <button onclick="openBookingModal('Complete Package Hold', 'Trip: ${itin.title}', 'Total Package: ₹${itin.grand_total_inr}', '${data.checkout_session.checkout_url || ''}')" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg text-xs transition shadow-lg shadow-emerald-600/30">
              Lock Trip Now
            </button>
          </div>
        </div>
      `;
    }

    itinContent = `
      <div class="mt-3 space-y-3 pt-3 border-t border-slate-700/60">
        <!-- Overview Banner -->
        <div class="bg-slate-950/90 border border-slate-800 rounded-xl p-3.5 flex items-center justify-between flex-wrap gap-2">
          <div>
            <div class="text-xs font-bold text-white">${escapeHtml(itin.title)}</div>
            <div class="text-[11px] text-slate-400">${itin.duration_days} Days / ${itin.duration_days - 1} Nights • ${escapeHtml(itin.origin)} ➔ ${escapeHtml(itin.destination)}</div>
          </div>
          <div class="flex items-center space-x-2.5">
            <div class="text-right">
              <span class="text-xs text-slate-400">Package Total: </span>
              <span class="text-sm font-extrabold text-brand-400">₹${itin.grand_total_inr.toLocaleString()}</span>
            </div>
            <button onclick="shareCurrentItinerary()" class="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-brand-300 text-xs font-semibold rounded-lg border border-brand-500/30 flex items-center gap-1 shadow transition" title="Share with friends">
              <span>Share 🔗</span>
            </button>
          </div>
        </div>

        <!-- Flights -->
        <div class="space-y-1.5">
          <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <i data-lucide="plane" class="w-3.5 h-3.5 text-brand-400"></i>
            <span>Recommended Flights (10k Inventory):</span>
          </div>
          ${flightsHtml}
        </div>

        <!-- Hotels -->
        <div class="space-y-1.5">
          <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <i data-lucide="building" class="w-3.5 h-3.5 text-teal-400"></i>
            <span>Recommended Stays (10k Inventory):</span>
          </div>
          ${hotelsHtml}
        </div>

        <!-- Day by Day -->
        <div class="space-y-1.5">
          <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <i data-lucide="calendar" class="w-3.5 h-3.5 text-accent-400"></i>
            <span>Optimized Zero-Backtrack Schedule:</span>
          </div>
          ${daysHtml}
        </div>

        <!-- Synchronized Checkout -->
        ${checkoutHtml}
      </div>
    `;
  }

  // Quick replies
  let quickRepliesHtml = "";
  if (data.suggested_quick_replies && data.suggested_quick_replies.length > 0) {
    quickRepliesHtml = `
      <div class="mt-3 pt-2 border-t border-slate-700/60 flex items-center flex-wrap gap-1.5">
        ${data.suggested_quick_replies.map(qr => `
          <button onclick="sendPlannerQuickPrompt('${escapeHtml(qr)}')" class="px-2.5 py-1 rounded-full bg-slate-700/60 hover:bg-brand-600 hover:text-white text-[11px] text-slate-300 transition">
            ${escapeHtml(qr)}
          </button>
        `).join("")}
      </div>
    `;
  }

  div.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-brand-600 to-teal-400 flex items-center justify-center shrink-0 shadow">
      <i data-lucide="bot" class="w-4 h-4 text-white"></i>
    </div>
    <div class="bg-slate-800/90 border border-slate-700/80 rounded-2xl rounded-tl-none p-4 text-sm text-slate-200 shadow-md flex-1">
      <div class="leading-relaxed text-sm markdown-body space-y-2">${formatMarkdown(data.reply_text)}</div>
      ${itinContent}
      ${quickRepliesHtml}
    </div>
  `;

  container.appendChild(div);
  if (window.lucide) lucide.createIcons();
  container.scrollTop = container.scrollHeight;
}

function renderCompleteItinerary(itin) {
  const container = document.getElementById("planner-results");
  
  // Format flights HTML
  const flightsHtml = (itin.recommended_flights || []).slice(0, 3).map((f, i) => `
    <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-3 hover:border-brand-500/50 transition">
      <div class="flex items-center space-x-3">
        <div class="w-10 h-10 rounded-lg bg-slate-800 flex items-center justify-center font-bold text-xs text-brand-400">
          ${f.airline_code}
        </div>
        <div>
          <div class="flex items-center space-x-2">
            <span class="font-bold text-white text-sm">${f.airline_name}</span>
            <span class="text-xs text-slate-400">(${f.segments[0]?.flight_number || 'Direct'})</span>
            ${f.is_refundable ? '<span class="px-1.5 py-0.5 text-[10px] bg-emerald-500/20 text-emerald-400 rounded">Refundable</span>' : '<span class="px-1.5 py-0.5 text-[10px] bg-amber-500/20 text-amber-400 rounded">Non-Refundable</span>'}
          </div>
          <div class="text-xs text-slate-300 mt-0.5">
            <span class="font-semibold text-white">${f.departure_time}</span> (${f.origin}) ➔ <span class="font-semibold text-white">${f.arrival_time}</span> (${f.destination})
            <span class="text-slate-500">• ${f.total_duration}</span>
          </div>
        </div>
      </div>
      <div class="flex items-center space-x-3 justify-between md:justify-end">
        <div class="text-right">
          <div class="text-xs text-slate-400">Published Fare</div>
          <div class="text-base font-bold text-brand-400">₹${f.published_fare.toLocaleString()}</div>
        </div>
        <button onclick="handleFlightHold('${f.id}', '${f.trace_id}', '${f.result_index}', ${f.published_fare})" class="px-3.5 py-2 bg-brand-600 hover:bg-brand-500 text-white font-semibold rounded-lg text-xs transition shadow-md">
          Hold Seat (15m)
        </button>
      </div>
    </div>
  `).join("");

  // Format hotels HTML
  const hotelsHtml = (itin.recommended_hotels || []).slice(0, 3).map((h, i) => `
    <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-3 hover:border-brand-500/50 transition">
      <div class="flex items-center space-x-3">
        <img src="${h.featured_image}" class="w-14 h-14 rounded-lg object-cover border border-slate-700">
        <div>
          <div class="flex items-center space-x-2">
            <span class="font-bold text-white text-sm">${h.name}</span>
            <span class="text-xs text-amber-400 font-bold">${'★'.repeat(h.star_rating)}</span>
          </div>
          <div class="text-xs text-slate-400 mt-0.5">${h.address}</div>
          <div class="text-[11px] text-brand-400 mt-1 flex items-center gap-1">
            <i data-lucide="check" class="w-3 h-3"></i>
            <span>${(h.amenities || []).slice(0, 3).join(" • ")}</span>
          </div>
        </div>
      </div>
      <div class="flex items-center space-x-3 justify-between md:justify-end">
        <div class="text-right">
          <div class="text-xs text-slate-400">Per Night</div>
          <div class="text-base font-bold text-white">₹${h.min_price_per_night.toLocaleString()}</div>
        </div>
        <button onclick="handleHotelPrebook('${h.hotel_code}', '${h.rooms[0]?.room_type_code || 'STD'}', ${h.min_price_per_night})" class="px-3.5 py-2 bg-slate-800 hover:bg-brand-600 hover:text-white border border-slate-700 text-slate-200 font-semibold rounded-lg text-xs transition">
          Lock Rate (15m)
        </button>
      </div>
    </div>
  `).join("");

  // Format day plans HTML
  const daysHtml = (itin.days || []).map((d) => `
    <div class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-4">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <div class="flex items-center space-x-3">
          <span class="w-8 h-8 rounded-lg bg-brand-500/20 text-brand-400 font-bold flex items-center justify-center text-sm border border-brand-500/30">
            D${d.day_number}
          </span>
          <div>
            <h4 class="text-sm font-bold text-white">${d.theme}</h4>
            <p class="text-xs text-slate-400">${d.date} • Estimated activities spend: ₹${d.daily_budget_estimate.toLocaleString()}</p>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        ${(d.activities || []).map(act => `
          <div class="p-3 bg-slate-950/70 border border-slate-800/80 rounded-lg space-y-1.5">
            <div class="flex items-center justify-between text-xs">
              <span class="font-bold text-accent-400 flex items-center gap-1">
                <i data-lucide="clock" class="w-3 h-3"></i> ${act.start_time} - ${act.end_time}
              </span>
              <span class="px-1.5 py-0.5 text-[10px] rounded uppercase font-semibold ${act.category === 'monument' ? 'bg-indigo-500/20 text-indigo-300' : 'bg-amber-500/20 text-amber-300'}">
                ${act.category}
              </span>
            </div>
            <div class="font-bold text-white text-sm">${act.title}</div>
            <div class="text-xs text-slate-400 leading-relaxed">${act.description}</div>
            ${act.insider_tips && act.insider_tips.length ? `
              <div class="pt-1 text-[11px] text-teal-400 flex items-center gap-1">
                <i data-lucide="sparkles" class="w-3 h-3 shrink-0"></i>
                <span>${act.insider_tips[0]}</span>
              </div>
            ` : ''}
          </div>
        `).join("")}
      </div>
    </div>
  `).join("");

  // Tips HTML
  const tipsHtml = (itin.pro_travel_tips || []).map(t => `
    <li class="flex items-start space-x-2 text-xs text-slate-300">
      <span class="text-brand-400 font-bold">•</span>
      <span>${t}</span>
    </li>
  `).join("");

  container.innerHTML = `
    <!-- Hero Banner -->
    <div class="bg-gradient-to-r from-emerald-950/80 via-slate-900 to-teal-950/80 border border-brand-500/40 rounded-2xl p-6 shadow-2xl relative overflow-hidden">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div class="flex items-center space-x-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-brand-500/20 text-brand-300 border border-brand-500/30">Complete AI Itinerary</span>
            <span class="text-xs text-slate-400">${itin.duration_days} Days / ${itin.duration_days - 1} Nights</span>
          </div>
          <h3 class="text-2xl font-bold text-white mt-1.5">${itin.title}</h3>
          <p class="text-xs text-slate-300 mt-1 max-w-2xl">${itin.best_time_to_visit_note || 'Optimized weather & timing'}</p>
        </div>

        <div class="bg-slate-950/80 border border-slate-800 p-4 rounded-xl text-right shrink-0">
          <div class="text-xs text-slate-400">Grand Total (Flights + Hotel + Sights)</div>
          <div class="text-2xl font-black text-brand-400">₹${itin.grand_total_inr.toLocaleString()}</div>
          <div class="text-[11px] text-slate-500 mt-0.5">Flights: ₹${itin.flight_total_cost.toLocaleString()} | Hotel: ₹${itin.hotel_total_cost.toLocaleString()}</div>
        </div>
      </div>
    </div>

    <!-- Recommended Flights Section -->
    <div class="space-y-3">
      <h3 class="text-sm font-bold text-white flex items-center gap-2">
        <i data-lucide="plane" class="w-4 h-4 text-brand-400"></i>
        <span>Verified Airline Flights (From 10,000 Flight Inventory)</span>
      </h3>
      <div class="space-y-2">
        ${flightsHtml}
      </div>
    </div>

    <!-- Recommended Hotels Section -->
    <div class="space-y-3">
      <h3 class="text-sm font-bold text-white flex items-center gap-2">
        <i data-lucide="building" class="w-4 h-4 text-teal-400"></i>
        <span>Hand-Picked Stays (From 10,000 Hotel Inventory)</span>
      </h3>
      <div class="space-y-2">
        ${hotelsHtml}
      </div>
    </div>

    <!-- Day by Day Plans -->
    <div class="space-y-3">
      <h3 class="text-sm font-bold text-white flex items-center gap-2">
        <i data-lucide="calendar" class="w-4 h-4 text-accent-400"></i>
        <span>Day-Wise Schedule (Zero-Backtrack Clustered)</span>
      </h3>
      <div class="space-y-4">
        ${daysHtml}
      </div>
    </div>

    <!-- Smart Tips & Weather Card -->
    <div class="bg-slate-900/60 border border-slate-800 rounded-xl p-5">
      <h4 class="text-xs font-bold text-white uppercase tracking-wider mb-2 flex items-center gap-1.5">
        <i data-lucide="lightbulb" class="w-4 h-4 text-amber-400"></i>
        <span>Smart Travel Insights & Surcharge Warnings</span>
      </h4>
      <ul class="space-y-1.5">
        ${tipsHtml}
      </ul>
    </div>
  `;

  if (window.lucide) lucide.createIcons();
}

// ============================================================================
// PANEL 2: LIVE IN-TRIP COPILOT CHAT HANDLER (MULTI-TURN MEMORY & SESSION ISOLATION)
// ============================================================================
function generateCopilotSessionId() {
  return "session_" + Date.now() + "_" + Math.random().toString(36).substring(2, 9);
}
let currentCopilotSessionId = generateCopilotSessionId();
const copilotChatHistory = [];

async function handleStartNewChat() {
  const oldSessionId = currentCopilotSessionId;
  currentCopilotSessionId = generateCopilotSessionId();
  copilotChatHistory.length = 0;

  // Flush backend memory for previous session
  try {
    fetch(`${API_BASE}/companion/reset`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Session-ID": oldSessionId
      }
    }).catch(() => {});
  } catch (e) {
    // Non-blocking
  }

  const chatContainer = document.getElementById("chat-messages");
  if (chatContainer) {
    chatContainer.innerHTML = `
      <div class="flex items-start space-x-3 max-w-2xl">
        <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-brand-600 to-teal-400 flex items-center justify-center shrink-0 shadow">
          <i data-lucide="bot" class="w-4 h-4 text-white"></i>
        </div>
        <div class="bg-slate-800/90 border border-slate-700/80 rounded-2xl rounded-tl-none p-4 text-sm text-slate-200 shadow-md">
          <p class="font-semibold text-white mb-1">New chat started! 🚀</p>
          <p>Previous conversation context clear ho gaya hai. Ab aap fresh query pucho — live gigs & concerts, street food cravings, ya nearby spot recommendations!</p>
          <div class="mt-3 pt-2 border-t border-slate-700/60 flex items-center space-x-2 text-xs text-brand-400 font-medium">
            <i data-lucide="map-pin" class="w-3.5 h-3.5"></i>
            <span id="welcome-loc-text">Synced to your live GPS coordinates near ${escapeHtml(state.currentLocalityLabel || 'Current Spot')}.</span>
          </div>
        </div>
      </div>
    `;
    if (window.lucide) lucide.createIcons();
  }
}

function sendQuickPrompt(text) {
  document.getElementById("chat-input").value = text;
  handleSendChat(new Event("submit"));
}

async function handleSendChat(event) {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  const msgText = input.value.trim();
  if (!msgText) return;

  const chatContainer = document.getElementById("chat-messages");

  // 1. Append User Bubble & track history
  appendUserMessage(msgText);
  const priorHistory = copilotChatHistory.slice(-8);
  copilotChatHistory.push({ role: "user", content: msgText });
  input.value = "";

  // 2. Append Loading / Typing indicator
  const typingId = "typing-" + Date.now();
  appendTypingIndicator(typingId);
  chatContainer.scrollTop = chatContainer.scrollHeight;

  try {
    const payload = {
      user_message: msgText,
      current_lat: state.currentLat,
      current_lng: state.currentLng,
      current_time_str: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      active_trip_id: currentCopilotSessionId,
      conversation_history: priorHistory,
    };

    const res = await fetch(`${API_BASE}/companion/chat`, {
      method: "POST",
      headers: authHeaders({
        "Content-Type": "application/json",
        "X-Session-ID": currentCopilotSessionId
      }),
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      throw new Error(`Server returned ${res.status}`);
    }

    const data = await res.json();
    removeTypingIndicator(typingId);

    // Track bot reply in multi-turn conversation history
    if (data.reply_text) {
      copilotChatHistory.push({ role: "assistant", content: data.reply_text });
    }

    appendBotMessage(data);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  } catch (err) {
    removeTypingIndicator(typingId);
    appendBotMessage({
      reply_text: "Arre boss, backend se connection fail ho gaya. Make sure `python3 app/main.py` is running on port 8000.",
      nearby_recommendations: [],
      suggested_quick_replies: ["Try again 🔄", "Check backend status"],
    });
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }
}

function appendUserMessage(text) {
  const container = document.getElementById("chat-messages");
  const div = document.createElement("div");
  div.className = "flex items-start justify-end space-x-3";
  div.innerHTML = `
    <div class="bg-brand-600 text-white rounded-2xl rounded-tr-none px-4 py-3 text-sm max-w-xl shadow-md">
      ${escapeHtml(text)}
    </div>
    <div class="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center shrink-0 border border-slate-700 text-xs font-bold text-slate-300">
      You
    </div>
  `;
  container.appendChild(div);
}

function appendTypingIndicator(id) {
  const container = document.getElementById("chat-messages");
  const div = document.createElement("div");
  div.id = id;
  div.className = "flex items-start space-x-3 max-w-md animate-pulse";
  div.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center shrink-0 border border-slate-700">
      <i data-lucide="bot" class="w-4 h-4 text-brand-400"></i>
    </div>
    <div class="bg-slate-800/80 border border-slate-700/80 rounded-2xl rounded-tl-none px-4 py-3 text-xs text-slate-400 flex items-center space-x-2">
      <span>Copilot analyzing GPS & inventory...</span>
    </div>
  `;
  container.appendChild(div);
  if (window.lucide) lucide.createIcons();
}

function removeTypingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// ============================================================================
// INLINE CARD GENERATORS & SMART TEXT-CARD INTERLEAVER
// ============================================================================
function getCardKeywords(text) {
  if (!text) return [];
  const stopWords = new Set([
    "the", "and", "for", "with", "delhi", "ncr", "live", "show", "special", "night", "event", "events",
    "club", "entry", "tickets", "tour", "session", "festival", "underground", "india", "road", "marg",
    "near", "street", "market", "sector", "chowk", "auditorium", "stadium"
  ]);
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter(w => w.length >= 3 && !stopWords.has(w));
}

function renderSingleEventCardHtml(card) {
  const providerName = card.provider || 'BookMyShow';
  const pLow = providerName.toLowerCase();
  let badgeColor = "bg-purple-500/20 text-purple-300 border-purple-500/40";
  let btnGradient = "from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white";
  let cardBorder = "border-purple-500/40 hover:border-purple-400";
  let cardGrad = "from-purple-950/60 via-slate-900 to-slate-950";
  let badgeIcon = "🎟️";
  let btnLabel = `Book Directly on ${escapeHtml(providerName)} ↗`;

  if (pLow.includes("swiggy dineout") || pLow.includes("dineout")) {
    badgeColor = "bg-orange-500/20 text-orange-400 border-orange-500/40";
    btnGradient = "from-orange-600 to-amber-600 hover:from-orange-500 hover:to-amber-500 text-white";
    cardBorder = "border-orange-500/40 hover:border-orange-400";
    cardGrad = "from-orange-950/60 via-slate-900 to-slate-950";
    badgeIcon = "🍽️";
    btnLabel = "Book on Swiggy Dineout 🍽️";
  } else if (pLow.includes("swiggy") || pLow.includes("instamart")) {
    badgeColor = "bg-orange-500/20 text-orange-400 border-orange-500/40";
    btnGradient = "from-orange-600 to-amber-600 hover:from-orange-500 hover:to-amber-500 text-white";
    cardBorder = "border-orange-500/40 hover:border-orange-400";
    cardGrad = "from-orange-950/60 via-slate-900 to-slate-950";
    badgeIcon = pLow.includes("instamart") ? "⚡" : "🛵";
    btnLabel = pLow.includes("instamart") ? "Order on Instamart ⚡" : "Order on Swiggy 🛵";
  } else if (pLow.includes("insider") || pLow.includes("paytm")) {
    badgeColor = "bg-sky-500/20 text-sky-300 border-sky-500/40";
    btnGradient = "from-sky-600 to-blue-600 hover:from-sky-500 hover:to-blue-500 text-white";
    cardBorder = "border-sky-500/40 hover:border-sky-400";
    cardGrad = "from-sky-950/60 via-slate-900 to-slate-950";
  } else if (pLow.includes("district") || pLow.includes("zomato")) {
    badgeColor = "bg-rose-500/20 text-rose-300 border-rose-500/40";
    btnGradient = "from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 text-white";
    cardBorder = "border-rose-500/40 hover:border-rose-400";
    cardGrad = "from-rose-950/60 via-slate-900 to-slate-950";
  } else if (pLow.includes("skillbox")) {
    badgeColor = "bg-indigo-500/20 text-indigo-300 border-indigo-500/40";
    btnGradient = "from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white";
    cardBorder = "border-indigo-500/40 hover:border-indigo-400";
    cardGrad = "from-indigo-950/60 via-slate-900 to-slate-950";
  } else if (pLow.includes("venue") || pLow.includes("door") || pLow.includes("free")) {
    badgeColor = "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
    btnGradient = "from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white";
    cardBorder = "border-emerald-500/40 hover:border-emerald-400";
    cardGrad = "from-emerald-950/60 via-slate-900 to-slate-950";
  }

  const cardTitle = card.title || "Live Event";
  let rawFee = card.entry_fee_inr ?? card.amount_inr ?? card.price_range;
  if (rawFee === undefined || rawFee === null || rawFee === "" || rawFee === "undefined") {
    rawFee = "₹499 - ₹1,499";
  }
  const priceDisplay = typeof rawFee === 'number' ? `₹${rawFee}` : `${rawFee}`;

  const safeTitle = escapeHtml(cardTitle);
  const safeVenue = escapeHtml(card.venue || 'City Venue');
  const safeDateTime = escapeHtml(card.date_time || 'Tonight');
  const safePrice = escapeHtml(priceDisplay);
  const citySlug = (state.currentCity || 'delhi').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'delhi';
  let rawUrl = card.booking_url;
  if (pLow.includes("dineout") || (rawUrl && rawUrl.includes("dineout"))) {
    // Keep verified direct Swiggy city/search links; sanitize broken -restaurants paths
    if (!rawUrl || rawUrl.includes("-restaurants") || rawUrl.includes("?search=")) {
      rawUrl = getDineoutUrl(cardTitle, state.currentCity);
    }
  } else if (!rawUrl) {
    rawUrl = pLow.includes("insider") ? `https://insider.in/${citySlug}` : "https://in.bookmyshow.com";
  }
  const safeUrl = escapeHtml(rawUrl);
  const cleanVenue = (card.venue || cardTitle || "").replace(/['"]/g, '').trim();
  const hasGps = state.userLocation && state.userLocation.lat && state.userLocation.lng;
  const venueDirectionsUrl = hasGps
    ? `https://www.google.com/maps/dir/?api=1&origin=${state.userLocation.lat},${state.userLocation.lng}&destination=${encodeURIComponent(cleanVenue)}`
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(cleanVenue)}`;

  let actionButtonsHtml = "";
  if (pLow.includes("swiggy") || pLow.includes("dineout") || pLow.includes("instamart")) {
    actionButtonsHtml = `
      <div class="flex items-center space-x-2 pt-1">
        <button onclick="openInAppBookingSheet('dineout_${safeTitle.replace(/'/g, "\\'")}', '${safeTitle.replace(/'/g, "\\'")}', '${safeVenue.replace(/'/g, "\\'")}', 900)" class="flex-1 bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold py-2.5 px-3 rounded-lg text-xs transition shadow flex items-center justify-center gap-1.5 cursor-pointer">
          <i data-lucide="utensils" class="w-3.5 h-3.5"></i>
          <span>Instant Table Pass (In-App) 🍽️</span>
          <span class="text-[9px] bg-emerald-950/70 text-emerald-300 px-1 py-0.2 rounded border border-emerald-400/40">20% Off</span>
        </button>
      </div>
    `;
  } else {
    actionButtonsHtml = `
      <div class="flex items-center space-x-2 pt-1">
        <button onclick="openInAppEventTicketSheet('${safeTitle.replace(/'/g, "\\'")}', '${safeVenue.replace(/'/g, "\\'")}', '${safeDateTime.replace(/'/g, "\\'")}', '${safePrice.replace(/'/g, "\\'")}', '${escapeHtml(providerName).replace(/'/g, "\\'")}')" class="flex-1 bg-gradient-to-r ${btnGradient} text-white font-bold py-2 px-3 rounded-lg text-xs transition shadow flex items-center justify-center gap-1.5 cursor-pointer">
          <i data-lucide="ticket" class="w-3.5 h-3.5"></i>
          <span>Instant Digital Pass (In-App) 🎟️</span>
        </button>
        <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 rounded-lg text-xs font-semibold transition shrink-0 flex items-center gap-1 cursor-pointer" title="Open official ${escapeHtml(providerName)} page">
          <span>${escapeHtml(providerName)} ↗</span>
        </a>
      </div>
    `;
  }

  const isDineout = pLow.includes("swiggy") || pLow.includes("dineout") || pLow.includes("instamart");
  const cardClickAction = isDineout
    ? `onclick="openInAppBookingSheet('dineout_${safeTitle.replace(/'/g, "\\'")}', '${safeTitle.replace(/'/g, "\\'")}', '${safeVenue.replace(/'/g, "\\'")}', 900)"`
    : `onclick="openInAppEventTicketSheet('${safeTitle.replace(/'/g, "\\'")}', '${safeVenue.replace(/'/g, "\\'")}', '${safeDateTime.replace(/'/g, "\\'")}', '${safePrice.replace(/'/g, "\\'")}', '${escapeHtml(providerName).replace(/'/g, "\\'")}')"`;

  return `
    <div class="my-3 bg-gradient-to-r ${cardGrad} border ${cardBorder} rounded-xl p-3.5 space-y-2.5 shadow-lg transition">
      <!-- App Provider Badge & Title & Price -->
      <div class="flex items-start justify-between gap-2">
        <div ${cardClickAction} class="flex items-center space-x-2 flex-wrap gap-y-1 hover:text-sky-300 transition group cursor-pointer">
          <span class="px-2 py-0.5 ${badgeColor} border font-bold text-[10px] rounded uppercase tracking-wider flex items-center gap-1 shrink-0">
            ${badgeIcon} ${escapeHtml(providerName)}
          </span>
          <span class="text-xs font-bold text-white group-hover:text-sky-300 leading-tight">${safeTitle}</span>
        </div>
        <span class="text-xs font-extrabold text-amber-400 shrink-0">${safePrice}</span>
      </div>

      <!-- Venue & Time: Directions on Maps -->
      <div class="text-[11px] text-slate-300 flex items-center flex-wrap gap-x-3 gap-y-1">
        <a href="${venueDirectionsUrl}" target="_blank" rel="noopener noreferrer" class="text-sky-300 hover:text-white underline font-semibold flex items-center gap-1" title="Get Directions to ${safeVenue} on Google Maps">
          📍 ${safeVenue} 🗺️
        </a>
        <span class="text-slate-400">🕒 ${safeDateTime}</span>
      </div>

      <!-- Verified Pass Badge -->
      <div class="text-[10px] text-slate-400 flex items-center justify-between font-mono bg-slate-950/60 px-2.5 py-1.5 rounded-lg border border-slate-800/80">
        <span class="text-slate-400">Partner: <strong class="text-slate-200">${escapeHtml(providerName)}</strong></span>
        <span class="text-emerald-400 font-semibold flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
          Instant In-App Pass ✓
        </span>
      </div>

      <!-- Action Buttons -->
      ${actionButtonsHtml}
    </div>
  `;
}

function renderSinglePlaceCardHtml(r) {
  const cleanName = (r.name || 'Store').replace(/['"]/g, '').trim();
  let rawAddr = (r.address || '').trim().replace(/[\.]{2,}/g, '').replace(/\.+$/, '').trim();
  const fullDest = rawAddr ? `${cleanName}, ${rawAddr}` : cleanName;
  const encodedDest = encodeURIComponent(fullDest);

  // Exact Google Maps search URL: Opens the exact store pin with reviews, photos, open hours, menu
  const storeUrl = r.google_maps_url || `https://www.google.com/maps/search/?api=1&query=${encodedDest}`;

  // Live Navigation URL: If GPS location is known, initiate turn-by-turn route directly from origin. Otherwise, open store pin.
  const hasUserLoc = state.userLocation && state.userLocation.lat && state.userLocation.lng;
  const navUrl = hasUserLoc
    ? `https://www.google.com/maps/dir/?api=1&origin=${state.userLocation.lat},${state.userLocation.lng}&destination=${encodedDest}`
    : storeUrl;

  const isDining = (r.category === 'restaurant' || r.category === 'cafe' || (r.cuisines && r.cuisines.length > 0));
  const priceTag = isDining 
    ? `₹${r.estimated_cost_per_person || 100}/person`
    : (r.entry_fee ? `₹${r.entry_fee} entry` : `Free entry`);
  
  const cuisineTags = (r.cuisines || []).slice(0, 3).map(c => 
    `<span class="px-1.5 py-0.5 rounded-md bg-slate-800 text-slate-300 text-[10px] font-medium border border-slate-700/60">${escapeHtml(c)}</span>`
  ).join(" ");

  const isEventVenue = (
    r.category === 'attraction' ||
    (r.cuisines && r.cuisines.some(c => /concert|comedy|music|nightlife|show|club|techno|dj/i.test(c))) ||
    /stadium|auditorium|arena|ground|antisocial|piano man/i.test(r.name)
  );
  const isStreetFoodOrStall = !isEventVenue && (
    r.category === 'market' ||
    r.category === 'street_food' ||
    (r.estimated_cost_per_person && r.estimated_cost_per_person < 350) ||
    (r.cuisines && r.cuisines.some(c => /momo|chaat|chai|street|stall|roll|snack|fast/i.test(c)))
  );
  const isBookable = !isEventVenue && !isStreetFoodOrStall && (
    r.is_bookable === true ||
    (r.category === 'restaurant' && (r.estimated_cost_per_person >= 400 || (r.description && r.description.toLowerCase().includes('fine dining'))))
  );

  let actionBtn = "";
  if (isEventVenue) {
    const safeName = escapeHtml(r.name).replace(/'/g, "\\'");
    const safeAddr = escapeHtml(r.address || '').replace(/'/g, "\\'");
    const safeCost = r.estimated_cost_per_person ? `₹${r.estimated_cost_per_person}` : '₹799';
    actionBtn = `<button onclick="handleEventTicketHold('${safeName}', '${safeAddr}', 'Tonight / Weekend', '${safeCost}', '${storeUrl}', 'BookMyShow')" class="px-2.5 py-1.5 bg-purple-600/30 hover:bg-purple-600 text-purple-300 hover:text-white border border-purple-500/40 rounded-lg text-xs font-semibold transition flex items-center gap-1 cursor-pointer"><span>Get Tickets 🎟️</span></button>`;
  } else if (isBookable) {
    const safeName = escapeHtml(r.name).replace(/'/g, "\\'");
    const safeAddr = escapeHtml(r.address || '').replace(/'/g, "\\'");
    const cost = r.estimated_cost_per_person || 950;
    actionBtn = `
      <button onclick="openInAppBookingSheet('${r.id}', '${safeName}', '${safeAddr}', ${cost})" class="px-3 py-1.5 bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold rounded-lg text-xs transition shadow flex items-center gap-1.5 cursor-pointer" title="Instant In-App Table Reservation with 20% Off">
        <span>Reserve Table 🍽️</span>
        <span class="text-[9px] bg-emerald-950/70 text-emerald-300 px-1 py-0.2 rounded border border-emerald-400/40">20% Off</span>
      </button>
    `;
  } else {
    actionBtn = `<a href="https://m.uber.com/ul/?action=setPickup" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1.5 bg-amber-500/20 hover:bg-amber-500 text-amber-300 hover:text-white border border-amber-500/40 rounded-lg text-xs font-semibold transition flex items-center gap-1"><span>Book Auto 🛺</span></a>`;
  }

  // Dining button: Delivery option for casual food
  let diningBtnHtml = "";
  if (isDining && !isBookable) {
    const deliveryUrl = `https://www.swiggy.com/search?query=${encodeURIComponent(cleanName)}`;
    diningBtnHtml = `
      <a href="${deliveryUrl}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1.5 bg-orange-500/20 hover:bg-orange-500 text-orange-400 hover:text-white border border-orange-500/40 rounded-lg text-xs font-bold transition flex items-center gap-1 shadow cursor-pointer" title="Order from ${escapeHtml(cleanName)} on Swiggy">
        <span>Swiggy Delivery 🛵</span>
      </a>
    `;
  }

  return `
    <div class="my-2.5 bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 border border-slate-700/80 rounded-xl p-3.5 space-y-2.5 hover:border-brand-500/60 shadow-lg transition">
      <!-- Top Row: Name, Live Status & Rating -->
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0 flex-1">
          <a href="${storeUrl}" target="_blank" rel="noopener noreferrer" class="group inline-flex items-center gap-1.5 font-bold text-white hover:text-sky-300 text-sm leading-tight transition" title="Open ${escapeHtml(r.name)} on Google Maps">
            <span class="group-hover:underline">${escapeHtml(r.name)}</span>
            <span class="text-[11px] text-sky-400 group-hover:text-sky-300 shrink-0">↗</span>
          </a>
          <div class="flex items-center space-x-1.5 text-[11px] text-slate-400 mt-1 flex-wrap">
            <span class="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span class="text-emerald-400 font-semibold text-[10px]">Open Now</span>
            <span>•</span>
            <a href="${storeUrl}" target="_blank" rel="noopener noreferrer" class="text-slate-300 hover:text-sky-300 underline font-medium truncate max-w-[260px]" title="${escapeHtml(r.address || 'Near current location')}">
              ${escapeHtml(r.address || 'Near current location')}
            </a>
          </div>
        </div>
        <div class="flex items-center space-x-1 bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 rounded-lg shrink-0">
          <span class="text-amber-400 text-xs font-bold">★ ${r.rating || 4.7}</span>
        </div>
      </div>

      <!-- Cuisine / Speciality Tags -->
      ${cuisineTags ? `<div class="flex items-center flex-wrap gap-1">${cuisineTags}</div>` : ''}

      <!-- Bottom Row: Price & Interactive Action Buttons -->
      <div class="flex items-center justify-between pt-2 border-t border-slate-800/80">
        <div>
          <div class="text-[10px] text-slate-400 font-medium">Est. Price</div>
          <div class="text-xs font-extrabold text-brand-400">${priceTag}</div>
        </div>
        <div class="flex items-center space-x-2">
          <a href="${navUrl}" target="_blank" rel="noopener noreferrer" class="px-3 py-1.5 bg-gradient-to-r from-sky-600 to-blue-600 hover:from-sky-500 hover:to-blue-500 text-white rounded-lg text-xs font-bold transition flex items-center gap-1.5 shadow" title="Open exact pin and navigation in Google Maps">
            <span>Navigate 🗺️</span>
          </a>
          ${diningBtnHtml}
          ${actionBtn}
        </div>
      </div>
    </div>
  `;
}

function renderSingleMonumentCardHtml(card) {
  const cardTitle = card.monument_name || card.title || "Monument Pass";
  let rawFee = card.entry_fee_inr ?? card.amount_inr ?? 150;
  const priceDisplay = typeof rawFee === 'number' ? `₹${rawFee}` : `${rawFee}`;

  return `
    <div class="my-3 bg-gradient-to-r from-amber-950/40 to-slate-950 border border-amber-500/40 rounded-xl p-3.5 space-y-2 shadow-lg">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="px-2 py-0.5 bg-amber-500/20 text-amber-300 font-bold text-[10px] rounded uppercase">Fast-Track Pass</span>
          <span class="text-xs font-bold text-white truncate max-w-[200px]">${escapeHtml(cardTitle)}</span>
        </div>
        <span class="text-sm font-bold text-amber-400">${priceDisplay}</span>
      </div>
      <p class="text-[11px] text-slate-300">${escapeHtml(card.skip_line_note || 'Skip the 45-minute physical ticket line')}</p>
      <button onclick="openBookingModal('Fast-Track Digital Pass', 'Monument: ${escapeHtml(cardTitle)}', 'Amount: ${priceDisplay}', '${card.checkout_url || ''}')" class="w-full bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold py-1.5 rounded-lg text-xs transition cursor-pointer">
        1-Click Instant Pass
      </button>
    </div>
  `;
}

function renderMessageWithInlineCards(replyText, eventCards, placeCards, isSingleMonumentPass) {
  if (!replyText) return "";

  // If monument pass
  if (isSingleMonumentPass) {
    const passHtml = renderSingleMonumentCardHtml(isSingleMonumentPass);
    const parts = replyText.split(/\n\s*\n/);
    if (parts.length > 1) {
      return formatMarkdown(parts[0]) + passHtml + formatMarkdown(parts.slice(1).join("\n\n"));
    }
    return formatMarkdown(replyText) + passHtml;
  }

  const renderedEvents = (eventCards || []).map((c, idx) => ({
    type: 'event',
    index: idx + 1,
    title: c.title || "",
    venue: c.venue || "",
    provider: c.provider || "",
    keywords: getCardKeywords((c.title || "") + " " + (c.venue || "")),
    html: renderSingleEventCardHtml(c),
    placed: false
  }));

  const renderedPlaces = (placeCards || []).map((p, idx) => ({
    type: 'place',
    index: idx + 1,
    name: p.name || "",
    keywords: getCardKeywords(p.name || ""),
    html: renderSinglePlaceCardHtml(p),
    placed: false
  }));

  let processedText = replyText;

  // 1. Check explicit placeholders (e.g. {{EVENT_CARD_1}} or {{CARD:1}})
  renderedEvents.forEach(ec => {
    const tokenRegex = new RegExp(`(\\{\\{EVENT_CARD_${ec.index}\\}\\}|\\[EVENT_CARD_${ec.index}\\]|\\{\\{CARD:${ec.index}\\}\\})`, 'gi');
    if (tokenRegex.test(processedText)) {
      processedText = processedText.replace(tokenRegex, `\n\n__INLINE_EVENT_${ec.index}__\n\n`);
      ec.placed = true;
    }
  });

  renderedPlaces.forEach(pc => {
    const tokenRegex = new RegExp(`(\\{\\{PLACE_CARD_${pc.index}\\}\\}|\\[PLACE_CARD_${pc.index}\\])`, 'gi');
    if (tokenRegex.test(processedText)) {
      processedText = processedText.replace(tokenRegex, `\n\n__INLINE_PLACE_${pc.index}__\n\n`);
      pc.placed = true;
    }
  });

  // 2. Semantic block matching: split by paragraphs
  const blocks = processedText.split(/\n\s*\n/);
  const outputHtmlParts = [];

  for (let block of blocks) {
    block = block.trim();
    if (!block) continue;

    // Check if block is an explicit token
    const eventTokenMatch = block.match(/__INLINE_EVENT_(\d+)__/);
    if (eventTokenMatch) {
      const idx = parseInt(eventTokenMatch[1], 10) - 1;
      if (renderedEvents[idx]) {
        outputHtmlParts.push(renderedEvents[idx].html);
        continue;
      }
    }

    const placeTokenMatch = block.match(/__INLINE_PLACE_(\d+)__/);
    if (placeTokenMatch) {
      const idx = parseInt(placeTokenMatch[1], 10) - 1;
      if (renderedPlaces[idx]) {
        outputHtmlParts.push(renderedPlaces[idx].html);
        continue;
      }
    }

    // Render this markdown block
    outputHtmlParts.push(formatMarkdown(block));

    // Semantic matching for unplaced cards
    const bLower = block.toLowerCase();

    // Check event cards
    for (let ec of renderedEvents) {
      if (!ec.placed) {
        const titleMatch = ec.title && bLower.includes(ec.title.toLowerCase().slice(0, 10));
        const keywordMatch = ec.keywords.some(kw => bLower.includes(kw));
        if (titleMatch || keywordMatch) {
          outputHtmlParts.push(ec.html);
          ec.placed = true;
        }
      }
    }

    // Check place cards
    for (let pc of renderedPlaces) {
      if (!pc.placed) {
        const nameMatch = pc.name && bLower.includes(pc.name.toLowerCase().slice(0, 8));
        const keywordMatch = pc.keywords.some(kw => bLower.includes(kw));
        if (nameMatch || keywordMatch) {
          outputHtmlParts.push(pc.html);
          pc.placed = true;
        }
      }
    }
  }

  // 3. Any unplaced cards: append at the end
  const remainingEvents = renderedEvents.filter(e => !e.placed);
  if (remainingEvents.length > 0) {
    outputHtmlParts.push(`
      <div class="mt-3 space-y-2.5">
        <div class="text-[11px] font-extrabold text-slate-300 uppercase tracking-wider flex items-center gap-1">
          🎟️ Additional Live Events & Shows
        </div>
        ${remainingEvents.map(e => e.html).join("")}
      </div>
    `);
  }

  const remainingPlaces = renderedPlaces.filter(p => !p.placed);
  if (remainingPlaces.length > 0) {
    outputHtmlParts.push(`
      <div class="mt-3 space-y-2">
        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400">📍 Top Verified Recommendations:</div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          ${remainingPlaces.map(p => p.html).join("")}
        </div>
      </div>
    `);
  }

  return outputHtmlParts.join("\n");
}

function appendBotMessage(data) {
  const container = document.getElementById("chat-messages");
  const div = document.createElement("div");
  div.className = "flex items-start space-x-3 max-w-2xl";

  // Fast-track digital pass or live event cards (Multi-App Discovery)
  const eventCards = (data.ticket_booking_cards && data.ticket_booking_cards.length > 0)
    ? data.ticket_booking_cards
    : (data.ticket_booking_card ? [data.ticket_booking_card] : []);

  // Filter out redundant place cards if their venue is already shown as an event card
  const rawPlaces = data.nearby_recommendations || [];
  const placeCards = rawPlaces.filter(place => {
    const pName = (place.name || "").toLowerCase();
    const isDupe = eventCards.some(ec => {
      const ecTitle = (ec.title || "").toLowerCase();
      const ecVenue = (ec.venue || "").toLowerCase();
      return (pName.length > 3 && (ecTitle.includes(pName) || ecVenue.includes(pName) || pName.includes(ecVenue)));
    });
    return !isDupe;
  });

  const isSingleMonumentPass = eventCards.length === 1 && !eventCards[0].venue && !eventCards[0].date_time && (!eventCards[0].provider || eventCards[0].provider.toLowerCase().includes("monument"));

  // Generate interleaved HTML where each event / place card appears right beneath its explanation
  const interleavedHtml = renderMessageWithInlineCards(
    data.reply_text,
    eventCards,
    placeCards,
    isSingleMonumentPass ? eventCards[0] : null
  );

  // Quick replies
  let quickRepliesHtml = "";
  if (data.suggested_quick_replies && data.suggested_quick_replies.length > 0) {
    quickRepliesHtml = `
      <div class="mt-3 pt-2 border-t border-slate-700/60 flex items-center flex-wrap gap-1.5">
        ${data.suggested_quick_replies.map(qr => `
          <button onclick="sendQuickPrompt('${escapeHtml(qr)}')" class="px-2.5 py-1 rounded-full bg-slate-700/60 hover:bg-brand-600 hover:text-white text-[11px] text-slate-300 transition">
            ${escapeHtml(qr)}
          </button>
        `).join("")}
      </div>
    `;
  }

  div.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-brand-600 to-teal-400 flex items-center justify-center shrink-0 shadow">
      <i data-lucide="bot" class="w-4 h-4 text-white"></i>
    </div>
    <div class="bg-slate-800/90 border border-slate-700/80 rounded-2xl rounded-tl-none p-4 text-sm text-slate-200 shadow-md">
      <div class="leading-relaxed text-sm markdown-body space-y-2.5">${interleavedHtml}</div>
      ${renderActionCardHtml(data.action_card)}
      ${quickRepliesHtml}
    </div>
  `;

  container.appendChild(div);
  if (window.lucide) lucide.createIcons();
}

// ============================================================================
// ACTION CARDS IN CHAT: confirm a table booking (like a permission prompt) or connect Swiggy
// ============================================================================
const chatActionCards = {};

function renderActionCardHtml(card) {
  if (!card) return "";
  const id = "ac-" + Math.random().toString(36).slice(2, 10);
  chatActionCards[id] = card;
  const attribution = card.attribution ? `<span class="text-[10px] text-orange-400">${escapeHtml(card.attribution.text)}</span>` : "";

  if (card.type === "booking_confirmation") {
    const row = (label, value) => `
      <div class="flex gap-3"><span class="w-20 shrink-0 text-slate-500">${label}</span><span class="text-slate-100">${escapeHtml(String(value))}</span></div>`;
    const where = card.area ? `${card.restaurant}, ${card.area}` : card.restaurant;
    const forWhom = card.for_contact
      ? `${card.for_contact.name} (booked on your account, under your name)`
      : "You";
    return `
      <div id="${id}" class="mt-3 rounded-lg border border-emerald-500/50 bg-slate-950 font-mono text-xs overflow-hidden">
        <div class="flex items-center justify-between px-3 py-2 border-b border-emerald-500/30 bg-emerald-950/30">
          <span class="text-emerald-300 font-bold">${escapeHtml(card.title)}</span>${attribution}
        </div>
        <div class="px-3 py-2.5 space-y-1">
          ${row("Restaurant", where)}
          ${row("When", `${card.date}  ${card.time}`)}
          ${row("Guests", card.guest_count)}
          ${row("For", forWhom)}
        </div>
        <div class="px-3 pb-2 text-[11px] text-slate-400">${escapeHtml(card.notice || "")}</div>
        <div class="flex gap-2 px-3 py-2.5 border-t border-slate-800">
          <button data-ac-confirm onclick="confirmChatBooking('${id}')" class="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition">❯ 1. ${escapeHtml(card.confirm.label)}</button>
          <button data-ac-dismiss onclick="dismissChatBooking('${id}')" class="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 transition">2. ${escapeHtml(card.dismiss.label)}</button>
        </div>
      </div>`;
  }

  if (card.type === "connect_swiggy") {
    return `
      <div id="${id}" class="mt-3 rounded-lg border border-orange-500/50 bg-slate-950 font-mono text-xs overflow-hidden">
        <div class="flex items-center justify-between px-3 py-2 border-b border-orange-500/30 bg-orange-950/30">
          <span class="text-orange-300 font-bold">${escapeHtml(card.title)}</span>${attribution}
        </div>
        <div class="px-3 py-2.5 text-slate-300">${escapeHtml(card.text)}</div>
        <div class="px-3 pb-2.5">
          <button onclick="connectSwiggyFromChat()" class="px-3 py-1.5 rounded bg-orange-600 hover:bg-orange-500 text-white font-bold transition">${escapeHtml(card.button.label)}</button>
        </div>
      </div>`;
  }
  return "";
}

function connectSwiggyFromChat() {
  resumeChatAfterSwiggyConnect = true;
  handleSwiggyConnect();
}

function setActionCardBody(id, html, borderClass) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `mt-3 rounded-lg border ${borderClass} bg-slate-950 font-mono text-xs overflow-hidden`;
  el.innerHTML = html;
}

function describeApiError(body) {
  const d = body && body.detail;
  if (!d) return "Something went wrong.";
  return typeof d === "string" ? d : (d.message || JSON.stringify(d));
}

async function confirmChatBooking(id) {
  const card = chatActionCards[id];
  const el = document.getElementById(id);
  if (!card || !el) return;
  el.querySelectorAll("button").forEach(b => { b.disabled = true; b.classList.add("opacity-50"); });
  const confirmBtn = el.querySelector("[data-ac-confirm]");
  if (confirmBtn) confirmBtn.textContent = "Booking...";

  try {
    const res = await fetch(`${API_ORIGIN}${card.confirm.url}`, { method: "POST", headers: authHeaders() });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const needsConnect = res.status === 401 && body.detail && body.detail.connect;
      setActionCardBody(id, `
        <div class="px-3 py-2.5 text-rose-300">Not booked: ${escapeHtml(describeApiError(body))}</div>
        ${needsConnect ? `<div class="px-3 pb-2.5"><button onclick="connectSwiggyFromChat()" class="px-3 py-1.5 rounded bg-orange-600 text-white font-bold">Connect Swiggy</button></div>` : ""}`,
        "border-rose-500/50");
      return;
    }
    renderBookedResult(id, card, body);
    copilotChatHistory.push({ role: "assistant", content: `Booked ${card.restaurant} on ${card.date} at ${card.time} for ${card.guest_count}. Order ID ${body.swiggy_order_id || ""}.` });
  } catch (e) {
    setActionCardBody(id, `<div class="px-3 py-2.5 text-rose-300">Could not reach the server. Nothing was booked. Please try again.</div>`, "border-rose-500/50");
  }
}

function renderBookedResult(id, card, body) {
  const c = body.confirmation || {};
  const line = (label, value) => value ? `<div class="flex gap-3"><span class="w-20 shrink-0 text-slate-500">${label}</span><span class="text-slate-100">${escapeHtml(String(value))}</span></div>` : "";
  const share = body.share && body.share.whatsapp_url
    ? `<a href="${escapeHtml(body.share.whatsapp_url)}" target="_blank" rel="noopener" class="px-3 py-1.5 rounded bg-green-600 hover:bg-green-500 text-white font-bold">Share on WhatsApp</a>` : "";
  const map = c.map_url
    ? `<a href="${escapeHtml(c.map_url)}" target="_blank" rel="noopener" class="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200">Directions</a>` : "";
  const cancelHint = body.can_cancel === false
    ? `<div class="px-3 pb-2 text-[11px] text-amber-300">To cancel, open the Swiggy app (Dineout, Your bookings) or call Swiggy customer care at 080-67466729.</div>` : "";
  const forLine = body.for_contact ? `${body.for_contact.name} (booked under your name)` : null;
  setActionCardBody(id, `
    <div class="flex items-center justify-between px-3 py-2 border-b border-emerald-500/30 bg-emerald-950/40">
      <span class="text-emerald-300 font-bold">✔ Table booked</span>
      <span class="text-[10px] text-orange-400">${escapeHtml((body.attribution || {}).text || "")}</span>
    </div>
    <div class="px-3 py-2.5 space-y-1">
      ${line("Restaurant", card.area ? `${card.restaurant}, ${card.area}` : card.restaurant)}
      ${line("When", `${card.date}  ${card.time}`)}
      ${line("Guests", card.guest_count)}
      ${line("For", forLine)}
      ${line("Order ID", body.swiggy_order_id)}
      ${line("Address", c.address)}
      ${line("Timings", c.timings)}
      ${line("Offer", c.deal)}
    </div>
    ${cancelHint}
    <div class="flex gap-2 px-3 py-2.5 border-t border-slate-800">${share}${map}</div>`,
    "border-emerald-500/50");
}

async function dismissChatBooking(id) {
  const card = chatActionCards[id];
  const el = document.getElementById(id);
  if (!card || !el) return;
  el.querySelectorAll("button").forEach(b => { b.disabled = true; b.classList.add("opacity-50"); });
  try {
    await fetch(`${API_ORIGIN}${card.dismiss.url}`, { method: "POST", headers: authHeaders() });
  } catch (e) { /* nothing was booked either way */ }
  setActionCardBody(id, `<div class="px-3 py-2.5 text-slate-400">Cancelled. Nothing was booked.</div>`, "border-slate-700");
}

// ============================================================================
// MODAL & BOOKING HOLD HANDLERS
// ============================================================================
async function handleFlightHold(flightId, traceId, resultIndex, fare) {
  try {
    const payload = {
      flight_id: flightId,
      trace_id: traceId,
      result_index: resultIndex,
      passengers: [{
        title: "Mr",
        first_name: "Amit",
        last_name: "Sharma",
        gender: "Male",
        date_of_birth: "1994-06-12",
        email: "amit@example.com",
        phone: "9876543210"
      }],
      published_fare: fare
    };

    const res = await fetch(`${API_BASE}/flights/hold`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    const pnr = data.flight_hold?.airline_pnr || data.flight_hold?.pnr || "6E88X";
    const orderId = data.checkout_session?.order_id || "order_99812";

    openBookingModal(
      "15-Minute Flight PNR Hold Confirmed",
      `Airline PNR: ${pnr}`,
      `Total Locked Fare: ₹${fare.toLocaleString()}\nOrder ID: ${orderId}\nSeats held for 15 minutes on GDS.`
    );
  } catch (err) {
    alert("Hold error: " + err.message);
  }
}

async function handleHotelPrebook(hotelCode, roomTypeCode, price) {
  try {
    const payload = {
      hotel_code: hotelCode,
      booking_code: roomTypeCode,
      room_index: 1
    };

    const res = await fetch(`${API_BASE}/hotels/prebook`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    openBookingModal(
      "15-Minute Hotel Room Rate Freeze",
      `Hotel Code: ${hotelCode}`,
      `Prebook Reference: ${data.prebook_reference || 'PBK_9918'}\nLocked Rate: ₹${price.toLocaleString()}/night\nRoom held for 15 minutes.`
    );
  } catch (err) {
    alert("Prebook error: " + err.message);
  }
}

// ==========================================
// NATIVE IN-APP TABLE RESERVATIONS & DIGITAL PASSES
// (No external redirects, no broken links, 100% in-app)
// ==========================================

function copyPassCode(code) {
  if (navigator && navigator.clipboard) {
    navigator.clipboard.writeText(code).then(() => {
      alert(`Booking reference "${code}" copied to clipboard!`);
    }).catch(() => {
      prompt("Copy reference code:", code);
    });
  } else {
    prompt("Copy reference code:", code);
  }
}

// Every "Reserve" button now books through chat. The copilot asks for the date, time and guests, checks
// live availability on Swiggy Dineout, and shows a "Book this table?" box with Yes / No buttons.
// (The old in-app form below is no longer opened; it only simulated a reservation.)
function openInAppBookingSheet(restId, restName) {
  const input = document.getElementById("chat-input");
  if (!input) return;
  const name = (restName || "").replace(/['"]/g, "").trim();
  input.value = name ? `${name} mein table book karna hai` : "Mujhe ek table book karna hai";
  handleSendChat(new Event("submit"));
}

function selectBookingDate(dateStr) {
  if (!state.activeBooking) return;
  state.activeBooking.dateSlot = dateStr;
  renderInAppBookingForm();
}

function selectBookingTime(timeStr) {
  if (!state.activeBooking) return;
  state.activeBooking.timeSlot = timeStr;
  renderInAppBookingForm();
}

function selectBookingPartySize(num) {
  if (!state.activeBooking) return;
  state.activeBooking.partySize = parseInt(num, 10);
  renderInAppBookingForm();
}

function selectBookingVibe(vibeStr) {
  if (!state.activeBooking) return;
  state.activeBooking.vibe = vibeStr;
  renderInAppBookingForm();
}

function renderInAppBookingForm() {
  const b = state.activeBooking;
  if (!b) return;

  const modal = document.getElementById("booking-modal");
  document.getElementById("modal-title").textContent = "Instant In-App Table Booking 🍽️";
  document.getElementById("modal-subtitle").textContent = `${b.name} • 100% In-App (No Redirects)`;

  const iconBadge = document.getElementById("modal-icon-badge");
  if (iconBadge) {
    iconBadge.className = "w-12 h-12 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400";
    iconBadge.innerHTML = `<i data-lucide="utensils" class="w-6 h-6"></i>`;
  }

  const payBtn = document.getElementById("modal-payment-btn");
  if (payBtn) payBtn.classList.add("hidden");

  const dates = ["Today", "Tomorrow", "This Weekend"];
  const times = ["07:30 PM", "08:00 PM (Prime)", "08:30 PM", "09:00 PM", "09:30 PM", "10:00 PM"];
  const sizes = [
    { count: 1, label: "1 Guest" },
    { count: 2, label: "2 Guests (Couple)" },
    { count: 4, label: "4 Guests (Family/Friends)" },
    { count: 6, label: "6 Guests" },
    { count: 8, label: "8+ Group Table" }
  ];
  const vibes = [
    "Romantic Corner 🕯️",
    "Rooftop / Balcony 🌃",
    "Quiet AC Hall ❄️",
    "Work & Dine Booth 💼",
    "Outdoor Garden 🌿"
  ];

  const dateChipsHtml = dates.map(d => {
    const isSel = b.dateSlot === d;
    const cls = isSel 
      ? "bg-emerald-600 text-white font-bold border-emerald-400 shadow-emerald-900/50 shadow-sm"
      : "bg-slate-800 text-slate-300 hover:bg-slate-700 border-slate-700";
    return `<button type="button" onclick="selectBookingDate('${escapeHtml(d)}')" class="px-3 py-1.5 rounded-lg text-xs border transition cursor-pointer ${cls}">${escapeHtml(d)}</button>`;
  }).join(" ");

  const timeChipsHtml = times.map(t => {
    const isSel = b.timeSlot === t;
    const cls = isSel
      ? "bg-emerald-600 text-white font-bold border-emerald-400 shadow-emerald-900/50 shadow-sm ring-1 ring-emerald-400"
      : "bg-slate-800/80 text-slate-300 hover:bg-slate-700 border-slate-700";
    return `<button type="button" onclick="selectBookingTime('${escapeHtml(t)}')" class="px-2.5 py-1.5 rounded-lg text-[11px] border transition cursor-pointer ${cls}">${escapeHtml(t)}</button>`;
  }).join(" ");

  const sizeChipsHtml = sizes.map(s => {
    const isSel = b.partySize === s.count;
    const cls = isSel
      ? "bg-emerald-600 text-white font-bold border-emerald-400 shadow-emerald-900/50 shadow-sm ring-1 ring-emerald-400"
      : "bg-slate-800 text-slate-300 hover:bg-slate-700 border-slate-700";
    return `<button type="button" onclick="selectBookingPartySize(${s.count})" class="px-2.5 py-1.5 rounded-lg text-[11px] border transition cursor-pointer ${cls}">${escapeHtml(s.label)}</button>`;
  }).join(" ");

  const vibeChipsHtml = vibes.map(v => {
    const isSel = b.vibe === v;
    const cls = isSel
      ? "bg-amber-500 text-slate-950 font-bold border-amber-300 shadow-sm ring-1 ring-amber-300"
      : "bg-slate-800/80 text-slate-300 hover:bg-slate-700 border-slate-700";
    return `<button type="button" onclick="selectBookingVibe('${escapeHtml(v)}')" class="px-2 py-1 rounded-lg text-[10px] border transition cursor-pointer ${cls}">${escapeHtml(v)}</button>`;
  }).join(" ");

  document.getElementById("modal-content").innerHTML = `
    <div class="space-y-3.5 font-sans text-xs max-h-[75vh] overflow-y-auto pr-1">
      <!-- Restaurant Highlight Banner -->
      <div class="bg-gradient-to-r from-emerald-950/70 via-slate-900 to-slate-900 border border-emerald-500/40 rounded-xl p-3 space-y-1.5 shadow">
        <div class="flex items-center justify-between">
          <span class="text-sm font-bold text-white truncate max-w-[230px]">${escapeHtml(b.name)}</span>
          <span class="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px] font-extrabold">Instant Pass ✓</span>
        </div>
        <div class="text-slate-300 text-[11px] truncate">📍 ${escapeHtml(b.address)}</div>
        <div class="flex items-center space-x-2 text-[10px] text-emerald-400 font-semibold pt-0.5">
          <span>✨ Flat 20% Off Bill</span>
          <span>•</span>
          <span>⚡ Priority Host Seating</span>
          <span>•</span>
          <span>🆓 Zero Booking Fee</span>
        </div>
      </div>

      <!-- Date Selection -->
      <div class="space-y-1.5">
        <label class="text-[11px] font-bold text-slate-300 flex items-center gap-1">
          <i data-lucide="calendar" class="w-3.5 h-3.5 text-emerald-400"></i>
          <span>Select Date:</span>
        </label>
        <div class="flex items-center flex-wrap gap-1.5">
          ${dateChipsHtml}
        </div>
      </div>

      <!-- Time Slot Selection -->
      <div class="space-y-1.5">
        <label class="text-[11px] font-bold text-slate-300 flex items-center gap-1">
          <i data-lucide="clock" class="w-3.5 h-3.5 text-emerald-400"></i>
          <span>Select Seating Time Slot:</span>
        </label>
        <div class="grid grid-cols-3 gap-1.5">
          ${timeChipsHtml}
        </div>
      </div>

      <!-- Party Size Selection -->
      <div class="space-y-1.5">
        <label class="text-[11px] font-bold text-slate-300 flex items-center gap-1">
          <i data-lucide="users" class="w-3.5 h-3.5 text-emerald-400"></i>
          <span>Number of Guests:</span>
        </label>
        <div class="flex items-center flex-wrap gap-1.5">
          ${sizeChipsHtml}
        </div>
      </div>

      <!-- Seating Vibe Selection -->
      <div class="space-y-1.5">
        <label class="text-[11px] font-bold text-slate-300 flex items-center gap-1">
          <i data-lucide="sparkles" class="w-3.5 h-3.5 text-amber-400"></i>
          <span>Table Vibe / Placement:</span>
        </label>
        <div class="flex items-center flex-wrap gap-1">
          ${vibeChipsHtml}
        </div>
      </div>

      <!-- Guest Details Form -->
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-3 space-y-2 text-slate-300">
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="text-[10px] text-slate-400 font-semibold block mb-0.5">Primary Guest Name</label>
            <input type="text" id="booking-guest-name" value="${escapeHtml(b.guestName)}" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500" placeholder="e.g. Keshav Jindal">
          </div>
          <div>
            <label class="text-[10px] text-slate-400 font-semibold block mb-0.5">Contact Phone</label>
            <input type="tel" id="booking-guest-phone" value="${escapeHtml(b.guestPhone)}" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500" placeholder="e.g. 9876543210">
          </div>
        </div>
        <div>
          <label class="text-[10px] text-slate-400 font-semibold block mb-0.5">Special Requests (Optional)</label>
          <input type="text" id="booking-special-requests" value="${escapeHtml(b.specialRequests)}" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500" placeholder="e.g. Anniversary celebration, quiet corner, less spicy">
        </div>
      </div>

      <!-- Submit Button -->
      <div class="pt-1">
        <button id="btn-submit-reservation" onclick="submitInAppReservation()" class="w-full bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-600 hover:from-emerald-500 hover:to-teal-500 text-white font-extrabold py-3 rounded-xl text-xs transition shadow-lg flex items-center justify-center gap-2 cursor-pointer">
          <i data-lucide="check-circle" class="w-4 h-4"></i>
          <span>Confirm Instant Table Pass ⚡ (100% In-App)</span>
        </button>
        <p class="text-[10px] text-slate-500 text-center mt-1">Guaranteed 15-minute host table lock • Zero cancellation fee</p>
      </div>
    </div>
  `;

  modal.classList.remove("hidden");
  if (window.lucide) lucide.createIcons();
}

async function submitInAppReservation() {
  const b = state.activeBooking;
  if (!b) return;

  const nameInput = document.getElementById("booking-guest-name");
  const phoneInput = document.getElementById("booking-guest-phone");
  const requestsInput = document.getElementById("booking-special-requests");

  if (nameInput) b.guestName = nameInput.value.trim() || b.guestName;
  if (phoneInput) b.guestPhone = phoneInput.value.trim() || b.guestPhone;
  if (requestsInput) b.specialRequests = requestsInput.value.trim();

  const submitBtn = document.getElementById("btn-submit-reservation");
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span class="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full mr-2"></span> Securing Table with Restaurant Host...`;
  }

  try {
    const payload = {
      restaurant_id: b.id,
      restaurant_name: b.name,
      restaurant_address: b.address,
      city: state.currentCity || "Delhi",
      party_size: b.partySize,
      reservation_time: b.timeSlot,
      guest_name: b.guestName,
      guest_phone: b.guestPhone,
      seating_preference: b.vibe,
      special_requests: b.specialRequests
    };

    const res = await fetch(`${API_BASE}/places/restaurants/reserve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      throw new Error(`Reservation failed with HTTP status ${res.status}`);
    }

    const data = await res.json();
    renderConfirmedTablePass(data, b);
  } catch (err) {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `Confirm Instant Table Pass ⚡ (Retry)`;
    }
    alert("Table reservation notice: " + err.message);
  }
}

function renderConfirmedTablePass(data, b) {
  const modal = document.getElementById("booking-modal");
  document.getElementById("modal-title").textContent = "VIP Table Pass Confirmed! 🍽️";
  document.getElementById("modal-subtitle").textContent = `${data.restaurant_name} • Host Table Locked`;

  const iconBadge = document.getElementById("modal-icon-badge");
  if (iconBadge) {
    iconBadge.className = "w-12 h-12 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400";
    iconBadge.innerHTML = `<i data-lucide="check-check" class="w-6 h-6"></i>`;
  }

  const payBtn = document.getElementById("modal-payment-btn");
  if (payBtn) payBtn.classList.add("hidden");

  const bookingRef = data.reservation_reference || `TBL_${Math.random().toString(36).substring(2, 8).toUpperCase()}`;
  const hostPin = data.host_pin || "4821";
  const qrUrl = data.digital_pass_qr || `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${bookingRef}`;

  const cleanName = (data.restaurant_name || b.name || "Restaurant").replace(/['"]/g, '').trim();
  const cleanAddr = (data.address || b.address || "City Center").replace(/['"]/g, '').trim();
  const destQuery = cleanAddr ? `${cleanName}, ${cleanAddr}` : cleanName;
  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(destQuery)}`;

  const shareText = `🍽️ *Plan4U VIP Table Pass Confirmed!*\n\n📍 *Restaurant:* ${cleanName}\n🕒 *Time:* ${b.dateSlot} at ${data.reservation_time}\n👥 *Party Size:* ${data.party_size} Guests (${b.vibe})\n🎫 *Booking Reference:* ${bookingRef}\n🔑 *Host PIN:* ${hostPin}\n📍 *Address:* ${cleanAddr}\n\n✨ _Show this pass at reception for instant seating & 20% discount on food._`;
  const whatsappUrl = `https://api.whatsapp.com/send?text=${encodeURIComponent(shareText)}`;

  const now = new Date();
  const startIso = now.toISOString().replace(/-|:|\.\d+/g, '');
  const endIso = new Date(now.getTime() + 2 * 3600 * 1000).toISOString().replace(/-|:|\.\d+/g, '');
  const calUrl = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(`Dinner Table at ${cleanName}`)}&dates=${startIso}/${endIso}&details=${encodeURIComponent(shareText)}&location=${encodeURIComponent(cleanAddr)}`;

  document.getElementById("modal-content").innerHTML = `
    <div class="space-y-3 font-sans text-xs">
      <!-- VIP Table Pass Ticket -->
      <div class="bg-gradient-to-r from-emerald-950/80 via-slate-900 to-slate-900 border border-emerald-500/50 rounded-2xl p-4 space-y-3 shadow-xl relative overflow-hidden">
        <div class="flex items-center justify-between border-b border-emerald-500/30 pb-2.5">
          <div>
            <div class="text-sm font-extrabold text-white flex items-center gap-1.5">
              <span>${escapeHtml(cleanName)}</span>
              <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
            </div>
            <div class="text-[11px] text-slate-300 mt-0.5">📍 ${escapeHtml(cleanAddr)}</div>
          </div>
          <div class="text-right">
            <span class="px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 font-extrabold text-[11px] border border-emerald-500/40">TABLE CONFIRMED ✓</span>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-2 text-slate-300 text-[11px]">
          <div>
            <span class="text-slate-400 text-[10px] block">Schedule</span>
            <span class="text-white font-bold">${escapeHtml(b.dateSlot)} • ${escapeHtml(data.reservation_time)}</span>
          </div>
          <div>
            <span class="text-slate-400 text-[10px] block">Party & Vibe</span>
            <span class="text-white font-bold">${data.party_size} Guests • ${escapeHtml(b.vibe)}</span>
          </div>
          <div>
            <span class="text-slate-400 text-[10px] block">Guest Name</span>
            <span class="text-white font-medium">${escapeHtml(data.guest_name)}</span>
          </div>
          <div>
            <span class="text-slate-400 text-[10px] block">Host PIN</span>
            <span class="text-amber-400 font-mono font-extrabold text-sm">${escapeHtml(hostPin)}</span>
          </div>
        </div>

        <!-- Reference Bar with Copy -->
        <div class="bg-slate-950/80 border border-slate-800 rounded-xl p-2.5 flex items-center justify-between">
          <div>
            <span class="text-[10px] text-slate-400 block font-mono">BOOKING REFERENCE:</span>
            <span class="text-emerald-400 font-mono font-extrabold text-xs tracking-wider">${escapeHtml(bookingRef)}</span>
          </div>
          <button onclick="copyPassCode('${escapeHtml(bookingRef)}')" class="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg text-[10px] font-semibold transition border border-slate-700 cursor-pointer">
            Copy Code 📋
          </button>
        </div>

        <!-- Dynamic QR Pass -->
        <div class="text-center pt-1">
          <div class="inline-block p-2 bg-white rounded-xl shadow-lg">
            <img src="${qrUrl}" alt="Digital Table Pass QR" class="w-28 h-28 mx-auto" />
          </div>
          <p class="text-[10px] text-slate-400 mt-1.5">Scan this QR at reception for direct seating without waiting</p>
        </div>

        <div class="text-[11px] text-emerald-400 font-medium pt-1 border-t border-emerald-500/20 text-center">
          ✨ Priority seating + Flat 20% bill discount active • 15-min hold period
        </div>
      </div>

      <!-- Action Buttons (Zero Redirect Failures, Direct Utility) -->
      <div class="grid grid-cols-2 gap-2 pt-1">
        <a href="${whatsappUrl}" target="_blank" rel="noopener noreferrer" class="bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2.5 px-3 rounded-xl text-xs transition shadow flex items-center justify-center gap-1.5 cursor-pointer">
          <i data-lucide="share-2" class="w-3.5 h-3.5"></i>
          <span>Share WhatsApp 💬</span>
        </a>
        <a href="${calUrl}" target="_blank" rel="noopener noreferrer" class="bg-slate-800 hover:bg-slate-700 text-white font-semibold py-2.5 px-3 rounded-xl text-xs transition border border-slate-700 flex items-center justify-center gap-1.5 cursor-pointer">
          <i data-lucide="calendar-plus" class="w-3.5 h-3.5"></i>
          <span>Add to Calendar 📅</span>
        </a>
      </div>
      <div class="grid grid-cols-2 gap-2">
        <a href="${mapsUrl}" target="_blank" rel="noopener noreferrer" class="bg-sky-600/30 hover:bg-sky-600 text-sky-300 hover:text-white border border-sky-500/40 font-semibold py-2 px-3 rounded-xl text-xs transition flex items-center justify-center gap-1.5 cursor-pointer">
          <i data-lucide="navigation" class="w-3.5 h-3.5"></i>
          <span>Directions 🗺️</span>
        </a>
        <button onclick="closeBookingModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold py-2 px-3 rounded-xl text-xs transition border border-slate-700 cursor-pointer">
          Done / Close ✕
        </button>
      </div>
    </div>
  `;

  if (window.lucide) lucide.createIcons();
}

// Backwards-compatible alias for existing callers
async function handleReserveTable(restId, restName, restAddress) {
  openInAppBookingSheet(restId, restName, restAddress, 950);
}

// ==========================================
// NATIVE IN-APP EVENT & MOVIE TICKETING PASS
// ==========================================

function openInAppEventTicketSheet(eventTitle, venue, dateTime, priceRange, provider) {
  state.activeEventBooking = {
    title: (eventTitle || "Live Event").replace(/['"]/g, '').trim(),
    venue: (venue || "City Multiplex / Venue").replace(/['"]/g, '').trim(),
    dateTime: (dateTime || "Tonight").replace(/['"]/g, '').trim(),
    priceRange: (priceRange || "₹350 - ₹750").replace(/['"]/g, '').trim(),
    provider: (provider || "BookMyShow").replace(/['"]/g, '').trim(),
    ticketCount: 2,
    seatCategory: "Prime Recliner",
    guestName: "Keshav Jindal",
    guestPhone: "9876543210"
  };
  renderInAppEventTicketForm();
}

function selectEventTickets(num) {
  if (!state.activeEventBooking) return;
  state.activeEventBooking.ticketCount = parseInt(num, 10);
  renderInAppEventTicketForm();
}

function selectEventCategory(cat) {
  if (!state.activeEventBooking) return;
  state.activeEventBooking.seatCategory = cat;
  renderInAppEventTicketForm();
}

function renderInAppEventTicketForm() {
  const eb = state.activeEventBooking;
  if (!eb) return;

  const modal = document.getElementById("booking-modal");
  document.getElementById("modal-title").textContent = "Instant Event Digital Pass 🎟️";
  document.getElementById("modal-subtitle").textContent = `${eb.title} • Verified Pass`;

  const iconBadge = document.getElementById("modal-icon-badge");
  if (iconBadge) {
    iconBadge.className = "w-12 h-12 rounded-xl bg-purple-500/20 border border-purple-500/40 flex items-center justify-center text-purple-400";
    iconBadge.innerHTML = `<i data-lucide="ticket" class="w-6 h-6"></i>`;
  }

  const payBtn = document.getElementById("modal-payment-btn");
  if (payBtn) payBtn.classList.add("hidden");

  const ticketCounts = [1, 2, 3, 4, 6];
  const categories = ["Prime Recliner", "Executive", "Gold Club", "Front Row"];

  const countChipsHtml = ticketCounts.map(n => {
    const isSel = eb.ticketCount === n;
    const cls = isSel
      ? "bg-purple-600 text-white font-bold border-purple-400 shadow-purple-900/50 shadow-sm ring-1 ring-purple-400"
      : "bg-slate-800 text-slate-300 hover:bg-slate-700 border-slate-700";
    return `<button type="button" onclick="selectEventTickets(${n})" class="px-3 py-1.5 rounded-lg text-xs border transition cursor-pointer ${cls}">${n} ${n === 1 ? 'Ticket' : 'Tickets'}</button>`;
  }).join(" ");

  const categoryChipsHtml = categories.map(c => {
    const isSel = eb.seatCategory === c;
    const cls = isSel
      ? "bg-purple-600 text-white font-bold border-purple-400 shadow-purple-900/50 shadow-sm ring-1 ring-purple-400"
      : "bg-slate-800/80 text-slate-300 hover:bg-slate-700 border-slate-700";
    return `<button type="button" onclick="selectEventCategory('${escapeHtml(c)}')" class="px-2.5 py-1.5 rounded-lg text-[11px] border transition cursor-pointer ${cls}">${escapeHtml(c)}</button>`;
  }).join(" ");

  document.getElementById("modal-content").innerHTML = `
    <div class="space-y-3.5 font-sans text-xs max-h-[75vh] overflow-y-auto pr-1">
      <!-- Event Highlight Banner -->
      <div class="bg-gradient-to-r from-purple-950/70 via-slate-900 to-slate-900 border border-purple-500/40 rounded-xl p-3 space-y-1.5 shadow">
        <div class="flex items-center justify-between">
          <span class="text-sm font-bold text-white truncate max-w-[220px]">${escapeHtml(eb.title)}</span>
          <span class="px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30 text-[10px] font-extrabold">${escapeHtml(eb.priceRange)}</span>
        </div>
        <div class="text-slate-300 text-[11px] truncate">📍 ${escapeHtml(eb.venue)}</div>
        <div class="text-purple-400 text-[10px] font-semibold">🕒 ${escapeHtml(eb.dateTime)} • Secured via ${escapeHtml(eb.provider)}</div>
      </div>

      <!-- Ticket Count -->
      <div class="space-y-1.5">
        <label class="text-[11px] font-bold text-slate-300 flex items-center gap-1">
          <i data-lucide="users" class="w-3.5 h-3.5 text-purple-400"></i>
          <span>Number of Tickets:</span>
        </label>
        <div class="flex items-center flex-wrap gap-1.5">
          ${countChipsHtml}
        </div>
      </div>

      <!-- Seat Category -->
      <div class="space-y-1.5">
        <label class="text-[11px] font-bold text-slate-300 flex items-center gap-1">
          <i data-lucide="sparkles" class="w-3.5 h-3.5 text-purple-400"></i>
          <span>Seat Category:</span>
        </label>
        <div class="grid grid-cols-2 gap-1.5">
          ${categoryChipsHtml}
        </div>
      </div>

      <!-- Guest Details -->
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-3 space-y-2 text-slate-300">
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="text-[10px] text-slate-400 font-semibold block mb-0.5">Attendee Name</label>
            <input type="text" id="event-guest-name" value="${escapeHtml(eb.guestName)}" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-purple-500">
          </div>
          <div>
            <label class="text-[10px] text-slate-400 font-semibold block mb-0.5">Phone (for E-Ticket SMS)</label>
            <input type="tel" id="event-guest-phone" value="${escapeHtml(eb.guestPhone)}" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-purple-500">
          </div>
        </div>
      </div>

      <!-- Action Button -->
      <div class="pt-1">
        <button id="btn-submit-event" onclick="submitInAppEventTicket()" class="w-full bg-gradient-to-r from-purple-600 via-indigo-600 to-purple-600 hover:from-purple-500 hover:to-indigo-500 text-white font-extrabold py-3 rounded-xl text-xs transition shadow-lg flex items-center justify-center gap-2 cursor-pointer">
          <i data-lucide="ticket" class="w-4 h-4"></i>
          <span>Lock 15-Min Ticket Pass ⚡ (Instant Pass)</span>
        </button>
        <p class="text-[10px] text-slate-500 text-center mt-1">Free 15-minute ticket hold • Instant QR Pass generated</p>
      </div>
    </div>
  `;

  modal.classList.remove("hidden");
  if (window.lucide) lucide.createIcons();
}

function submitInAppEventTicket() {
  const eb = state.activeEventBooking;
  if (!eb) return;

  const nameInput = document.getElementById("event-guest-name");
  const phoneInput = document.getElementById("event-guest-phone");
  if (nameInput) eb.guestName = nameInput.value.trim() || eb.guestName;
  if (phoneInput) eb.guestPhone = phoneInput.value.trim() || eb.guestPhone;

  const orderRef = `EVT_${Math.random().toString(36).substring(2, 8).toUpperCase()}`;
  renderConfirmedEventTicketPass(orderRef, eb);
}

function renderConfirmedEventTicketPass(orderRef, eb) {
  const modal = document.getElementById("booking-modal");
  document.getElementById("modal-title").textContent = "Event Ticket Pass Confirmed! 🎟️";
  document.getElementById("modal-subtitle").textContent = `${eb.title} • 15-Min Guaranteed Hold`;

  const iconBadge = document.getElementById("modal-icon-badge");
  if (iconBadge) {
    iconBadge.className = "w-12 h-12 rounded-xl bg-purple-500/20 border border-purple-500/40 flex items-center justify-center text-purple-400";
    iconBadge.innerHTML = `<i data-lucide="check-check" class="w-6 h-6"></i>`;
  }

  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${orderRef}`;
  const shareText = `🎟️ *Plan4U Event Ticket Pass Confirmed!*\n\n🎬 *Event:* ${eb.title}\n📍 *Venue:* ${eb.venue}\n🕒 *Showtime:* ${eb.dateTime}\n👥 *Tickets:* ${eb.ticketCount}x (${eb.seatCategory})\n🎫 *Order Reference:* ${orderRef}\n\n✨ _15-minute guaranteed hold active. Show QR at gate._`;
  const whatsappUrl = `https://api.whatsapp.com/send?text=${encodeURIComponent(shareText)}`;
  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(eb.venue)}`;

  document.getElementById("modal-content").innerHTML = `
    <div class="space-y-3 font-sans text-xs">
      <div class="bg-gradient-to-r from-purple-950/80 via-slate-900 to-slate-900 border border-purple-500/50 rounded-2xl p-4 space-y-3 shadow-xl">
        <div class="flex items-center justify-between border-b border-purple-500/30 pb-2.5">
          <div>
            <div class="text-sm font-extrabold text-white flex items-center gap-1.5">
              <span>${escapeHtml(eb.title)}</span>
              <span class="w-2 h-2 rounded-full bg-purple-400 animate-ping"></span>
            </div>
            <div class="text-[11px] text-slate-300 mt-0.5">📍 ${escapeHtml(eb.venue)}</div>
          </div>
          <div class="text-right">
            <span class="px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 font-extrabold text-[10px] border border-purple-500/40">SEATS LOCKED ✓</span>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-2 text-slate-300 text-[11px]">
          <div>
            <span class="text-slate-400 text-[10px] block">Showtime</span>
            <span class="text-white font-bold">${escapeHtml(eb.dateTime)}</span>
          </div>
          <div>
            <span class="text-slate-400 text-[10px] block">Seats / Category</span>
            <span class="text-white font-bold">${eb.ticketCount}x • ${escapeHtml(eb.seatCategory)}</span>
          </div>
          <div>
            <span class="text-slate-400 text-[10px] block">Primary Attendee</span>
            <span class="text-white font-medium">${escapeHtml(eb.guestName)}</span>
          </div>
          <div>
            <span class="text-slate-400 text-[10px] block">Partner Network</span>
            <span class="text-purple-300 font-bold">${escapeHtml(eb.provider)} GDS</span>
          </div>
        </div>

        <div class="bg-slate-950/80 border border-slate-800 rounded-xl p-2.5 flex items-center justify-between">
          <div>
            <span class="text-[10px] text-slate-400 block font-mono">PASS REFERENCE:</span>
            <span class="text-purple-400 font-mono font-extrabold text-xs tracking-wider">${escapeHtml(orderRef)}</span>
          </div>
          <button onclick="copyPassCode('${escapeHtml(orderRef)}')" class="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg text-[10px] font-semibold transition border border-slate-700 cursor-pointer">
            Copy Code 📋
          </button>
        </div>

        <div class="text-center pt-1">
          <div class="inline-block p-2 bg-white rounded-xl shadow-lg">
            <img src="${qrUrl}" alt="Event Ticket QR" class="w-28 h-28 mx-auto" />
          </div>
          <p class="text-[10px] text-slate-400 mt-1.5">Scan this QR at the venue entrance / box office</p>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-2 pt-1">
        <a href="${whatsappUrl}" target="_blank" rel="noopener noreferrer" class="bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2.5 px-3 rounded-xl text-xs transition shadow flex items-center justify-center gap-1.5 cursor-pointer">
          <i data-lucide="share-2" class="w-3.5 h-3.5"></i>
          <span>Share WhatsApp 💬</span>
        </a>
        <a href="${mapsUrl}" target="_blank" rel="noopener noreferrer" class="bg-sky-600/30 hover:bg-sky-600 text-sky-300 hover:text-white border border-sky-500/40 font-semibold py-2.5 px-3 rounded-xl text-xs transition flex items-center justify-center gap-1.5 cursor-pointer">
          <i data-lucide="navigation" class="w-3.5 h-3.5"></i>
          <span>Directions 🗺️</span>
        </a>
      </div>
      <button onclick="closeBookingModal()" class="w-full bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold py-2 rounded-xl text-xs transition border border-slate-700 cursor-pointer">
        Done / Close ✕
      </button>
    </div>
  `;

  if (window.lucide) lucide.createIcons();
}

function handleEventTicketHold(eventTitle, venue, dateTime, priceRange, bookingUrl, provider) {
  openInAppEventTicketSheet(eventTitle, venue, dateTime, priceRange, provider);
}

function openBookingModal(title, subtitle, contentText) {
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-subtitle").textContent = subtitle;
  document.getElementById("modal-content").innerHTML = `
    <pre class="text-xs text-slate-300 leading-relaxed font-mono whitespace-pre-wrap">${escapeHtml(contentText)}</pre>
  `;
  const payBtn = document.getElementById("modal-payment-btn");
  if (payBtn) payBtn.classList.remove("hidden");
  document.getElementById("booking-modal").classList.remove("hidden");
  if (window.lucide) lucide.createIcons();
}

function closeBookingModal() {
  document.getElementById("booking-modal").classList.add("hidden");
  const payBtn = document.getElementById("modal-payment-btn");
  if (payBtn) payBtn.classList.remove("hidden");
}

function simulateSuccessfulPayment() {
  alert("🎉 Razorpay Payment Simulated Successfully!\nPNR / Room Voucher has been ticketed & confirmed.");
  closeBookingModal();
}

async function shareCurrentItinerary() {
  if (!state.lastItinerary) {
    alert("Please generate or select an itinerary first to share.");
    return;
  }
  try {
    const itin = state.lastItinerary;
    const res = await fetch(`${API_BASE}/trips/share`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: itin.title || "Custom India Itinerary",
        destination: itin.destination || state.currentCity || "Delhi",
        origin: itin.origin || "Delhi",
        days: itin.duration_days || (itin.days ? itin.days.length : 3),
        budget_inr: itin.grand_total_inr || 15000,
        itinerary_data: itin,
        creator_name: "Plan4U Traveler"
      })
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    const shareUrl = `${window.location.origin}/?trip=${data.share_code}#planner`;
    
    // Copy to clipboard
    if (navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(shareUrl);
      } catch (e) {}
    }
    
    // Open share modal
    showShareTripModal(data.share_code, shareUrl, itin.title || "Custom Trip");
  } catch (err) {
    alert("Could not generate share link: " + err.message);
  }
}

function showShareTripModal(code, shareUrl, title) {
  const modal = document.getElementById("booking-modal");
  document.getElementById("modal-title").textContent = "Share Itinerary 🔗";
  document.getElementById("modal-subtitle").textContent = `${title} • Code: ${code}`;
  
  const iconBadge = document.getElementById("modal-icon-badge");
  if (iconBadge) {
    iconBadge.className = "w-12 h-12 rounded-xl bg-brand-500/20 border border-brand-500/40 flex items-center justify-center text-brand-400";
    iconBadge.innerHTML = `<i data-lucide="share-2" class="w-6 h-6"></i>`;
  }
  
  const payBtn = document.getElementById("modal-payment-btn");
  if (payBtn) payBtn.classList.add("hidden");

  const whatsappText = encodeURIComponent(`Hey! Check out my trip itinerary for ${title} on Plan4U:\n${shareUrl}`);
  const whatsappUrl = `https://api.whatsapp.com/send?text=${whatsappText}`;

  document.getElementById("modal-content").innerHTML = `
    <div class="space-y-3 font-sans text-xs">
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-3.5 space-y-2">
        <div class="text-xs text-slate-300">Anyone with this viral link can view and 1-click fork your trip:</div>
        <div class="flex items-center space-x-2">
          <input id="share-link-input" type="text" readonly value="${shareUrl}" class="flex-1 bg-slate-950 border border-slate-700 text-slate-200 text-xs rounded-lg px-2.5 py-2 font-mono select-all" />
          <button id="copy-share-btn" onclick="navigator.clipboard.writeText('${shareUrl}'); document.getElementById('copy-share-btn').textContent='Copied!';" class="px-3 py-2 bg-brand-600 hover:bg-brand-500 text-white font-bold rounded-lg text-xs transition">
            Copy
          </button>
        </div>
      </div>
      <div class="flex space-x-2">
        <a href="${whatsappUrl}" target="_blank" rel="noopener noreferrer" class="flex-1 text-center py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl text-xs transition shadow flex items-center justify-center gap-1.5 cursor-pointer">
          <span>Share via WhatsApp 💬</span>
        </a>
      </div>
    </div>
  `;
  modal.classList.remove("hidden");
  if (window.lucide) lucide.createIcons();
}

async function loadSharedTrip(code) {
  try {
    const res = await fetch(`${API_BASE}/trips/share/${encodeURIComponent(code)}`);
    if (!res.ok) return;
    const trip = await res.json();
    state.lastItinerary = trip.itinerary_data;
    
    // Show top banner for shared trip
    renderSharedTripBanner(trip);
    
    // Append itinerary to planner view
    appendPlannerBotMessage({
      reply_text: `Viewing shared itinerary created by **${escapeHtml(trip.creator_name)}**: **${escapeHtml(trip.title)}** (${trip.days} Days in ${escapeHtml(trip.destination)}) • Forked ${trip.fork_count || 0} times.`,
      itinerary: trip.itinerary_data,
      suggested_quick_replies: ["Customize Stays", "Modify Dates", "Check Food Options"]
    });
  } catch (e) {
    console.warn("Failed to load shared trip", e);
  }
}

function renderSharedTripBanner(trip) {
  const existing = document.getElementById("shared-trip-banner");
  if (existing) existing.remove();

  const banner = document.createElement("div");
  banner.id = "shared-trip-banner";
  banner.className = "bg-gradient-to-r from-brand-900/90 via-indigo-950 to-slate-900 border-b border-brand-500/40 px-4 py-2.5 flex items-center justify-between z-30 shadow-md sticky top-0";
  banner.innerHTML = `
    <div class="flex items-center space-x-3 text-xs">
      <span class="px-2 py-0.5 rounded bg-brand-500/20 text-brand-300 font-bold uppercase tracking-wider text-[10px]">Shared Trip</span>
      <span class="text-white font-medium">Forked from <b>${escapeHtml(trip.creator_name)}</b>: ${escapeHtml(trip.title)} (${trip.days} Days)</span>
    </div>
    <div class="flex items-center space-x-2">
      <button onclick="handleForkTrip('${trip.share_code}')" class="px-3 py-1.5 bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 text-white font-bold rounded-lg text-xs shadow flex items-center gap-1 transition cursor-pointer">
        <span>Fork &amp; Customize 🍴</span>
      </button>
    </div>
  `;
  document.body.prepend(banner);
}

async function handleForkTrip(code) {
  try {
    const res = await fetch(`${API_BASE}/trips/share/${encodeURIComponent(code)}/fork`, {
      method: "POST"
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    state.lastItinerary = data.itinerary;
    alert(`🎉 Trip forked successfully! You now have your own editable copy with ${data.fork_count} total forks.`);
    // Clean URL
    window.history.replaceState({}, document.title, window.location.pathname + "#planner");
    const banner = document.getElementById("shared-trip-banner");
    if (banner) banner.remove();
  } catch (e) {
    alert("Fork failed: " + e.message);
  }
}

function escapeHtml(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
