<template>
  <div class="stl-viewer-outer">
    <div class="stl-logo-overlay">
      <div class="stl-logo-cloud">
        <img src="/logo.svg" alt="ProtaLab Logo" class="stl-logo" />
      </div>
    </div>
    <div class="stl-viewer-container">
      <transition name="hideSTL-fade">
        <div v-if="hideSTL" class="stl-hideSTL-overlay" :style="{ background: overlayColor }"></div>
      </transition>
      <div ref="rendererContainer" class="stl-container"></div>
      <div class="controls-overlay">
        <ViewerControls :autoRotate="autoRotate" :showWireframe="showWireframe" :selectedColor="selectedColor"
          @autoRotateChange="toggleAutoRotate" @showWireframeChange="toggleWireframe" @resetView="resetCamera"
          @colorChange="changeModelColor" />
      </div>
      <div v-if="isLoading" class="loading-overlay">
        <div class="spinner"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, defineProps } from 'vue';
import ViewerControls from './ViewerControls.vue';
import * as THREE from 'three';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

const props = defineProps<{
  chatOpen: boolean;
  hideSTL: boolean;
  overlayColor: string;
  appState?: any;
  selectedStlIndex?: number;
}>();

const rendererContainer = ref(null);
const isLoading = ref(true);
const autoRotate = ref(false);
const showWireframe = ref(false);
const selectedColor = ref('#f5876c');

let scene: THREE.Scene;
let camera: THREE.PerspectiveCamera;
let renderer: THREE.WebGLRenderer;
let controls: OrbitControls;
let mesh: THREE.Mesh | null;
let frameId: number | null;


function loadSTLFromGeometry(geometry: THREE.BufferGeometry) {
  const material = new THREE.MeshPhongMaterial({
    color: selectedColor.value,
    wireframe: showWireframe.value,
  });
  mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  scene.add(mesh);
  fitCameraToObject(mesh);
  isLoading.value = false;
}

function loadSTL(stlPath: string) {
  isLoading.value = true;
  clearScene();
  const loader = new STLLoader();
  loader.load(
    stlPath,
    geometry => {
      loadSTLFromGeometry(geometry);
    }
  );
  isLoading.value = false;
}

function loadSTLFromBase64(base64String: string) {
  isLoading.value = true;
  clearScene();
  const loader = new STLLoader();
  // Convert base64 to Blob and then to ObjectURL
  const binary = atob(base64String);
  const len = binary.length;
  const arrayBuffer = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    arrayBuffer[i] = binary.charCodeAt(i);
  }
  const blob = new Blob([arrayBuffer], { type: 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  loader.load(
    url,
    geometry => {
      loadSTLFromGeometry(geometry);
      URL.revokeObjectURL(url);
    }
  );
  isLoading.value = false;
  URL.revokeObjectURL(url);
}

function animate() {
  if (autoRotate.value && mesh) {
    mesh.rotation.y -= 0.002;
  }
  controls && controls.update();
  renderer && renderer.render(scene, camera);
  frameId = requestAnimationFrame(animate);
}

function clearScene() {
  if (scene && mesh) {
    scene.remove(mesh);
    if (mesh.geometry) mesh.geometry.dispose();
    if (mesh.material) {
      if (Array.isArray(mesh.material)) {
        mesh.material.forEach((mat) => {
          if ('dispose' in mat && typeof mat.dispose === 'function') mat.dispose();
        });
      } else if ('dispose' in mesh.material && typeof mesh.material.dispose === 'function') {
        mesh.material.dispose();
      }
    }
    mesh = null;
  }
}

function fitCameraToObject(object: THREE.Object3D) {
  const box = new THREE.Box3().setFromObject(object);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = camera.fov * (Math.PI / 180);
  let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));
  cameraZ *= 1.5;
  camera.position.set(center.x, center.y, cameraZ + center.z);
  camera.lookAt(center);
  controls.target.copy(center);
  controls.update();
}

function resetCamera() {
  if (mesh) fitCameraToObject(mesh);
  if (mesh) mesh.rotation.y = 0;
}

function changeModelColor(color: string) {
  selectedColor.value = color;
  if (mesh && mesh.material) {
    if (!Array.isArray(mesh.material) && 'color' in mesh.material && mesh.material.color && typeof (mesh.material.color as any).set === 'function') {
      (mesh.material.color as any).set(color);
      (mesh.material as any).needsUpdate = true;
    }
  }
}

function toggleWireframe(val: boolean) {
  showWireframe.value = val;
  if (mesh && mesh.material) {
    if (!Array.isArray(mesh.material) && 'wireframe' in mesh.material) {
      mesh.material.wireframe = val;
      mesh.material.needsUpdate = true;
    }
  }
}

function toggleAutoRotate(val: boolean) {
  autoRotate.value = val;
}

function onResize() {
  if (!rendererContainer.value || !renderer || !camera) return;
  const container = rendererContainer.value as HTMLElement | null;
  if (!container) return;
  const width = container.clientWidth;
  const height = container.clientHeight;
  renderer.setSize(width, height);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

onMounted(() => {
  scene = new THREE.Scene();
  scene.background = null;
  camera = new THREE.PerspectiveCamera(70, 1, 0.1, 1000);
  camera.position.z = 100;

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  if (rendererContainer.value) {
    (rendererContainer.value as HTMLElement).appendChild(renderer.domElement);
  }

  // Lights
  scene.add(new THREE.AmbientLight(0x888888));
  const light = new THREE.DirectionalLight(0xffffff, 0.8);
  light.position.set(1, 1, 1).normalize();
  scene.add(light);
  const backLight = new THREE.DirectionalLight(0xffffff, 0.3);
  backLight.position.set(-1, -1, -1).normalize();
  scene.add(backLight);

  // Controls
  controls = new OrbitControls(camera, renderer.domElement);
  controls.update();

  window.addEventListener('resize', onResize);
  onResize();

  // Load initial STL if available, otherwise show default
  if (props.appState && props.appState.stl_files && props.appState.stl_files.length > 0) {
    const idx = props.selectedStlIndex || 0;
    loadSTLFromBase64(props.appState.stl_files[idx]);
  } else {
    loadSTL('/F1-Model.stl');
  }
  animate();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize);
  if (frameId) cancelAnimationFrame(frameId);
  if (renderer && renderer.domElement && renderer.domElement.parentNode) {
    renderer.domElement.parentNode.removeChild(renderer.domElement);
  }
  clearScene();
});

// Watch for chatOpen changes to trigger resize
watch(() => props.chatOpen, () => {
  setTimeout(() => {
    onResize();
  }, 400);
});

// Watch for selected STL index or stl_files change
watch(
  () => [props.selectedStlIndex, props.appState?.stl_files],
  ([newIdx, newStlFiles], [oldIdx, oldStlFiles]) => {
    if (newStlFiles && newStlFiles.length > 0 && newIdx !== undefined) {
      loadSTLFromBase64(newStlFiles[newIdx]);
    }
  },
  { immediate: false }
);
</script>

<style scoped>
.stl-viewer-outer {
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
  width: 100%;
}

.stl-logo-overlay {
  display: flex;
  justify-content: center;
  left: 0;
  pointer-events: none;
  position: absolute;
  top: 0;
  width: 100%;
  z-index: 30;
}

.stl-logo-cloud {
  align-items: center;
  background: rgba(245, 135, 108, 0.18);
  border-radius: 50% 50% 60% 60% / 60% 60% 50% 50%;
  box-shadow: 0 4px 24px 0 rgba(245, 135, 108, 0.10);
  display: flex;
  justify-content: center;
  margin-top: 18px;
  min-height: 60px;
  min-width: 120px;
  padding: 16px 36px;
  pointer-events: auto;
}

.stl-logo {
  display: block;
  filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.08));
  height: 70px;
  width: auto;
}

.stl-viewer-container {
  flex: 1;
  height: 100%;
  position: relative;
  width: 100%;
}

.stl-container {
  border: 0px solid #ddd;
  height: 100%;
  width: 100%;
}

.controls-overlay {
  align-items: center;
  display: flex;
  height: 100%;
  justify-content: flex-start;
  left: 0;
  padding-left: 24px;
  pointer-events: none;
  position: absolute;
  top: 0;
  width: 100%;
  z-index: 10;
}

.controls-overlay>* {
  pointer-events: auto;
}

.loading-overlay {
  align-items: center;
  background: rgba(200, 200, 200, 0.7);
  display: flex;
  height: 100%;
  justify-content: center;
  left: 0;
  position: absolute;
  top: 0;
  width: 100%;
  z-index: 20;
}

.spinner {
  width: 48px;
  height: 48px;
  border: 6px solid #ccc;
  border-top: 6px solid #333;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }

  100% {
    transform: rotate(360deg);
  }
}

.stl-hideSTL-overlay {
  background: #fff;
  height: 100%;
  left: 0;
  opacity: 1;
  pointer-events: none;
  position: absolute;
  top: 0;
  width: 100%;
  z-index: 20;
}

.hideSTL-fade-enter-active,
.hideSTL-fade-leave-active {
  transition: opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.hideSTL-fade-enter-from,
.hideSTL-fade-leave-to {
  opacity: 0;
}

.hideSTL-fade-enter-to,
.hideSTL-fade-leave-from {
  opacity: 1;
}
</style>
