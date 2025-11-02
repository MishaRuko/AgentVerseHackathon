import { ref, computed, watchEffect } from 'vue';

const ACCESS_TOKEN = "agent-prota25!";

// 'local' or 'remote'
const BACKEND_ENV = 'local';

const BACKEND_CONFIG = {
  local: {
    API_URL: 'http://localhost:8000',
    WS_URL: 'ws://localhost:8000/ws',
  },
  remote: {
    API_URL: 'https://protalab.dev:8447',
    WS_URL: 'wss://protalab.dev:8447/ws',
  },
};

const { API_URL, WS_URL } = BACKEND_CONFIG[BACKEND_ENV] || BACKEND_CONFIG.remote;

function getStoredToken() {
  return localStorage.getItem('sessionToken');
}
function setStoredToken(token) {
  localStorage.setItem('sessionToken', token);
}

export function useBackendService() {
  const sessionToken = ref(getStoredToken() || '');
  const ws = ref(null);
  const wsConnected = ref(false);
  const reconnectAttempts = ref(0);
  const reconnectTimeout = ref(null);

  // State from backend
  const backendState = ref(null);
  const messages = ref([]);
  const interruptCode = ref(null);
  const appState = ref({});

  // --- Session Management ---
  async function fetchSessionToken() {
    const resp = await fetch(`${API_URL}/new-session?Access_token=${ACCESS_TOKEN}`);
    const data = await resp.json();
    if (data.token) {
      sessionToken.value = data.token;
      setStoredToken(data.token);
      return data.token;
    }
    throw new Error('Failed to fetch session token');
  }

  function updateState(data) {
    backendState.value = data;
    if (data.state) {
      messages.value = data.state.messages || [];
      interruptCode.value = data.state.interrupt_code || null;
      appState.value = data.state.app_state || {};
    }
  }
  // --- WebSocket Management ---
  function connectWebSocket() {
    if (!sessionToken.value) return;
    if (ws.value) ws.value.close();
    const url = `${WS_URL}?token=${sessionToken.value}`;
    const socket = new WebSocket(url);
    ws.value = socket;

    socket.onopen = () => {
      wsConnected.value = true;
      reconnectAttempts.value = 0;
    };
    socket.onclose = () => {
      wsConnected.value = false;
      scheduleReconnect();
    };
    socket.onerror = () => {
      wsConnected.value = false;
      socket.close();
    };
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        updateState(data);
      } catch (e) {
        // Ignore parse errors
      }
    };
  }

  function scheduleReconnect() {
    if (reconnectTimeout.value) return;
    reconnectAttempts.value++;
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.value), 10000);
    reconnectTimeout.value = setTimeout(() => {
      reconnectTimeout.value = null;
      connectWebSocket();
    }, delay);
  }

  // --- Message Sending ---
  function sendMessage(resumeValue) {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) return;
    ws.value.send(JSON.stringify({ resume_value: resumeValue }));
  }

  // --- Initialization ---
  async function init() {
    if (!sessionToken.value) {
      await fetchSessionToken();
    }
    // Fetch initial state from /state endpoint
    try {
      const resp = await fetch(`${API_URL}/state?token=${sessionToken.value}`);
      const data = await resp.json();
      updateState(data);
    } catch (e) {
      console.log(`Error getting state: ${e}`);
    }
    // connectWebSocket();
  }

  // --- Watch for token changes ---
  watchEffect(() => {
    if (sessionToken.value && (!ws.value || ws.value.readyState !== WebSocket.OPEN)) {
      connectWebSocket();
    }
  });

  // --- Expose API ---
  return {
    sessionToken,
    wsConnected: computed(() => wsConnected.value),
    backendState,
    messages,
    interruptCode,
    appState,
    sendMessage,
    fetchSessionToken,
    init,
    API_URL, // Expose for debugging/testing
    WS_URL,
  };
}
