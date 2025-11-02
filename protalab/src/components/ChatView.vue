<template>
  <div class="chat-outer-container">
    <div class="chat-root">
      <div class="chat-messages-area">
        <div class="chat-welcome" :class="{ 'hidden-welcome': messages && messages.length > 0 }">
          <h2>Hi there!<br /></h2>
          <p>What can I make for you today?</p>
        </div>
        <div class="chat-messages" :class="{ 'visible-messages': messages && messages.length > 0 }"
          ref="messagesContainer">
          <div v-for="(message, idx) in messages" :key="idx" :class="['chat-message', message.type]">
            <div class="chat-message-content">{{ message.content }}</div>
          </div>
        </div>
      </div>
      <div v-if="showMenuForInterrupt(props.interruptCode || '', props.appState)" class="chat-menu-container">
        <div class="chat-menu-bubble">
          <div class="chat-menu">
            <template v-if="interruptCode === 'START_PRINTING'">
              <label>Start printing?</label>
              <button @click="emitSelect('Y')" :disabled="menuDisabled">Yes</button>
              <button @click="emitSelect('N')" :disabled="menuDisabled">No</button>
            </template>
            <template
              v-else-if="interruptCode === 'CHOOSE_DESIGN' && appState && appState.stl_files && appState.stl_files.length > 1">
              <label>Select a design:</label>
              <div class="design-selector">
                <button type="button" class="design-nav-btn" @click="prevDesign"
                  :disabled="pendingDesignIndex <= 0 || designConfirmed || menuDisabled">
                  <i class="fa fa-chevron-left"></i>
                </button>
                <span class="design-number">Design {{ pendingDesignIndex + 1 }}</span>
                <button type="button" class="design-nav-btn" @click="nextDesign"
                  :disabled="pendingDesignIndex >= appState.stl_files.length - 1 || designConfirmed || menuDisabled">
                  <i class="fa fa-chevron-right"></i>
                </button>
              </div>
              <button @click="confirmDesign" :disabled="designConfirmed || menuDisabled">Confirm</button>
            </template>
            <template
              v-else-if="interruptCode === 'CONFIRM_PRINTER_AND_MATERIAL_CHOICE' || interruptCode === 'LLM_FAILED_TO_SUGGEST'">
              <div>
                <label>Select printer/material/colour:</label>
                <div v-if="interruptCode === 'CONFIRM_PRINTER_AND_MATERIAL_CHOICE' && printerMaterialReason" class="menu-reason"
                  @mouseenter="showReasonTooltip = true"
                  @mouseleave="showReasonTooltip = false"
                  style="position: relative;">
                  {{ printerMaterialReason }}
                  <div v-if="showReasonTooltip" class="reason-tooltip">
                    <span class="reason-tooltip-text">LLM-generated suggestion.</span>
                  </div>
                </div>
                <select v-model="selectedPrinter" :disabled="menuDisabled">
                  <option v-for="(printer, name) in appState.available_printers" :key="name" :value="name">{{ name }}
                  </option>
                </select>
                <select v-if="selectedPrinter && appState.available_printers[selectedPrinter]"
                  v-model="selectedMaterial" :disabled="menuDisabled">
                  <option v-for="(colours, material) in appState.available_printers[selectedPrinter].filaments"
                    :key="material" :value="material">{{ material }}</option>
                </select>
                <select
                  v-if="selectedMaterial && appState.available_printers[selectedPrinter].filaments[selectedMaterial]"
                  v-model="selectedColour" :disabled="menuDisabled">
                  <option v-for="colour in appState.available_printers[selectedPrinter].filaments[selectedMaterial]"
                    :key="colour" :value="colour">{{ colour }}</option>
                </select>
                <button @click="emitSelectPrinterMaterial()"
                  :disabled="!selectedPrinter || !selectedMaterial || !selectedColour || menuDisabled">Confirm</button>
              </div>
            </template>
            <template v-else-if="interruptCode === 'CONFIRM_SLICER_CONFIG' && appState && appState.slicer_config">
              <div>
                <label>Confirm or edit slicer config:</label>
                <div v-for="(val, key) in appState.slicer_config" :key="key">
                  <label>{{ key }}:</label>
                  <input v-model="slicerConfigEdit[key]" :disabled="menuDisabled" />
                </div>
                <button @click="emitSelectSlicerConfig()" :disabled="menuDisabled">Confirm</button>
              </div>
            </template>
          </div>
        </div>
      </div>
      <div class="chat-input-area">
        <form class="chat-input-form" @submit.prevent="onSend">
          <textarea v-model="input" class="chat-input-box" placeholder="Type your message..." autocomplete="off"
            rows="1" @input="autoResize" ref="inputBoxRef" />
          <button class="chat-send-btn" type="submit"
            :disabled="!input.trim() || showMenuForInterrupt(props.interruptCode || '', props.appState)">
            <i class="fa fa-paper-plane"></i>
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, defineProps, defineEmits, onMounted, watch, computed } from 'vue';

interface ChatMessage {
  type: 'human' | 'ai';
  content: string;
  timestamp: Date | string;
}

const props = defineProps<{
  messages: ChatMessage[];
  interruptCode?: string;
  appState?: any;
  selectedStlIndex: number;
}>();

const emit = defineEmits(['send', 'select', 'changeDesign']);
const input = ref('');
const inputBoxRef = ref<HTMLTextAreaElement | null>(null);
const messagesContainer = ref<HTMLDivElement | null>(null);

// For menu/selection UI
const selectedPrinter = ref('');
const selectedMaterial = ref('');
const selectedColour = ref('');
const slicerConfigEdit = ref<any>({});
const pendingDesignIndex = ref(props.selectedStlIndex);
const designConfirmed = ref(false);
const menuDisabled = ref(false);

// Add a ref for the reason for printer/material
const printerMaterialReason = ref('');
const showReasonTooltip = ref(false);

// Watch for interrupt changes and appState to set preselection and reasons
watch([
  () => props.interruptCode,
  () => props.appState
], ([newCode, newAppState]) => {
  if (newCode === 'CONFIRM_PRINTER_AND_MATERIAL_CHOICE' && newAppState && newAppState.selected_printer_and_material_option) {
    const opt = newAppState.selected_printer_and_material_option;
    selectedPrinter.value = opt.model_name || '';
    selectedMaterial.value = opt.filament_material || '';
    selectedColour.value = opt.filament_colour || '';
    printerMaterialReason.value = opt.reason || '';
  } else if (newCode === 'LLM_FAILED_TO_SUGGEST') {
    selectedPrinter.value = '';
    selectedMaterial.value = '';
    selectedColour.value = '';
    printerMaterialReason.value = '';
  }
}, { immediate: true });


function showMenuForInterrupt(interruptCode: string, appState: any) {
  if (!interruptCode) return false;
  if (interruptCode === 'START_PRINTING') return true;
  if (interruptCode === 'CHOOSE_DESIGN' && appState && appState.stl_files && appState.stl_files.length > 1) return true;
  if ((interruptCode === 'CONFIRM_PRINTER_AND_MATERIAL_CHOICE' || interruptCode === 'LLM_FAILED_TO_SUGGEST') && appState && appState.available_printers) return true;
  if (interruptCode === 'CONFIRM_SLICER_CONFIG' && appState && appState.slicer_config) return true;
  return false;
}

function changeDesign() {
  emit('changeDesign', pendingDesignIndex.value)
}

function emitSelect(val: any) {
  emit('select', val);
  menuDisabled.value = true;
}


function emitSelectPrinterMaterial() {
  emit('select', {
    selected_printer_and_material_option: {
      model_name: selectedPrinter.value,
      filament_material: selectedMaterial.value,
      filament_colour: selectedColour.value,
    },
  });
  menuDisabled.value = true;
}
function emitSelectSlicerConfig() {
  emit('select', {
    slicer_config: { ...slicerConfigEdit.value },
  });
  menuDisabled.value = true;
}

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
  }
}

function confirmDesign() {
  designConfirmed.value = true;
  console.log(`Pending design index: ${pendingDesignIndex.value}`)
  emit('select', pendingDesignIndex.value);
  menuDisabled.value = true;
}

function prevDesign() {
  if (pendingDesignIndex.value > 0) {
    pendingDesignIndex.value--;
    changeDesign();
  }
}

function nextDesign() {
  if (props.appState && props.appState.stl_files && pendingDesignIndex.value < props.appState.stl_files.length - 1) {
    pendingDesignIndex.value++;
    changeDesign();
  }
}

onMounted(() => {
  autoResize();
});

// Watch for interrupt changes to reset selector state
watch(
  () => props.interruptCode,
  (newCode) => {
    if (newCode === 'CHOOSE_DESIGN') {
      pendingDesignIndex.value = props.selectedStlIndex;
      designConfirmed.value = false;
    } else {
      designConfirmed.value = false;
    }
  },
  { immediate: true }
);


watch(
  () => props.appState?.slicer_config,
  (val) => {
    if (val) slicerConfigEdit.value = { ...val };
  },
  { immediate: true }
);



watch(
  () => props.messages.length,
  () => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
    }
  },
  { flush: 'post' }
);

// Watch for appState changes to re-enable the menu
watch(
  () => props.appState,
  () => {
    menuDisabled.value = false;
  }
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
  background: linear-gradient(135deg, #ee5832 0%, #ffd8cd 100%);
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
  background: rgb(255, 225, 219);
}

.chat-send-btn {
  align-items: center;
  background: linear-gradient(135deg, rgb(236, 120, 91) 0%, rgb(228, 168, 153) 100%);
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
  background: rgb(216, 181, 172);
  cursor: not-allowed;
}

.chat-send-btn:hover:not(:disabled) {
  background: rgb(219, 99, 69);
  color: #fff;
}

.chat-menu-container {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  width: 100%;
  margin-bottom: 8px;
  margin-top: 0;
  z-index: 3;
}

.chat-menu-bubble {
  background: #fffbe6;
  border-radius: 22px;
  box-shadow: 0 2px 12px 0 rgba(31, 38, 135, 0.10);
  color: #333;
  padding: 14px 20px;
  min-width: 60%;
  max-width: 90%;
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 0 auto;
  border: 2px solid #ffd8cd;
}

.chat-menu {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.chat-menu label {
  font-weight: 600;
  margin-bottom: 4px;
  color: #ee5832;
}

.chat-menu select,
.chat-menu input {
  border-radius: 8px;
  border: 1px solid #ffd8cd;
  padding: 4px 10px;
  font-size: 1rem;
  margin-bottom: 4px;
  background: #fff;
  color: #333;
}

.chat-menu button {
  background: linear-gradient(135deg, #ee5832 0%, #ffd8cd 100%);
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  margin: 0 4px;
  transition: background 0.2s;
}

.chat-menu button:disabled {
  background: #ffd8cd;
  color: #aaa;
  cursor: not-allowed;
}

.design-selector {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 8px;
}

.design-nav-btn {
  background: linear-gradient(135deg, rgb(236, 120, 91) 0%, rgb(228, 168, 153) 100%);
  color: #fff;
  border: none;
  border-radius: 50%;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  cursor: pointer;
  box-shadow: 0 2px 8px 0 rgba(31, 38, 135, 0.08);
  transition: background 0.2s;
}

.design-nav-btn:disabled {
  background: #ffd8cd;
  color: #aaa;
  cursor: not-allowed;
}

.design-nav-btn:hover:not(:disabled) {
  background: rgb(219, 99, 69);
  color: #fff;
}

.design-number {
  font-size: 1.1rem;
  font-weight: 600;
  color: #ee5832;
  min-width: 80px;
  text-align: center;
}

.menu-reason {
  background: #fff3e6;
  color: #b85c00;
  border-left: 4px solid #ee5832;
  border-radius: 8px;
  padding: 8px 14px;
  margin-bottom: 10px;
  font-size: 0.98rem;
  font-style: italic;
  max-width: 90%;
  cursor: pointer;
  position: relative;
}

.reason-tooltip {
  position: absolute;
  left: 50%;
  top: -38px;
  transform: translateX(-50%);
  background: #fffbe6;
  color: #ee5832;
  border: 1px solid #ffd8cd;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 0.92rem;
  white-space: nowrap;
  box-shadow: 0 2px 8px 0 rgba(31, 38, 135, 0.10);
  z-index: 10;
  pointer-events: none;
  opacity: 1;
  transition: opacity 0.2s;
}
.reason-tooltip-text {
  display: block;
}
</style>
