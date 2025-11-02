<template>
  <div class="app-row">
    <div :class="['graph-viewer-wrapper', { expanded: !chatOpen }]">
      <GraphView :graphData="graphData" :chatOpen="chatOpen" />
    </div>
    <div :class="['chat-view-wrapper', { closed: !chatOpen }]">
      <ChatView :messages="messages" @send="handleSend" />
    </div>
    <button class="chat-toggle-btn" :class="{ closed: !chatOpen }" @click="toggleChat">
      <i class="fa fa-chevron-right" :class="{ closed: !chatOpen }"></i>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';

import ChatView from './components/ChatView.vue';
import GraphView from './components/GraphView.vue';

// @ts-expect-error: JS module, no type declarations
import { useBackendService } from './components/BackendService.js';

const chatOpen = ref(true);

// --- Backend Service ---
const backend = useBackendService();
const messages = backend.messages;
const graphData = backend.graphData;

function toggleChat() {
  chatOpen.value = !chatOpen.value;
}

function handleSend(msg: string) {
  backend.sendMessage(msg);
}

onMounted(() => {
  backend.init();
});
</script>

<style scoped>
.app-row {
  display: flex;
  height: 100vh;
  position: relative;
  width: 100vw;
}

.graph-viewer-wrapper {
  flex: 2 1 0;
  height: 100%;
  min-width: 0;
  overflow: hidden;
  position: relative;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 0;
}

.graph-viewer-wrapper::after {
  background: linear-gradient(to left, #faf9f6, rgba(255, 255, 255, 0));
  content: '';
  height: 100%;
  pointer-events: none;
  position: absolute;
  right: 0;
  top: 0;
  width: 10px;
  z-index: 1;
}

.graph-viewer-wrapper.expanded {
  min-width: 100%;
}

.chat-view-wrapper {
  background: none;
  flex: 1 1 0;
  height: 100%;
  min-height: 0;
  min-width: 33.33%;
  position: relative;
  transition: all 0.4s ease;
  z-index: 0;
}

.chat-view-wrapper.closed {
  transform: translateX(100%);
}

.chat-slide-enter-active,
.chat-slide-leave-active {
  transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.chat-slide-enter-from,
.chat-slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.chat-slide-enter-to,
.chat-slide-leave-from {
  transform: translateX(0);
  opacity: 1;
}

.chat-toggle-btn {
  align-items: center;
  background: #fff;
  border-radius: 50%;
  border: none;
  box-shadow: 0 2px 8px 0 rgba(31, 38, 135, 0.08);
  cursor: pointer;
  display: flex;
  font-size: 1.2rem;
  height: 36px;
  justify-content: center;
  left: calc(66.66% + 15px);
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  width: 36px;
  z-index: 3000;
}

.chat-toggle-btn:hover {
  background: #B0F0ED;
}

.chat-toggle-btn.closed {
  left: calc(100% - 46px);
}

.chat-toggle-btn i {
  transition: transform 0.4s ease;
}

.chat-toggle-btn i.closed {
  transform: rotate(-180deg);
}
</style>

