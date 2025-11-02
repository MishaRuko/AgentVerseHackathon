<template>
  <div class="controls-panel">
    <div class="palette-container">
      <!-- Auto Rotate -->
      <button @click="emit('autoRotateChange', !autoRotate)" class="icon-button">
        <i v-if="autoRotate" class="fas fa-stop"></i>
        <i v-else class="fas fa-arrows-rotate"></i>
      </button>
      <!-- Wireframe -->
      <button @click="emit('showWireframeChange', !showWireframe)" class="icon-button">
        <i v-if="showWireframe" class="fas fa-circle"></i>
        <i v-else class="fas fa-circle-notch"></i>
      </button>
      <!-- Reset View -->
      <button @click="emit('resetView')" class="icon-button">
        <i class="fas fa-arrow-rotate-left"></i>
      </button>
      <!-- Colour input -->
      <div class="color-input-wrapper">
        <input type="color" v-model="color" class="color-input" :style="{ borderColor: color }"
          @input="emit('colorChange', color)" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';

const props = defineProps({
  autoRotate: Boolean,
  showWireframe: Boolean,
  selectedColor: String
});
const emit = defineEmits([
  'autoRotateChange',
  'showWireframeChange',
  'resetView',
  'colorChange'
]);

const color = ref(props.selectedColor || '#f5876c');
// watch(() => props.selectedColor, (val) => { color.value = val || '#f5876c'; });
</script>

<style scoped>
.controls-panel {
  position: absolute;
  z-index: 1000;
  background: #f8f8f8;
  border: 1px solid #ddd;
  border-radius: 10px;
  padding: 6px;
  display: inline-block;
}

.palette-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: 5px;
  padding-top: 7px;
  padding-bottom: 7px;
}

.icon-button {
  background-color: #fff;
  color: #1c1c1c;
  border: none;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: pointer;
  transition: background-color 0.3s ease;
  margin: 0 4px;
}

.icon-button:hover,
.icon-button:active {
  background-color: #dedede;
}

.icon-button i {
  font-size: 20px;
}

.color-input-wrapper {
  margin: 0 4px;
  display: flex;
  align-items: center;
}

.color-input {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 2px solid #ddd;
  padding: 0;
  background: none;
  cursor: pointer;
  box-shadow: none;
  outline: none;
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
}

.color-input::-webkit-color-swatch-wrapper {
  padding: 0;
  border-radius: 50%;
}

.color-input::-webkit-color-swatch {
  border-radius: 50%;
  border: none;
  padding: 0;
}

.color-input::-moz-color-swatch {
  border-radius: 50%;
  border: none;
  padding: 0;
}
</style>
