<template>
  <div class="chat-outer-container">
    <div class="chat-root">
      <div class="chat-messages-area">
        <div class="chat-welcome" :class="{ 'hidden-welcome': messages && messages.length > 0 }">
          <h2>Hi there!<br /></h2>
          <p>What social area would you like to learn about?</p>
        </div>
        <div class="chat-messages" :class="{ 'visible-messages': messages && messages.length > 0 }"
          ref="messagesContainer">
          <div v-for="(message, idx) in messages" :key="idx" :class="['chat-message', message.type]">
            <div class="chat-message-content">{{ message.content }}</div>
          </div>
        </div>
      </div>
      <div class="chat-input-area">
        <form class="chat-input-form" @submit.prevent="onSend">
          <textarea v-model="input" class="chat-input-box" placeholder="Type your message..." autocomplete="off"
            rows="1" @input="autoResize" ref="inputBoxRef" />
          <button class="chat-send-btn" type="submit" :disabled="!input.trim()">
            <i class="fa fa-paper-plane"></i>
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, defineProps, defineEmits, onMounted, watch } from 'vue';

interface ChatMessage {
  type: 'human' | 'ai';
  content: string;
  timestamp: Date | string;
}

const props = defineProps<{
  messages: ChatMessage[];
}>();

const emit = defineEmits(['send']);
const input = ref('');
const inputBoxRef = ref<HTMLTextAreaElement | null>(null);
const messagesContainer = ref<HTMLDivElement | null>(null);

function autoResize() {
  const el = inputBoxRef.value;
  if (el) {
    el.style.height = 'auto';
    const maxHeight = el.parentElement?.clientHeight || 120;
    el.style.height = Math.min(el.scrollHeight, maxHeight) + 'px';
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }
}

function onSend() {
  if (input.value.trim()) {
    emit('send', input.value.trim());
    input.value = '';
    autoResize();
  }
}

onMounted(() => {
  autoResize();
});

watch(
  () => props.messages.length,
  () => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
    }
  },
  { flush: 'post' }
);
</script>

<style scoped>
.chat-outer-container {
  background: none;
  box-sizing: border-box;
  height: 100%;
  padding: 32px;
  width: 100%;
}

.chat-root {
  background: linear-gradient(135deg, #0ABAB5 0%, #7FE3DE 100%);
  border-radius: 35px;
  display: flex;
  flex-direction: column;
  height: 100%;
  margin: 0 auto;
  max-width: 600px;
  position: relative;
  width: 100%;
}

.chat-welcome {
  align-items: center;
  background: none;
  color: #222;
  display: flex;
  flex-direction: column;
  flex: 1;
  inset: 0;
  justify-content: center;
  min-height: 300px;
  position: absolute;
  text-align: center;
  transition: all 0.3s ease-in;
  z-index: 2;
}

.chat-welcome h2 {
  font-size: 2.2rem;
  font-weight: 700;
  letter-spacing: -1px;
  margin-bottom: 0.5rem;
}

.chat-welcome p {
  color: #555;
  font-size: 1.2rem;
  font-weight: 400;
}

.chat-welcome.hidden-welcome {
  opacity: 0;
  pointer-events: none;
  transform: translateY(-30px);
}

.chat-messages-area {
  border-radius: 25px;
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  justify-content: flex-end;
  margin: 32px 24px 16px 24px;
  overflow-y: auto;
  position: relative;

  mask-image: linear-gradient(to bottom,
      rgba(0, 0, 0, 0) 0px,
      rgba(0, 0, 0, 1) 32px,
      rgba(0, 0, 0, 1) calc(100% - 32px),
      rgba(0, 0, 0, 0) 100%);
  -webkit-mask-image: linear-gradient(to bottom,
      rgba(0, 0, 0, 0) 0px,
      rgba(0, 0, 0, 1) 32px,
      rgba(0, 0, 0, 1) calc(100% - 32px),
      rgba(0, 0, 0, 0) 100%);
}

.chat-messages {
  display: flex;
  flex-direction: column;
  gap: 12px;
  opacity: 0;
  overflow: auto;
  padding: 16px;
  scrollbar-width: none;
  transition: opacity 0.6s ease;
}

.chat-messages.visible-messages {
  opacity: 1;
}

.chat-messages::-webkit-scrollbar {
  display: none;
}

.chat-message {
  display: flex;
  align-items: flex-end;
}

.chat-message.human {
  justify-content: flex-end;
}

.chat-message.ai {
  justify-content: flex-start;
}

.chat-message-content {
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 2px 8px 0 rgba(31, 38, 135, 0.06);
  color: #222;
  font-size: 1.08rem;
  max-width: 70%;
  overflow-wrap: break-word;
  padding: 10px 18px;
  word-break: break-word;
}

.chat-message.human .chat-message-content {
  background: #000;
  border-bottom-right-radius: 6px;
  color: #fff;
}

.chat-message.ai .chat-message-content {
  background: #f0f0f0;
  border-bottom-left-radius: 6px;
  color: #333;
}

.chat-input-area {
  align-items: center;
  background: transparent;
  box-sizing: border-box;
  display: flex;
  flex: 0 0 auto;
  height: 120px;
  justify-content: center;
  min-height: 60px;
  padding: 16px 16px 16px 16px;
}

.chat-input-form {
  align-items: center;
  box-sizing: border-box;
  display: flex;
  gap: 12px;
  height: 100%;
  max-width: 520px;
  width: 90%;
}

.chat-input-box {
  align-items: center;
  background: rgba(255, 255, 255, 0.85);
  border-radius: 24px;
  border: none;
  box-shadow: 0 2px 12px 0 rgba(31, 38, 135, 0.08);
  display: flex;
  flex: 1 1 320px;
  font-family: inherit;
  font-size: 1.08rem;
  line-height: 1.5;
  max-height: 100%;
  max-width: 420px;
  min-height: 44px;
  min-width: 120px;
  outline: none;
  overflow-y: auto;
  padding: 10px 18px;
  resize: none;
  scrollbar-width: none;
  transition: background 0.2s;
}

.chat-input-box::-webkit-scrollbar {
  display: none;
}

.chat-input-box:focus {
  background: rgba(127, 227, 222, 0.3);
}

.chat-send-btn {
  align-items: center;
  background: linear-gradient(135deg, #0ABAB5 0%, #089895 100%);
  border-radius: 50%;
  border: none;
  box-shadow: 0 2px 8px 0 rgba(31, 38, 135, 0.08);
  color: #fff;
  cursor: pointer;
  display: flex;
  flex-shrink: 0;
  font-size: 1.2rem;
  height: 44px;
  justify-content: center;
  min-height: 44px;
  min-width: 44px;
  width: 44px;
}

.chat-send-btn:disabled {
  background: #B0F0ED;
  cursor: not-allowed;
}

.chat-send-btn:hover:not(:disabled) {
  background: #089895;
  color: #fff;
}
</style>

