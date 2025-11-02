import { ref, computed } from 'vue';

const WS_URL = 'ws://localhost:8001/ws';

export function useBackendService() {
  const ws = ref(null);
  const wsConnected = ref(false);
  const reconnectAttempts = ref(0);
  const reconnectTimeout = ref(null);

  // State from backend
  const messages = ref([]);
  const graphData = ref(null); // { nodes, annotations, similarity_matrix }
  const isLoading = ref(false);
  const progressMessage = ref('');

  // --- WebSocket Management ---
  function connectWebSocket() {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) return;
    if (ws.value) ws.value.close();
    
    const socket = new WebSocket(WS_URL);
    ws.value = socket;

    socket.onopen = () => {
      wsConnected.value = true;
      reconnectAttempts.value = 0;
      console.log('WebSocket connected');
    };

    socket.onclose = () => {
      wsConnected.value = false;
      scheduleReconnect();
    };

    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
      wsConnected.value = false;
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // Check if this is a progress message
        if (data.type === 'progress' && data.message) {
          // Ensure message is a string, not an object
          const messageText = typeof data.message === 'string' ? data.message : String(data.message);
          if (messageText && messageText !== '[object Object]') {
            progressMessage.value = messageText;
            isLoading.value = true;
          }
          return;
        }
        
        // Check if this is graph data (has nodes, annotations, similarity_matrix)
        if (data.nodes && data.annotations && data.similarity_matrix) {
          console.log('Received graph data:', { 
            nodeCount: data.nodes.length, 
            annotationCount: Object.keys(data.annotations).length 
          });
          graphData.value = data;
          // Keep loading state true - more progress may come
          // Also add a message confirming graph was received
          addMessage('ai', `I've generated a graph showing ${data.nodes.length} related trend clusters. You can now ask questions about the connections and relationships.`);
        } else if (typeof data === 'string') {
          // Regular chat message (if JSON was a string)
          // If it's a final response, stop loading
          isLoading.value = false;
          progressMessage.value = '';
          addMessage('ai', data);
        } else {
          // Handle other message formats
          // If it looks like a final response, stop loading
          if (data.answer || data.result) {
            isLoading.value = false;
            progressMessage.value = '';
          }
          addMessage('ai', JSON.stringify(data));
        }
      } catch (e) {
        // If it's not JSON, treat it as plain text
        if (typeof event.data === 'string') {
          // If it's a plain text response (final answer), stop loading
          isLoading.value = false;
          progressMessage.value = '';
          addMessage('ai', event.data);
        } else {
          console.error('Error parsing message:', e);
        }
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

  // --- Message Management ---
  function addMessage(type, content) {
    messages.value.push({
      type,
      content,
      timestamp: new Date(),
    });
  }

  // --- Message Sending ---
  function sendMessage(message) {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      console.warn('WebSocket not connected, attempting to connect...');
      connectWebSocket();
      // Wait a bit for connection
      setTimeout(() => {
        if (ws.value && ws.value.readyState === WebSocket.OPEN) {
          ws.value.send(message);
          addMessage('human', message);
          // Start loading when message is sent
          isLoading.value = true;
          progressMessage.value = 'Processing your request...';
        } else {
          console.error('Failed to connect WebSocket');
        }
      }, 500);
      return;
    }
    ws.value.send(message);
    addMessage('human', message);
    // Start loading when message is sent
    isLoading.value = true;
    progressMessage.value = 'Processing your request...';
    console.log('Message Sent');
  }

  // --- Initialization ---
  function init() {
    connectWebSocket();
  }

  // --- Expose API ---
  return {
    wsConnected: computed(() => wsConnected.value),
    messages,
    graphData,
    isLoading: computed(() => isLoading.value),
    progressMessage: computed(() => progressMessage.value),
    sendMessage,
    init,
    WS_URL,
  };
}

